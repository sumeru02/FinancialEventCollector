/// <summary>
/// Runs every incident scenario through the investigation pipeline and compares
/// the LLM's verdict against the human-authored ground-truth label stored in
/// IncidentTestMetadata.ExpectedRootCause.
///
/// Useful for regression testing the LLM prompt and for measuring overall
/// accuracy and cost across the full scenario suite.
/// </summary>
public interface IValidationService
{
    /// <summary>
    /// Executes the investigation pipeline for up to <paramref name="limit"/> incidents
    /// and returns a per-incident comparison of the expected vs. actual root cause,
    /// plus the aggregated LLM cost across all non-cached calls.
    /// The cache is always bypassed so every incident is sent directly to the LLM endpoint.
    /// </summary>
    /// <param name="limit">Maximum number of incidents to process.</param>
    /// <param name="ct">Cancellation token.</param>
    Task<ValidationRunResponse> RunAsync(int limit, CancellationToken ct = default);
}
