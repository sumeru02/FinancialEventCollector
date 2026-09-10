/// <summary>
/// Top-level response returned by IValidationService.RunAsync.
/// </summary>
public record ValidationRunResponse
{
    /// <summary>Per-incident investigation results with expected vs. actual root cause.</summary>
    public required IReadOnlyList<ValidationScenarioResult> Results { get; init; }

    /// <summary>Total number of incidents processed in this run.</summary>
    public required int TotalScenarios { get; init; }

    /// <summary>
    /// Number of incidents that carry a human-authored ExpectedRootCause label
    /// and therefore contribute to the accuracy metric.
    /// </summary>
    public required int LabelledScenarios { get; init; }

    /// <summary>Number of labelled incidents where the LLM matched the expected root cause.</summary>
    public required int CorrectPredictions { get; init; }

    /// <summary>
    /// Percentage of labelled scenarios where the LLM matched the expected root cause,
    /// rounded to one decimal place. null when no labelled scenarios exist.
    /// </summary>
    public double? AccuracyPercent { get; init; }

    /// <summary>
    /// Sum of ValidationScenarioResult.EstimatedCostUsd across all non-cached
    /// LLM calls made during this run, rounded to 6 decimal places.
    /// Zero when all results were served from cache.
    /// </summary>
    public required double TotalCostUsd { get; init; }
}

/// <summary>
/// Investigation result for a single incident scenario, including the
/// expected vs. actual root cause comparison.
/// </summary>
public record ValidationScenarioResult
{
    /// <summary>The unique identifier of the incident.</summary>
    public required int IncidentId { get; init; }

    /// <summary>
    /// The scenario name from IncidentTestMetadata.ScenarioName,
    /// e.g. "MissingIndexingEvent". null for unlabelled incidents.
    /// </summary>
    public string? ScenarioName { get; init; }

    /// <summary>
    /// Human-authored ground-truth root cause. null for unlabelled incidents.
    /// </summary>
    public RootCause? ExpectedRootCause { get; init; }

    /// <summary>The root cause verdict returned by the LLM.</summary>
    public required RootCause ActualRootCause { get; init; }

    /// <summary>
    /// true if the LLM matched the expected root cause, false if it did not.
    /// null when ExpectedRootCause is null (unlabelled incident).
    /// </summary>
    public bool? RootCauseMatch { get; init; }

    /// <summary>LLM confidence level: HIGH, MEDIUM, or LOW.</summary>
    public required string Confidence { get; init; }

    /// <summary>True if the result was served from the in-memory cache; false if the LLM was called.</summary>
    public required bool FromCache { get; init; }

    /// <summary>Total elapsed time in milliseconds for this investigation.</summary>
    public required long ResponseTimeMs { get; init; }

    /// <summary>
    /// Estimated USD cost of the LLM call for this scenario.
    /// null when the result was served from cache or token counts were unavailable.
    /// </summary>
    public double? EstimatedCostUsd { get; init; }
}
