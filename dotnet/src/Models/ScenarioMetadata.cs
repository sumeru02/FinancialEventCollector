/// <summary>
/// Optional test scenario metadata attached to each EventLog in data/EventLogs.json.
/// Describes the diagnostic pattern the scenario exercises and provides ground-truth labels
/// for LLM evaluation and regression testing.
/// Not present on real production events.
/// </summary>
public record ScenarioMetadata
{
    /// <summary>
    /// Identifies the specific diagnostic pattern this scenario exercises,
    /// e.g. "AllAuditEventsPresent" or "MissingIndexingEvent".
    /// Mirrors the RootCause enum values.
    /// </summary>
    public required string ScenarioName { get; init; }

    /// <summary>
    /// Human-readable description of what this scenario represents and why it is interesting.
    /// </summary>
    public string? ScenarioDescription { get; init; }

    /// <summary>
    /// Human-authored ground-truth root cause for this scenario.
    /// Used to assert correctness of the LLM's InvestigationResult.RootCause
    /// in integration tests. Null for events that have not yet been labelled.
    /// </summary>
    public RootCause? ExpectedRootCause { get; init; }

    /// <summary>
    /// Human-authored explanation of why ExpectedRootCause was assigned.
    /// Null for events that have not yet been labelled.
    /// </summary>
    public string? ExpectedExplanation { get; init; }
}
