# MCP Server Integration — High-Level Overview

This document describes how **FinancialEventCollector** could be extended to
support the
[Model Context Protocol (MCP)](https://modelcontextprotocol.io) so that AI
clients such as **Claude Desktop** or **Cursor** can discover and invoke the
service's capabilities as first-class tools.

---

## What is MCP?

MCP is an open standard (created by Anthropic) built on JSON-RPC 2.0 that lets
an AI client discover and call **tools**, **resources**, and **prompts** exposed
by a server. Instead of an AI model calling a REST API directly, it uses the MCP
protocol to discover available capabilities and invoke them autonomously during a
conversation.

```
┌─────────────────────────┐        JSON-RPC 2.0 (SSE)        ┌──────────────────────────────┐
│   MCP Client            │ ────────────────────────────────► │   MCP Server (this service)  │
│   Claude Desktop/Cursor │                                   │                              │
│                         │ ◄──────────────────────────────── │   Tools                      │
└─────────────────────────┘        tool results               │   • get_event_lineage        │
                                                              │   • investigate_event        │
                                                              │   • list_incidents           │
                                                              │   • investigate_incident     │
                                                              └──────────────────────────────┘
```

---

## Approach

MCP would be added **within the same ASP.NET Core process** as the existing REST
API using the official `ModelContextProtocol.AspNetCore` NuGet package. The
existing DI-registered services are reused directly — no business logic is
duplicated and the existing REST endpoints continue to work unchanged.

The MCP layer acts as a **thin adapter**: it translates MCP tool calls into
calls to the same service interfaces already used by the REST controllers.

---

## Capabilities Exposed as MCP Tools

Four tools map naturally onto the existing service layer:

| MCP Tool | Maps to | Description |
|---|---|---|
| `get_event_lineage` | `IEventRepository.GetEventLineage()` | Returns the data lineage view for a pipeline event — which stages succeeded, which are missing, and publish latency |
| `investigate_event` | `IEventRepository.GetEventLogById()` + `IInvestigationService` | Runs an AI-powered root-cause investigation directly against a pipeline event ID |
| `list_incidents` | `IIncidentRepository` | Returns all available incidents with their IDs and titles |
| `investigate_incident` | `IIncidentRepository` + `IEventRepository` + `IInvestigationService` | Runs an AI-powered root-cause investigation for a given incident ID |

These are the same operations already available via the REST API — MCP simply
provides an additional, AI-native interface to them.

---

## What an AI Client Can Do

Once connected, an AI client can autonomously chain tool calls during a
conversation:

| User asks | AI calls |
|---|---|
| "Show me the lineage for evt-003" | `get_event_lineage(eventId: "evt-003")` |
| "Investigate event evt-003 directly" | `investigate_event(eventId: "evt-003")` |
| "Which events failed to publish and why?" | `get_event_lineage` for each → `investigate_event` for failures |
| "What incidents are available?" | `list_incidents` |
| "Investigate incident 2" | `investigate_incident(incidentId: 2)` |
| "Which incidents have missing indexing events?" | `list_incidents` → `investigate_incident` for each |
| "Summarize all root causes" | Chains multiple `investigate_incident` calls |
| "Are there any HIGH confidence findings?" | Chains all investigations, filters by confidence |

---

## Architecture

```
AI Client (Claude Desktop / Cursor)
    │  MCP over SSE (/mcp)
    ▼
MCP Tool Adapter                        ← new, thin layer
    │
    ├─► IIncidentRepository             ← existing (unchanged)
    ├─► IEventRepository                ← existing (unchanged)
    │       ├─ GetEventLineage()
    │       └─ GetEventLogById()
    └─► IInvestigationService           ← existing (unchanged)
            │
            ├─► IMemoryCache            ← shared with REST controllers
            └─► ILlmService             ← existing abstraction (unchanged)
```

Key properties of this design:

- The **REST API** continues to work alongside the MCP endpoint — both share the
  same underlying services.
- The **memory cache** is shared: a result fetched via REST is served from cache
  when the AI client calls the MCP tool for the same event or incident, and vice
  versa.
- The **`ILlmService` abstraction** is preserved: the MCP layer never calls the
  LLM directly. Swapping the LLM provider requires no changes to the MCP tools.
- **SSE transport** (HTTP) is preferred over stdio because it works with the
  existing Kestrel host and supports remote/cloud deployments without additional
  process management.

---

## What Would Need to Change

| Area | Change required |
|---|---|
| NuGet dependency | Add `ModelContextProtocol.AspNetCore` package |
| Service registration | Register MCP server and map the `/mcp` SSE endpoint |
| Tool definitions | Create a thin adapter class that wraps existing service calls |
| Client configuration | Point the AI client's MCP config at the service URL |

No changes are required to existing controllers, services, models, or data
access code.
