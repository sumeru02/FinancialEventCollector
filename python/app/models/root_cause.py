"""
RootCause enum and catalog loaded from shared/data/root-causes.json.
≈ RootCause.cs + RootCauseCatalogService.cs
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# ── Load catalog from shared/ folder ──────────────────────────────────────────

# parents[0] = models/, parents[1] = app/, parents[2] = python/, parents[3] = repo root.
# The shared/ directory lives at the repo root.
_SHARED_DIR = Path(__file__).parents[3] / "shared"
# The file is named RootCauses.json in shared/data/ (matches the .NET data file).
_catalog_path = _SHARED_DIR / "data" / "RootCauses.json"
_catalog_data: dict = json.loads(_catalog_path.read_text(encoding="utf-8"))


# ── Enum ──────────────────────────────────────────────────────────────────────

class RootCause(str, Enum):
    """
    Identifies the specific audit-event gap (or absence of gap) found in a
    pipeline incident.  Values match the JSON strings the LLM is asked to produce.
    ≈ RootCause enum in C#.
    """
    ALL_AUDIT_EVENTS_PRESENT        = "AllAuditEventsPresent"
    MISSING_INGESTION_AUDIT_EVENT   = "MissingIngestionAuditEvent"
    MISSING_INDEXING_AUDIT_EVENT    = "MissingIndexingAuditEvent"
    MISSING_PUBLISHING_AUDIT_EVENT  = "MissingPublishingAuditEvent"
    PUBLISH_LATENCY_EXCEEDS_SLA     = "PublishLatencyExceedsSLA"
    UNKNOWN                         = "Unknown"


# ── Catalog entry ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RootCauseEntry:
    """A single entry in the root-cause catalog.  ≈ RootCauseCatalogEntry.cs"""
    name: str
    ordinal: int
    description: str
    recommended_action: str
    team: str


# ── Catalog dictionary ────────────────────────────────────────────────────────

def _build_catalog() -> dict[RootCause, RootCauseEntry]:
    catalog: dict[RootCause, RootCauseEntry] = {}
    for rc in _catalog_data["rootCauses"]:
        key = RootCause(rc["name"])
        catalog[key] = RootCauseEntry(
            name=rc["name"],
            ordinal=rc["ordinal"],
            description=rc["description"],
            recommended_action=rc["recommendedAction"],
            team=rc["team"],
        )
    return catalog


ROOT_CAUSE_CATALOG: dict[RootCause, RootCauseEntry] = _build_catalog()

# Ordered list for catalog endpoints
ROOT_CAUSE_CATALOG_LIST: list[RootCauseEntry] = sorted(
    ROOT_CAUSE_CATALOG.values(), key=lambda e: e.ordinal
)


def get_recommended_action(root_cause: RootCause) -> str:
    """Returns the recommended action for the given root cause."""
    entry = ROOT_CAUSE_CATALOG.get(root_cause)
    return (
        entry.recommended_action
        if entry
        else "Manual review required — evidence is ambiguous or contradictory."
    )
