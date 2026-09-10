# FinancialEventCollector — Python Service

FastAPI service that investigates financial pipeline incidents using an LLM (Anthropic Claude).
It mirrors the .NET `FinancialEventCollector` service and shares the same `shared/` folder at the
repo root's `shared/` folder.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| pip | bundled with Python |

---

## Setup

All commands below are run from the **`python/`** directory.

```bash
cd python
```

### 1. Create a virtual environment

**Windows**
```bat
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

**macOS / Linux**
```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

### 2. Configure environment variables

Copy the example env file and fill in your Anthropic API key:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env`:

```
CLAUDE__APIKEY=sk-ant-...
CLAUDE__MODEL=claude-sonnet-4-6
CACHE__TTL_HOURS=24
```

---

## Running Locally

### Option A — convenience script (recommended)

From the **repo root**:

```bat
# Windows
python python\scripts\local.py

# macOS / Linux
python python/scripts/local.py
```

Or from `python/scripts/`:

```bat
# Windows
python local.py

# macOS / Linux
python local.py
```

To stop the server:

```bash
python python/scripts/local.py stop
```

### Option B — uvicorn directly

```bash
# from the python/ directory
.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running, open the interactive API docs at:
**http://localhost:8000/docs**

---

## Running Tests

From the **`python/`** directory:

```bash
.venv\Scripts\pytest tests\          # Windows
.venv/bin/pytest tests/              # macOS / Linux
```

---

## Project Structure

```
python/
├── app/
│   ├── config.py          # Pydantic settings (env-var driven)
│   ├── main.py            # FastAPI app factory
│   ├── helpers/           # Prompt assembly
│   ├── models/            # Pydantic domain models
│   ├── routers/           # API route handlers
│   └── services/          # Business logic (LLM, incidents, cache)
├── scripts/
│   └── local.py           # Cross-platform start/stop helper
├── tests/                 # pytest test suite
├── pyproject.toml         # Package metadata & dependencies
└── README.md              # ← you are here
```

Shared data files (incidents, prompts, pipeline config) live in the **repo-root `shared/`** folder
and are referenced by the Python service at runtime.

---

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE__APIKEY` | *(required)* | Anthropic API key |
| `CLAUDE__MODEL` | `claude-sonnet-4-6` | Claude model identifier |
| `CLAUDE__MAX_TOKENS` | `1024` | Max tokens per LLM response |
| `CLAUDE__API_BASE_URL` | `https://api.anthropic.com` | Anthropic base URL |
| `CACHE__TTL_HOURS` | `24` | Investigation result cache TTL |
