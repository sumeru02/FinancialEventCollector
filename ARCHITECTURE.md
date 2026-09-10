# Architecture — FinancialEventCollector

## 1. System Overview

**FinancialEventCollector** is a financial event ingestion, indexing, and
publishing service with endpoints for data lineage lookup and missing-event
investigation.

A missing event has real downstream consequences — e.g. a missing
`InvoiceCreated` event can mean an invoice PDF never gets generated at
month-end close, or that downstream financial calculations run against
incomplete data. For every event it processes, the system records an
`AuditEvent` at each pipeline stage — **Ingest**, **Index**, and **Publish** —
keyed by a shared `EventId`.

These per-stage audit records exist to support two goals:

- **Data lineage** — reconstruct the full journey of a given event through the
  pipeline by looking up all `AuditEvent` records for its `EventId`.
- **Missing-event investigation** — detect events that started the pipeline but
  never completed one or more expected stages, so gaps can be surfaced and
  investigated rather than silently lost.

The service is implemented in both Python (FastAPI) and .NET (ASP.NET Core),
sharing config, seed data, and LLM prompts under `shared/`.

<details>
<summary><strong><code>shared/</code> — files shared by both runtimes</strong></summary>

- **`config/`**
  - [`app-config.json`](shared/config/app-config.json) — Default Claude + cache settings
  - [`pipeline-config.json`](shared/config/pipeline-config.json) — SLA thresholds, stage maps, worker keywords
  - [`llm-response-schema.json`](shared/config/llm-response-schema.json) — JSON Schema the LLM must conform to
- **`data/`**
  - [`EventLogs.json`](shared/data/EventLogs.json) — Worker log entries for each scenario
  - [`Incidents.json`](shared/data/Incidents.json) — Seed incident scenarios
  - [`RootCauses.json`](shared/data/RootCauses.json) — Root cause catalog (descriptions + actions)
- **`prompts/`**
  - [`investigation-prompt.md`](shared/prompts/investigation-prompt.md) — LLM prompt template

</details>

### Core Data Structures

Two primary data structures flow through the service:

**`EventLog`** — the unit of investigation for a single pipeline event. Loaded
from [`shared/data/EventLogs.json`](shared/data/EventLogs.json) by `EventRepository`. Contains the merged
audit events and worker logs for one `EventId`:

```json
{
  "eventId": "evt-004",
  "eventType": "InvoiceCreated",
  "eventSource": "InvoicingService",
  "scenarioMetadata": {
    "scenarioName": "MissingPublishingEvent",
    "scenarioDescription": "Publish audit event never recorded — Ingest and Index present. The most common real-world gap: an event fully processed internally but never made it to downstream consumers.",
    "expectedRootCause": "MissingPublishingAuditEvent",
    "expectedExplanation": "No PublishAuditEvent recorded; the PublishingWorker exceeded the connection retry limit to EventHub, so the event never reached downstream consumers."
  },
  "auditEvents": [
    {
      "name": "IngestAuditEvent",
      "telemetryType": "EventTelemetry",
      "sourceEventTimestamp": "2026-08-10T17:25:10Z",
      "ingestionTimestamp": "2026-08-10T17:25:45Z"
    },
    {
      "name": "IndexAuditEvent",
      "telemetryType": "EventTelemetry",
      "sourceEventTimestamp": "2026-08-10T17:25:10Z",
      "indexingTimestamp": "2026-08-10T17:26:03Z"
    },
    {
      "name": "PublishAuditEvent",
      "telemetryType": "ExceptionTelemetry",
      "sourceEventTimestamp": "2026-08-10T17:25:10Z",
      "exceptionOccurred": true,
      "exceptionType": "EventHubConnectionException",
      "exceptionMessage": "Failed to publish event to EventHub: connection retry limit exceeded."
    }
  ],
  "workerLogs": [
    {
      "timestamp": "2026-08-10T17:26:46Z",
      "workerName": "PublishingWorker",
      "level": "Error",
      "message": "Failed to publish event to EventHub: connection retry limit exceeded."
    }
  ]
}
```

**`Incident`** — links an `incidentId` and title to an `EventLog` via `eventId`.
Loaded from [`shared/data/Incidents.json`](shared/data/Incidents.json); `IncidentDataService` resolves the
full `EventLog` at query time:

