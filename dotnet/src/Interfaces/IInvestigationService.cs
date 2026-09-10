/// <summary>
/// Domain-specific service that orchestrates an event log investigation:
/// builds the LLM prompt via PromptHelper, sends it to the configured
/// ILlmService, and deserializes the response into a
/// strongly-typed InvestigationResult.
/// Results are cached in memory by EventId to avoid redundant LLM calls.
/// </summary>
public interface IInvestigationService
{
    /// <summary>
    /// Investigates the pipeline event described by <paramref name="eventLog"/> and
    /// returns a structured verdict from the LLM (or from cache if previously investigated).
    /// </summary>
    /// <param name="eventLog">The raw event log record containing the EventId, audit events, and worker logs to investigate.</param>
    /// <param name="bypassCache">When true, skips the in-memory cache and always calls the LLM.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>
    /// A tuple containing:
    /// <list type="bullet">
    ///   <item>InvestigationResult — the structured LLM verdict.</item>
    ///   <item>FromCache — true if served from cache, false if the LLM was called.</item>
    ///   <item>LlmCompletionResult — model and token usage metadata; null on a cache hit.</item>
    /// </list>
    /// </returns>
    Task<(InvestigationResult Result, bool FromCache, LlmCompletionResult? LlmMetadata)> InvestigateAsync(
        EventLog eventLog,
        bool bypassCache = false,
        CancellationToken ct = default);
}
