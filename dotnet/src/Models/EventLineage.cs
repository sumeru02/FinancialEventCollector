/// <summary>
/// Projected data lineage view for a single pipeline EventId.
/// Constructed from a raw EventLog record; all derived fields are
/// computed once in the constructor and stored as read-only properties.
/// Returned by GET /events/lineage and GET /events/{eventId}/lineage.
/// </summary>
public class EventLineage
{
    private static readonly string[] AllStages =
        ["IngestAuditEvent", "IndexAuditEvent", "PublishAuditEvent"];

    /// <summary>The pipeline EventId, e.g. "evt-001".</summary>
    public string EventId { get; }

    /// <summary>
    /// The upstream service's domain event type, e.g. "InvoiceCreated".
    /// Null when the event was never successfully parsed (e.g. connection drop at ingestion).
    /// </summary>
    public string? EventType { get; }

    /// <summary>
    /// The upstream service that produced the original business event, e.g. "InvoicingService".
    /// </summary>
    public string EventSource { get; }

    /// <summary>
    /// True when an IngestAuditEvent with TelemetryType "EventTelemetry" is present,
    /// indicating the event was successfully received and parsed by the IngestionWorker.
    /// </summary>
    public bool IngestSuccess { get; }

    /// <summary>
    /// True when an IndexAuditEvent with TelemetryType "EventTelemetry" is present,
    /// indicating the event was successfully written to the index store by the IndexingWorker.
    /// </summary>
    public bool IndexSuccess { get; }

    /// <summary>
    /// True when a PublishAuditEvent with TelemetryType "EventTelemetry" is present,
    /// indicating the event was successfully delivered to downstream consumers by the PublishingWorker.
    /// </summary>
    public bool PublishSuccess { get; }

    /// <summary>
    /// Names of the audit events that completed successfully (TelemetryType = "EventTelemetry").
    /// Possible values: "IngestAuditEvent", "IndexAuditEvent", "PublishAuditEvent".
    /// </summary>
    public IReadOnlyList<string> AuditEventsPresent { get; }

    /// <summary>
    /// Names of the expected audit events that are absent or recorded only as ExceptionTelemetry.
    /// Possible values: "IngestAuditEvent", "IndexAuditEvent", "PublishAuditEvent".
    /// </summary>
    public IReadOnlyList<string> MissingAuditEvents { get; }

    /// <summary>
    /// Elapsed seconds from the upstream source event timestamp to the PublishingWorker completion timestamp.
    /// Null when PublishSuccess is false (Publish never completed).
    /// </summary>
    public double? PublishLatencySeconds { get; }

    /// <summary>
    /// True when PublishLatencySeconds is within the configured SLA threshold.
    /// False when the threshold is exceeded.
    /// Null when PublishSuccess is false (latency is not applicable).
    /// </summary>
    public bool? PublishLatencySlaMet { get; }

    /// <summary>
    /// Projects an EventLog into a data lineage view.
    /// All derived fields are computed from the audit events at construction time.
    /// </summary>
    /// <param name="log">The raw event log record to project.</param>
    /// <param name="slaThresholdMinutes">
    /// The publish latency SLA threshold in minutes, read from pipeline-config.json.
    /// </param>
    public EventLineage(EventLog log, int slaThresholdMinutes)
    {
        var successNames = log.AuditEvents
            .Where(a => a.TelemetryType == "EventTelemetry")
            .Select(a => a.Name)
            .ToList();

        var ingest  = log.AuditEvents.FirstOrDefault(a => a.Name == "IngestAuditEvent"  && a.TelemetryType == "EventTelemetry");
        var publish = log.AuditEvents.FirstOrDefault(a => a.Name == "PublishAuditEvent" && a.TelemetryType == "EventTelemetry");

        double? latency = (ingest is not null && publish?.PublishingTimestamp is not null)
            ? (publish.PublishingTimestamp.Value - ingest.SourceEventTimestamp).TotalSeconds
            : null;

        EventId               = log.EventId;
        EventType             = log.EventType;
        EventSource           = log.EventSource;
        IngestSuccess         = successNames.Contains("IngestAuditEvent");
        IndexSuccess          = successNames.Contains("IndexAuditEvent");
        PublishSuccess        = successNames.Contains("PublishAuditEvent");
        AuditEventsPresent    = successNames.AsReadOnly();
        MissingAuditEvents    = AllStages.Except(successNames).ToList().AsReadOnly();
        PublishLatencySeconds = latency.HasValue ? Math.Round(latency.Value, 1) : null;
        PublishLatencySlaMet  = latency.HasValue ? latency.Value <= slaThresholdMinutes * 60.0 : null;
    }
}
