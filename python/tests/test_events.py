"""
Tests for the events router — GET /events/{eventId}/lineage,
GET /events/{eventId}/logs, GET /events/{eventId}/prompt,
and POST /events/{eventId}/investigations.
≈ EventController.cs tests
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.models.investigation import InvestigationResult
from app.models.root_cause import RootCause
from app.services.event_repository import EventRepository
from app.services.investigation_service import InvestigationService
from app.services.telemetry_store import TelemetryStore
from app.services.llm_service import LlmCompletionResult
from app.routers import events_router, telemetry_router
from app import auth as auth_module
from app.config import Settings


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def event_repo() -> EventRepository:
    return EventRepository()


def _make_mock_llm_result() -> LlmCompletionResult:
    return LlmCompletionResult(
        text='{"rootCause": "AllAuditEventsPresent", "explanation": "All events present.", "confidence": "HIGH"}',
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cached_tokens=20,
    )


def _make_mock_investigation_svc(llm_result: LlmCompletionResult) -> InvestigationService:
    mock_svc = MagicMock(spec=InvestigationService)
    mock_svc.investigate_async = AsyncMock(
        return_value=(
            InvestigationResult(
                root_cause=RootCause.ALL_AUDIT_EVENTS_PRESENT,
                explanation="All events present.",
                confidence="HIGH",
            ),
            False,   # from_cache
            llm_result,
        )
    )
    return mock_svc


@pytest.fixture()
def events_test_client():
    """
    Builds a minimal FastAPI test app with:
      - events_router (GET lineage, GET logs, GET prompt, POST investigations)
      - telemetry_router (GET /telemetry)
    All dependencies are overridden with in-process singletons; the
    InvestigationService is mocked so no real LLM calls are made.
    """
    store = TelemetryStore()
    llm_result = _make_mock_llm_result()
    mock_inv_svc = _make_mock_investigation_svc(llm_result)
    settings = Settings()
    event_repository = EventRepository()

    app = FastAPI()

    from app.limiter import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(events_router.router, prefix="/events", tags=["Events"])
    app.include_router(telemetry_router.router, prefix="/telemetry", tags=["Telemetry"])

    app.dependency_overrides[events_router._get_event_repository]   = lambda: event_repository
    app.dependency_overrides[events_router._get_investigation_svc]  = lambda: mock_inv_svc
    app.dependency_overrides[events_router._get_telemetry_store]    = lambda: store
    app.dependency_overrides[events_router._get_settings]           = lambda: settings
    app.dependency_overrides[telemetry_router._get_telemetry_store] = lambda: store
    app.dependency_overrides[auth_module._get_settings]             = lambda: settings

    client = TestClient(app, raise_server_exceptions=True)
    return client, store, mock_inv_svc, event_repository


_USER_HEADERS  = {"X-Api-Key": "UserSecret"}
_ADMIN_HEADERS = {"X-Api-Key": "AdminSecret"}


# ── GET /events/{eventId}/lineage ─────────────────────────────────────────────

class TestGetLineage:
    def test_get_lineage_returns_200(self, events_test_client) -> None:
        """GET /events/evt-001/lineage should return 200 with lineage data."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/lineage", headers=_USER_HEADERS)
        assert resp.status_code == 200

    def test_get_lineage_has_required_fields(self, events_test_client) -> None:
        """Lineage response should contain all required fields."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/lineage", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "event_id" in body
        assert "event_source" in body
        assert "ingest_success" in body
        assert "index_success" in body
        assert "publish_success" in body
        assert "audit_events_present" in body
        assert "missing_audit_events" in body

    def test_get_lineage_healthy_event(self, events_test_client) -> None:
        """evt-001 (AllAuditEventsPresent) should have all three stages present."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/lineage", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == "evt-001"
        assert body["ingest_success"] is True
        assert body["index_success"] is True
        assert body["publish_success"] is True
        assert body["missing_audit_events"] == []

    def test_get_lineage_not_found(self, events_test_client) -> None:
        """GET /events/evt-nonexistent/lineage should return 404."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-nonexistent/lineage", headers=_USER_HEADERS)
        assert resp.status_code == 404

    def test_get_lineage_requires_auth(self, events_test_client) -> None:
        """GET /events/{eventId}/lineage should return 401 without auth."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/lineage")
        assert resp.status_code == 401


# ── GET /events/{eventId}/logs ────────────────────────────────────────────────

class TestGetLogs:
    def test_get_logs_returns_200(self, events_test_client) -> None:
        """GET /events/evt-001/logs should return 200 with log data."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/logs", headers=_USER_HEADERS)
        assert resp.status_code == 200

    def test_get_logs_has_required_fields(self, events_test_client) -> None:
        """Logs response should contain event_id, event_source, audit_events, worker_logs."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/logs", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "event_id" in body
        assert "event_source" in body
        assert "audit_events" in body
        assert "worker_logs" in body

    def test_get_logs_excludes_scenario_metadata(self, events_test_client) -> None:
        """Logs response must NOT contain scenario_metadata (internal test data)."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/logs", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "scenario_metadata" not in body, (
            "scenario_metadata must be excluded from the logs response "
            "(it is internal test scaffolding)"
        )

    def test_get_logs_not_found(self, events_test_client) -> None:
        """GET /events/evt-nonexistent/logs should return 404."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-nonexistent/logs", headers=_USER_HEADERS)
        assert resp.status_code == 404


# ── GET /events/{eventId}/prompt ──────────────────────────────────────────────

