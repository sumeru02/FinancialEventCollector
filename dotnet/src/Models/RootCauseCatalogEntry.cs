using System.Text.Json.Serialization;

/// <summary>
/// A single entry in the root-cause catalog loaded from data/RootCauses.json.
/// Carries the description and recommended action for one RootCause value.
/// </summary>
public record RootCauseCatalogEntry(
    [property: JsonPropertyName("name")]              string Name,
    [property: JsonPropertyName("ordinal")]           int    Ordinal,
    [property: JsonPropertyName("description")]       string Description,
    [property: JsonPropertyName("recommendedAction")] string RecommendedAction,
    [property: JsonPropertyName("team")]              string Team
);
