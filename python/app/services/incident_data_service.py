"""
Loads incident data from shared/data/Incidents.json.
≈ IncidentDataService.cs
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.incident import Incident

# parents[0] = app/services, parents[1] = app, parents[2] = python/, parents[3] = repo root.
# The shared/ directory lives at the repo root.
_SHARED_DIR = Path(__file__).parents[3] / "shared"


class IncidentDataService:
    """
    Loads incident data from shared/data/Incidents.json once at startup.
    ≈ IncidentDataService.cs
    """

    def __init__(self) -> None:
        path = _SHARED_DIR / "data" / "Incidents.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._incidents: list[Incident] = [
            Incident.model_validate(item) for item in raw
        ]

    def get_incidents(self) -> list[Incident]:
        """Returns all available incidents."""
        return self._incidents
