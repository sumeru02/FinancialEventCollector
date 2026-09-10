"""
In-memory ring buffer for InvestigationTelemetryEvent records.
≈ TelemetryStore.cs
"""
from __future__ import annotations

import asyncio
from collections import deque

from app.models.telemetry import InvestigationTelemetryEvent

_MAX_CAPACITY = 1000


class TelemetryStore:
    """
    Thread-safe in-memory ring buffer for telemetry events.
    ≈ TelemetryStore.cs
    """

    def __init__(self) -> None:
        self._events: deque[InvestigationTelemetryEvent] = deque(maxlen=_MAX_CAPACITY)
        self._lock = asyncio.Lock()

    async def add(self, event: InvestigationTelemetryEvent) -> None:
        """Appends a telemetry event to the store."""
        async with self._lock:
            self._events.append(event)

    def get_recent(self, limit: int = 10) -> list[InvestigationTelemetryEvent]:
        """
        Returns the most recent telemetry events in descending chronological order
        (newest first). limit is clamped to [1, 100].
        ≈ TelemetryStore.GetRecent() which uses OrderByDescending(e => e.Timestamp).
        """
        clamped = max(1, min(limit, 100))
        # deque is ordered oldest→newest; take last N then sort descending (newest-first)
        recent = list(self._events)[-clamped:]
        return sorted(recent, key=lambda e: e.timestamp, reverse=True)
