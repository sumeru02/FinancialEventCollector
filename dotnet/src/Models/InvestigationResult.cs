/// <summary>
/// Strongly-typed deserialization of the LLM's JSON investigation response.
/// Contains only the three fields the model is asked to produce; all
/// deterministic / policy fields live in InvestigationResponse.
/// Property names use camelCase to match the JSON schema the prompt specifies.
/// </summary>
public record InvestigationResult
{
    /// <summary>
    /// The specific audit-event gap (or absence of gap) identified by the LLM.
    /// One of the RootCause enum values.
    /// </summary>
    public required RootCause RootCause { get; init; }

    /// <summary>
    /// 1-2 sentence explanation of what the audit log shows and why this root cause was chosen.
    /// </summary>
    public required string Explanation { get; init; }

    /// <summary>
    /// Confidence level based on whether null-eventId entries drove the verdict.
    /// One of: HIGH | MEDIUM | LOW.
    /// </summary>
    public required string Confidence { get; init; }
}
