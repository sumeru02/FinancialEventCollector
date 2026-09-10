using System.Text.Json;

/// <summary>
/// Loads incident data from Data/Incidents.json on disk.
/// Registered as a Singleton so the file is parsed once and cached in memory.
/// </summary>
public class IncidentRepository : IIncidentRepository
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() }
    };

    private readonly IReadOnlyList<Incident> _incidents;

    public IncidentRepository(IWebHostEnvironment env)
    {
        var path = Path.Combine(env.ContentRootPath, "data", "Incidents.json");
        var json  = File.ReadAllText(path);
        _incidents = JsonSerializer.Deserialize<List<Incident>>(json, JsonOptions)
                     ?? [];
    }

    /// <inheritdoc/>
    public IReadOnlyList<Incident> GetIncidents() => _incidents;
}
