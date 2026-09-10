using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// Orchestrates an incident investigation by:
/// <list type="number">
///   <item>Checking the in-memory cache for a previously computed result.</item>
///   <item>Building the LLM prompt via the static PromptHelper on a cache miss.</item>
///   <item>Sending the prompt to the configured ILlmService.</item>
///   <item>Deserializing the raw JSON response into a typed InvestigationResult.</item>
///   <item>Caching the result for subsequent requests for the same incident.</item>
/// </list>
/// </summary>
public class InvestigationService : IInvestigationService
{
    /// <summary>
    /// The prompt instructs Claude to respond with camelCase JSON keys.
    /// Case-insensitive matching handles any minor casing variation from the LLM.
    /// JsonStringEnumConverter maps the string enum value (e.g. "MissingIngestionAuditEvent")
    /// to the RootCause enum during LLM response deserialization.
    /// </summary>
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        Converters = { new JsonStringEnumConverter() }
    };

    private readonly ILlmService                   _llm;
    private readonly IMemoryCache                  _cache;
    private readonly CacheOptions                  _cacheOptions;
    private readonly ClaudeOptions                 _claudeOptions;
    private readonly ILogger<InvestigationService> _logger;

    public InvestigationService(
        ILlmService llm,
        IMemoryCache cache,
        IOptions<CacheOptions> cacheOptions,
        IOptions<ClaudeOptions> claudeOptions,
        ILogger<InvestigationService> logger)
    {
        _llm           = llm;
        _cache         = cache;
        _cacheOptions  = cacheOptions.Value;
        _claudeOptions = claudeOptions.Value;
        _logger        = logger;
    }

    /// <inheritdoc/>
    public async Task<(InvestigationResult Result, bool FromCache, LlmCompletionResult? LlmMetadata)> InvestigateAsync(
        EventLog eventLog,
        bool bypassCache = false,
        CancellationToken ct = default)
    {
        var cacheKey = $"investigation:event:{eventLog.EventId}";

        if (!bypassCache && _cacheOptions.Enabled &&
            _cache.TryGetValue(cacheKey, out InvestigationResult? cached) && cached is not null)
        {
            _logger.LogInformation("Cache HIT for EventId={EventId}", eventLog.EventId);
            return (cached, FromCache: true, LlmMetadata: null);
        }

        // 1. Build prompt — pure static helper, no injection needed
        var prompt = PromptHelper.BuildInvestigationPrompt(eventLog, _claudeOptions.MaxPromptChars);

        _logger.LogInformation(
            "Cache MISS — starting LLM investigation for EventId={EventId} ScenarioName={ScenarioName}",
            eventLog.EventId, eventLog.ScenarioMetadata?.ScenarioName ?? "N/A");

        // 2. Call the LLM — provider determined by which ILlmService is registered
        var llmCompletion = await _llm.CompleteAsync(prompt, ct);

        _logger.LogDebug("LLM raw response for EventId={EventId}: {LlmResponse}", eventLog.EventId, llmCompletion.Text);

        // 3. Strip markdown code fences if the LLM wrapped the JSON in ```json ... ```
        var json = llmCompletion.Text.Trim();
        if (json.StartsWith("```", StringComparison.Ordinal))
        {
            var firstNewline = json.IndexOf('\n');
            if (firstNewline >= 0)
                json = json[(firstNewline + 1)..];

            if (json.EndsWith("```", StringComparison.Ordinal))
                json = json[..^3].TrimEnd();
        }

        // 4. Deserialize the structured JSON verdict
        var result = JsonSerializer.Deserialize<InvestigationResult>(json, JsonOptions);

        if (result is null)
            throw new InvalidOperationException(
                $"LLM response could not be deserialized for EventId={eventLog.EventId}. Raw: {llmCompletion.Text}");

        _logger.LogInformation(
            "Investigation complete for EventId={EventId}: RootCause={RootCause} Confidence={Confidence} Model={Model} InputTokens={InputTokens} OutputTokens={OutputTokens}",
            eventLog.EventId, result.RootCause, result.Confidence,
            llmCompletion.Model, llmCompletion.InputTokens, llmCompletion.OutputTokens);

        // 5. Cache the result for subsequent requests (only when caching is enabled and not bypassed)
        if (!bypassCache && _cacheOptions.Enabled)
        {
            var entryOptions = new MemoryCacheEntryOptions
            {
                AbsoluteExpirationRelativeToNow = TimeSpan.FromHours(_cacheOptions.TtlHours),
                Priority = CacheItemPriority.Normal
            };
            _cache.Set(cacheKey, result, entryOptions);
        }

        return (result, FromCache: false, LlmMetadata: llmCompletion);
    }
}
