"""
Pydantic models for Incident.
≈ Incident.cs

The Incident model is a thin manifest record that links an incident identifier
and title to a pipeline EventId. The full pipeline data (audit events, worker logs)
is stored separately in data/EventLogs.json and accessed via EventRepository.
≈ Incident.cs + IncidentRepository.cs
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Incident(BaseModel):
    """
    A single incident loaded from data/Incidents.json.
    A thin manifest record that links an incident identifier and title to a
    pipeline EventId. The full pipeline data (audit events, worker logs) is
    stored separately in data/EventLogs.json and accessed via EventRepository.
    ≈ Incident.cs
    """
    incident_id: int = Field(alias="incidentId")
    """Unique identifier for this incident."""

    incident_title: str = Field(alias="incidentTitle")
    """The partner-reported incident title, e.g. 'Missing InvoiceCreated Event'."""

    event_id: str = Field(alias="eventId")
    """The pipeline EventId associated with this incident, e.g. 'evt-001'."""

    model_config = {"populate_by_name": True}
