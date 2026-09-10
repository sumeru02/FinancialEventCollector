"""
Integration tests for ValidationService.

Mirrors the pattern in dotnet/tests/IntegrationTests.cs:
  - Module-scoped fixture builds the real service stack (no mocks).
  - A single integration test calls ValidationService.run_async(limit=10),
    logs the full response, then asserts root_cause_match is True for every
    labelled incident.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import Settings
from app.services.event_repository import EventRepository
from app.services.incident_data_service import IncidentDataService
from app.services.investigation_service import InvestigationService
from app.services.llm_service import ClaudeService
from app.services.validation_service import ValidationService
from app.models.validation import ValidationRunResponse, ValidationScenarioResult
from app.models.root_cause import RootCause
from app.routers import validation_router
from app import auth as auth_module

logger = logging.getLogger(__name__)


# ── Module-scoped fixture — equivalent to [ClassInitialize] in TestBase ────────

@pytest.fixture(scope="module")
def validation_svc() -> ValidationService:
    """
    Builds the real ValidationService backed by the shared Incidents.json data
    and a live ClaudeService (API key must be present in env / config).
    ≈ TestBase.InitialiseService()
    """
    settings          = Settings()
    incident_data     = IncidentDataService()
    event_repo        = EventRepository()
    claude_svc        = ClaudeService(settings)
    investigation_svc = InvestigationService(
        claude_svc,
        cache_enabled=settings.cache.enabled,
        ttl_hours=settings.cache.ttl_hours,
        max_prompt_chars=settings.claude.max_prompt_chars,
    )
    return ValidationService(incident_data, investigation_svc, event_repo)


# ── Validation integration tests ───────────────────────────────────────────────

class TestValidationIntegration:
    """
    Integration tests that exercise the full validation pipeline.
    ≈ IntegrationTests in dotnet/tests/IntegrationTests.cs
    """

    async def test_validation_run_incidents_root_cause_match_is_true(
        self,
        validation_svc: ValidationService,
    ) -> None:
        """
        Runs the full validation pipeline via ValidationService and asserts that
        every labelled incident's root cause is correctly identified by the LLM
        (root_cause_match == True).
        ≈ IntegrationTests.ValidationRun_Incidents_RootCauseMatchIsTrue()
        """
        response: ValidationRunResponse = await validation_svc.run_async(limit=10)

        # Log the full response (≈ response.Log() in C#)
        logger.info(
            "ValidationRunResponse:\n%s",
            json.dumps(response.model_dump(mode="json"), indent=2, default=str),
        )

        labelled_results = [r for r in response.results if r.root_cause_match is not None]

        for scenario in labelled_results:
            assert scenario.root_cause_match is True, (
                f"root_cause_match failed for incident_id={scenario.incident_id} "
                f"scenario={scenario.scenario_name}: "
                f"expected={scenario.expected_root_cause}, "
                f"actual={scenario.actual_root_cause}"
            )


# ── Unit tests for the validation HTTP endpoint ────────────────────────────────

def _make_mock_validation_svc(num_results: int = 5) -> ValidationService:
    """
    Returns a ValidationService whose run_async() is mocked to return a
    fixed ValidationRunResponse with *num_results* scenario results.
    No real LLM calls are made.
    """
    mock_svc = MagicMock(spec=ValidationService)

    results = [
        ValidationScenarioResult(
            incident_id=i + 1,
            scenario_name=f"Scenario{i + 1}",
            expected_root_cause=RootCause.ALL_AUDIT_EVENTS_PRESENT,
            actual_root_cause=RootCause.ALL_AUDIT_EVENTS_PRESENT,
            root_cause_match=True,
            confidence="HIGH",
            from_cache=False,
            response_time_ms=10,
            estimated_cost_usd=0.0001,
        )
        for i in range(num_results)
    ]

    mock_svc.run_async = AsyncMock(
        return_value=ValidationRunResponse(
            results=results,
            total_scenarios=num_results,
            labelled_scenarios=num_results,
            correct_predictions=num_results,
            accuracy_percent=100.0,
            total_cost_usd=0.0005,
        )
    )
    return mock_svc


@pytest.fixture()
def validation_test_client():
    """
    Builds a minimal FastAPI test app with the validation_router mounted and
    all dependencies overridden with mocks so no real LLM calls are made.
    """
    settings = Settings()
    mock_svc = _make_mock_validation_svc(num_results=5)

    app = FastAPI()

    from app.limiter import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(validation_router.router, prefix="/validation", tags=["Validation"])

    app.dependency_overrides[validation_router._get_validation_svc] = lambda: mock_svc
    app.dependency_overrides[auth_module._get_settings]             = lambda: settings

    return TestClient(app, raise_server_exceptions=True)


_ADMIN_HEADERS = {"X-Api-Key": "AdminSecret"}


class TestValidationRunLimitQueryParam:
    """
    Tests that POST /validation/run accepts `limit` as a query parameter
    (not a request body) — Step 7 of the parity migration.
    """

    def test_validation_run_accepts_limit_as_query_param(
        self, validation_test_client: TestClient
    ) -> None:
        """
        POST /validation/run?limit=5 should return HTTP 200 and at most 5
        results, confirming that `limit` is accepted as a query parameter.
        """
        resp = validation_test_client.post(
            "/validation/run?limit=5",
            headers=_ADMIN_HEADERS,
        )
        assert resp.status_code == 200, (
            f"Expected 200 OK, got {resp.status_code}: {resp.text}"
        )

        body = resp.json()
        assert "results" in body, "Response must contain 'results' key"
        assert len(body["results"]) <= 5, (
            f"Response must contain at most 5 results, got {len(body['results'])}"
        )
