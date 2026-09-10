# Plan: `EventController.cs`

> **File:** `dotnet/src/Controllers/EventController.cs`  
> **Route prefix:** `events`  
> **Auth:** `[Authorize(Roles = "user")]` — API-key bearer, `user` role  
> **Purpose:** Exposes four HTTP endpoints that let callers browse event lineage data, inspect raw pipeline logs, preview the LLM investigation prompt, and trigger an AI-powered root-cause investigation for a single pipeline event (without requiring an incident).

---

## 1. Context & Motivation

The FinancialEventCollector pipeline ingests, indexes, and publishes financial domain events (e.g. `InvoiceCreated`). When an event fails to flow through all three stages, on-call engineers need to:

1. **See the data lineage** — which pipeline stages succeeded or failed.
2. **Inspect the raw logs** — the underlying audit events and worker log entries.
3. **Preview the LLM prompt** — for debugging and prompt iteration without incurring LLM cost.
4. **Run an AI investigation** — get a structured root-cause verdict from Claude, with caching and cost telemetry.

`EventController` is the single HTTP surface for all four of these needs, scoped to a single `eventId`.

---

## 2. Dependencies to Wire Up First

Before writing the controller, the following types must already exist and be registered in `Program.cs`.

| Dependency | Interface / Type | Registration | Notes |
|---|---|---|---|
| Event data store | `IEventRepository` | `AddSingleton` | Loads `data/EventLogs.json`; provides `GetEventLineage` and `GetEventLogById` |
| LLM orchestration | `IInvestigationService` | `AddScoped` or `AddSingleton` | Wraps `ILlmService` + `IMemoryCache`; returns `(InvestigationResult, bool fromCache, LlmCompletionResult?)` |
| Telemetry store | `ITelemetryRepository` | `AddSingleton` | In-memory ring buffer; `Add(InvestigationTelemetryEvent)` |
| Root-cause catalog | `RootCauseCatalogService` | `AddSingleton` | Loads `data/RootCauses.json`; `GetRecommendedAction(RootCause)` |
| LLM config | `IOptions<ClaudeOptions>` | `Configure<ClaudeOptions>` | Provides `MaxPromptChars` |
| Logging | `ILogger<EventController>` | Built-in ASP.NET Core DI | — |

---

## 3. Models to Define

### 3.1 Input / lookup models (already exist)

| Model | File | Role |
|---|---|---|
| `EventLog` | `Models/EventLog.cs` | Raw record from `EventLogs.json`; source for both lineage projection and LLM prompt |
| `EventLineage` | `Models/EventLineage.cs` | Projected view: per-stage success flags, missing audit events, publish latency |

### 3.2 Response models

| Model | File | Returned by |
|---|---|---|
| `EventLineage` | `Models/EventLineage.cs` | `GET /{eventId}/lineage` |
| `EventLogResponse` | `Models/EventLogResponse.cs` | `GET /{eventId}/logs` — wraps `EventLog`, strips `ScenarioMetadata` |
| `InvestigationResponse` | `Models/InvestigationResponse.cs` | `POST /{eventId}/investigations` |
| `InvestigationResult` | `Models/InvestigationResult.cs` | Nested inside `InvestigationResponse`; LLM verdict (`RootCause`, `Explanation`, `Confidence`) |
| `LlmUsageTelemetry` | `Models/InvestigationTelemetryEvent.cs` | Nested inside `InvestigationResponse`; token counts + estimated cost |

### 3.3 Telemetry models (emitted, not returned)

| Model | File | Purpose |
|---|---|---|
| `InvestigationTelemetryEvent` | `Models/InvestigationTelemetryEvent.cs` | Written to `ITelemetryRepository` after each investigation |
| `InvestigationResponseTelemetry` | `Models/InvestigationTelemetryEvent.cs` | Nested: response time, cache flag, confidence, root cause, LLM usage |
| `InvestigationValidationTelemetry` | `Models/InvestigationTelemetryEvent.cs` | Nested: expected vs actual root cause, match flag |

---

## 4. Helpers to Implement First

### 4.1 `PromptHelper.BuildInvestigationPrompt(EventLog, int maxChars)`

