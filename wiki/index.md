# Wiki

Documentation for the **FinancialEventCollector** project.

---

## Core Documentation

| Document | Description |
|----------|-------------|
| [README](../README.md) | Landing page, quick start, and scenario reference |
| [ARCHITECTURE](../ARCHITECTURE.md) | System design, pipeline stages, LLM investigation flow, auth model, and data model |
| [API Reference](../API.md) | All REST endpoints, authentication, request/response schemas, and error codes |
| [Setup Guide](../SETUP.md) | Full setup instructions for both runtimes (Python + .NET) |

---

## Plans

Migration and parity plans for the current and upcoming work.

| Document | Description |
|----------|-------------|
| [Python Port & Monorepo Restructure](plans/python-migration-plan.md) | Phases 1–4: repo restructure, shared JSON config extraction, FastAPI port, and C# refactor |
| [Python ↔ .NET Parity Fixes](plans/python-dotnet-parity-plan.md) | 13 identified gaps between the Python and .NET implementations, with ordered fix steps |

## V-Next

Planned features not yet implemented.

| Document | Description |
|----------|-------------|
| [MCP Server Integration](vnext/mcp.md) | Planned: exposing the service as a Model Context Protocol server for Claude Desktop, Cursor, and other AI clients |
