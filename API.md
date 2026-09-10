# REST API Reference — FinancialEventCollector

Interactive docs (Swagger UI) are served at the root of each runtime:

| Runtime | URL |
|---|---|
| .NET (ASP.NET Core) | `http://localhost:5000` |
| Python (FastAPI) | `http://localhost:8000/docs` |

This document adds auth context, business semantics, and error tables that
Swagger does not auto-generate.

---

## Authentication

All endpoints require the `X-Api-Key` header. Two keys are configured:

| Key config | Role granted | Accessible endpoints |
|---|---|---|
| `ApiKey:UserSecret` | `user` | `/events/*`, `/incidents/*`, `/telemetry` |
| `ApiKey:AdminSecret` | `admin` | All `user` endpoints + `/validation/*`, `/admin/*` |

The admin key grants both `admin` and `user` claims — admin callers can access
every endpoint without needing separate keys.

**Demo keys** (defaults in [`appsettings.json`](dotnet/src/appsettings.json)):

| Role | Key value |
|---|---|
| admin | `AdminSecret` |
| user | `UserSecret` |

**Example:**
```http
GET /incidents HTTP/1.1
X-Api-Key: UserSecret
```

### Error Responses

| Status | Meaning |
|---|---|
| `401 Unauthorized` | `X-Api-Key` header is missing or the key is invalid |
| `403 Forbidden` | Key is valid but the role is insufficient for this endpoint |
| `429 Too Many Requests` | Rate limit exceeded (10 LLM calls/minute per IP) |

---

## Events

### `GET /events/{eventId}/lineage`

Returns the data lineage view for a single pipeline event.

**Auth:** `user`

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `eventId` | `string` | Pipeline event ID (e.g. "evt-001") |

**Response:** `200 OK`
```json
{
  "eventId": "evt-001",
  "eventType": "InvoiceCreated",
  "eventSource": "InvoicingService",
  "ingestSuccess": true,
  "indexSuccess": true,
  "publishSuccess": true,
  "auditEventsPresent": ["IngestAuditEvent", "IndexAuditEvent", "PublishAuditEvent"],
  "missingAuditEvents": [],
  "publishLatencySeconds": 4.2,
  "publishLatencySlaMet": true
}
```

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No event with the given ID exists |

---

### `GET /events/{eventId}/logs`

Returns the raw audit events and worker logs for a single pipeline event.
Exposes the underlying telemetry records that feed the lineage projection and
the LLM investigation prompt. Internal test scenario metadata is excluded.

**Auth:** `user`

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `eventId` | `string` | Pipeline event ID (e.g. "evt-001") |

**Response:** `200 OK`
```json
{
  "eventId": "evt-001",
  "eventType": "InvoiceCreated",
  "eventSource": "InvoicingService",
  "auditEvents": [
    {
      "name": "IngestAuditEvent",
      "telemetryType": "EventTelemetry",
      "sourceEventTimestamp": "2026-09-08T17:20:00Z",
      "publishingTimestamp": null
    }
  ],
  "workerLogs": [
    {
      "level": "Warning",
      "message": "Retry attempt 1 for EventId evt-001"
    }
  ]
}
```

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No event with the given ID exists |

---

### `GET /events/{eventId}/prompt`

Returns the fully-assembled LLM investigation prompt for the given event
**without** invoking the LLM. Useful for debugging, prompt iteration, and
auditing exactly what data is sent to the external AI service.

**Auth:** `user`

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `eventId` | `string` | Pipeline event ID (e.g. "evt-001") |

**Response:** `200 OK`
```json
{ "prompt": "You are an on-call engineer for a distributed event pipeline..." }
```

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No event with the given ID exists |
| `422 Unprocessable Entity` | Assembled prompt exceeds the configured `MaxPromptChars` limit |

---

### `POST /events/{eventId}/investigations`

Runs an AI-powered root-cause investigation for the given pipeline event.

