using System.Text.Json.Serialization;

/// <summary>
/// A single row in the merged, correlated event log for one EventId.
/// Covers all pipeline stages (Ingest, Index, Publish) and both
/// EventTelemetry and ExceptionTelemetry record types.
/// </summary>
public record EventLogEntry
{
    /// <summary>
    /// UTC timestamp of this log entry.
    /// The log is sorted ascending by this field before being sent to the LLM.
    /// </summary>
    public required DateTimeOffset Timestamp { get; init; }

    /// <summary>
    /// Pipeline stage derived from the worker's cloud_RoleName/WorkerName.
    /// Values: "Ingest" | "Index" | "Publish" | "Unknown".
    /// </summary>
    public required string Stage { get; init; }

    /// <summary>
    /// Whether this row came from a direct EventId match or a loose
    /// source+time-window correlation.
    /// Values: "EventTelemetry" | "ExceptionTelemetry".
    /// </summary>
    public required string TelemetryType { get; init; }

    /// <summary>
    /// The upstream service that produced the original business event,
    /// e.g. "InvoicingService".
    /// </summary>
    public required string EventSource { get; init; }

    /// <summary>
    /// The pipeline's own classification of this entry,
    /// e.g. "BatchIngestedEvent", "PublishAuditEvent", "403 Forbidden".
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// The upstream service's own domain event type, e.g. "invoiceCreated".
    /// Null when the message was not successfully read (e.g. auth/connection error).
    /// </summary>
    public string? EventType { get; init; }

    /// <summary>
    /// The pipeline EventId. Null on ExceptionTelemetry rows that were correlated
    /// by eventSource + time window rather than by a direct EntryId match.
    /// </summary>
    [JsonPropertyName("eventId")]
    public string? EventId { get; init; }

    /// <summary>
    /// Free-text exception or log message. Present on ExceptionTelemetry rows.
    /// </summary>
    public string? Message { get; init; }
}