- **File:** `Helper/PromptHelper.cs`
- **Behaviour:**
  - Loads `prompts/investigation-prompt.md` once at class init (static field).
  - Loads `config/pipeline-config.json` and `config/llm-response-schema.json` once at class init.
  - Substitutes `{{sla.publishLatencyThresholdMinutes}}` and `{{llm_response_schema}}` into the system prompt.
  - Appends per-request dynamic data: `EventId`, `EventType`, `EventSource`, merged audit events + worker logs (pretty-printed JSON).
  - Throws `InvalidOperationException` if the assembled prompt exceeds `maxChars`.
- **Why needed by controller:** `GET /{eventId}/prompt` calls this directly; `POST /{eventId}/investigations` calls it indirectly via `IInvestigationService`.

### 4.2 `LlmCostHelper.CalculateRoundedCostUsd(LlmCompletionResult)`

- **File:** `Helper/LlmCostHelper.cs`
- **Behaviour:** Applies Claude pricing (input / output / cache-read token rates) and rounds to 2 decimal places.
- **Why needed by controller:** Used when building `LlmUsageTelemetry` inside `Investigate`.

---

## 5. Rate Limiting

Register a named rate-limit policy `"llm-investigation"` in `Program.cs` **before** writing the controller:

```csharp
builder.Services.AddRateLimiter(options =>
{
    options.AddFixedWindowLimiter("llm-investigation", opt =>
    {
        opt.PermitLimit       = 10;   // tune to your LLM budget
        opt.Window            = TimeSpan.FromMinutes(1);
        opt.QueueProcessingOrder = QueueProcessingOrder.OldestFirst;
        opt.QueueLimit        = 0;
    });
});
```

The `[EnableRateLimiting("llm-investigation")]` attribute on `Investigate` references this policy by name.

---

## 6. Controller Skeleton

```csharp
[ApiController]
[Route("events")]
[Produces("application/json")]
[Authorize(Roles = "user")]
public class EventController : ControllerBase
{
    private readonly IEventRepository          _eventRepository;
    private readonly IInvestigationService     _investigationService;
    private readonly ITelemetryRepository      _telemetryStore;
    private readonly RootCauseCatalogService   _rootCauseCatalog;
    private readonly ClaudeOptions             _claudeOptions;
    private readonly ILogger<EventController>  _logger;

    public EventController(
        IEventRepository eventRepository,
        IInvestigationService investigationService,
        ITelemetryRepository telemetryStore,
        RootCauseCatalogService rootCauseCatalog,
        IOptions<ClaudeOptions> claudeOptions,
        ILogger<EventController> logger) { … }
}
```

---

## 7. Endpoint Implementation Plan

### 7.1 `GET /events/{eventId}/lineage` → `GetLineageByEventId`

**Goal:** Return the projected `EventLineage` for a given event.

**Steps:**
1. Call `_eventRepository.GetEventLineage(eventId)`.
2. If `null` → `404 NotFound` with `{ message: "Event '{eventId}' not found." }`.
3. Otherwise → `200 OK` with the `EventLineage` object.

**Return type:** `ActionResult<EventLineage>`

**No async needed** — repository is synchronous (in-memory).

---

### 7.2 `GET /events/{eventId}/logs` → `GetLogsByEventId`

**Goal:** Return the raw audit events and worker logs, excluding internal test scenario metadata.

**Steps:**
1. Call `_eventRepository.GetEventLogById(eventId)`.
2. If `null` → `404 NotFound`.
3. Otherwise → `200 OK` with `EventLogResponse.FromEventLog(eventLog)`.
   - `EventLogResponse.FromEventLog` is a static factory that copies `AuditEvents` and `WorkerLogs` but omits `ScenarioMetadata`.

**Return type:** `ActionResult<EventLogResponse>`

**Design note:** The `FromEventLog` factory keeps the controller thin and ensures `ScenarioMetadata` is never accidentally serialised.

---

### 7.3 `GET /events/{eventId}/prompt` → `GetPrompt`

**Goal:** Return the fully-assembled LLM prompt string without invoking the LLM. Useful for debugging and prompt iteration.