class TestGetPrompt:
    def test_get_prompt_returns_200(self, events_test_client) -> None:
        """GET /events/evt-001/prompt should return 200 with a prompt string."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/prompt", headers=_USER_HEADERS)
        assert resp.status_code == 200

    def test_get_prompt_contains_prompt_key(self, events_test_client) -> None:
        """Prompt response should contain a 'prompt' key with a non-empty string."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/prompt", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "prompt" in body
        assert isinstance(body["prompt"], str)
        assert len(body["prompt"]) > 0

    def test_get_prompt_contains_event_id(self, events_test_client) -> None:
        """The prompt should contain the event ID."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-001/prompt", headers=_USER_HEADERS)
        assert resp.status_code == 200
        assert "evt-001" in resp.json()["prompt"]

    def test_get_prompt_not_found(self, events_test_client) -> None:
        """GET /events/evt-nonexistent/prompt should return 404."""
        client, *_ = events_test_client
        resp = client.get("/events/evt-nonexistent/prompt", headers=_USER_HEADERS)
        assert resp.status_code == 404


# ── POST /events/{eventId}/investigations ─────────────────────────────────────

class TestInvestigateEvent:
    def test_investigate_returns_200(self, events_test_client) -> None:
        """POST /events/evt-001/investigations should return 200."""
        client, *_ = events_test_client
        resp = client.post("/events/evt-001/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 200

    def test_investigate_response_has_investigation(self, events_test_client) -> None:
        """Investigation response should contain an 'investigation' object."""
        client, *_ = events_test_client
        resp = client.post("/events/evt-001/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "investigation" in body
        inv = body["investigation"]
        assert "root_cause" in inv
        assert "explanation" in inv
        assert "confidence" in inv

    def test_investigate_response_has_event_context(self, events_test_client) -> None:
        """Investigation response should contain an 'event_context' with lineage data.
        ≈ InvestigationResponse.EventContext in C#."""
        client, *_ = events_test_client
        resp = client.post("/events/evt-001/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "event_context" in body, "Response must contain 'event_context'"
        ctx = body["event_context"]
        assert ctx is not None, "event_context must not be null"
        assert "event_id" in ctx
        assert "ingest_success" in ctx
        assert "index_success" in ctx
        assert "publish_success" in ctx

    def test_investigate_response_has_llm_usage(self, events_test_client) -> None:
        """Investigation response should contain an 'llm_usage' object."""
        client, *_ = events_test_client
        resp = client.post("/events/evt-001/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "llm_usage" in body
        llm_usage = body["llm_usage"]
        assert llm_usage is not None
        assert "input_tokens" in llm_usage
        assert "output_tokens" in llm_usage
        assert "cached_tokens" in llm_usage

    def test_investigate_sets_x_cache_header(self, events_test_client) -> None:
        """Investigation response should set the X-Cache header."""
        client, *_ = events_test_client
        resp = client.post("/events/evt-001/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 200
        assert "x-cache" in resp.headers

    def test_investigate_not_found(self, events_test_client) -> None:
        """POST /events/evt-nonexistent/investigations should return 404."""
        client, *_ = events_test_client
        resp = client.post("/events/evt-nonexistent/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 404

    def test_investigate_emits_telemetry_with_null_incident_id(
        self, events_test_client
    ) -> None:
        """
        POST /events/{eventId}/investigations should emit telemetry with
        incident_id=null (no incident — event-driven investigation).
        ≈ EventController.Investigate() sets IncidentId = null in C#.
        """
        client, store, *_ = events_test_client
        resp = client.post("/events/evt-001/investigations", headers=_USER_HEADERS)
        assert resp.status_code == 200

        # Fetch telemetry
        tel_resp = client.get("/telemetry", headers=_USER_HEADERS)
        assert tel_resp.status_code == 200
        events = tel_resp.json()
        assert len(events) >= 1

        # Find the event for evt-001 with null incident_id
        matching = [
            e for e in events
            if e["event_id"] == "evt-001" and e["incident_id"] is None
        ]
        assert len(matching) >= 1, (
            "Expected at least one telemetry event for evt-001 with incident_id=null"
        )


# ── EventRepository unit tests ────────────────────────────────────────────────

class TestEventRepository:
    def test_all_events_loaded(self, event_repo: EventRepository) -> None:
        """EventRepository should load all events from EventLogs.json."""
        logs = event_repo.get_all_event_logs()
        assert len(logs) >= 6, "Expected at least 6 event logs"

    def test_get_event_log_by_id(self, event_repo: EventRepository) -> None:
        """get_event_log_by_id should return the correct event log."""
        log = event_repo.get_event_log_by_id("evt-001")
        assert log is not None
        assert log.event_id == "evt-001"

    def test_get_event_lineage_healthy(self, event_repo: EventRepository) -> None:
        """evt-001 lineage should show all three stages present."""
        lineage = event_repo.get_event_lineage("evt-001")
        assert lineage is not None
        assert lineage.ingest_success is True
        assert lineage.index_success is True
        assert lineage.publish_success is True
        assert lineage.missing_audit_events == []
        assert lineage.publish_latency_seconds is not None
        assert lineage.publish_latency_sla_met is not None

    def test_get_event_lineage_missing_ingestion(self, event_repo: EventRepository) -> None:
        """evt-002 (MissingIngestionEvent) should show ingest_success=False."""
        lineage = event_repo.get_event_lineage("evt-002")
        assert lineage is not None
        assert lineage.ingest_success is False
        assert "IngestAuditEvent" in lineage.missing_audit_events

    def test_event_log_response_excludes_scenario_metadata(
        self, event_repo: EventRepository
    ) -> None:
        """EventLogResponse.from_event_log should exclude scenario_metadata."""
        from app.models.event_log import EventLogResponse
        log = event_repo.get_event_log_by_id("evt-001")
        assert log is not None
        response = EventLogResponse.from_event_log(log)
        # Verify scenario_metadata is not in the serialized response
        data = response.model_dump()
        assert "scenario_metadata" not in data