```json
[
  { "incidentId": 1, "incidentTitle": "Missing InvoiceCreated Event",  "eventId": "evt-001" },
  { "incidentId": 2, "incidentTitle": "Missing InvoiceCreated Event",  "eventId": "evt-002" },
  { "incidentId": 3, "incidentTitle": "Missing InvoiceCreated Event",  "eventId": "evt-003" },
  { "incidentId": 4, "incidentTitle": "Missing InvoiceCreated Event",  "eventId": "evt-004" },
  { "incidentId": 5, "incidentTitle": "Delayed InvoiceCreated Event",  "eventId": "evt-005" },
  { "incidentId": 6, "incidentTitle": "Missing InvoiceCreated Event",  "eventId": "evt-006" }
]
```

---

## 2. Pipeline Dependency Graph

The pipeline has three stages. Each stage records an `AuditEvent` keyed by
`EventId`. An `AuditEvent` with `telemetryType = "EventTelemetry"` indicates
the stage completed successfully; `telemetryType = "ExceptionTelemetry"`
indicates the stage was reached but failed. **Absence of an `EventTelemetry`
record for a stage is the signal for a gap** — only `EventTelemetry` implies
success.

```
                     +-----------+
                     |  INGEST   |
                     +-----------+
                           |
                (gates both stages below)
                           |
              +------------+------------+
              |                         |
              v                         v
        +-----------+             +-----------+
        |   INDEX   |             |  PUBLISH  |
        +-----------+             +-----------+

  Ingest must complete before either Index or Publish can occur.
  Index and Publish are separate, independent parallel workers —
  neither depends on the other.
```

### Valid States

| Ingest | Index | Publish | Meaning |
|--------|-------|---------|---------|
| ✓ | ✓ | ✓ | Healthy — all stages complete |
| ✓ | ✗ | ✓ | Index worker failed; Publish unaffected |
| ✓ | ✓ | ✗ | Publish worker failed; event not delivered |
| ✗ | ✗ | ✗ | Event never entered the pipeline |

### SLA

The publish latency SLA is configured in `shared/config/pipeline-config.json`:

```json
{ "sla": { "publishLatencyThresholdMinutes": 15 } }
```

If all three audit events are present but the elapsed time between
`IngestAuditEvent` and `PublishAuditEvent` exceeds 15 minutes, the root cause
is classified as `PublishLatencyExceedsSLA`.

### Seed Scenarios

Six scenarios are defined in `shared/data/EventLogs.json` and cover every
valid root cause value:

| Incident | Scenario | EventId | Stages Present | Expected Root Cause |
|---|----------|---------|----------------|---------------------|
| 1 | AllAuditEventsPresent | `evt-001` | Ingest ✓ Index ✓ Publish ✓ | `AllAuditEventsPresent` |
| 2 | MissingIngestionEvent | `evt-002` | Ingest ✗ (ExceptionTelemetry) | `MissingIngestionAuditEvent` |
| 3 | MissingIndexingEvent | `evt-003` | Ingest ✓ Index ✗ (ExceptionTelemetry) Publish ✓ | `MissingIndexingAuditEvent` |
| 4 | MissingPublishingEvent | `evt-004` | Ingest ✓ Index ✓ Publish ✗ (ExceptionTelemetry) | `MissingPublishingAuditEvent` |
| 5 | PublishLatencyExceedsSLA | `evt-005` | Ingest ✓ Index ✓ Publish ✓ (Ingest→Publish ~17 min) | `PublishLatencyExceedsSLA` |
| 6 | UnknownRootCause | `evt-006` | No audit events; only a generic restart warning | `Unknown` |

---

## 3. LLM Investigation Flow

### Why LLM?

The missing-stage root cause (`MissingIngestionAuditEvent`, `MissingIndexingAuditEvent`,
`MissingPublishingAuditEvent`) can be derived deterministically by querying which
`EventTelemetry` audit records exist for a given `EventId`. The LLM adds value
in two ways that a query alone cannot provide:

1. **Explaining *why* the stage failed** — the LLM correlates the audit event
   gap with `WorkerLog` entries (e.g. a `ConnectionDropException` or an
   `IndexStoreTimeoutException`) to produce a human-readable explanation of the
   failure, not just a label.
2. **Handling ambiguous evidence** — when logs are absent, contradictory, or
   point to no clear cause (scenario 6 — `UnknownRootCause`), a deterministic
   rule engine would either misclassify or require explicit case coverage for
   every edge case. The LLM returns `Unknown` with a reasoned explanation,
   which is more useful to an on-call engineer than a silent fallback.

The structured `rootCause` field in the LLM response is validated against
`llm-response-schema.json` so the output remains machine-readable and
comparable against `expectedRootCause` in validation runs.

The LLM can be invoked via two independent entry points — both converge on the
same investigation pipeline:

