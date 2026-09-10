# Migration Plan: Python Port + Monorepo Restructure

## Overview

This document captures the full plan to:
1. Restructure the repository into a clean `dotnet/` + `python/` monorepo layout
2. Extract hardcoded business logic into shared JSON config files consumed by both runtimes
3. Build a Python (FastAPI) port of the existing C# API service

---

## Phase 1 — Restructure the Repository

### Target Folder Layout

```
FinancialEventCollector/
  data/                                     ← shared, language-agnostic config & test data
    root-causes.json                        ← RootCause enum + descriptions + recommendedActions
    pipeline-config.json                    ← SLA threshold, stage maps, worker log filter rules
    llm-response-schema.json                ← JSON Schema for LLM output validation
    Incidents.json                          ← test scenarios (promoted from src/Data/)
    Prompts/
      investigation-prompt.md              ← templatized with {{placeholders}}

  dotnet/
    FinancialEventCollector.sln             ← moved from root
    src/                                    ← moved from root src/
      FinancialEventCollector.csproj
      appsettings.json
      appsettings.Development.json
      Program.cs
      Controllers/
      Models/
      Interfaces/
      Helper/
      Extensions/
      Data/                                 ← build-output copies only (MSBuild copies from root data/)
    tests/                                  ← moved from root tests/
      FinancialEventCollector.Tests.csproj
      IntegrationTests.cs
      TestBase.cs
      Properties/

  python/
    app/
      main.py                               ← FastAPI app + lifespan (≈ Program.cs)
      config.py                             ← Pydantic Settings (≈ appsettings.json + ClaudeOptions)
      routers/
        incident_router.py                  ← ≈ IncidentController.cs
        config_router.py                    ← ≈ ConfigController.cs
        telemetry_router.py                 ← ≈ TelemetryController.cs
      models/
        investigation.py                    ← InvestigationResult, InvestigationResponse (Pydantic)
        root_cause.py                       ← RootCause enum (loaded from data/root-causes.json)
        incident.py                         ← Incident, AuditEvent, WorkerLog (Pydantic)
        telemetry.py                        ← InvestigationTelemetryEvent (Pydantic)
      services/
        investigation_service.py            ← ≈ IInvestigationService impl
        llm_service.py                      ← ≈ ILlmService / ClaudeService
        incident_data_service.py            ← ≈ IIncidentDataService impl
        telemetry_store.py                  ← ≈ ITelemetryStore impl
      helpers/
        prompt_helper.py                    ← ≈ PromptHelper.cs
    tests/
      test_investigation.py
      test_incidents.py
      test_config.py
    pyproject.toml
    config.json                             ← runtime config (API keys via env vars)

  README.md
  wiki/migration/python-migration-plan.md   ← this file
```

### Files to Move

| File / Folder | From | To | Notes |
|---|---|---|---|
| `FinancialEventCollector.sln` | root | `dotnet/` | Project paths remain valid — `src/` and `tests/` are still siblings of the `.sln` |
| `src/` | root | `dotnet/src/` | Update `.csproj` `<Content>` paths for `Data/` files |
| `tests/` | root | `dotnet/tests/` | Update `<ProjectReference>` path to `src/` |
| `src/Data/Incidents.json` | `src/Data/` | `data/Incidents.json` | Promote to shared; update `.csproj` copy path |
| `src/Data/Prompts/investigation-prompt.md` | `src/Data/Prompts/` | `data/Prompts/` | Promote to shared; update `.csproj` copy path |

### `.csproj` Copy Path Update

After moving shared data to root `data/`, update the copy directive in `dotnet/src/FinancialEventCollector.csproj`:

```xml
<!-- Before -->
<Content Include="Data\**\*" CopyToOutputDirectory="PreserveNewest" />

<!-- After -->
<Content Include="..\..\data\**\*" CopyToOutputDirectory="PreserveNewest" />
<CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
```

---

## Phase 2 — Extract Shared JSON Config

### 2.1 `data/root-causes.json`

