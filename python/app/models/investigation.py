"""
Pydantic models for InvestigationResult and InvestigationResponse.
≈ InvestigationResult.cs + InvestigationResponse.cs
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, computed_field
from pydantic import PrivateAttr

from app.models.root_cause import RootCause, get_recommended_action
from app.models.telemetry import LlmUsageTelemetry


class InvestigationResult(BaseModel):
    """
    Strongly-typed deserialization of the LLM's JSON investigation response.
    Contains only the three fields the model is asked to produce.
    All three fields are required — mirrors the C# `required` keyword on
    InvestigationResult.cs so that a malformed LLM response raises a clear
    ValidationError rather than silently producing a None root_cause.
    ≈ InvestigationResult.cs
    """
    root_cause: RootCause
    explanation: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]

    model_config = {"populate_by_name": True}


class InvestigationResponse(BaseModel):
    """
    Envelope returned by POST /events/{eventId}/investigations and
    POST /incidents/{id}/investigations.
    Wraps the LLM-generated InvestigationResult and adds deterministically-computed fields.

    Field order reflects the natural reading flow:
      1. investigation  — what the LLM found (diagnosis)
      2. event_context  — structured pipeline lineage that corroborates the verdict
      3. recommended_action — the action that follows from both
      4. llm_usage      — token counts and estimated cost for this call

    ≈ InvestigationResponse.cs
    """
    investigation: InvestigationResult

    # Private attributes hold the values that are exposed via computed_field.
    # Using Any to avoid circular import issues with EventLineage.
    _event_context: Optional[Any] = PrivateAttr(default=None)
    _publish_latency_seconds: Optional[float] = PrivateAttr(default=None)
    _llm_usage: Optional[LlmUsageTelemetry] = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        event_context: Optional[Any] = None,
        publish_latency_seconds: Optional[float] = None,
        llm_usage: Optional[LlmUsageTelemetry] = None,
        **data,
    ):
        super().__init__(**data)
        self._event_context = event_context
        # publish_latency_seconds is kept for backward compatibility;
        # when event_context is provided it is ignored in favour of
        # event_context.publish_latency_seconds.
        self._publish_latency_seconds = publish_latency_seconds
        self._llm_usage = llm_usage

    @computed_field  # type: ignore[misc]
    @property
    def event_context(self) -> Optional[Any]:
        """
        Projected data lineage for the pipeline event that was investigated.
        Contains the per-stage success flags, missing audit events, and publish
        latency — the same evidence the LLM reasoned over — so callers can
        correlate the LLM's prose explanation with structured, machine-readable data
        without a separate GET /events/{eventId} round-trip.
        null when the event log cannot be resolved (should not occur in normal operation).
        ≈ InvestigationResponse.EventContext in C#.
        """
        return self._event_context

    @computed_field  # type: ignore[misc]
    @property
    def publish_latency_seconds(self) -> Optional[float]:
        """
        End-to-end publish latency in seconds.
        Derived from event_context when available; falls back to the value
        supplied directly (legacy path).
        ≈ InvestigationResponse.PublishLatencySeconds in C#.
        """
        if self._event_context is not None:
            return self._event_context.publish_latency_seconds
        return self._publish_latency_seconds

    @computed_field  # type: ignore[misc]
    @property
    def recommended_action(self) -> str:
        """
        Deterministic recommended action derived from root_cause.
        Loaded from data/root-causes.json via ROOT_CAUSE_CATALOG.
        ≈ InvestigationResponse.RecommendedAction in C#.
        """
        return get_recommended_action(self.investigation.root_cause)

    @computed_field  # type: ignore[misc]
    @property
    def llm_usage(self) -> Optional[LlmUsageTelemetry]:
        """
        LLM token usage and estimated cost for this investigation call.
        ≈ InvestigationResponse.LlmUsage in C#.
        """
        return self._llm_usage
