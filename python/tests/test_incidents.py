"""
Tests for IncidentDataService — verifies that Incidents.json loads correctly.
Also tests EventRepository — verifies that EventLogs.json loads correctly.
"""
from __future__ import annotations

import pytest

from app.services.incident_data_service import IncidentDataService
from app.services.event_repository import EventRepository


@pytest.fixture(scope="module")
def incident_svc() -> IncidentDataService:
    return IncidentDataService()


@pytest.fixture(scope="module")
def event_repo() -> EventRepository:
    return EventRepository()


# ── IncidentDataService tests ─────────────────────────────────────────────────

def test_incidents_loaded(incident_svc: IncidentDataService) -> None:
    """Incidents.json should load at least one incident."""
    incidents = incident_svc.get_incidents()
    assert len(incidents) > 0, "Expected at least one incident in Incidents.json"


def test_incident_has_required_fields(incident_svc: IncidentDataService) -> None:
    """Each incident should have an id, title, and event_id.
    The Incident model is now a thin manifest — audit events and worker logs
    are stored in EventLogs.json and accessed via EventRepository.
    ≈ Incident.cs (thin manifest record)
    """
    for incident in incident_svc.get_incidents():
        assert incident.incident_id > 0
        assert incident.incident_title
        assert incident.event_id


# ── EventRepository tests ─────────────────────────────────────────────────────

def test_event_logs_loaded(event_repo: EventRepository) -> None:
    """EventLogs.json should load at least one event log."""
    logs = event_repo.get_all_event_logs()
    assert len(logs) > 0, "Expected at least one event log in EventLogs.json"


def test_event_log_has_required_fields(event_repo: EventRepository) -> None:
    """Each event log should have an event_id, event_source, audit_events, and worker_logs."""
    for log in event_repo.get_all_event_logs():
        assert log.event_id
        assert log.event_source
        assert isinstance(log.audit_events, list)
        assert isinstance(log.worker_logs, list)


def test_event_log_scenario_metadata(event_repo: EventRepository) -> None:
    """Event logs with scenario metadata should have a scenario name and expected root cause."""
    labelled = [log for log in event_repo.get_all_event_logs() if log.scenario_metadata is not None]
    assert len(labelled) > 0, "Expected at least one labelled event log"
    for log in labelled:
        assert log.scenario_metadata is not None
        assert log.scenario_metadata.scenario_name
        assert log.scenario_metadata.expected_root_cause is not None


def test_get_event_log_by_id(event_repo: EventRepository) -> None:
    """get_event_log_by_id should return the correct event log."""
    logs = event_repo.get_all_event_logs()
    first = logs[0]
    found = event_repo.get_event_log_by_id(first.event_id)
    assert found is not None
    assert found.event_id == first.event_id


def test_get_event_log_by_id_case_insensitive(event_repo: EventRepository) -> None:
    """get_event_log_by_id should be case-insensitive."""
    logs = event_repo.get_all_event_logs()
    first = logs[0]
    found = event_repo.get_event_log_by_id(first.event_id.upper())
    assert found is not None
    assert found.event_id == first.event_id


def test_get_event_log_by_id_not_found(event_repo: EventRepository) -> None:
    """get_event_log_by_id should return None for unknown event IDs."""
    assert event_repo.get_event_log_by_id("evt-nonexistent") is None


def test_get_event_lineage(event_repo: EventRepository) -> None:
    """get_event_lineage should return a projected EventLineage for a known event."""
    logs = event_repo.get_all_event_logs()
    first = logs[0]
    lineage = event_repo.get_event_lineage(first.event_id)
    assert lineage is not None
    assert lineage.event_id == first.event_id
    assert lineage.event_source == first.event_source
    assert isinstance(lineage.audit_events_present, list)
    assert isinstance(lineage.missing_audit_events, list)


def test_event_lineage_healthy_event(event_repo: EventRepository) -> None:
    """evt-001 (AllAuditEventsPresent) should have all three stages present."""
    lineage = event_repo.get_event_lineage("evt-001")
    assert lineage is not None
    assert lineage.ingest_success is True
    assert lineage.index_success is True
    assert lineage.publish_success is True
    assert lineage.missing_audit_events == []
    assert lineage.publish_latency_seconds is not None
    assert lineage.publish_latency_sla_met is not None


def test_incidents_reference_valid_event_logs(
    incident_svc: IncidentDataService,
    event_repo: EventRepository,
) -> None:
    """Every incident's event_id should resolve to an event log in EventLogs.json."""
    for incident in incident_svc.get_incidents():
        log = event_repo.get_event_log_by_id(incident.event_id)
        assert log is not None, (
            f"Incident {incident.incident_id} references event_id='{incident.event_id}' "
            f"which is not in EventLogs.json"
        )
