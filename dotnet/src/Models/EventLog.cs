/// <summary>
/// Raw pipeline event record loaded from data/EventLogs.json.
/// Carries the audit events and worker logs for one pipeline EventId.
/// Used as the source for EventLineage projection and as
/// the input to IInvestigationService for LLM root-cause analysis.
/// </summary>
public record EventLog
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
    /// Optional test scenario metadata describing the diagnostic pattern this event exercises
    /// and providing ground-truth labels for LLM evaluation.
    /// Null for real production events that have no associated test scenario.
    /// </summary>
    public ScenarioMetadata? ScenarioMetadata { get; init; }

    /// <summary>
    /// Audit events recorded for this pipeline EventId.
    /// Each entry carries a TelemetryType of either "EventTelemetry" (success)
    /// or "ExceptionTelemetry" (failure), along with optional exception details.
    /// </summary>
    public required IReadOnlyList<AuditEvent> AuditEvents { get; init; }

    /// <summary>
    /// Worker log entries associated with this pipeline EventId.
    /// Only Warning and Error level entries are included in the LLM investigation prompt
    /// (controlled by pipeline-config.json → workerLogLevelsToInclude).
    /// </summary>
    public required IReadOnlyList<WorkerLog> WorkerLogs { get; init; }
}
