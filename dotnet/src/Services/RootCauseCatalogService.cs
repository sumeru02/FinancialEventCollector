using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// Singleton service that loads the root-cause catalog from data/RootCauses.json
/// once at startup and provides fast dictionary lookups by RootCause enum value.
/// </summary>
public class RootCauseCatalogService
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    /// <summary>All entries in the catalog, keyed by RootCause enum value.</summary>
    public IReadOnlyDictionary<RootCause, RootCauseCatalogEntry> Entries { get; }

    /// <summary>All entries in ordinal order (for catalog endpoints).</summary>
    public IReadOnlyList<RootCauseCatalogEntry> AllEntries { get; }

    public RootCauseCatalogService(IWebHostEnvironment env)
    {
        var path = Path.Combine(env.ContentRootPath, "data", "RootCauses.json");
        var json  = File.ReadAllText(path);
        var doc   = JsonSerializer.Deserialize<RootCausesCatalogDocument>(json, JsonOptions)
                    ?? throw new InvalidOperationException("Failed to load RootCauses.json");

        AllEntries = doc.RootCauses.OrderBy(e => e.Ordinal).ToList().AsReadOnly();

        Entries = AllEntries
            .ToDictionary(
                e => Enum.Parse<RootCause>(e.Name),
                e => e)
            .AsReadOnly();
    }

    /// <summary>
    /// Returns the recommended action for the given root cause,
    /// or a generic fallback if the entry is not found.
    /// </summary>
    public string GetRecommendedAction(RootCause rootCause)
        => Entries.TryGetValue(rootCause, out var entry)
            ? entry.RecommendedAction
            : "Manual review required — evidence is ambiguous or contradictory.";

    // ── Private deserialization model ─────────────────────────────────────────

    private record RootCausesCatalogDocument(
        [property: JsonPropertyName("rootCauses")] List<RootCauseCatalogEntry> RootCauses
    );
}
