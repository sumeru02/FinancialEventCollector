/// <summary>
/// Represents a single incident entry loaded from data/Incidents.json.
/// A thin manifest record that links an incident identifier and title to a
/// pipeline EventId. The full pipeline data (audit events, worker logs) is
/// stored separately in data/EventLogs.json and accessed via IEventRepository.
/// </summary>
public record Incident
{
    /// <summary>Unique identifier for this incident.</summary>
    public required int IncidentId { get; init; }

    /// <summary>
    /// The partner-reported incident title, e.g. "Missing InvoiceCreated Event".
    /// </summary>
    public required string IncidentTitle { get; init; }

    /// <summary>The pipeline EventId associated with this incident, e.g. "evt-001".</summary>
    public required string EventId { get; init; }
}
