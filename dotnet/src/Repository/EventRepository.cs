using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// Loads pipeline event log data from data/EventLogs.json on disk.
/// Registered as a Singleton so the file is parsed once and the
/// EventLineage projections are computed once at startup.
/// </summary>
public class EventRepository : IEventRepository
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        Converters = { new JsonStringEnumConverter() }
    };

    private readonly Dictionary<string, EventLog>     _eventLogs;
    private readonly Dictionary<string, EventLineage> _eventLineages;

    public EventRepository(IWebHostEnvironment env)
    {
        // Load raw event logs from disk
        var path = Path.Combine(env.ContentRootPath, "data", "EventLogs.json");
        var json  = File.ReadAllText(path);
        var logs  = JsonSerializer.Deserialize<List<EventLog>>(json, JsonOptions) ?? [];

        _eventLogs = logs.ToDictionary(l => l.EventId, StringComparer.OrdinalIgnoreCase);

        // Load SLA threshold from pipeline-config.json (same source as PromptHelper)
        var configPath = Path.Combine(env.ContentRootPath, "config", "pipeline-config.json");
        var config     = JsonSerializer.Deserialize<PipelineConfig>(
                             File.ReadAllText(configPath), JsonOptions)!;

        // Project EventLog → EventLineage once at startup (O(n), stored in a dictionary for O(1) lookups)
        _eventLineages = logs.ToDictionary(
            l => l.EventId,
            l => new EventLineage(l, config.Sla.PublishLatencyThresholdMinutes),
            StringComparer.OrdinalIgnoreCase);
    }

    /// <inheritdoc/>
    public EventLineage? GetEventLineage(string eventId)
        => _eventLineages.GetValueOrDefault(eventId);

    /// <inheritdoc/>
    public EventLog? GetEventLogById(string eventId)
        => _eventLogs.GetValueOrDefault(eventId);
}