**Steps:**
1. Call `_eventRepository.GetEventLogById(eventId)`.
2. If `null` → `404 NotFound`.
3. Call `PromptHelper.BuildInvestigationPrompt(eventLog, _claudeOptions.MaxPromptChars)`.
4. If `BuildInvestigationPrompt` throws `InvalidOperationException` (prompt too large):
   - Log a warning: `"Prompt for EventId={EventId} exceeds MaxPromptChars limit"`.
   - Return `422 UnprocessableEntity` with `{ message: ex.Message }`.
5. Otherwise → `200 OK` with `{ prompt: <string> }`.

**Return type:** `ActionResult<object>`

**Error handling:**

| Exception | HTTP status | Log level |
|---|---|---|
| `InvalidOperationException` | 422 | Warning |

---

### 7.4 `POST /events/{eventId}/investigations` → `Investigate`

**Goal:** Run an AI-powered root-cause investigation for the event. Cache results; emit telemetry; return structured verdict.

**Attributes:**
- `[EnableRateLimiting("llm-investigation")]`
- `[HttpPost("{eventId}/investigations")]`

**Steps:**

#### Step 1 — Resolve the event log
```
eventLog = _eventRepository.GetEventLogById(eventId)
if null → 404 NotFound
```

#### Step 2 — Start a stopwatch
```csharp
var sw = Stopwatch.StartNew();
```
Measures total response time including cache lookup.

#### Step 3 — Call the investigation service
```csharp
var (result, fromCache, llmMetadata) = await _investigationService.InvestigateAsync(eventLog);
sw.Stop();
```
- `result` — `InvestigationResult` (RootCause, Explanation, Confidence)
- `fromCache` — `bool`; drives the `X-Cache` response header
- `llmMetadata` — `LlmCompletionResult?`; `null` on a cache hit

#### Step 4 — Set `X-Cache` response header
```csharp
Response.Headers["X-Cache"] = fromCache ? "HIT" : "MISS";
```

#### Step 5 — Build `LlmUsageTelemetry`
```csharp
var llmUsage = llmMetadata is null ? null : new LlmUsageTelemetry
{
    Model            = llmMetadata.Model,
    InputTokens      = llmMetadata.InputTokens,
    OutputTokens     = llmMetadata.OutputTokens,
    CachedTokens     = llmMetadata.CachedTokens,
    EstimatedCostUsd = LlmCostHelper.CalculateRoundedCostUsd(llmMetadata)
};
```
`null` on cache hit — no LLM call was made, so no cost to report.

#### Step 6 — Resolve lineage for `EventContext`
```csharp
var lineage = _eventRepository.GetEventLineage(eventId);
```
Passed through in the response so callers can correlate the LLM verdict with structured pipeline stage data without a separate round-trip.

#### Step 7 — Build and store telemetry
```csharp
var telemetry = new InvestigationTelemetryEvent
{
    TelemetryType = "InvestigationCompleted",
    Timestamp     = DateTimeOffset.UtcNow,
    IncidentId    = null,   // event-driven — no incident
    EventId       = eventId,
    Response      = new InvestigationResponseTelemetry
    {
        ResponseTimeMs = sw.ElapsedMilliseconds,
        Cached         = fromCache,
        Confidence     = result.Confidence,
        RootCause      = result.RootCause,
        LlmUsage       = llmUsage
    },
    Validation = new InvestigationValidationTelemetry
    {
        ExpectedRootCause = eventLog.ScenarioMetadata?.ExpectedRootCause,
        ActualRootCause   = result.RootCause,
        RootCauseMatch    = eventLog.ScenarioMetadata?.ExpectedRootCause.HasValue == true
                               ? eventLog.ScenarioMetadata.ExpectedRootCause == result.RootCause
                               : null
    }
};
_telemetryStore.Add(telemetry);
```

**`IncidentId = null`** distinguishes event-driven investigations from incident-driven ones (which set a real `IncidentId`).

**`RootCauseMatch`** is `null` when the event has no `ExpectedRootCause` label (i.e. it is not a labelled test scenario).

#### Step 8 — Log structured telemetry
```csharp
_logger.LogInformation(
    "Investigation telemetry recorded: EventId={EventId} RootCause={RootCause} Cached={Cached} ResponseTimeMs={ResponseTimeMs} EstimatedCostUsd={EstimatedCostUsd}",
    eventId, result.RootCause, fromCache, sw.ElapsedMilliseconds, llmUsage?.EstimatedCostUsd);
```

