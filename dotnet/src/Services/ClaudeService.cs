using System.Net.Http.Json;
using Microsoft.Extensions.Options;

/// <summary>
/// Anthropic Claude implementation of ILlmService.
/// Registered via AddHttpClient&lt;ILlmService, ClaudeService&gt; so the
/// HttpClient base address and auth headers are configured once in Program.cs.
/// </summary>
public class ClaudeService : ILlmService
{
    private readonly HttpClient             _http;
    private readonly ClaudeOptions          _options;
    private readonly ILogger<ClaudeService> _logger;

    public ClaudeService(
        HttpClient http,
        IOptions<ClaudeOptions> options,
        ILogger<ClaudeService> logger)
    {
        _http    = http;
        _options = options.Value;
        _logger  = logger;
    }

    /// <inheritdoc/>
    public async Task<LlmCompletionResult> CompleteAsync(string prompt, CancellationToken ct = default)
    {
        var body = new ClaudeRequest
        {
            Model     = _options.Model,
            MaxTokens = _options.MaxTokens,
            Messages  = [new ClaudeMessage { Role = "user", Content = prompt }]
        };

        _logger.LogDebug("Calling Claude model={Model} maxTokens={MaxTokens}", _options.Model, _options.MaxTokens);

        using var response = await _http.PostAsJsonAsync("v1/messages", body, ct);
        response.EnsureSuccessStatusCode();

        var result = await response.Content.ReadFromJsonAsync<ClaudeResponse>(ct);

        var text = result?.Content?.FirstOrDefault(c => c.Type == "text")?.Text;

        if (string.IsNullOrWhiteSpace(text))
            throw new InvalidOperationException("Claude returned an empty or missing text content block.");

        _logger.LogDebug(
            "Claude response: model={Model} inputTokens={InputTokens} outputTokens={OutputTokens} cachedTokens={CachedTokens}",
            result?.Model, result?.Usage?.InputTokens, result?.Usage?.OutputTokens, result?.Usage?.CacheReadTokens);

        return new LlmCompletionResult
        {
            Text         = text,
            Model        = result?.Model,
            InputTokens  = result?.Usage?.InputTokens,
            OutputTokens = result?.Usage?.OutputTokens,
            CachedTokens = result?.Usage?.CacheReadTokens ?? 0
        };
    }
}
