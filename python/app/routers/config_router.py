"""
Config router — exposes runtime configuration at GET /admin/config.
≈ ConfigController.cs
"""
from __future__ import annotations

import importlib.metadata
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import require_role
from app.config import Settings
from app.models.root_cause import ROOT_CAUSE_CATALOG_LIST

# Router-level dependency — every route in this router requires a valid X-Api-Key
# with the 'admin' role.
# ≈ [Authorize(Roles = "admin")] on AdminController.cs:13
router = APIRouter(
    dependencies=[Depends(require_role("admin"))],
    tags=["Admin (role: admin)"],
)


# ── Response models ───────────────────────────────────────────────────────────

class RootCauseEntryResponse(BaseModel):
    """A single entry in the RootCause catalog.  ≈ RootCauseEntry record in C#."""
    name: str
    description: str


class LlmConfigSnapshot(BaseModel):
    model: str
    max_tokens: int
    api_base_url: str
    api_version: str


class CacheConfigSnapshot(BaseModel):
    enabled:   bool
    ttl_hours: int


class AdminConfigResponse(BaseModel):
    environment: str
    application: str
    version: str
    llm: LlmConfigSnapshot
    cache: CacheConfigSnapshot
    root_cause_values: list[RootCauseEntryResponse]


# ── Dependency ────────────────────────────────────────────────────────────────

def _get_settings() -> Settings:
    """Default dependency — returns a fresh Settings instance (overridden in main.py)."""
    return Settings()


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/config", response_model=AdminConfigResponse)
async def get_config(
    settings: Annotated[Settings, Depends(_get_settings)],
) -> AdminConfigResponse:
    """
    Returns a full snapshot of the current runtime configuration.
    """
    try:
        version = importlib.metadata.version("financial-event-collector")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    return AdminConfigResponse(
        environment=os.environ.get("APP_ENVIRONMENT", os.environ.get("ASPNETCORE_ENVIRONMENT", "Production")),
        application="FinancialEventCollector",
        version=version,
        llm=LlmConfigSnapshot(
            model=settings.claude.model,
            max_tokens=settings.claude.max_tokens,
            api_base_url=settings.claude.api_base_url,
            api_version=settings.claude.api_version,
        ),
        cache=CacheConfigSnapshot(
            enabled=settings.cache.enabled,
            ttl_hours=settings.cache.ttl_hours,
        ),
        root_cause_values=[
            RootCauseEntryResponse(
                name=entry.name,
                description=entry.description,
            )
            for entry in ROOT_CAUSE_CATALOG_LIST
        ],
    )
