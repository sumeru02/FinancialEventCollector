public record WorkerLog(
    DateTimeOffset Timestamp,
    string WorkerName,  // IngestionWorker | IndexingWorker | PublishingWorker
    string Level,       // Info | Warning | Error
    string Message,
    string? EventId     // null when failure occurred before per-event processing context
);
