"""
Pydantic models for investigation telemetry events.
≈ InvestigationTelemetryEvent.cs
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.root_cause import RootCause


class LlmUsageTelemetry(BaseModel):
    """Model identifier and token usage for a single LLM completion call."""
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_tokens: int = 0
    estimated_cost_usd: Optional[float] = None


class InvestigationResponseTelemetry(BaseModel):
    """Infrastructure and performance metadata for a single investigation response."""
    response_time_ms: int
    cached: bool
    confidence: str
    root_cause: RootCause
    llm_usage: Optional[LlmUsageTelemetry] = None


class InvestigationValidationTelemetry(BaseModel):
    """Correctness metadata comparing the LLM verdict against the ground-truth label."""
    expected_root_cause: Optional[RootCause] = None
    actual_root_cause: RootCause
    root_cause_match: Optional[bool] = None


class InvestigationTelemetryEvent(BaseModel):
    """
    Telemetry event emitted after each call to the investigation endpoint.
    Emitted by both the incident router and the events router.
    ≈ InvestigationTelemetryEvent.cs
    """
    telemetry_type: Literal["InvestigationCompleted"] = "InvestigationCompleted"
    timestamp: datetime
    incident_id: Optional[int] = None
    """The incident identifier used in the route. None for event-driven investigations
    that are not associated with an incident.
    ≈ InvestigationTelemetryEvent.IncidentId (int?) in C#."""
    event_id: str
    response: InvestigationResponseTelemetry
    validation: InvestigationValidationTelemetry