**Eliminates:**
- The `switch` expression in `InvestigationResponse.RecommendedAction` (C#)
- The description dictionary in `ConfigController.BuildRootCauseCatalog()` (C#)
- Duplicated descriptions in `RootCause.cs` XML doc comments

**Schema:**

```json
{
  "rootCauses": [
    {
      "name": "AllAuditEventsPresent",
      "ordinal": 0,
      "description": "All three audit events are present and within normal timing — no issue detected.",
      "recommendedAction": "Transfer incident to the Downstream team consuming from Collector EventHub — all three audit events are present, confirming a successful Collector publish. The issue is likely in their EventHub reader or downstream service.",
      "team": "Downstream"
    },
    {
      "name": "MissingIngestionAuditEvent",
      "ordinal": 1,
      "description": "No IngestAuditEvent recorded — the event never entered the pipeline.",
      "recommendedAction": "Collector on-call: re-ingest the missing event from the upstream InvoicingService — no IngestAuditEvent was recorded, so the event never entered the Collector pipeline.",
      "team": "Collector"
    },
    {
      "name": "MissingIndexingAuditEvent",
      "ordinal": 2,
      "description": "No IndexAuditEvent recorded — the index worker failed or was skipped.",
      "recommendedAction": "Collector on-call: trigger a re-index for this event — the event exists in Collector Blob Storage (IngestAuditEvent is present) but the IndexAuditEvent was not recorded.",
      "team": "Collector"
    },
    {
      "name": "MissingPublishingAuditEvent",
      "ordinal": 3,
      "description": "No PublishAuditEvent recorded — the event never reached downstream consumers.",
      "recommendedAction": "Collector on-call: trigger a re-publish for this event — the event exists in Collector Blob Storage (IngestAuditEvent is present) but the PublishAuditEvent was not recorded.",
      "team": "Collector"
    },
    {
      "name": "PublishLatencyExceedsSLA",
      "ordinal": 4,
      "description": "All three audit events are present but elapsed time between IngestAuditEvent and PublishAuditEvent exceeds the SLA threshold.",
      "recommendedAction": "Collector on-call: investigate the publish pipeline for bottlenecks — all three audit events are present but the Ingest-to-Publish gap exceeds the SLA threshold. No data loss has occurred, but SLA has been breached.",
      "team": "Collector"
    },
    {
      "name": "Unknown",
      "ordinal": 5,
      "description": "Evidence is ambiguous or contradictory; manual review required.",
      "recommendedAction": "Manual review required — evidence is ambiguous or contradictory. Escalate with the full correlated event log for this EventId.",
      "team": "Escalation"
    }
  ]
}
```

**C# usage:** Load once at startup; `InvestigationResponse.RecommendedAction` becomes a dictionary lookup keyed by `RootCause` enum value.

**Python usage:** Load into a `dict[RootCause, RootCauseEntry]`; `InvestigationResponse.recommended_action` is a computed Pydantic field doing the same lookup.

---

### 2.2 `data/pipeline-config.json`

**Eliminates:**
- `PromptHelper.ResolveAuditStage()` switch expression (C#)
- `PromptHelper.ResolveWorkerStage()` switch expression (C#)
- Hardcoded `15 minutes` SLA value in `investigation-prompt.md`

**Schema:**

```json
{
  "sla": {
    "publishLatencyThresholdMinutes": 15
  },
  "auditEventStageMap": {
    "IngestAuditEvent":  { "stage": "Ingest",  "timestampField": "ingestionTimestamp"  },
    "IndexAuditEvent":   { "stage": "Index",   "timestampField": "indexingTimestamp"   },
    "PublishAuditEvent": { "stage": "Publish", "timestampField": "publishingTimestamp" }
  },
  "workerStageKeywords": [
    { "keyword": "Ingest",  "stage": "Ingest"  },
    { "keyword": "Index",   "stage": "Index"   },
    { "keyword": "Publish", "stage": "Publish" }
  ],
  "nonBlockingStages": ["Index"],
  "workerLogLevelsToInclude": ["Error", "Warning"]
}
```

**C# usage:** `PromptHelper` loads this at startup; `ResolveAuditStage()` and `ResolveWorkerStage()` become dictionary/LINQ lookups.

**Python usage:** `prompt_helper.py` reads the same file; stage resolution is a simple dict lookup.

---

### 2.3 `data/llm-response-schema.json`

**Eliminates:**
- Hardcoded JSON schema block at the bottom of `investigation-prompt.md`
- Pipe-delimited enum list in the prompt (which can drift from the actual `RootCause` enum)

**Schema:**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["rootCause", "explanation", "confidence"],
  "properties": {
    "rootCause": {
      "type": "string",
      "enum": [
        "AllAuditEventsPresent",
        "MissingIngestionAuditEvent",
        "MissingIndexingAuditEvent",
        "MissingPublishingAuditEvent",
        "PublishLatencyExceedsSLA",
        "Unknown"
      ]
    },
    "explanation": { "type": "string" },
    "confidence":  { "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"] }
  }
}
```

**C# usage:** Inject the schema JSON into the prompt template at build time; optionally use `System.Text.Json` schema validation on the LLM response.

**Python usage:** Use `jsonschema.validate()` to validate the LLM response before deserializing.

---

### 2.4 Templatize `data/Prompts/investigation-prompt.md`

Replace hardcoded values with `{{placeholder}}` tokens that both runtimes substitute at runtime:

| Placeholder | Source |
|---|---|
| `{{sla.publishLatencyThresholdMinutes}}` | `pipeline-config.json` |
| `{{llm_response_schema}}` | `llm-response-schema.json` (pretty-printed) |

**C# substitution** in `PromptHelper.BuildInvestigationPrompt()`:
```csharp
template
    .Replace("{{sla.publishLatencyThresholdMinutes}}", pipelineConfig.Sla.PublishLatencyThresholdMinutes.ToString())
    .Replace("{{llm_response_schema}}", llmSchemaJson);
```

**Python substitution** in `prompt_helper.py`:
```python
template.replace("{{sla.publishLatencyThresholdMinutes}}", str(pipeline_config["sla"]["publishLatencyThresholdMinutes"]))
        .replace("{{llm_response_schema}}", json.dumps(llm_schema, indent=2))
```

---

## Phase 3 — Build the Python FastAPI Service

### Why FastAPI (not Flask)

| Feature | FastAPI | Flask |
|---|---|---|
| Pydantic models (like C# records) | ✅ Native | ❌ Third-party |
| Auto OpenAPI/Swagger docs at `/docs` | ✅ Native | ❌ Third-party |
| Async/await (ASGI) | ✅ Native | ⚠️ Bolted on (WSGI by default) |
| Type hints enforced at runtime | ✅ Yes | ❌ No |
| Closest to ASP.NET Core style | ✅ Yes | ❌ No |

FastAPI produces Python code that maps almost 1:1 to the C# structure, making the two codebases easy to compare and maintain in parallel.

### C# → Python Mapping

| C# | Python (FastAPI) |
|---|---|
| `record InvestigationResponse(...)` | `class InvestigationResponse(BaseModel)` |
| `record InvestigationResult(...)` | `class InvestigationResult(BaseModel)` |
| `enum RootCause` | `class RootCause(str, Enum)` loaded from `root-causes.json` |
| `IInvestigationService` | `Protocol` or abstract base class |
| `ILlmService` | `Protocol` or abstract base class |
| `ClaudeOptions` (IOptions) | `class Settings(BaseSettings)` (pydantic-settings) |
| `[HttpGet("{id:int}")]` | `@router.get("/{id}")` |
| `[HttpPost("{id:int}/investigations")]` | `@router.post("/{id}/investigations")` |
| `CancellationToken` | `asyncio.CancelledError` / `anyio` |
| `IMemoryCache` | `cachetools.TTLCache` or `aiocache` |
| `X-Cache` response header | `Response` object header injection |
| `ITelemetryStore` | In-memory list with `asyncio.Lock` |
| `PromptHelper` (static) | Module-level functions in `prompt_helper.py` |

### Key Python Files

#### `python/app/main.py`
```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.routers import incident_router, config_router, telemetry_router
from app.config import Settings

settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load shared JSON config once at startup
    # (equivalent to Program.cs service registration)
    yield

app = FastAPI(title="FinancialEventCollector", lifespan=lifespan)
app.include_router(incident_router.router, prefix="/incidents")
app.include_router(config_router.router, prefix="/admin")
app.include_router(telemetry_router.router, prefix="/telemetry")
```

#### `python/app/config.py`
```python
from pydantic_settings import BaseSettings

class ClaudeSettings(BaseSettings):
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024
    api_base_url: str = "https://api.anthropic.com"
    api_version: str = "2023-06-01"

    class Config:
        env_prefix = "CLAUDE__"   # matches C# Claude:ApiKey → CLAUDE__API_KEY

class CacheSettings(BaseSettings):
    ttl_hours: int = 24

    class Config:
        env_prefix = "CACHE__"

class Settings(BaseSettings):
    claude: ClaudeSettings = ClaudeSettings()
    cache: CacheSettings = CacheSettings()
```

#### `python/app/models/investigation.py`
```python
from pydantic import BaseModel, computed_field
from app.models.root_cause import RootCause, ROOT_CAUSE_CATALOG

class InvestigationResult(BaseModel):
    root_cause: RootCause
    explanation: str
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"

class InvestigationResponse(BaseModel):
    investigation: InvestigationResult
    publish_latency_seconds: float | None

    @computed_field
    @property
    def recommended_action(self) -> str:
        entry = ROOT_CAUSE_CATALOG.get(self.investigation.root_cause)
        return entry.recommended_action if entry else "Manual review required."
```

#### `python/app/models/root_cause.py`
```python
import json
from enum import Enum
from pathlib import Path
from dataclasses import dataclass

# Load from shared data/ folder
_catalog_path = Path(__file__).parents[4] / "data" / "root-causes.json"
_catalog_data = json.loads(_catalog_path.read_text())

class RootCause(str, Enum):
    ALL_AUDIT_EVENTS_PRESENT        = "AllAuditEventsPresent"
    MISSING_INGESTION_AUDIT_EVENT   = "MissingIngestionAuditEvent"
    MISSING_INDEXING_AUDIT_EVENT    = "MissingIndexingAuditEvent"
    MISSING_PUBLISHING_AUDIT_EVENT  = "MissingPublishingAuditEvent"
    PUBLISH_LATENCY_EXCEEDS_SLA     = "PublishLatencyExceedsSLA"
    UNKNOWN                         = "Unknown"

@dataclass
class RootCauseEntry:
    name: str
    ordinal: int
    description: str
    recommended_action: str
    team: str

ROOT_CAUSE_CATALOG: dict[RootCause, RootCauseEntry] = {
    RootCause(rc["name"]): RootCauseEntry(**rc)
    for rc in _catalog_data["rootCauses"]
}
```

---

## Phase 4 — Refactor C# to Consume Shared JSON Config

### 4.1 `InvestigationResponse.RecommendedAction`

**Before** (switch expression):
```csharp
public string RecommendedAction => Investigation.RootCause switch
{
    RootCause.AllAuditEventsPresent => "Transfer incident to the Downstream team...",
    // ...
};
```

**After** (dictionary lookup from loaded catalog):
```csharp
public string RecommendedAction =>
    RootCauseCatalog.GetRecommendedAction(Investigation.RootCause);
```

Where `RootCauseCatalog` is a singleton service loaded from `data/root-causes.json` at startup.

### 4.2 `PromptHelper` Stage Resolution

**Before** (switch expressions):
```csharp
private static (string Stage, DateTimeOffset? Timestamp) ResolveAuditStage(AuditEvent audit)
    => audit.Name switch
    {
        "IngestAuditEvent"  => ("Ingest",  audit.IngestionTimestamp),
        "IndexAuditEvent"   => ("Index",   audit.IndexingTimestamp),
        "PublishAuditEvent" => ("Publish", audit.PublishingTimestamp),
        _                   => ("Unknown", audit.CollectorStageTimestamp)
    };
```

**After** (dictionary lookup from `pipeline-config.json`):
```csharp
private static (string Stage, DateTimeOffset? Timestamp) ResolveAuditStage(AuditEvent audit)
{
    if (_pipelineConfig.AuditEventStageMap.TryGetValue(audit.Name, out var mapping))
        return (mapping.Stage, audit.GetTimestamp(mapping.TimestampField));
    return ("Unknown", audit.CollectorStageTimestamp);
}
```

### 4.3 `ConfigController.BuildRootCauseCatalog()`

**Before** (hardcoded dictionary):
```csharp
var descriptions = new Dictionary<RootCause, string>
{
    [RootCause.AllAuditEventsPresent] = "All three audit events are present...",
    // ...
};
```

**After** (read from loaded catalog):
```csharp
return _rootCauseCatalog.Entries
    .Select(e => new RootCauseEntry(e.Name, e.Ordinal, e.Description))
    .ToList()
    .AsReadOnly();
```

---

## Migration Checklist

### Phase 1 — Restructure
- [ ] Create `data/` folder at repo root
- [ ] Move `src/Data/Incidents.json` → `data/Incidents.json`
- [ ] Move `src/Data/Prompts/investigation-prompt.md` → `data/Prompts/investigation-prompt.md`
- [ ] Move `src/` → `dotnet/src/`
- [ ] Move `tests/` → `dotnet/tests/`
- [ ] Move `FinancialEventCollector.sln` → `dotnet/`
- [ ] Update `.csproj` `<Content>` copy paths to `..\..\data\**\*`
- [ ] Verify `dotnet build` and `dotnet test` still pass from `dotnet/`

### Phase 2 — Shared JSON Config
- [ ] Create `data/root-causes.json`
- [ ] Create `data/pipeline-config.json`
- [ ] Create `data/llm-response-schema.json`
- [ ] Templatize `data/Prompts/investigation-prompt.md` with `{{placeholders}}`
- [ ] Refactor `InvestigationResponse.RecommendedAction` to use catalog lookup
- [ ] Refactor `PromptHelper.ResolveAuditStage()` to use config map
- [ ] Refactor `PromptHelper.ResolveWorkerStage()` to use config map
- [ ] Refactor `ConfigController.BuildRootCauseCatalog()` to use catalog
- [ ] Verify all existing tests still pass

### Phase 3 — Python FastAPI Service
- [ ] Create `python/` folder structure
- [ ] Set up `pyproject.toml` with FastAPI, pydantic-settings, httpx, cachetools
- [ ] Implement `app/models/root_cause.py` (loads from `data/root-causes.json`)
- [ ] Implement `app/models/incident.py` (Pydantic, matches `Incidents.json` schema)
- [ ] Implement `app/models/investigation.py` (Pydantic, with `computed_field`)
- [ ] Implement `app/helpers/prompt_helper.py` (reads `pipeline-config.json`)
- [ ] Implement `app/services/llm_service.py` (Claude API via `httpx`)
- [ ] Implement `app/services/investigation_service.py` (with TTL cache)
- [ ] Implement `app/routers/incident_router.py`
- [ ] Implement `app/routers/config_router.py`
- [ ] Implement `app/routers/telemetry_router.py`
- [ ] Implement `app/main.py`
- [ ] Write integration tests in `python/tests/`
- [ ] Verify `/docs` Swagger UI matches C# `/swagger` output

---

## Dependency Summary

### Python (`pyproject.toml`)

```toml
[project]
name = "financial-event-collector"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "httpx>=0.27",          # async HTTP client for Claude API (≈ HttpClient)
    "cachetools>=5.3",      # TTLCache (≈ IMemoryCache)
    "jsonschema>=4.22",     # LLM response validation
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "httpx",                # also used as test client via TestClient
]
```
