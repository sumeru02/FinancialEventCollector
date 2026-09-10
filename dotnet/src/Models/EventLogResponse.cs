/// <summary>
/// API response DTO for GET /events/{eventId}/logs.
/// Exposes the raw audit events and worker logs for a pipeline event without
/// leaking internal test scaffolding (ScenarioMetadata).
/// </summary>
public record EventLogResponse
{
    /// <summary>The pipeline EventId, e.g. "evt-001".</summary>
    public required string EventId { get; init; }

    /// <summary>
    /// The upstream service's domain event type, e.g. "InvoiceCreated".
    /// Null when the event was never successfully parsed (e.g. connection drop at ingestion).
    /// </summary>
    public string? EventType { get; init; }

    /// <summary>
    /// The upstream service that produced the original business event, e.g. "InvoicingService".
    /// </summary>
    public required string EventSource { get; init; }

    /// <summary>
    /// Audit events recorded for this pipeline EventId.
    /// Each entry carries a TelemetryType of either "EventTelemetry" (success)
    /// or "ExceptionTelemetry" (failure), along with optional exception details.
    /// </summary>
    public required IReadOnlyList<AuditEvent> AuditEvents { get; init; }

    /// <summary>
    /// Worker log entries associated with this pipeline EventId.
    /// Only Warning and Error level entries are included
    /// (controlled by pipeline-config.json → workerLogLevelsToInclude).
    /// </summary>
    public required IReadOnlyList<WorkerLog> WorkerLogs { get; init; }

    /// <summary>
    /// Projects a raw EventLog into an EventLogResponse,
    /// deliberately omitting EventLog.ScenarioMetadata to avoid
    /// leaking internal test labels to API consumers.
    /// </summary>
    public static EventLogResponse FromEventLog(EventLog log) => new()
    {
        EventId      = log.EventId,
        EventType    = log.EventType,
        EventSource  = log.EventSource,
        AuditEvents  = log.AuditEvents,
        WorkerLogs   = log.WorkerLogs,
    };
}