```
  POST /events/{eventId}/investigations     POST /incidents/{id}/investigations
             |                                            |
             v                                            v
      EventController                          IncidentController
      EventRepository                          IncidentDataService
      (EventLogs.json)                         (Incidents.json)
             |                                            |
             |   resolves to EventLog ──────────────────► |
             |   { eventId, auditEvents, workerLogs }     |
             +--------------------+------------------------+
                                  |
                              EventLog
                                  |
                                  v
                        +------------------------+
                        |   InvestigationService  |
                        |   InvestigateAsync      |
                        |   (EventLog eventLog)   |
                        |   IMemoryCache check    |
                        +------------------------+
                          |                  |
                     CACHE HIT           CACHE MISS
                          |                  |
                          |                  v
                          |        +------------------+
                          |        |   PromptHelper   |
                          |        |   injects into   |
                          |        |   prompt template:|
                          |        |   • auditEvents  |
                          |        |   • workerLogs   |
                          |        |   • SLA threshold|
                          |        |   • response     |
                          |        |     schema       |
                          |        +------------------+
                          |                  |
                          |                  v
                          |        +------------------+
                          |        |  ClaudeService   |
                          |        |  (ILlmService)   |
                          |        |  POST /v1/messages|
                          |        +------------------+
                          |                  |
                          |        validate JSON response
                          |        → InvestigationResult
                          |           { rootCause,
                          |             explanation,
                          |             confidence }
                          |        → IMemoryCache.Set
                          |                  |
                          +------------------+
                                  |
                                  v
                        InvestigationResponse
                        X-Cache: HIT | MISS
```

**Example assembled prompt** (scenario 4 — `evt-004 / MissingPublishingEvent`; the
full prompt template lives in [`shared/prompts/investigation-prompt.md`](shared/prompts/investigation-prompt.md)
and the response schema in [`shared/config/llm-response-schema.json`](shared/config/llm-response-schema.json)):

```
EVENT LOG (evt-004):
{
  "eventId": "evt-004",
  "eventType": "InvoiceCreated",
  "eventSource": "InvoicingService",
  "auditEvents": [
    { "name": "IngestAuditEvent",  "telemetryType": "EventTelemetry",
      "ingestionTimestamp": "2026-08-10T17:25:45Z" },
    { "name": "IndexAuditEvent",   "telemetryType": "EventTelemetry",
      "indexingTimestamp": "2026-08-10T17:26:03Z" },
    { "name": "PublishAuditEvent", "telemetryType": "ExceptionTelemetry",
      "exceptionType": "EventHubConnectionException",
      "exceptionMessage": "Failed to publish event to EventHub: connection retry limit exceeded." }
  ],
  "workerLogs": [
    { "workerName": "PublishingWorker", "level": "Error",
      "message": "Failed to publish event to EventHub: connection retry limit exceeded." }
  ]
}

ROOT CAUSE LOGIC — apply exactly one:
1. No successful IngestAuditEvent  → MissingIngestionAuditEvent
2. Ingest present; no successful IndexAuditEvent  → MissingIndexingAuditEvent
3. Ingest present; no successful PublishAuditEvent → MissingPublishingAuditEvent
4. All three present AND Ingest→Publish gap > 15 min → PublishLatencyExceedsSLA
5. All three present AND gap within threshold → AllAuditEventsPresent
6. Ambiguous or contradictory evidence → Unknown
```

**Expected LLM response:**

```json
{
  "rootCause": "MissingPublishingAuditEvent",
  "explanation": "IngestAuditEvent and IndexAuditEvent are both present with EventTelemetry, but PublishAuditEvent has ExceptionTelemetry — the PublishingWorker exceeded the EventHub connection retry limit and the event never reached downstream consumers.",
  "confidence": "HIGH"
}
```

### Root Cause Values

The LLM must return exactly one of these values in its `rootCause` field:

| Value | Meaning |
|---|---|
| `AllAuditEventsPresent` | All three stages present and within SLA — no issue |
| `MissingIngestionAuditEvent` | Event never entered the pipeline |
| `MissingIndexingAuditEvent` | Index worker failed or was skipped |
| `MissingPublishingAuditEvent` | Event never reached downstream consumers |
| `PublishLatencyExceedsSLA` | All stages present but publish took > 15 minutes |
| `Unknown` | Evidence is ambiguous or contradictory |

### Prompt Engineering

The prompt template lives in `shared/prompts/investigation-prompt.md` and is
assembled at runtime by `PromptHelper`. To iterate on the prompt:

1. Edit `shared/prompts/investigation-prompt.md`
2. Call `GET /events/{eventId}/prompt` or `GET /incidents/{id}/prompt` to
   preview the assembled prompt without incurring any LLM cost
