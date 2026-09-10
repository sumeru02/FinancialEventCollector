using System.Text.Json.Serialization;

/// <summary>
/// Request body sent to the Anthropic Messages API (POST /v1/messages).
/// </summary>
public class ClaudeRequest
{
    [JsonPropertyName("model")]
    public string Model { get; set; } = string.Empty;

    [JsonPropertyName("max_tokens")]
    public int MaxTokens { get; set; }

    [JsonPropertyName("messages")]
    public IReadOnlyList<ClaudeMessage> Messages { get; set; } = [];
}

/// <summary>
/// A single turn in the Anthropic Messages API conversation.
/// </summary>
public class ClaudeMessage
{
    [JsonPropertyName("role")]
    public string Role { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;
}

/// <summary>
/// Top-level response envelope returned by the Anthropic Messages API.
/// </summary>
public class ClaudeResponse
{
    [JsonPropertyName("model")]
    public string? Model { get; set; }

    [JsonPropertyName("content")]
    public IReadOnlyList<ClaudeContentBlock>? Content { get; set; }

    [JsonPropertyName("usage")]
    public ClaudeUsage? Usage { get; set; }
}

/// <summary>
/// Token usage reported by the Anthropic Messages API for a single completion.
/// CacheReadTokens and CacheCreationTokens are only present when
/// prompt caching is active on the Anthropic side.
/// </summary>
public class ClaudeUsage
{
    [JsonPropertyName("input_tokens")]
    public int InputTokens { get; set; }

    [JsonPropertyName("output_tokens")]
    public int OutputTokens { get; set; }

    /// <summary>Tokens read from the Anthropic prompt cache (billed at a reduced rate).</summary>
    [JsonPropertyName("cache_read_input_tokens")]
    public int CacheReadTokens { get; set; }

    /// <summary>Tokens written to the Anthropic prompt cache on this request.</summary>
    [JsonPropertyName("cache_creation_input_tokens")]
    public int CacheCreationTokens { get; set; }
}

/// <summary>
/// A single content block inside a ClaudeResponse.
/// The type field is typically "text" for plain-text completions.
/// </summary>
public class ClaudeContentBlock
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}

/// <summary>
/// Configuration for the Anthropic Claude API.
/// Bind from appsettings.json under the "Claude" section.
/// </summary>
public class ClaudeOptions
{
    public const string SectionName = "Claude";

    /// <summary>Anthropic API key (x-api-key header).</summary>
    public string ApiKey { get; set; } = string.Empty;

    /// <summary>Model identifier, e.g. "claude-sonnet-4-6".</summary>
    public string Model { get; set; } = "claude-sonnet-4-6";

    /// <summary>Maximum tokens to generate in the response.</summary>
    public int MaxTokens { get; set; } = 1024;

    /// <summary>
    /// Maximum prompt size in characters before the LLM call is rejected.
    /// Derived from the model context window: claude-sonnet-4-6 supports ~200 K tokens
    /// (~800 K chars at 4 chars/token). 600 000 leaves a ~25 % safety margin.
    /// </summary>
    public int MaxPromptChars { get; set; } = 600_000;

    /// <summary>Base URL for the Anthropic API.</summary>
    public string ApiBaseUrl { get; set; } = "https://api.anthropic.com";

    /// <summary>Anthropic API version header value.</summary>
    public string ApiVersion { get; set; } = "2023-06-01";
}
