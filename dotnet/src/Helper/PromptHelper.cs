using System.Text;
using System.Text.Json;

/// <summary>
/// Pure static helper that assembles the full LLM prompt for an incident investigation.
/// The system instructions template is loaded once from
/// prompts/investigation-prompt.md at startup;
/// pipeline config and LLM schema are loaded from config/pipeline-config.json
/// and config/llm-response-schema.json respectively.
/// Per-request dynamic data (EventId, description, merged event log) is appended at call time.
/// </summary>
public static class PromptHelper
{
    private static readonly JsonSerializerOptions PrettyJson  = new() { WriteIndented = true };
    private static readonly JsonSerializerOptions ParseJson   = new() { PropertyNameCaseInsensitive = true };

    /// <summary>
    /// Loaded once from disk when the class is first used.
    /// Uses AppContext.BaseDirectory so it resolves correctly
    /// whether the app is run from dotnet run or a published output.
    /// </summary>
    private static readonly string SystemPromptTemplate =
        ReadRequiredFile(Path.Combine(AppContext.BaseDirectory, "prompts", "investigation-prompt.md"));

    /// <summary>Pipeline configuration loaded from config/pipeline-config.json.</summary>
    private static readonly PipelineConfig PipelineConfig =
        DeserializeRequiredConfig<PipelineConfig>(
            Path.Combine(AppContext.BaseDirectory, "config", "pipeline-config.json"));

    /// <summary>LLM response schema JSON loaded from config/llm-response-schema.json.</summary>
    private static readonly string LlmSchemaJson =
        ReadRequiredFile(Path.Combine(AppContext.BaseDirectory, "config", "llm-response-schema.json"));

    /// <summary>
    /// Resolved system prompt with all placeholders substituted.
    /// Computed once at class initialization.
    /// </summary>
    private static readonly string ResolvedSystemPrompt = SystemPromptTemplate
        .Replace("{{sla.publishLatencyThresholdMinutes}}", PipelineConfig.Sla.PublishLatencyThresholdMinutes.ToString())
        .Replace("{{llm_response_schema}}", LlmSchemaJson);

    // ── Static initializer helpers ────────────────────────────────────────────

    /// <summary>
    /// Reads a required file from disk and returns its contents.
    /// Throws <see cref="FileNotFoundException"/> with a clear path if the file is missing,
    /// avoiding the opaque <see cref="System.TypeInitializationException"/> that would
    /// otherwise wrap the error when called from a static field initializer.
    /// </summary>
    private static string ReadRequiredFile(string path)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException(
                $"PromptHelper: required file not found — '{path}'. " +
                "Ensure the file is present in the application output directory.", path);

