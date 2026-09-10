/// <summary>
/// Provider-agnostic interface for sending a prompt to a large language model
/// and receiving a raw text response.
/// <para>
/// Implementations: ClaudeService (Anthropic), OpenAiService (future), etc.
/// Switch providers in Program.cs by changing which implementation is registered
/// — no other code changes required.
/// </para>
/// </summary>
public interface ILlmService
{
    /// <summary>
    /// Sends <paramref name="prompt"/> to the configured LLM and returns
    /// the completion result including the raw text, model identifier, and token usage.
    /// </summary>
    /// <param name="prompt">The full prompt string to send.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>
    /// An LlmCompletionResult containing the text response, model name,
    /// and input/output token counts for telemetry and cost tracking.
    /// </returns>
    Task<LlmCompletionResult> CompleteAsync(string prompt, CancellationToken ct = default);
}
