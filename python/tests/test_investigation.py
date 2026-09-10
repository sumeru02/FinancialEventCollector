"""
Tests for InvestigationResponse and prompt_helper (no LLM calls required).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.models.investigation import InvestigationResponse, InvestigationResult
from app.models.root_cause import RootCause, get_recommended_action
from app.helpers.prompt_helper import build_investigation_prompt
from app.services.event_repository import EventRepository
from app.services.incident_data_service import IncidentDataService
from app.services.investigation_service import InvestigationService
from app.services.telemetry_store import TelemetryStore
from app.services.llm_service import LlmCompletionResult
from app.models.telemetry import LlmUsageTelemetry
from app.routers import incident_router, telemetry_router
from app import auth as auth_module
from app.config import Settings


@pytest.fixture(scope="module")
def event_repo() -> EventRepository:
    return EventRepository()


@pytest.fixture(scope="module")
def incident_svc() -> IncidentDataService:
    return IncidentDataService()


# ── HTTP test client fixtures for endpoint tests ───────────────────────────────

def _make_mock_llm_result(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cached_tokens: int = 20,
) -> LlmCompletionResult:
    """Returns a fake LlmCompletionResult with controllable token counts."""
    return LlmCompletionResult(
        text='{"rootCause": "AllAuditEventsPresent", "explanation": "All events present.", "confidence": "HIGH"}',
        model="claude-sonnet-4-6",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
    )


def _make_mock_investigation_svc(llm_result: LlmCompletionResult) -> InvestigationService:
    """
    Returns an InvestigationService whose investigate_async() is mocked to
    return a fixed InvestigationResult without calling the real LLM.
    """
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
def test_app_and_store():
    """
    Builds a minimal FastAPI test app with:
      - incident_router (POST /incidents/{id}/investigations, GET /incidents)
      - telemetry_router (GET /telemetry)
    All dependencies are overridden with in-process singletons; the
    InvestigationService is mocked so no real LLM calls are made.
    """
    # Fresh telemetry store per test so events don't bleed across tests
    store = TelemetryStore()

    llm_result = _make_mock_llm_result()
    mock_inv_svc = _make_mock_investigation_svc(llm_result)

    # Settings with known API keys
    settings = Settings()

    app = FastAPI()

    # Rate limiter (required by incident_router)
    from app.limiter import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(incident_router.router, prefix="/incidents", tags=["Incidents"])
    app.include_router(telemetry_router.router, prefix="/telemetry", tags=["Telemetry"])

    incident_data_svc = IncidentDataService()
    event_repository  = EventRepository()

    app.dependency_overrides[incident_router._get_incident_svc]      = lambda: incident_data_svc
    app.dependency_overrides[incident_router._get_event_repository]  = lambda: event_repository
    app.dependency_overrides[incident_router._get_investigation_svc] = lambda: mock_inv_svc
    app.dependency_overrides[incident_router._get_telemetry_store]   = lambda: store
    app.dependency_overrides[telemetry_router._get_telemetry_store]  = lambda: store
    app.dependency_overrides[auth_module._get_settings]              = lambda: settings

    client = TestClient(app, raise_server_exceptions=True)
    return client, store, mock_inv_svc


# ── Headers used in every authenticated request ────────────────────────────────
_USER_HEADERS  = {"X-Api-Key": "UserSecret"}
_ADMIN_HEADERS = {"X-Api-Key": "AdminSecret"}


class TestInvestigationResponse:
    def test_recommended_action_all_present(self) -> None:
        """AllAuditEventsPresent should recommend transferring to Downstream team."""
        result = InvestigationResult(
            root_cause=RootCause.ALL_AUDIT_EVENTS_PRESENT,
            explanation="All events present.",
            confidence="HIGH",
        )
        resp = InvestigationResponse(investigation=result, publish_latency_seconds=120.0)
        assert "Downstream" in resp.recommended_action

    def test_recommended_action_missing_ingestion(self) -> None:
        """MissingIngestionAuditEvent should recommend re-ingestion."""
        result = InvestigationResult(
            root_cause=RootCause.MISSING_INGESTION_AUDIT_EVENT,
            explanation="No ingest event.",
            confidence="HIGH",
        )
        resp = InvestigationResponse(investigation=result, publish_latency_seconds=None)
        assert "re-ingest" in resp.recommended_action.lower()

    def test_recommended_action_sla_breach(self) -> None:
        """PublishLatencyExceedsSLA should mention SLA threshold."""
        result = InvestigationResult(
            root_cause=RootCause.PUBLISH_LATENCY_EXCEEDS_SLA,
            explanation="Latency exceeded.",
            confidence="HIGH",
        )
        resp = InvestigationResponse(investigation=result, publish_latency_seconds=1200.0)
        assert "SLA" in resp.recommended_action

    def test_all_root_causes_have_recommended_action(self) -> None:
        """Every RootCause value should produce a non-empty recommended action."""
        for rc in RootCause:
            action = get_recommended_action(rc)
            assert action, f"Empty recommended_action for {rc}"

    def test_event_context_publish_latency_takes_precedence(self) -> None:
        """When event_context is provided, publish_latency_seconds should come from it."""
        from app.models.event_log import EventLineage
        lineage = EventLineage(
            event_id="evt-001",
            event_source="InvoicingService",
            ingest_success=True,
            index_success=True,
            publish_success=True,
            audit_events_present=["IngestAuditEvent", "IndexAuditEvent", "PublishAuditEvent"],
            missing_audit_events=[],
            publish_latency_seconds=69.0,
            publish_latency_sla_met=True,
        )
        result = InvestigationResult(
            root_cause=RootCause.ALL_AUDIT_EVENTS_PRESENT,
            explanation="All events present.",
            confidence="HIGH",
        )
        resp = InvestigationResponse(investigation=result, event_context=lineage)
        assert resp.event_context is lineage
        assert resp.publish_latency_seconds == 69.0


class TestPromptHelper:
    def test_prompt_contains_event_id(self, event_repo: EventRepository) -> None:
        """The built prompt should contain the event's EventId."""
        event_log = event_repo.get_all_event_logs()[0]
        prompt = build_investigation_prompt(event_log)
        assert event_log.event_id in prompt

    def test_prompt_contains_sla_threshold(self, event_repo: EventRepository) -> None:
        """The built prompt should contain the SLA threshold (15 minutes)."""
        event_log = event_repo.get_all_event_logs()[0]
        prompt = build_investigation_prompt(event_log)
        assert "15" in prompt

    def test_prompt_contains_merged_event_log(self, event_repo: EventRepository) -> None:
        """The built prompt should contain the MERGED EVENT LOG section."""
        event_log = event_repo.get_all_event_logs()[0]
        prompt = build_investigation_prompt(event_log)
        assert "MERGED EVENT LOG" in prompt

    def test_prompt_contains_llm_schema(self, event_repo: EventRepository) -> None:
        """The built prompt should contain the LLM response schema."""
        event_log = event_repo.get_all_event_logs()[0]
        prompt = build_investigation_prompt(event_log)
        assert "rootCause" in prompt
        assert "confidence" in prompt


