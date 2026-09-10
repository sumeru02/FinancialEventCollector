"""
Loads pipeline event log data from shared/data/EventLogs.json.
Registered as a singleton so the file is parsed once and the
EventLineage projections are computed once at startup.
≈ EventRepository.cs
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.event_log import EventLog, EventLineage

# parents[0] = app/services, parents[1] = app, parents[2] = python/, parents[3] = repo root.
# The shared/ directory lives at the repo root.
_SHARED_DIR = Path(__file__).parents[3] / "shared"


class EventRepository:
    """
    Loads pipeline event log data from shared/data/EventLogs.json once at startup.
    Provides both the raw EventLog records (used by the LLM investigation service)
    and the projected EventLineage views (returned by the Events API endpoints).
    ≈ EventRepository.cs
    """

    def __init__(self) -> None:
        # Load raw event logs from disk
        logs_path = _SHARED_DIR / "data" / "EventLogs.json"
        raw = json.loads(logs_path.read_text(encoding="utf-8"))
        logs: list[EventLog] = [EventLog.model_validate(item) for item in raw]

        # Build O(1) lookup by eventId (case-insensitive)
        self._event_logs: dict[str, EventLog] = {
            log.event_id.lower(): log for log in logs
        }

        # Load SLA threshold from pipeline-config.json (same source as PromptHelper)
        config_path = _SHARED_DIR / "config" / "pipeline-config.json"
        config: dict = json.loads(config_path.read_text(encoding="utf-8"))
        sla_threshold_minutes: int = config["sla"]["publishLatencyThresholdMinutes"]

        # Project EventLog → EventLineage once at startup (O(n), stored for O(1) lookups)
        self._event_lineages: dict[str, EventLineage] = {
            log.event_id.lower(): EventLineage.from_event_log(log, sla_threshold_minutes)
            for log in logs
        }

    def get_event_lineage(self, event_id: str) -> EventLineage | None:
        """
        Returns the projected data lineage view for a single pipeline event.
        Returns None when no event with the given event_id exists.
        Used by GET /events/{eventId}/lineage.
        ≈ IEventRepository.GetEventLineage()
        """
        return self._event_lineages.get(event_id.lower())

    def get_event_log_by_id(self, event_id: str) -> EventLog | None:
        """
        Returns the raw event log record for a single pipeline event.
        Returns None when no event with the given event_id exists.
        Used by GET /events/{eventId}/logs, POST /events/{eventId}/investigations,
        and POST /incidents/{id}/investigations.
        ≈ IEventRepository.GetEventLogById()
        """
        return self._event_logs.get(event_id.lower())

    def get_all_event_logs(self) -> list[EventLog]:
        """Returns all raw event log records."""
        return list(self._event_logs.values())