3. Call `POST /validation/run` to measure accuracy impact across all scenarios

### Caching

Results are cached in-memory with a configurable TTL (default: 24 hours).
The `X-Cache` response header on investigation endpoints indicates `HIT` or `MISS`.
Cache settings are in `shared/config/app-config.json` under the `cache` key.

### Switching LLM Providers

`ClaudeService` implements `ILlmService`. To swap providers:

1. Implement `ILlmService` in a new class (e.g. `OpenAiService`)
2. Register it in `Program.cs` (replace `ClaudeService` in `AddHttpClient<ILlmService, ...>`)
3. Update the API key and base URL in `appsettings.json`

No changes to controllers, `InvestigationService`, or MCP tools are required.

---

## 4. Authentication & Security

All endpoints require an `X-Api-Key` header. The key is validated by
`ApiKeyAuthHandler` using constant-time comparison
(`CryptographicOperations.FixedTimeEquals`) to prevent timing-based key
enumeration attacks.

### Roles

Two keys are configured — `ApiKey:UserSecret` and `ApiKey:AdminSecret`:

| Role | Key | Accessible endpoints |
|---|---|---|
| `user` | `ApiKey:UserSecret` | `/events/*`, `/incidents/*`, `/telemetry` |
| `admin` | `ApiKey:AdminSecret` | All `user` endpoints + `/validation/*`, `/admin/*` |

The admin key grants both `admin` and `user` claims, so admin callers can
access all endpoints without needing to enumerate roles on each controller.

### Rate Limiting

A fixed-window rate limiter protects LLM-backed endpoints from unbounded cost:

| Limit | Window | Applies to |
|---|---|---|
| 10 requests | 1 minute per IP | `POST /events/{eventId}/investigations` |
| 10 requests | 1 minute per IP | `POST /incidents/{id}/investigations` |
| 10 requests | 1 minute per IP | `POST /validation/run` |

Requests that exceed the limit receive `429 Too Many Requests`.

---

## 5. Data Model

### AuditEvent

Records that a pipeline stage completed successfully for a given `EventId`.
Absence of a record for a stage means that stage never completed.

```csharp
public sealed record AuditEvent(
    string         Name,          // IngestAuditEvent | IndexAuditEvent | PublishAuditEvent
    DateTimeOffset EventTime,
    string         EventId,       // partner-provided, e.g. "evt-001"
    string         EventType,     // partner-provided, e.g. "InvoiceCreated"
    string         EventSource    // inferred by the Collector, e.g. "InvoicingService"
);
```

### WorkerLog

Raw diagnostic log entries emitted by pipeline workers. Used by the LLM to
understand *why* a stage failed, once a gap is detected from `AuditEvent` records.

```csharp
public sealed record WorkerLog(
    DateTimeOffset Timestamp,
    string         WorkerName,   // IngestionWorker | IndexingWorker | PublishingWorker
    string         Level,        // "Info" | "Warning" | "Error"
    string         Message,
    string?        EventId       // null when failure occurred before per-event context
);
```

`EventId` is `null` on log entries emitted before the worker entered per-event
processing (e.g. a connection pool failure at startup). This is why it appears
in the `missingIngest` scenario but not in `missingIndex`/`missingPublish`.

### Incident

The unit of investigation. Loaded from `shared/data/Incidents.json`.

```csharp
public record Incident
{
    int                        IncidentId;     // 1–6 for seed scenarios
    string                     IncidentTitle;
    string                     EventId;        // e.g. "evt-001"
    IncidentTestMetadata?      TestMetadata;   // ground-truth label for validation
    IReadOnlyList<AuditEvent>  AuditEvents;
    IReadOnlyList<WorkerLog>   WorkerLogs;
}
```

`TestMetadata.ExpectedRootCause` is the human-authored ground-truth label used
by `POST /validation/run` to measure LLM accuracy.

---

## 6. Dual-Runtime Design

Both the Python (FastAPI) and .NET (ASP.NET Core) implementations expose
identical REST endpoints and share all config, data, and prompts from `shared/`.

| Concern | Python | .NET |
|---|---|---|
| Entry point | `python/app/main.py` | `dotnet/src/Program.cs` |
| Routers / Controllers | `python/app/routers/` | `dotnet/src/Controllers/` |
| Services | `python/app/services/` | `dotnet/src/Services/` |
| Models | `python/app/models/` | `dotnet/src/Models/` |
| Auth | `python/app/auth.py` | `dotnet/src/Auth/ApiKeyAuthHandler.cs` |
| Interactive docs | `http://localhost:8000/docs` | `http://localhost:5000` |
