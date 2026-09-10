"""
Events router — handles GET /events/{eventId}/lineage, GET /events/{eventId}/logs,
GET /events/{eventId}/prompt, and POST /events/{eventId}/investigations.
≈ EventController.cs
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

from app.models.event_log import EventLineage, EventLogResponse
from app.models.investigation import InvestigationResponse
from app.models.telemetry import (
    InvestigationResponseTelemetry,
    InvestigationTelemetryEvent,
    InvestigationValidationTelemetry,
    LlmUsageTelemetry,
)
from app.services.event_repository import EventRepository
from app.services.investigation_service import InvestigationService
from app.services.telemetry_store import TelemetryStore

logger = logging.getLogger(__name__)

# Router-level dependency — every route in this router requires a valid X-Api-Key
# with the 'user' role (admin keys are also accepted because ApiKeyAuthHandler grants
# both "admin" and "user" claims to the admin key).
# ≈ [Authorize(Roles = "user")] on EventController.cs:14
router = APIRouter(
    dependencies=[Depends(require_role("user"))],
    tags=["Event (role: user)"],
)


# ── Dependency functions ──────────────────────────────────────────────────────
# These are overridden in main.py with the application-level singletons.

def _get_settings() -> Settings:
    """Default dependency — overridden in main.py with the application singleton."""
    return Settings()

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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{event_id}/lineage", response_model=EventLineage)
async def get_lineage_by_event_id(
    event_id: str,
    event_repo: Annotated[EventRepository, Depends(_get_event_repository)],
) -> EventLineage:
    """
    Returns the data lineage view for a given event ID.
    ≈ EventController.GetLineageByEventId()
    """
    lineage = event_repo.get_event_lineage(event_id)
    if lineage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Event '{event_id}' not found."},
        )
    return lineage


@router.get("/{event_id}/logs", response_model=EventLogResponse)
async def get_logs_by_event_id(
    event_id: str,
    event_repo: Annotated[EventRepository, Depends(_get_event_repository)],
) -> EventLogResponse:
    """
    Returns the raw audit events and worker logs for a given event ID.

    Exposes the underlying pipeline telemetry records that feed the data lineage
    projection and the LLM investigation prompt. Internal test scenario metadata
    is excluded.
    ≈ EventController.GetLogsByEventId()
    """
    event_log = event_repo.get_event_log_by_id(event_id)
    if event_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Event '{event_id}' not found."},
        )
    return EventLogResponse.from_event_log(event_log)


@router.get("/{event_id}/prompt", response_model=dict)
async def get_prompt(
    event_id: str,
    event_repo: Annotated[EventRepository, Depends(_get_event_repository)],
    settings: Annotated[Settings, Depends(_get_settings)],
) -> dict:
    """
    Returns the fully-assembled LLM investigation prompt for the given event
    without invoking the LLM.

    Useful for debugging, prompt iteration, and auditing exactly what data is
    sent to the external AI service.
    ≈ EventController.GetPrompt()
    """
    event_log = event_repo.get_event_log_by_id(event_id)
    if event_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Event '{event_id}' not found."},
        )

    try:
        prompt = build_investigation_prompt(event_log, settings.claude.max_prompt_chars)
        return {"prompt": prompt}
    except ValueError as ex:
        logger.warning("Prompt for event_id=%s exceeds max_prompt_chars limit: %s", event_id, ex)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(ex)},
        ) from ex


@limiter.limit("10/minute")
@router.post("/{event_id}/investigations", response_model=InvestigationResponse)
async def investigate(
    request: Request,
    event_id: str,
    response: Response,
    event_repo: Annotated[EventRepository, Depends(_get_event_repository)],
    investigation_svc: Annotated[InvestigationService, Depends(_get_investigation_svc)],
    telemetry_store: Annotated[TelemetryStore, Depends(_get_telemetry_store)],
) -> InvestigationResponse:
    """
    Runs an AI-powered investigation for the given pipeline event.

    Looks up the event by its EventId and returns a structured verdict from the
    configured LLM (Claude by default). No request body is required — all data
    needed for the investigation is stored in data/EventLogs.json. Results are
    cached in memory; the X-Cache response header indicates whether the result
    was served from cache (HIT) or freshly generated (MISS).
    ≈ EventController.Investigate()
    """
    event_log = event_repo.get_event_log_by_id(event_id)
    if event_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Event '{event_id}' not found."},
        )

    start_ms = time.monotonic() * 1000

    try:
        result, from_cache, llm_metadata = await investigation_svc.investigate_async(event_log)
        elapsed_ms = int(time.monotonic() * 1000 - start_ms)

        # X-Cache header
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"

        # Build LLM usage telemetry (null on cache hit — no LLM call was made)
        llm_usage_telemetry: LlmUsageTelemetry | None = None
        if llm_metadata is not None:
            raw_cost = calculate_claude_sonnet_cost_usd(
                input_tokens=llm_metadata.input_tokens,
                cached_tokens=llm_metadata.cached_tokens,
                output_tokens=llm_metadata.output_tokens,
            )
            # Round to 2 d.p. for display — mirrors Math.Round(cost.Value, 2) in
            # EventController.ComputeEstimatedCostUsd() (C#).
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
        lineage = event_repo.get_event_lineage(event_id)

        # Emit telemetry for observability and LLM accuracy tracking
        telemetry = InvestigationTelemetryEvent(
            telemetry_type="InvestigationCompleted",
            timestamp=datetime.now(tz=timezone.utc),
            incident_id=None,   # no incident — event-driven investigation
            event_id=event_id,
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
            "Investigation telemetry recorded: event_id=%s root_cause=%s cached=%s "
            "elapsed_ms=%d estimated_cost_usd=%s",
            event_id,
            result.root_cause,
            from_cache,
            elapsed_ms,
            llm_usage_telemetry.estimated_cost_usd if llm_usage_telemetry else None,
        )

        return InvestigationResponse(
            investigation=result,
            event_context=lineage,
            llm_usage=llm_usage_telemetry,
        )

    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("Investigation upstream error for event_id=%s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            # ≈ EventController.cs: return StatusCode(502, new { message = "LLM service unavailable." })
            detail={"message": "LLM service unavailable."},
        ) from exc

    except ValueError as exc:
        logger.error("Investigation value error for event_id=%s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            # ≈ EventController.cs: return StatusCode(500, new { message = "Investigation failed." })
            detail={"message": "Investigation failed."},
        ) from exc

    except Exception as exc:
        logger.error("Investigation failed for event_id=%s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Investigation failed."},
        ) from exc
