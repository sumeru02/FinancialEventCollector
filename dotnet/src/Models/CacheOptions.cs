/// <summary>
/// Configuration for the investigation result cache.
/// Bind from appsettings.json under the "Cache" section.
/// </summary>
public class CacheOptions
{
    public const string SectionName = "Cache";

    /// <summary>
    /// Whether caching is active. Defaults to false so every request
    /// exercises the Claude endpoint (useful for demos and development).
    /// Set to true to avoid redundant LLM calls for the same incident.
    /// </summary>
    public bool Enabled { get; set; } = false;

    /// <summary>
    /// How long (in hours) a cached investigation result is retained before expiry.
    /// Only relevant when Enabled is true. Defaults to 24 hours.
    /// </summary>
    public int TtlHours { get; set; } = 24;
}
