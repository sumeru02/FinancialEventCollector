"""
Telemetry router — exposes the in-memory telemetry store at GET /telemetry.
≈ TelemetryController.cs
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import require_role
from app.models.telemetry import InvestigationTelemetryEvent
from app.services.telemetry_store import TelemetryStore

# Router-level dependency — every route in this router requires a valid X-Api-Key
# with the 'user' role (admin keys are also accepted because ApiKeyAuthHandler grants
# both "admin" and "user" claims to the admin key).
# ≈ [Authorize(Roles = "user")] on TelemetryController.cs:10
router = APIRouter(
    dependencies=[Depends(require_role("user"))],
    tags=["Telemetry (role: user)"],
)


def _get_telemetry_store() -> TelemetryStore:
    """Default dependency — overridden in main.py with the application singleton."""
    return TelemetryStore()


@router.get("", response_model=list[InvestigationTelemetryEvent])
async def get_recent(
    telemetry_store: Annotated[TelemetryStore, Depends(_get_telemetry_store)],
    limit: int = Query(default=10, ge=1, le=100),
) -> list[InvestigationTelemetryEvent]:
    """
    Returns the most recent investigation telemetry events in descending chronological
    order (newest first). Matches TelemetryStore.GetRecent() which uses OrderByDescending.
    """
    return telemetry_store.get_recent(limit)
