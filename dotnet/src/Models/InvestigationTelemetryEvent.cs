/// <summary>
/// Telemetry event emitted by IncidentController or EventController after each call to the
/// investigation endpoint. Captures response performance and optional validation against
/// ground-truth labels stored on the incident or event.
/// </summary>
public record InvestigationTelemetryEvent
{
    /// <summary>
    /// Identifies the type of telemetry record. Always "InvestigationCompleted".
    /// </summary>
    public required string TelemetryType { get; init; }

    /// <summary>UTC timestamp of when the investigation completed.</summary>
    public required DateTimeOffset Timestamp { get; init; }

    /// <summary>
    /// The incident identifier used in the route (maps to Incident.IncidentId).
    /// Null for event-driven investigations that are not associated with an incident.
    /// </summary>
    public required int? IncidentId { get; init; }

    /// <summary>The pipeline EventId associated with the incident.</summary>
    public required string EventId { get; init; }

    /// <summary>Performance and LLM response metadata.</summary>
    public required InvestigationResponseTelemetry Response { get; init; }

    /// <summary>
    /// Correctness metadata comparing the LLM verdict against the ground-truth label.
    /// Fields are null when the incident has no expected root cause label.
    /// </summary>
    public required InvestigationValidationTelemetry Validation { get; init; }
}

/// <summary>
/// Infrastructure and performance metadata for a single investigation response.
/// </summary>
public record InvestigationResponseTelemetry
{
    /// <summary>True if the result was served from the in-memory cache; false if the LLM was called.</summary>
    public required bool Cached { get; init; }

    /// <summary>LLM confidence level: HIGH, MEDIUM, or LOW.</summary>
    public required string Confidence { get; init; }

    /// <summary>The root cause verdict returned by the LLM (or from cache).</summary>
    public required RootCause RootCause { get; init; }

    /// <summary>
    /// LLM model and token usage metadata. Null when the result was served from cache
    /// (no LLM call was made).
    /// </summary>
    public LlmUsageTelemetry? LlmUsage { get; init; }

    /// <summary>Total elapsed time in milliseconds, measured from before cache lookup to after result is returned.</summary>
    public required long ResponseTimeMs { get; init; }
}

/// <summary>
/// Model identifier, token usage, and estimated cost for a single LLM completion call.
/// Only present when the investigation was not served from cache.
/// </summary>
public record LlmUsageTelemetry
{
    /// <summary>The model identifier used, e.g. "claude-sonnet-4-6".</summary>
    public string? Model { get; init; }

    /// <summary>Number of tokens in the prompt sent to the LLM.</summary>
    public int? InputTokens { get; init; }

    /// <summary>Number of tokens in the completion returned by the LLM.</summary>
    public int? OutputTokens { get; init; }

    /// <summary>
    /// Number of prompt tokens served from the provider's prompt cache.
    /// Zero when prompt caching is not active.
    /// </summary>
    public int CachedTokens { get; init; }

    /// <summary>
    /// Estimated cost of this completion in USD, rounded to 2 decimal places.
    /// Calculated using claude-sonnet-4-6 pricing:
    /// $3.00 / 1M input tokens, $15.00 / 1M output tokens, $0.30 / 1M cache-read tokens.
    /// Null when token counts are unavailable.
    /// </summary>
    public double? EstimatedCostUsd { get; init; }
}

/// <summary>
/// Correctness metadata comparing the LLM verdict against the human-authored ground-truth label.
/// All nullable fields are null when the incident has no ExpectedRootCause label.
/// </summary>
public record InvestigationValidationTelemetry
{
    /// <summary>
    /// Human-authored ground-truth root cause. Null for unlabelled incidents.
    /// </summary>
    public RootCause? ExpectedRootCause { get; init; }

    /// <summary>The root cause returned by the LLM for this investigation.</summary>
    public required RootCause ActualRootCause { get; init; }

    /// <summary>
    /// True if the LLM matched the expected root cause, false if it did not.
    /// Null when ExpectedRootCause is null (unlabelled incident — excluded from accuracy metrics).
    /// </summary>
    public bool? RootCauseMatch { get; init; }
}
