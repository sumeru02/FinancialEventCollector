# FinancialEventCollector

**FinancialEventCollector** is a financial event ingestion, indexing, and
publishing service with endpoints for data lineage lookup and missing-event
investigation.

A missing event has real downstream consequences — e.g. a missing
`InvoiceCreated` event can mean an invoice PDF never gets generated at
month-end close, or that downstream financial calculations run against
incomplete data. When a missing or delayed event is detected, the service
uses Claude to classify Missing and Lagging Events automatically, so on-call engineers get a structured verdict with an explained `RootCause` instead of raw log triage.

**🌐 Azure Deployment:**
[https://financialeventcollector-bzf0e4htg8d7ecfr.westus2-01.azurewebsites.net/index.html](https://financialeventcollector-bzf0e4htg8d7ecfr.westus2-01.azurewebsites.net/index.html)

**📬 Postman Collection:**
[`FinancialEventCollector.postman_collection.json`](shared/postman/FinancialEventCollector.postman_collection.json) — targets the deployed Azure App Service; authentication via `X-Api-Key` header is pre-configured at the collection level.

---

## Quick Start

### Python (FastAPI)

```bash
# 1. Configure your Anthropic API key
cd python
cp .env.example .env
# Edit .env: CLAUDE__APIKEY=sk-ant-...

# 2. Run (from repo root)
python python/scripts/local.py

# 3. Open interactive docs
#    http://localhost:8000/docs
```

### .NET (ASP.NET Core)

```bash
# 1. Configure your Anthropic API key
#    Edit dotnet/src/appsettings.json and set Claude:ApiKey
#    or set the environment variable: CLAUDE__APIKEY=sk-ant-...

# 2. Run
cd dotnet/src
dotnet run

# 3. Open Swagger UI
#    http://localhost:5000
```

---

## Scenario Reference

Six seed scenarios are pre-loaded and ready to investigate:

| Scenario | EventId | IncidentId | Expected `RootCause` |
|---|---|---|---|
| All stages healthy | `evt-001` | 1 | `AllAuditEventsPresent` |
| Missing ingest | `evt-002` | 2 | `MissingIngestionAuditEvent` |
| Missing index | `evt-003` | 3 | `MissingIndexingAuditEvent` |
| Missing publish | `evt-004` | 4 | `MissingPublishingAuditEvent` |
| Publish latency exceeds SLA | `evt-005` | 5 | `PublishLatencyExceedsSLA` |
| Unknown root cause | `evt-006` | 6 | `Unknown` |

Investigations can be triggered via either entry point:

- `POST /incidents/{id}/investigations` — by incident ID
- `POST /events/{eventId}/investigations` — by event ID directly

Both return an AI-generated `RootCause`, confidence level, and explanation.

---

## Documentation

| Document | Description |
|---|---|
| [SETUP.md](SETUP.md) | Full setup instructions for both runtimes (Python + .NET), including virtual environments, environment variables, and test commands |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design: pipeline stages, LLM investigation flow, auth model, data model, and dual-runtime layout |
| [API.md](API.md) | REST API reference: all endpoints, authentication, request/response schemas, and error codes |
| [MCP (v-next)](wiki/vnext/mcp.md) | Planned: exposing the service as a Model Context Protocol server for Claude Desktop and Cursor |
| [Wiki](wiki/index.md) | Migration plans, parity tracking, and integration design notes |

---

## Repository Layout

```
/
├── dotnet/          .NET 8 / ASP.NET Core implementation
├── python/          Python 3.12 / FastAPI implementation
├── shared/          Config, data, and prompts shared by both runtimes
│   ├── config/      pipeline-config.json, llm-response-schema.json, app-config.json
│   ├── data/        Incidents.json, EventLogs.json, RootCauses.json
│   └── prompts/     investigation-prompt.md
└── wiki/            Planning documents, migration notes, integration guides
```