# ── Endpoint tests: llm_usage, telemetry fields, and ordering ─────────────────

class TestInvestigationEndpointLlmUsage:
    """
    Tests that POST /incidents/{id}/investigations returns an llm_usage object
    with the expected fields (Step 4 of the parity migration).
    """

    def test_investigation_response_includes_llm_usage(
        self, test_app_and_store
    ) -> None:
        """
        POST /incidents/{id}/investigations should return an llm_usage object
        containing at minimum: input_tokens, output_tokens, cached_tokens,
        and estimated_cost_usd.
        """
        client, _store, _mock_svc = test_app_and_store

        # Use the first available incident
        incidents_resp = client.get("/incidents", headers=_USER_HEADERS)
        assert incidents_resp.status_code == 200
        incident_id = incidents_resp.json()[0]["incidentId"]

        resp = client.post(
            f"/incidents/{incident_id}/investigations",
            headers=_USER_HEADERS,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "llm_usage" in body, "Response must contain 'llm_usage' key"

        llm_usage = body["llm_usage"]
        assert llm_usage is not None, "llm_usage must not be null"
        assert "input_tokens" in llm_usage, "llm_usage must contain 'input_tokens'"
        assert "output_tokens" in llm_usage, "llm_usage must contain 'output_tokens'"
        assert "cached_tokens" in llm_usage, "llm_usage must contain 'cached_tokens'"
        assert "estimated_cost_usd" in llm_usage, "llm_usage must contain 'estimated_cost_usd'"

        # Verify the values are of the expected types
        assert isinstance(llm_usage["input_tokens"], int)
        assert isinstance(llm_usage["output_tokens"], int)
        assert isinstance(llm_usage["cached_tokens"], int)
        # estimated_cost_usd may be float or None
        assert llm_usage["estimated_cost_usd"] is None or isinstance(
            llm_usage["estimated_cost_usd"], float
        )

    def test_investigation_response_includes_event_context(
        self, test_app_and_store
    ) -> None:
        """
        POST /incidents/{id}/investigations should return an event_context object
        with lineage fields (ingest_success, index_success, publish_success, etc.).
        ≈ InvestigationResponse.EventContext in C#.
        """
        client, _store, _mock_svc = test_app_and_store

        incidents_resp = client.get("/incidents", headers=_USER_HEADERS)
        assert incidents_resp.status_code == 200
        incident_id = incidents_resp.json()[0]["incidentId"]

        resp = client.post(
            f"/incidents/{incident_id}/investigations",
            headers=_USER_HEADERS,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "event_context" in body, "Response must contain 'event_context' key"

        ctx = body["event_context"]
        assert ctx is not None, "event_context must not be null"
        assert "event_id" in ctx
        assert "ingest_success" in ctx
        assert "index_success" in ctx
        assert "publish_success" in ctx
        assert "audit_events_present" in ctx
        assert "missing_audit_events" in ctx


class TestTelemetryLlmUsageFields:
    """
    Tests that GET /telemetry returns events whose llm_usage contains
    cached_tokens (int) and estimated_cost_usd (float or null) — Step 2.
    """

    def test_telemetry_event_llm_usage_has_cached_tokens_and_estimated_cost(
        self, test_app_and_store
    ) -> None:
        """
        After calling POST /incidents/{id}/investigations, GET /telemetry
        should return at least one event whose response.llm_usage contains
        cached_tokens (int) and estimated_cost_usd (float or null).
        """
        client, _store, _mock_svc = test_app_and_store

        incidents_resp = client.get("/incidents", headers=_USER_HEADERS)
        assert incidents_resp.status_code == 200
        incident_id = incidents_resp.json()[0]["incidentId"]

        # Trigger an investigation to populate telemetry
        inv_resp = client.post(
            f"/incidents/{incident_id}/investigations",
            headers=_USER_HEADERS,
        )
        assert inv_resp.status_code == 200

        # Fetch telemetry
        tel_resp = client.get("/telemetry", headers=_USER_HEADERS)
        assert tel_resp.status_code == 200

        events = tel_resp.json()
        assert len(events) >= 1, "At least one telemetry event must be present"

        # Find the event for our incident
        matching = [e for e in events if e["incident_id"] == incident_id]
        assert len(matching) >= 1, f"No telemetry event found for incident_id={incident_id}"

        llm_usage = matching[0]["response"]["llm_usage"]
        assert llm_usage is not None, "response.llm_usage must not be null"

        assert "cached_tokens" in llm_usage, "llm_usage must contain 'cached_tokens'"
        assert isinstance(llm_usage["cached_tokens"], int), (
            f"cached_tokens must be int, got {type(llm_usage['cached_tokens'])}"
        )

        assert "estimated_cost_usd" in llm_usage, "llm_usage must contain 'estimated_cost_usd'"
        assert llm_usage["estimated_cost_usd"] is None or isinstance(
            llm_usage["estimated_cost_usd"], float
        ), f"estimated_cost_usd must be float or null, got {type(llm_usage['estimated_cost_usd'])}"


class TestTelemetryDescendingOrder:
    """
    Tests that GET /telemetry returns events in descending (newest-first) order
    — Step 6 of the parity migration.
    """

    def test_telemetry_returns_events_newest_first(
        self, test_app_and_store
    ) -> None:
        """
        After calling POST /incidents/{id}/investigations twice, GET /telemetry
        should return events with the first event having a timestamp >=
        the second event's timestamp (newest-first ordering).
        """
        client, _store, _mock_svc = test_app_and_store

        incidents_resp = client.get("/incidents", headers=_USER_HEADERS)
        assert incidents_resp.status_code == 200
        incidents = incidents_resp.json()
        assert len(incidents) >= 2, "Need at least 2 incidents for ordering test"

        # Call investigations for two different incidents to generate two events
        id_1 = incidents[0]["incidentId"]
        id_2 = incidents[1]["incidentId"]

        resp1 = client.post(
            f"/incidents/{id_1}/investigations",
            headers=_USER_HEADERS,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            f"/incidents/{id_2}/investigations",
            headers=_USER_HEADERS,
        )
        assert resp2.status_code == 200

        # Fetch telemetry
        tel_resp = client.get("/telemetry", headers=_USER_HEADERS)
        assert tel_resp.status_code == 200

        events = tel_resp.json()
        assert len(events) >= 2, "At least two telemetry events must be present"

        # Verify descending order: first event timestamp >= second event timestamp
        ts_first  = events[0]["timestamp"]
        ts_second = events[1]["timestamp"]
        assert ts_first >= ts_second, (
            f"Telemetry events must be newest-first: "
            f"events[0].timestamp={ts_first!r} should be >= events[1].timestamp={ts_second!r}"
        )
