using System.Text.Json.Serialization;

/// <summary>
/// Deserialization model for data/pipeline-config.json.
/// Loaded once at startup by PromptHelper.
/// </summary>
public record PipelineConfig(
    [property: JsonPropertyName("sla")]                  SlaConfig                          Sla,
    [property: JsonPropertyName("auditEventStageMap")]   Dictionary<string, AuditStageEntry> AuditEventStageMap,
    [property: JsonPropertyName("workerStageKeywords")]  List<WorkerStageKeyword>            WorkerStageKeywords,
    [property: JsonPropertyName("nonBlockingStages")]    List<string>                        NonBlockingStages,
    [property: JsonPropertyName("workerLogLevelsToInclude")] List<string>                   WorkerLogLevelsToInclude
);

public record SlaConfig(
    [property: JsonPropertyName("publishLatencyThresholdMinutes")] int PublishLatencyThresholdMinutes
);

public record AuditStageEntry(
    [property: JsonPropertyName("stage")]          string Stage,
    [property: JsonPropertyName("timestampField")] string TimestampField
);

public record WorkerStageKeyword(
    [property: JsonPropertyName("keyword")] string Keyword,
    [property: JsonPropertyName("stage")]   string Stage
);
