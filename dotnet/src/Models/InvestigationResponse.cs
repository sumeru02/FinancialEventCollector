using System.Text.Json.Serialization;

/// <summary>
/// Envelope returned by POST /events/{eventId}/investigations and
/// POST /incidents/{id}/investigations.
/// Wraps the LLM-generated InvestigationResult and adds
/// deterministically-computed fields so callers never need to parse
/// free-text fields to obtain structured data.
///
/// Field order reflects the natural reading flow:
///   1. Investigation  — what the LLM found (diagnosis)
///   2. EventContext   — structured pipeline lineage that corroborates the verdict
///   3. RecommendedAction — the action that follows from both
///   4. LlmUsage       — token counts and estimated cost for this call
/// </summary>
public record InvestigationResponse
{
    /// <summary>The structured LLM verdict for this incident.</summary>
    public required InvestigationResult Investigation { get; init; }

    /// <summary>
    /// Projected data lineage for the pipeline event that was investigated.
    /// Contains the per-stage success flags, missing audit events, and publish
    /// latency — the same evidence the LLM reasoned over — so callers can
    /// correlate the LLM's prose explanation with structured, machine-readable data
    /// without a separate GET /events/{eventId} round-trip.
    /// null when the event log cannot be resolved (should not occur in normal operation).
    /// </summary>
    public EventLineage? EventContext { get; init; }

    /// <summary>
    /// Singleton catalog service used to resolve the recommended action.
    /// Set after construction; excluded from serialization.
    /// </summary>
    [JsonIgnore]
    public RootCauseCatalogService? RootCauseCatalog { get; init; }

    /// <summary>
    /// Deterministic recommended action for the on-call engineer, derived from
    /// InvestigationResult.RootCause. This is policy — not LLM output —
    /// so it is computed here rather than inside the LLM deserialization record.
    /// Loaded from data/RootCauses.json via RootCauseCatalogService.
    /// </summary>
    public string RecommendedAction =>
        RootCauseCatalog?.GetRecommendedAction(Investigation.RootCause)
        ?? "Manual review required — evidence is ambiguous or contradictory.";

    /// <summary>
    /// Token usage and estimated cost for the LLM call that produced this result.
    /// null when the result was served from the in-memory cache (no LLM call was made).
    /// </summary>
    public LlmUsageTelemetry? LlmUsage { get; init; }
}
