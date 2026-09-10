/// <summary>
/// Identifies the specific audit-event gap (or absence of gap) found in a pipeline incident.
/// Used both as the LLM's output (InvestigationResult.RootCause) and as the
/// ground-truth label on each test scenario (IncidentTestMetadata.ExpectedRootCause).
/// </summary>
public enum RootCause
{
    /// <summary>All three audit events are present and within normal timing — no issue detected.</summary>
    AllAuditEventsPresent,

    /// <summary>No IngestAuditEvent recorded — the event never entered the pipeline.</summary>
    MissingIngestionAuditEvent,

    /// <summary>No IndexAuditEvent recorded — the index worker failed or was skipped.</summary>
    MissingIndexingAuditEvent,

    /// <summary>No PublishAuditEvent recorded — the event never reached downstream consumers.</summary>
    MissingPublishingAuditEvent,

    /// <summary>
    /// All three audit events are present but the elapsed time between
    /// IngestAuditEvent and PublishAuditEvent exceeds the 15-minute SLA threshold.
    /// </summary>
    PublishLatencyExceedsSLA,

    /// <summary>Evidence is ambiguous or contradictory; manual review required.</summary>
    Unknown
}
