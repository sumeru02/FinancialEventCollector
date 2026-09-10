/// <summary>
/// Repository for InvestigationTelemetryEvent records emitted by the investigation endpoint.
/// The current implementation uses a bounded in-memory ring buffer; intended to be backed
/// by a persistent store in production.
/// </summary>
public interface ITelemetryRepository
{
    /// <summary>Appends a telemetry event to the repository.</summary>
    void Add(InvestigationTelemetryEvent evt);

    /// <summary>
    /// Returns the most recent telemetry events in ascending chronological order.
    /// </summary>
    /// <param name="limit">Maximum number of events to return. Clamped to [1, 100].</param>
    IReadOnlyList<InvestigationTelemetryEvent> GetRecent(int limit = 10);
}
