"""
Validation router — POST /validation/run.
≈ dotnet/src/Controllers/ValidationController.cs

Runs every incident scenario through the investigation pipeline and compares
the LLM's verdict against the human-authored ground-truth label stored in
IncidentTestMetadata.expected_root_cause.

Useful for regression testing the LLM prompt and for measuring overall
accuracy and cost across the full scenario suite.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from app.limiter import limiter

from app.auth import require_role
from app.models.validation import ValidationRunResponse
from app.services.validation_service import ValidationService

logger = logging.getLogger(__name__)

# Hard cap on the number of incidents processed per validation run.
# ≈ ValidationController.MaxLimit
_MAX_LIMIT = 10

# Router-level dependency — every route requires a valid X-Api-Key with admin role.
# ≈ [Authorize(Roles = "admin")] on ValidationController.cs:16
router = APIRouter(
    dependencies=[Depends(require_role("admin"))],
    tags=["Validation (role: admin)"],
)


# ── Dependency functions ──────────────────────────────────────────────────────
# These are overridden in main.py with the application-level singletons.

def _get_validation_svc() -> ValidationService:
    from app.config import Settings
    from app.services.event_repository import EventRepository
    from app.services.incident_data_service import IncidentDataService
    from app.services.investigation_service import InvestigationService
    from app.services.llm_service import ClaudeService
    settings = Settings()
    return ValidationService(
        IncidentDataService(),
        InvestigationService(
            ClaudeService(settings),
            max_prompt_chars=settings.claude.max_prompt_chars,
        ),
        EventRepository(),
    )


@limiter.limit("10/minute")
@router.post("/run", response_model=ValidationRunResponse)
async def run(
    request: Request,
    validation_svc: Annotated[ValidationService, Depends(_get_validation_svc)],
    limit: int = Query(default=_MAX_LIMIT, ge=1, le=_MAX_LIMIT),
    bypass_cache: bool = Query(default=False),
) -> ValidationRunResponse:
    """
    Executes the investigation pipeline for every incident scenario and returns
    a per-incident comparison of the expected vs. actual root cause, plus the
    aggregated LLM cost across all non-cached calls.

    Incidents without a TestMetadata.expected_root_cause label are still included;
    their expected_root_cause and root_cause_match fields will be None.
    By default, results are served from the investigation cache when available.
    Set bypass_cache=true to force every incident through the LLM endpoint.

    - **limit**: Maximum number of incidents to process (1–10). Defaults to 10.
    - **bypass_cache**: When true, skips the in-memory cache so every incident is
      sent to the LLM endpoint regardless of whether a cached result exists. Defaults to false.
    """
    if limit < 1 or limit > _MAX_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": f"'limit' must be between 1 and {_MAX_LIMIT}. Received: {limit}."},
        )

    return await validation_svc.run_async(limit, bypass_cache=bypass_cache)
