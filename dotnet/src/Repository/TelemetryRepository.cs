using System.Collections.Concurrent;

/// <summary>
/// Thread-safe in-memory ring buffer for InvestigationTelemetryEvent records.
/// Registered as a singleton so events persist across requests for the application lifetime.
/// Older events are evicted automatically once MaxCapacity is reached.
/// Current implementation is in-memory; intended to be backed by a persistent store in production.
/// </summary>
public class TelemetryRepository : ITelemetryRepository
{
    /// <summary>Maximum number of events retained in memory before oldest are evicted.</summary>
    private const int MaxCapacity = 1000;

    private readonly ConcurrentQueue<InvestigationTelemetryEvent> _events = new();

    /// <inheritdoc/>
    public void Add(InvestigationTelemetryEvent evt)
    {
        _events.Enqueue(evt);

        // Evict oldest events when capacity is exceeded
        while (_events.Count > MaxCapacity)
            _events.TryDequeue(out _);
    }

    /// <inheritdoc/>
    public IReadOnlyList<InvestigationTelemetryEvent> GetRecent(int limit = 10)
        => _events.TakeLast(Math.Clamp(limit, 1, 100))
                  .OrderByDescending(e => e.Timestamp)
                  .ToList();
}