**Auth:** `user`
**Rate limit:** 10 requests/minute per IP

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `eventId` | `string` | Pipeline event ID (e.g. "evt-001") |

No request body is required — all data needed for the investigation is stored
in `data/EventLogs.json`.

**Response headers:**

| Header | Values | Meaning |
|---|---|---|
| `X-Cache` | `HIT` / `MISS` | Whether the result was served from the in-memory cache |

**Response:** `200 OK` — same shape as `POST /incidents/{id}/investigations`

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No event with the given ID exists |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Investigation failed (e.g. LLM response failed schema validation) |
| `502 Bad Gateway` | Claude API is unreachable |

---

## Incidents

### `GET /incidents`

Returns all available incidents.

**Auth:** `user`

**Response:** `200 OK`
```json
[
  {
    "incidentId": 1,
    "incidentTitle": "Missing InvoiceCreated Event",
    "eventId": "evt-001"
  }
]
```

---

### `GET /incidents/{id}`

Returns a single incident by ID.

**Auth:** `user`

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `id` | `int` | Incident ID (1–6 for seed scenarios) |

**Response:** `200 OK` — same shape as a single element from `GET /incidents`

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No incident with the given ID exists |

---

### `GET /incidents/{id}/prompt`

Returns the fully-assembled LLM investigation prompt for the given incident
**without** invoking the LLM. Useful for debugging, prompt iteration, and
auditing exactly what data is sent to the external AI service.

**Auth:** `user`

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `id` | `int` | Incident ID |

**Response:** `200 OK`
```json
{ "prompt": "You are an on-call engineer for a distributed event pipeline..." }
```

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No incident with the given ID exists |
| `422 Unprocessable Entity` | Assembled prompt exceeds the configured `MaxPromptChars` limit |

---

### `POST /incidents/{id}/investigations`

Runs an AI-powered root-cause investigation for the given incident.

**Auth:** `user`  
**Rate limit:** 10 requests/minute per IP

**Path parameters:**

| Name | Type | Description |
|---|---|---|
| `id` | `int` | Incident ID |

No request body is required — all data needed for the investigation is stored
in `shared/data/EventLogs.json`.

**Response headers:**

| Header | Values | Meaning |
|---|---|---|
| `X-Cache` | `HIT` / `MISS` | Whether the result was served from the in-memory cache |

**Response:** `200 OK`
```json
{
  "investigation": {
    "rootCause": "MissingPublishingAuditEvent",
    "confidence": "HIGH",
    "explanation": "IngestAuditEvent and IndexAuditEvent are present for evt-004, but no PublishAuditEvent was recorded. The PublishingWorker logged a connection retry limit exceeded error at 17:25:46 UTC."
  },
  "eventContext": {
    "eventId": "evt-004",
    "eventType": "InvoiceCreated",
    "eventSource": "InvoicingService",
    "ingestSuccess": true,
    "indexSuccess": true,
    "publishSuccess": false,
    "auditEventsPresent": ["IngestAuditEvent", "IndexAuditEvent"],
    "missingAuditEvents": ["PublishAuditEvent"],
    "publishLatencySeconds": null,
    "publishLatencySlaMet": null
  },
  "recommendedAction": "Replay the event through the Publish worker. Check EventHub connectivity and retry limits.",
  "llmUsage": {
    "model": "claude-sonnet-4-6",
    "inputTokens": 1240,
    "outputTokens": 87,
    "cachedTokens": 0,
    "estimatedCostUsd": 0.04
  }
}
```

`eventContext` is the projected data lineage for the pipeline event — the same
evidence the LLM reasoned over — so callers can correlate the verdict with
structured, machine-readable pipeline stage data without a separate
`GET /events/{eventId}/lineage` round-trip.

`eventContext.publishLatencySeconds` and `eventContext.publishLatencySlaMet`
are `null` when the publish audit event is missing.
`llmUsage` is `null` when the result was served from cache.

**Errors:**

