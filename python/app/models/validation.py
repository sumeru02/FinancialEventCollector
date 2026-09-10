"""
Pydantic models for the validation pipeline.
≈ dotnet/src/Models/ValidationModels.cs
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.models.root_cause import RootCause


class ValidationScenarioResult(BaseModel):
    """
    Investigation result for a single incident scenario, including the
    expected vs. actual root cause comparison.
    ≈ ValidationScenarioResult.cs
    """

    incident_id: int
    """The unique identifier of the incident."""

    scenario_name: Optional[str] = None
    """
    The scenario name from IncidentTestMetadata.scenario_name,
    e.g. "MissingIndexingEvent". None for unlabelled incidents.
    """

    expected_root_cause: Optional[RootCause] = None
    """Human-authored ground-truth root cause. None for unlabelled incidents."""

    actual_root_cause: RootCause
    """The root cause verdict returned by the LLM."""

    root_cause_match: Optional[bool] = None
    """
    True if the LLM matched the expected root cause, False if it did not.
    None when expected_root_cause is None (unlabelled incident).
    """

    confidence: str
    """LLM confidence level: HIGH, MEDIUM, or LOW."""

    from_cache: bool
    """True if the result was served from the in-memory cache; False if the LLM was called."""

    response_time_ms: int
    """Total elapsed time in milliseconds for this investigation."""

    estimated_cost_usd: Optional[float] = None
    """
    Estimated USD cost of the LLM call for this scenario.
    None when the result was served from cache or token counts were unavailable.
    """


class ValidationRunResponse(BaseModel):
    """
    Top-level response returned by ValidationService.run_async().
    ≈ ValidationRunResponse.cs
    """

    results: list[ValidationScenarioResult]
    """Per-incident investigation results with expected vs. actual root cause."""

    total_scenarios: int
    """Total number of incidents processed in this run."""

    labelled_scenarios: int
    """
    Number of incidents that carry a human-authored expected_root_cause label
    and therefore contribute to the accuracy metric.
    """

    correct_predictions: int
    """Number of labelled incidents where the LLM matched the expected root cause."""

    accuracy_percent: Optional[float] = None
    """
    Percentage of labelled scenarios where the LLM matched the expected root cause,
    rounded to one decimal place. None when no labelled scenarios exist.
    """

    total_cost_usd: float
    """
    Sum of estimated_cost_usd across all non-cached LLM calls made during this run,
    rounded to 6 decimal places. Zero when all results were served from cache.
    """
