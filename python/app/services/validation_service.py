"""
Runs every incident scenario through the investigation pipeline and compares
the LLM's verdict against the human-authored ground-truth label stored in
ScenarioMetadata.expected_root_cause on the associated EventLog.

Useful for regression testing the LLM prompt and for measuring overall
accuracy and cost across the full scenario suite.
≈ dotnet/src/Services/ValidationService.cs
"""
from __future__ import annotations

import logging
import time

from app.helpers.llm_cost_helper import calculate_claude_sonnet_cost_usd
from app.models.validation import ValidationRunResponse, ValidationScenarioResult
from app.services.event_repository import EventRepository
from app.services.incident_data_service import IncidentDataService
from app.services.investigation_service import InvestigationService

logger = logging.getLogger(__name__)


class ValidationService:
    """
    Runs every incident scenario through the investigation pipeline and compares
    the LLM's verdict against the human-authored ground-truth label.
    Uses EventRepository to resolve the EventLog for each incident, mirroring
    the .NET ValidationService which calls _eventRepository.GetEventLogById().
    ≈ ValidationService.cs
    """

    def __init__(
        self,
        incident_data: IncidentDataService,
        investigation_service: InvestigationService,
        event_repository: EventRepository | None = None,
    ) -> None:
        self._incident_data         = incident_data
        self._investigation_service = investigation_service
        # event_repository is optional for backward compatibility; when None,
        # the service falls back to the legacy Incident-based investigation path.
        self._event_repository      = event_repository

    async def run_async(self, limit: int = 10, bypass_cache: bool = False) -> ValidationRunResponse:
        """
        Executes the investigation pipeline for up to *limit* incidents and
        returns a per-incident comparison of the expected vs. actual root cause,
        plus the aggregated LLM cost across all non-cached calls.
        When bypass_cache=True every incident is sent to the LLM regardless of
        whether a cached result exists.
        ≈ ValidationService.RunAsync()
        """
        incidents = self._incident_data.get_incidents()[:limit]
        results: list[ValidationScenarioResult] = []
        total_cost_usd = 0.0

        for incident in incidents:
            # Resolve the EventLog from EventLogs.json — mirrors .NET ValidationService
            # which calls _eventRepository.GetEventLogById(incident.EventId).
            if self._event_repository is not None:
                event_log = self._event_repository.get_event_log_by_id(incident.event_id)
                if event_log is None:
                    logger.warning(
                        "Validation: incident_id=%d skipped — EventLog for event_id='%s' not found.",
                        incident.incident_id,
                        incident.event_id,
                    )
                    continue
                source = event_log
                expected = (
                    event_log.scenario_metadata.expected_root_cause
                    if event_log.scenario_metadata
                    else None
                )
                scenario_name = (
                    event_log.scenario_metadata.scenario_name
                    if event_log.scenario_metadata
                    else None
                )
            else:
                # Legacy path: investigate using Incident directly
                source = incident
                expected = incident.test_metadata.expected_root_cause if incident.test_metadata else None
                scenario_name = incident.test_metadata.scenario_name if incident.test_metadata else None

            start_ms = time.monotonic() * 1000
            result, from_cache, llm_metadata = await self._investigation_service.investigate_async(
                source, bypass_cache=bypass_cache
            )
            elapsed_ms = int(time.monotonic() * 1000 - start_ms)

            scenario_cost_usd: float | None = None
            if not from_cache and llm_metadata is not None:
                scenario_cost_usd = calculate_claude_sonnet_cost_usd(
                    input_tokens=llm_metadata.input_tokens,
                    cached_tokens=llm_metadata.cached_tokens,
                    output_tokens=llm_metadata.output_tokens,
                )
                if scenario_cost_usd is not None:
                    total_cost_usd += scenario_cost_usd

            root_cause_match: bool | None = (
                expected == result.root_cause if expected is not None else None
            )

            results.append(ValidationScenarioResult(
                incident_id=incident.incident_id,
                scenario_name=scenario_name,
                expected_root_cause=expected,
                actual_root_cause=result.root_cause,
                root_cause_match=root_cause_match,
                confidence=result.confidence,
                from_cache=from_cache,
                response_time_ms=elapsed_ms,
                estimated_cost_usd=scenario_cost_usd,
            ))

            logger.info(
                "Validation: incident_id=%d expected=%s actual=%s match=%s cached=%s",
                incident.incident_id,
                expected,
                result.root_cause,
                root_cause_match,
                from_cache,
            )

        labelled_results = [r for r in results if r.root_cause_match is not None]
        labelled_count   = len(labelled_results) if labelled_results else 0
        correct_count    = sum(1 for r in labelled_results if r.root_cause_match is True)
        accuracy: float | None = (
            round(correct_count / labelled_count * 100.0, 1) if labelled_count > 0 else None
        )

        return ValidationRunResponse(
            results=results,
            total_scenarios=len(results),
            labelled_scenarios=labelled_count,
            correct_predictions=correct_count,
            accuracy_percent=accuracy,
            total_cost_usd=round(total_cost_usd, 6),
        )
