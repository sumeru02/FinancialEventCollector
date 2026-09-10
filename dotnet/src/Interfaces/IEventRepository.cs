/// <summary>
/// Repository for pipeline event log data loaded from data/EventLogs.json.
/// Provides both the raw EventLog records (used by the LLM investigation service)
/// and the projected EventLineage views (returned by the Events API endpoints).
/// </summary>
public interface IEventRepository
{
    /// <summary>
    /// Returns the projected data lineage view for a single pipeline event.
    /// Returns null when no event with the given <paramref name="eventId"/> exists.
    /// Used by GET /events/{eventId}/lineage.
    /// </summary>
    EventLineage? GetEventLineage(string eventId);

    /// <summary>
    /// Returns the raw event log record for a single pipeline event.
    /// Returns null when no event with the given <paramref name="eventId"/> exists.
    /// Used by GET /events/{eventId}/logs, POST /events/{eventId}/investigations,
    /// and POST /incidents/{id}/investigations.
    /// </summary>
    EventLog? GetEventLogById(string eventId);
}
