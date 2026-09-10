"""
FastAPI application entry point.
≈ Program.cs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter

from app.config import Settings
from app import auth as auth_module
from app.routers import config_router, incident_router, telemetry_router, validation_router
from app.routers import events_router
from app.services.event_repository import EventRepository
from app.services.incident_data_service import IncidentDataService
from app.services.investigation_service import InvestigationService
from app.services.llm_service import ClaudeService
from app.services.telemetry_store import TelemetryStore
from app.services.validation_service import ValidationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Application-level singletons ──────────────────────────────────────────────
# These are created once at startup and injected via FastAPI's dependency system.

settings = Settings()

_incident_svc    = IncidentDataService()
_event_repo      = EventRepository()
_claude_svc      = ClaudeService(settings)
_investigation_svc = InvestigationService(
    _claude_svc,
    cache_enabled=settings.cache.enabled,
    ttl_hours=settings.cache.ttl_hours,
    max_prompt_chars=settings.claude.max_prompt_chars,
)
_telemetry_store = TelemetryStore()
_validation_svc  = ValidationService(_incident_svc, _investigation_svc, _event_repo)


# ── Dependency overrides ──────────────────────────────────────────────────────

def get_incident_svc()      -> IncidentDataService:   return _incident_svc
def get_event_repo()        -> EventRepository:       return _event_repo
def get_investigation_svc() -> InvestigationService:  return _investigation_svc
def get_telemetry_store()   -> TelemetryStore:        return _telemetry_store
def get_settings()          -> Settings:              return settings
def get_validation_svc()    -> ValidationService:     return _validation_svc


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup / shutdown lifecycle.
    ≈ Program.cs service registration + WebApplication.Run()
    """
    logger.info("FinancialEventCollector Python service starting up")
    yield
    logger.info("Shutting down — closing HTTP client")
    await _claude_svc.aclose()


# ── FastAPI app ───────────────────────────────────────────────────────────────

# Tag ordering controls the display order in Swagger UI — Admin first, matching the .NET swagger layout.
_OPENAPI_TAGS = [
    {"name": "Admin (role: admin)",      "description": "Admin-only configuration endpoints."},
    {"name": "Event (role: user)",       "description": "Event lineage, logs, and AI investigation endpoints."},
    {"name": "Incident (role: user)",    "description": "Incident retrieval and AI investigation endpoints."},
    {"name": "Telemetry (role: user)",   "description": "In-memory investigation telemetry endpoints."},
    {"name": "Validation (role: admin)", "description": "Batch validation / regression-test endpoints."},
]

app = FastAPI(
    title="FinancialEventCollector",
    description="AI-powered financial event pipeline incident investigation service",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Wire dependency overrides so routers receive the singletons
app.dependency_overrides[incident_router._get_settings]            = get_settings
app.dependency_overrides[incident_router._get_incident_svc]        = get_incident_svc
app.dependency_overrides[incident_router._get_event_repository]    = get_event_repo
app.dependency_overrides[incident_router._get_investigation_svc]   = get_investigation_svc
app.dependency_overrides[incident_router._get_telemetry_store]     = get_telemetry_store
app.dependency_overrides[events_router._get_settings]              = get_settings
app.dependency_overrides[events_router._get_event_repository]      = get_event_repo
app.dependency_overrides[events_router._get_investigation_svc]     = get_investigation_svc
app.dependency_overrides[events_router._get_telemetry_store]       = get_telemetry_store
app.dependency_overrides[config_router._get_settings]              = get_settings
app.dependency_overrides[telemetry_router._get_telemetry_store]    = get_telemetry_store
app.dependency_overrides[validation_router._get_validation_svc]    = get_validation_svc
# Ensure the auth dependency uses the same Settings singleton (and therefore the
# same ApiKey secrets) as the rest of the application.
app.dependency_overrides[auth_module._get_settings]                = get_settings

# Register routers — Admin first to match the .NET Swagger display order.
# Tags are defined on each router; no tags= override needed here.
app.include_router(config_router.router,     prefix="/admin")
app.include_router(events_router.router,     prefix="/events")
app.include_router(incident_router.router,   prefix="/incidents")
app.include_router(telemetry_router.router,  prefix="/telemetry")
app.include_router(validation_router.router, prefix="/validation")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect root to Swagger UI, matching .NET behaviour."""
    return RedirectResponse(url="/docs")
