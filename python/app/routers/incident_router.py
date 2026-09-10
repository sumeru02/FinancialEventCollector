"""
Incident router — handles GET /incidents and POST /incidents/{id}/investigations.
≈ IncidentController.cs
"""
from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.auth import require_role
from app.config import Settings
from app.helpers.llm_cost_helper import calculate_claude_sonnet_cost_usd
from app.helpers.prompt_helper import build_investigation_prompt
from app.limiter import limiter

from app.models.incident import Incident
from app.models.investigation import InvestigationResponse
from app.models.telemetry import (
    InvestigationResponseTelemetry,
    InvestigationTelemetryEvent,
    InvestigationValidationTelemetry,
    LlmUsageTelemetry,
)
from app.services.event_repository import EventRepository
from app.services.incident_data_service import IncidentDataService
from app.services.investigation_service import InvestigationService
from app.services.telemetry_store import TelemetryStore

logger = logging.getLogger(__name__)

# Router-level dependency — every route in this router requires a valid X-Api-Key
# with the 'user' role (admin keys are also accepted because ApiKeyAuthHandler grants
# both "admin" and "user" claims to the admin key).
# ≈ [Authorize(Roles = "user")] on IncidentController.cs:14
router = APIRouter(
    dependencies=[Depends(require_role("user"))],
    tags=["Incident (role: user)"],
)


# ── Dependency functions ──────────────────────────────────────────────────────
# These are overridden in main.py with the application-level singletons.

def _get_settings() -> Settings:
    """Default dependency — overridden in main.py with the application singleton."""
    return Settings()

def _get_incident_svc() -> IncidentDataService:
    return IncidentDataService()

def _get_event_repository() -> EventRepository:
    return EventRepository()

def _get_investigation_svc() -> InvestigationService:
    from app.services.llm_service import ClaudeService
    settings = Settings()
    return InvestigationService(
        ClaudeService(settings),
        max_prompt_chars=settings.claude.max_prompt_chars,
    )

def _get_telemetry_store() -> TelemetryStore:
    return TelemetryStore()


@router.get("", response_model=list[Incident])
async def get_all(
    incident_svc: Annotated[IncidentDataService, Depends(_get_incident_svc)],
) -> list[Incident]:
    """Returns all available incidents with their audit events and worker logs."""
    return incident_svc.get_incidents()


@router.get("/{id}", response_model=Incident)
async def get_by_id(
    id: int,
    incident_svc: Annotated[IncidentDataService, Depends(_get_incident_svc)],
) -> Incident:
    """Returns the incident for the given id."""
    incident = next((i for i in incident_svc.get_incidents() if i.incident_id == id), None)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {id} not found.")
    return incident


@router.get("/{id}/prompt", response_model=dict)
async def get_prompt(
    id: int,
    incident_svc: Annotated[IncidentDataService, Depends(_get_incident_svc)],
    event_repo: Annotated[EventRepository, Depends(_get_event_repository)],
    settings: Annotated[Settings, Depends(_get_settings)],
) -> dict:
    """
    Returns the fully-assembled LLM investigation prompt for the given incident
    without invoking the LLM.

    Useful for debugging, prompt iteration, and auditing exactly what data is
    sent to the external AI service.
    ≈ IncidentController.GetPrompt()
    """
    incident = next((i for i in incident_svc.get_incidents() if i.incident_id == id), None)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {id} not found.")

    # Resolve the EventLog from EventLogs.json (mirrors .NET IncidentController.GetPrompt)
    event_log = event_repo.get_event_log_by_id(incident.event_id)
    if event_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"EventLog for EventId '{incident.event_id}' not found."},
        )

    try:
        prompt = build_investigation_prompt(event_log, settings.claude.max_prompt_chars)
        return {"prompt": prompt}
    except ValueError as ex:
        logger.warning("Prompt for incident_id=%d exceeds max_prompt_chars limit: %s", id, ex)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(ex)},
        ) from ex


