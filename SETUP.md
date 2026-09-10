# Setup Guide — FinancialEventCollector

This repo contains two implementations of the same service:

| Implementation | Location | Runtime |
|---|---|---|
| Python (FastAPI) | `python/` | Python 3.12+ |
| .NET (ASP.NET Core) | `dotnet/` | .NET 8 |

Shared data files (incidents, prompts, pipeline config) live in `shared/` at the repo root.

---

## Python Service

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12+ | See platform-specific install instructions below |
| pip | bundled with Python | |

---

### macOS / Linux Setup

#### Install Python 3.12

**macOS (Homebrew):**
```bash
brew install python@3.12
```

**macOS (python.org):** Download the macOS installer from [python.org/downloads](https://www.python.org/downloads/).

Verify:
```bash
python3.12 --version
```

#### Create the virtual environment (recommended)

A virtual environment isolates this project's dependencies from your system Python and other projects. It is strongly recommended but not strictly required if you manage your own global Python environment (e.g., via pyenv or conda).

From the **`python/`** directory:
```bash
cd python
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

#### Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:
```
CLAUDE__APIKEY=sk-ant-...
CLAUDE__MODEL=claude-sonnet-4-6
```

#### Run the service

From the **repo root**:
```bash
python python/scripts/local.py
```

Or from `python/scripts/`:
```bash
python local.py
```

Browse to **http://localhost:8000/docs** once running.

To stop:
```bash
python python/scripts/local.py stop
```

#### Run tests

With venv active:
```bash
cd python
pytest tests/ -v
```

Without venv (if packages installed globally):
```bash
cd python
python3.12 -m pytest tests/ -v
```

---

### Windows Setup

#### Install Python 3.12

Install Python 3.12 from the **Windows Store** (search "Python 3.12") or from [python.org](https://www.python.org/downloads/).

Verify the install:
```bat
python3.12 --version
```
Expected: `Python 3.12.x`

#### Create the virtual environment

From the **`python/`** directory:
```bat
cd python
python3.12 -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

#### Configure environment variables

```bat
copy .env.example .env
```

Edit `.env` and set your Anthropic API key:
```
CLAUDE__APIKEY=sk-ant-...
CLAUDE__MODEL=claude-sonnet-4-6
```

#### Run the service

From the **repo root**:
```bat
python python/scripts/local.py
```

Browse to **http://localhost:8000/docs** once running.

To stop:
```bat
python python/scripts/local.py stop
```

#### Run tests

From the **`python/`** directory, activate the virtual environment first, then run pytest:

```bat
cd python
.venv\Scripts\activate
pytest tests\ -v
```

Or without activating (using the venv's pytest directly):

```bat
cd python
.venv\Scripts\pytest.exe tests\ -v
```

---

## .NET Service

### Prerequisites

| Tool | Version |
|---|---|
| .NET SDK | 8.0+ |

### Install .NET SDK

**macOS (Homebrew):**
```bash
brew install --cask dotnet-sdk
```

**macOS (installer):** Download the macOS `.pkg` from [dotnet.microsoft.com/download](https://dotnet.microsoft.com/download/dotnet/8.0).

**Windows:** Download the installer from [dotnet.microsoft.com/download](https://dotnet.microsoft.com/download/dotnet/8.0).

Verify:
```bash
dotnet --version
# Expected: 8.x.x
```

### Run

**macOS / Linux:**
```bash
cd dotnet/src
dotnet run
```

**Windows:**
```bat
cd dotnet/src
dotnet run
```

### Test

From the **repo root**:

**macOS / Linux:**
```bash
dotnet test dotnet/FinancialEventCollector.sln \
  --settings dotnet/FinancialEventCollector.runsettings \
  --logger "console;verbosity=normal"
```

**Windows:**
```bat
dotnet test dotnet/FinancialEventCollector.sln --settings dotnet/FinancialEventCollector.runsettings --logger "console;verbosity=normal"
```

---

## Shared Data Files

Both implementations read from the `shared/` folder at the repo root:

```
shared/
├── config/
│   ├── pipeline-config.json        # SLA thresholds, stage maps
│   └── llm-response-schema.json    # JSON Schema for LLM output validation
├── data/
│   ├── EventLogs.json              # Worker log entries for each scenario
│   ├── Incidents.json              # Test/seed incident fixtures
│   └── RootCauses.json             # Root cause catalog
└── prompts/
    └── investigation-prompt.md     # LLM investigation prompt template
```