#### Step 9 — Return `200 OK`
```csharp
return Ok(new InvestigationResponse
{
    Investigation    = result,
    EventContext     = lineage,
    RootCauseCatalog = _rootCauseCatalog,
    LlmUsage         = llmUsage
});
```

`RootCauseCatalog` is `[JsonIgnore]` on `InvestigationResponse`; it is set so the computed `RecommendedAction` property can resolve the action string from the catalog without serialising the catalog itself.

#### Error handling

| Exception | `sw.Stop()` | HTTP status | Log level | Message |
|---|---|---|---|---|
| `HttpRequestException` | Yes | 502 Bad Gateway | Error | `"LLM service unavailable."` |
| `InvalidOperationException` | Yes | 500 Internal Server Error | Error | `"Investigation failed."` |

**Return type:** `Task<ActionResult<InvestigationResponse>>`

---

## 8. `InvestigationResponse` — Computed Property Note

`InvestigationResponse.RecommendedAction` is a **computed property**, not a constructor parameter:

```csharp
public string RecommendedAction =>
    RootCauseCatalog?.GetRecommendedAction(Investigation.RootCause)
    ?? "Manual review required — evidence is ambiguous or contradictory.";
```

This means the controller must set `RootCauseCatalog` on the response object (even though it is `[JsonIgnore]`) so the serialiser can call `RecommendedAction` and include it in the JSON output.

---

## 9. XML Documentation Requirements

Every public member must carry `<summary>` and `<param>` XML doc comments so they appear in Swagger UI (the project includes XML comments via `IncludeXmlComments` in `Program.cs`).

Minimum required:
- Class-level `<summary>` describing all four endpoint groups.
- Each endpoint method: `<summary>`, `<remarks>` (for non-trivial endpoints), `<param name="eventId">`.

---

## 10. Build & Test Checklist

- [ ] All six constructor parameters resolve from DI without `InvalidOperationException` at startup.
- [ ] `GET /events/evt-001/lineage` returns `200` with `EventLineage` JSON.
- [ ] `GET /events/evt-999/lineage` returns `404` with `{ message: "Event 'evt-999' not found." }`.
- [ ] `GET /events/evt-001/logs` returns `200`; response does **not** contain `scenarioMetadata`.
- [ ] `GET /events/evt-001/prompt` returns `200` with `{ prompt: "…" }`.
- [ ] `POST /events/evt-001/investigations` returns `200`; `X-Cache: MISS` on first call, `X-Cache: HIT` on second call.
- [ ] `POST /events/evt-001/investigations` with LLM unavailable returns `502`.
- [ ] Rate limiter rejects excess requests to `POST /events/{eventId}/investigations` with `429`.
- [ ] Telemetry record appears in `GET /telemetry` after a successful investigation.
- [ ] Unauthenticated request returns `401`.

---

## 11. File Creation Order

1. `Models/EventLog.cs`
2. `Models/AuditEvent.cs`, `Models/WorkerLog.cs`, `Models/ScenarioMetadata.cs`
3. `Models/EventLineage.cs`
4. `Models/EventLogResponse.cs`
5. `Models/InvestigationResult.cs`
6. `Models/InvestigationTelemetryEvent.cs` (includes `LlmUsageTelemetry`, `InvestigationResponseTelemetry`, `InvestigationValidationTelemetry`)
7. `Models/InvestigationResponse.cs`
8. `Models/ClaudeModels.cs` (includes `ClaudeOptions`)
9. `Models/RootCause.cs` (enum)
10. `Interfaces/IEventRepository.cs`
11. `Interfaces/IInvestigationService.cs`
12. `Interfaces/ITelemetryRepository.cs`
13. `Helper/LlmCostHelper.cs`
14. `Helper/PromptHelper.cs`
15. `Services/RootCauseCatalogService.cs`
16. `Services/InvestigationService.cs`
17. `Repository/EventRepository.cs`
18. `Repository/TelemetryRepository.cs`
19. `Program.cs` — register all services + rate limiter policy
20. **`Controllers/EventController.cs`** ← this file