@limiter.limit("10/minute")
@router.post("/{id}/investigations", response_model=InvestigationResponse)
async def investigate(
    request: Request,
    id: int,
    response: Response,
    incident_svc: Annotated[IncidentDataService, Depends(_get_incident_svc)],
    event_repo: Annotated[EventRepository, Depends(_get_event_repository)],
    investigation_svc: Annotated[InvestigationService, Depends(_get_investigation_svc)],
    telemetry_store: Annotated[TelemetryStore, Depends(_get_telemetry_store)],
) -> InvestigationResponse:
    """
    Runs an AI-powered incident investigation for the given incident.
    Results are cached; X-Cache header indicates HIT or MISS.
    ≈ IncidentController.Investigate()
    """
    incident = next((i for i in incident_svc.get_incidents() if i.incident_id == id), None)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {id} not found.")

    # Resolve the EventLog from EventLogs.json — mirrors .NET IncidentController.Investigate()
    # which calls _eventRepository.GetEventLogById(incident.EventId).
    event_log = event_repo.get_event_log_by_id(incident.event_id)
    if event_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"EventLog for EventId '{incident.event_id}' not found."},
        )

    start_ms = time.monotonic() * 1000

    try:
        # Investigate using EventLog (primary path, mirrors .NET)
        result, from_cache, llm_metadata = await investigation_svc.investigate_async(event_log)
        elapsed_ms = int(time.monotonic() * 1000 - start_ms)

        # X-Cache header
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"

        # Build LLM usage telemetry
        llm_usage_telemetry: LlmUsageTelemetry | None = None
        if llm_metadata is not None:
            raw_cost = calculate_claude_sonnet_cost_usd(
                input_tokens=llm_metadata.input_tokens,
                cached_tokens=llm_metadata.cached_tokens,
                output_tokens=llm_metadata.output_tokens,
            )
            # Round to 2 d.p. for display — mirrors Math.Round(cost.Value, 2) in
            # IncidentController.ComputeEstimatedCostUsd() (C#).
            estimated_cost = round(raw_cost, 2) if raw_cost is not None else None
            llm_usage_telemetry = LlmUsageTelemetry(
                model=llm_metadata.model,
                input_tokens=llm_metadata.input_tokens,
                output_tokens=llm_metadata.output_tokens,
                cached_tokens=llm_metadata.cached_tokens,
                estimated_cost_usd=estimated_cost,
            )

        # Resolve the projected lineage — passed through as event_context so callers
        # can correlate the LLM verdict with structured pipeline stage data.
        lineage = event_repo.get_event_lineage(incident.event_id)

        # Emit telemetry
        telemetry = InvestigationTelemetryEvent(
            telemetry_type="InvestigationCompleted",
            timestamp=datetime.now(tz=timezone.utc),
            incident_id=id,
            event_id=incident.event_id,
            response=InvestigationResponseTelemetry(
                response_time_ms=elapsed_ms,
                cached=from_cache,
                confidence=result.confidence,
                root_cause=result.root_cause,
                llm_usage=llm_usage_telemetry,
            ),
            validation=InvestigationValidationTelemetry(
                expected_root_cause=(
                    event_log.scenario_metadata.expected_root_cause
                    if event_log.scenario_metadata
                    else None
                ),
                actual_root_cause=result.root_cause,
                root_cause_match=(
                    event_log.scenario_metadata.expected_root_cause == result.root_cause
                    if event_log.scenario_metadata
                    and event_log.scenario_metadata.expected_root_cause is not None
                    else None
                ),
            ),
        )
        await telemetry_store.add(telemetry)

        logger.info(
            "Investigation telemetry recorded: incident_id=%d root_cause=%s cached=%s elapsed_ms=%d",
            id, result.root_cause, from_cache, elapsed_ms,
        )

        return InvestigationResponse(
            investigation=result,
            event_context=lineage,
            llm_usage=llm_usage_telemetry,
        )

    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("Investigation upstream error for incident_id=%d: %s", id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            # ≈ IncidentController.cs: return StatusCode(502, new { message = "LLM service unavailable." })
            detail={"message": "LLM service unavailable."},
        ) from exc

    except ValueError as exc:
        logger.error("Investigation value error for incident_id=%d: %s", id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            # ≈ IncidentController.cs: return StatusCode(500, new { message = "Investigation failed." })
            # Internal detail is logged above; do not expose it to callers (information disclosure).
            detail={"message": "Investigation failed."},
        ) from exc

    except Exception as exc:
        logger.error("Investigation failed for incident_id=%d: %s", id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            # Internal detail is logged above; do not expose it to callers (information disclosure).
            detail={"message": "Investigation failed."},
        ) from exc