        return File.ReadAllText(path);
    }

    /// <summary>
    /// Reads and deserializes a required JSON config file.
    /// Throws <see cref="FileNotFoundException"/> if the file is missing, or
    /// <see cref="InvalidOperationException"/> if deserialization returns null.
    /// </summary>
    private static T DeserializeRequiredConfig<T>(string path)
    {
        var json = ReadRequiredFile(path);

        return JsonSerializer.Deserialize<T>(json, ParseJson)
            ?? throw new InvalidOperationException(
                $"PromptHelper: failed to deserialize '{typeof(T).Name}' from '{path}'. " +
                "The file may be empty or contain invalid JSON.");
    }

    /// <summary>
    /// Builds the complete prompt string to send to the LLM.
    /// Merges and sorts the event log's audit events and worker logs internally.
    /// </summary>
    /// <param name="eventLog">The raw event log record to investigate.</param>
    /// <param name="maxPromptChars">Maximum number of characters allowed in the final prompt; the event log is truncated to fit.</param>
    /// <returns>A single string containing the system instructions followed by the dynamic investigation data.</returns>
    public static string BuildInvestigationPrompt(EventLog eventLog, int maxPromptChars)
    {
        var sb = new StringBuilder();

        // Static system instructions from the .md file (with placeholders already resolved)
        sb.AppendLine(ResolvedSystemPrompt);

        // Dynamic per-request context
        sb.AppendLine($"""
            INVESTIGATION DETAILS:
            EventId: {eventLog.EventId}
            ScenarioDescription: {eventLog.ScenarioMetadata?.ScenarioDescription ?? "No description provided."}
            """);

        // Merge audit events + worker logs into a single sorted timeline
        var mergedLog = BuildMergedLog(eventLog);
        sb.AppendLine("MERGED EVENT LOG (sorted by timestamp, benign exceptions already filtered):");
        sb.AppendLine(JsonSerializer.Serialize(mergedLog, PrettyJson));

        if (sb.Length > maxPromptChars)
            throw new InvalidOperationException(
                $"Prompt for EventId={eventLog.EventId} exceeds MaxPromptChars limit " +
                $"({sb.Length:N0} > {maxPromptChars:N0}). Reduce the event log size.");

        return sb.ToString();
    }

    // ── Private helpers ───────────────────────────────────────────────────────

    /// <summary>
    /// Merges audit events and worker logs into a unified list sorted ascending
    /// by timestamp, mirroring the merged event-log shape the LLM prompt expects.
    /// Only Error and Warning worker logs are included (benign Info logs are filtered out).
    /// </summary>
    private static IReadOnlyList<EventLogEntry> BuildMergedLog(EventLog eventLog)
    {
        var entries = new List<EventLogEntry>();

        // Map AuditEvents → rows (EventTelemetry for success, ExceptionTelemetry for failures)
        foreach (var audit in eventLog.AuditEvents)
        {
            var (stage, timestamp) = ResolveAuditStage(audit);
            entries.Add(new EventLogEntry
            {
                Timestamp     = timestamp ?? audit.SourceEventTimestamp,
                Stage         = stage,
                TelemetryType = audit.TelemetryType,
                EventSource   = eventLog.EventSource,
                Name          = audit.Name,
                EventType     = eventLog.EventType,
                EventId       = audit.EventId ?? eventLog.EventId,
                Message       = audit.ExceptionMessage
            });
        }

        // Map WorkerLogs → ExceptionTelemetry rows (errors/warnings only, driven by config)
        var levelsToInclude = PipelineConfig.WorkerLogLevelsToInclude.ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var log in eventLog.WorkerLogs.Where(l => levelsToInclude.Contains(l.Level)))
        {
            entries.Add(new EventLogEntry
            {
                Timestamp     = log.Timestamp,
                Stage         = ResolveWorkerStage(log.WorkerName),
                TelemetryType = "ExceptionTelemetry",
                EventSource   = log.WorkerName,
                Name          = log.Level,
                EventId       = log.EventId ?? eventLog.EventId,
                Message       = log.Message
            });
        }

        return entries.OrderBy(e => e.Timestamp).ToList();
    }

    /// <summary>
    /// Resolves the pipeline stage and relevant timestamp for an audit event
    /// using the auditEventStageMap from config/pipeline-config.json.
    /// </summary>
    private static (string Stage, DateTimeOffset? Timestamp) ResolveAuditStage(AuditEvent audit)
    {
        if (PipelineConfig.AuditEventStageMap.TryGetValue(audit.Name, out var mapping))
        {
            var timestamp = mapping.TimestampField switch
            {
                "ingestionTimestamp"  => audit.IngestionTimestamp,
                "indexingTimestamp"   => audit.IndexingTimestamp,
                "publishingTimestamp" => audit.PublishingTimestamp,
                _                    => audit.CollectorStageTimestamp
            };
            return (mapping.Stage, timestamp);
        }
        return ("Unknown", audit.CollectorStageTimestamp);
    }

    /// <summary>
    /// Resolves the pipeline stage for a worker log entry
    /// using the workerStageKeywords from config/pipeline-config.json.
    /// </summary>
    private static string ResolveWorkerStage(string workerName)
    {
        foreach (var kw in PipelineConfig.WorkerStageKeywords)
        {
            if (workerName.Contains(kw.Keyword, StringComparison.OrdinalIgnoreCase))
                return kw.Stage;
        }
        return "Unknown";
    }
}
