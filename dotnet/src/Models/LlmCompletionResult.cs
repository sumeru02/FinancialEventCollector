/// <summary>
/// Provider-agnostic result returned by ILlmService.CompleteAsync.
/// Carries the raw text response alongside model and token usage metadata
/// for telemetry and cost tracking.
/// </summary>
public record LlmCompletionResult
{
    /// <summary>The raw text content returned by the LLM.</summary>
    public required string Text { get; init; }

    /// <summary>
    /// The model identifier used for this completion, e.g. "claude-sonnet-4-6".
    /// Null when the provider does not return the model in the response.
    /// </summary>
    public string? Model { get; init; }

    /// <summary>
    /// Number of tokens in the prompt sent to the LLM.
    /// Null when the provider does not return token usage (e.g. on a cache hit).
    /// </summary>
    public int? InputTokens { get; init; }

    /// <summary>
    /// Number of tokens in the completion returned by the LLM.
    /// Null when the provider does not return token usage (e.g. on a cache hit).
    /// </summary>
    public int? OutputTokens { get; init; }

    /// <summary>
    /// Number of prompt tokens served from the provider's prompt cache (e.g. Anthropic cache_read_input_tokens).
    /// Zero when prompt caching is not active or the provider does not support it.
    /// </summary>
    public int CachedTokens { get; init; } = 0;
}
