using System.Text.Json.Serialization;

public record AuditEvent(
    string Name,                                    // IngestAuditEvent | IndexAuditEvent | PublishAuditEvent
    string? EventId           = null,               // e.g. "evt-001" — null on ExceptionTelemetry (event never parsed)
    DateTimeOffset SourceEventTimestamp = default,  // partner-provided; when the business event occurred upstream
    DateTimeOffset? IngestionTimestamp  = null,     // collector-assigned; set by IngestionWorker on receipt
    DateTimeOffset? IndexingTimestamp   = null,     // collector-assigned; set by IndexingWorker on completion
    DateTimeOffset? PublishingTimestamp = null,     // collector-assigned; set by PublishingWorker on completion
    string TelemetryType      = "EventTelemetry",  // "EventTelemetry" (success) | "ExceptionTelemetry" (failure)
    bool ExceptionOccurred    = false,              // true when this record represents a pipeline failure
    string? ExceptionType     = null,               // e.g. "ConnectionDropException" — null on ExceptionTelemetry
    string? ExceptionMessage  = null                // free-text failure reason — null on ExceptionTelemetry
)
{
    /// <summary>
    /// The collector-assigned timestamp for this stage, regardless of which stage produced the record.
    /// Resolves to whichever stage-specific timestamp is present.
    /// </summary>
    [JsonIgnore]
    public DateTimeOffset? CollectorStageTimestamp =>
        IngestionTimestamp ?? IndexingTimestamp ?? PublishingTimestamp;
}