| Status | Condition |
|---|---|
| `404 Not Found` | No incident with the given ID exists |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Investigation failed (e.g. LLM response failed schema validation) |
| `502 Bad Gateway` | Claude API is unreachable |

---

## Telemetry

### `GET /telemetry`

Returns the most recent investigation telemetry events in ascending
chronological order. The telemetry store is in-memory and resets on restart.

**Auth:** `user`

**Query parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `limit` | `int` | `10` | Maximum events to return. Clamped to [1, 100]. |

**Response:** `200 OK`
```json
[
  {
    "telemetryType": "InvestigationCompleted",
    "timestamp": "2026-09-08T20:30:00Z",
    "incidentId": 4,
    "eventId": "evt-004",
    "response": {
      "cached": false,
      "confidence": "HIGH",
      "rootCause": "MissingPublishingAuditEvent",
      "responseTimeMs": 1842,
      "llmUsage": {
        "model": "claude-sonnet-4-6",
        "inputTokens": 1240,
        "outputTokens": 87,
        "cachedTokens": 0,
        "estimatedCostUsd": 0.04
      }
    },
    "validation": {
      "expectedRootCause": "MissingPublishingAuditEvent",
      "actualRootCause": "MissingPublishingAuditEvent",
      "rootCauseMatch": true
    }
  }
]
```

`validation.expectedRootCause` and `validation.rootCauseMatch` are `null` for
incidents that have no human-authored ground-truth label.

`incidentId` is `null` for event-driven investigations that are not associated
with an incident (i.e. triggered via `POST /events/{eventId}/investigations`).

---

## Validation

### `POST /validation/run`

Runs the investigation pipeline for every incident scenario and compares the
LLM's verdict against the human-authored ground-truth label stored in
`ScenarioMetadata.ExpectedRootCause` on the associated event log. Used for
regression testing the LLM prompt and measuring overall accuracy and cost.
The in-memory cache is always bypassed — every incident is sent directly to
the LLM.

**Auth:** `admin`  
**Rate limit:** 10 requests/minute per IP

**Query parameters:**

| Name | Type | Default | Description |
|---|---|---|---|
| `limit` | `int` | `10` | Maximum incidents to process (1–10) |

**Response:** `200 OK`
```json
{
  "results": [
    {
      "incidentId": 1,
      "scenarioName": "AllAuditEventsPresent",
      "expectedRootCause": "AllAuditEventsPresent",
      "actualRootCause": "AllAuditEventsPresent",
      "rootCauseMatch": true,
      "confidence": "HIGH",
      "fromCache": false,
      "responseTimeMs": 1654,
      "estimatedCostUsd": 0.03
    }
  ],
  "totalScenarios": 6,
  "labelledScenarios": 6,
  "correctPredictions": 6,
  "accuracyPercent": 100.0,
  "totalCostUsd": 0.14
}
```

`accuracyPercent` is `null` when no labelled scenarios exist.
`estimatedCostUsd` per result is `null` when served from cache.

**Errors:**

| Status | Condition |
|---|---|
| `400 Bad Request` | `limit` is outside the range [1, 10] |
| `429 Too Many Requests` | Rate limit exceeded |

---

## Admin

### `GET /admin/config`

Returns a full snapshot of the current runtime configuration. Useful for
verifying which model, cache TTL, and API base URL are active without
restarting the service.

**Auth:** `admin`

**Response:** `200 OK`
```json
{
  "environment": "Production",
  "application": "FinancialEventCollector",
  "version": "1.0.0.0",
  "llm": {
    "model": "claude-sonnet-4-6",
    "maxTokens": 1024,
    "apiBaseUrl": "https://api.anthropic.com",
    "apiVersion": "2023-06-01"
  },
  "cache": {
    "enabled": true,
    "ttlHours": 24
  },
  "rootCauseValues": [
    {
      "name": "AllAuditEventsPresent",
      "description": "All three audit events are present and within normal timing."
    }
  ]
}
```
