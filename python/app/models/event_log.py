"""
Pydantic models for EventLog, EventLogAuditEvent, EventLogWorkerLog,
EventLogScenarioMetadata, EventLineage, and EventLogResponse.
≈ EventLog.cs + AuditEvent.cs + WorkerLog.cs + ScenarioMetadata.cs
  + EventLineage.cs + EventLogResponse.cs
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.root_cause import RootCause

# ── Pipeline stage constants ──────────────────────────────────────────────────

_ALL_STAGES = ["IngestAuditEvent", "IndexAuditEvent", "PublishAuditEvent"]


# ── EventLog sub-models ───────────────────────────────────────────────────────

class EventLogAuditEvent(BaseModel):
    """
    A single audit event recorded by the Collector pipeline, as stored in
    data/EventLogs.json.  Mirrors the C# AuditEvent record but uses the
    EventLogs.json field names (no eventId/eventType/eventSource at the
    audit-event level — those are hoisted from the parent EventLog).
    ≈ AuditEvent.cs
    """
    name: str
    """IngestAuditEvent | IndexAuditEvent | PublishAuditEvent"""

    telemetry_type: str = Field("EventTelemetry", alias="telemetryType")
    """'EventTelemetry' (success) | 'ExceptionTelemetry' (failure)"""

    source_event_timestamp: datetime = Field(alias="sourceEventTimestamp")
    """Partner-provided; when the business event occurred upstream."""

    ingestion_timestamp: Optional[datetime] = Field(None, alias="ingestionTimestamp")
    indexing_timestamp: Optional[datetime] = Field(None, alias="indexingTimestamp")
    publishing_timestamp: Optional[datetime] = Field(None, alias="publishingTimestamp")

    exception_occurred: bool = Field(False, alias="exceptionOccurred")
    exception_type: Optional[str] = Field(None, alias="exceptionType")
    exception_message: Optional[str] = Field(None, alias="exceptionMessage")

    model_config = {"populate_by_name": True}

    @property
    def collector_stage_timestamp(self) -> Optional[datetime]:
        """The collector-assigned timestamp for this stage, whichever is present.
        ≈ AuditEvent.CollectorStageTimestamp in C#."""
        return self.ingestion_timestamp or self.indexing_timestamp or self.publishing_timestamp


class EventLogWorkerLog(BaseModel):
    """
    A single worker log entry as stored in data/EventLogs.json.
    ≈ WorkerLog.cs
    """
    timestamp: datetime
    worker_name: str = Field(alias="workerName")
    """IngestionWorker | IndexingWorker | PublishingWorker"""
    level: str
    """Info | Warning | Error"""
    message: str
    event_id: Optional[str] = Field(None, alias="eventId")
    """null when failure occurred before per-event processing context"""

    model_config = {"populate_by_name": True}


class EventLogScenarioMetadata(BaseModel):
    """
    Optional test scenario metadata attached to each EventLog in data/EventLogs.json.
    ≈ ScenarioMetadata.cs
    """
    scenario_name: str = Field(alias="scenarioName")
    scenario_description: Optional[str] = Field(None, alias="scenarioDescription")
    expected_root_cause: Optional[RootCause] = Field(None, alias="expectedRootCause")
    expected_explanation: Optional[str] = Field(None, alias="expectedExplanation")

    model_config = {"populate_by_name": True}


class EventLog(BaseModel):
    """
    Raw pipeline event record loaded from data/EventLogs.json.
    Carries the audit events and worker logs for one pipeline EventId.
    Used as the source for EventLineage projection and as the input to
    InvestigationService for LLM root-cause analysis.
    ≈ EventLog.cs
    """
    event_id: str = Field(alias="eventId")
    """The pipeline EventId, e.g. 'evt-001'."""

    event_type: Optional[str] = Field(None, alias="eventType")
    """The upstream service's domain event type, e.g. 'InvoiceCreated'.
    Null when the event was never successfully parsed."""

    event_source: str = Field(alias="eventSource")
    """The upstream service that produced the original business event."""

    scenario_metadata: Optional[EventLogScenarioMetadata] = Field(None, alias="scenarioMetadata")
    """Optional test scenario metadata. Null for real production events."""

    audit_events: list[EventLogAuditEvent] = Field(alias="auditEvents")
    """Audit events recorded for this pipeline EventId."""

    worker_logs: list[EventLogWorkerLog] = Field(alias="workerLogs")
    """Worker log entries associated with this pipeline EventId."""

    model_config = {"populate_by_name": True}


# ── EventLineage ──────────────────────────────────────────────────────────────

class EventLineage(BaseModel):
    """
    Projected data lineage view for a single pipeline EventId.
    Constructed from a raw EventLog record; all derived fields are
    computed once in the constructor and stored as read-only properties.
    Returned by GET /events/{eventId}/lineage.
    ≈ EventLineage.cs
    """
    event_id: str
    """The pipeline EventId, e.g. 'evt-001'."""

    event_type: Optional[str] = None
    """The upstream service's domain event type. Null when never successfully parsed."""

    event_source: str
    """The upstream service that produced the original business event."""

    ingest_success: bool
    """True when an IngestAuditEvent with telemetry_type 'EventTelemetry' is present."""

    index_success: bool
    """True when an IndexAuditEvent with telemetry_type 'EventTelemetry' is present."""

    publish_success: bool
    """True when a PublishAuditEvent with telemetry_type 'EventTelemetry' is present."""

    audit_events_present: list[str]
    """Names of the audit events that completed successfully."""

    missing_audit_events: list[str]
    """Names of the expected audit events that are absent or recorded only as ExceptionTelemetry."""

    publish_latency_seconds: Optional[float] = None
    """Elapsed seconds from source event timestamp to PublishingWorker completion.
    Null when PublishSuccess is false."""

    publish_latency_sla_met: Optional[bool] = None
    """True when PublishLatencySeconds is within the configured SLA threshold.
    Null when PublishSuccess is false."""

    @classmethod
    def from_event_log(cls, log: EventLog, sla_threshold_minutes: int) -> "EventLineage":
        """
        Projects an EventLog into a data lineage view.
        All derived fields are computed from the audit events.
        ≈ EventLineage constructor in C#.
        """
        success_names = [
            a.name
            for a in log.audit_events
            if a.telemetry_type == "EventTelemetry"
        ]

        ingest = next(
            (a for a in log.audit_events
             if a.name == "IngestAuditEvent" and a.telemetry_type == "EventTelemetry"),
            None,
        )
        publish = next(
            (a for a in log.audit_events
             if a.name == "PublishAuditEvent" and a.telemetry_type == "EventTelemetry"),
            None,
        )

        latency: Optional[float] = None
        if ingest is not None and publish is not None and publish.publishing_timestamp is not None:
            delta = publish.publishing_timestamp - ingest.source_event_timestamp
            latency = round(delta.total_seconds(), 1)

        sla_met: Optional[bool] = None
        if latency is not None:
            sla_met = latency <= sla_threshold_minutes * 60.0

        return cls(
            event_id=log.event_id,
            event_type=log.event_type,
            event_source=log.event_source,
            ingest_success="IngestAuditEvent" in success_names,
            index_success="IndexAuditEvent" in success_names,
            publish_success="PublishAuditEvent" in success_names,
            audit_events_present=success_names,
            missing_audit_events=[s for s in _ALL_STAGES if s not in success_names],
            publish_latency_seconds=latency,
            publish_latency_sla_met=sla_met,
        )


# ── EventLogResponse ──────────────────────────────────────────────────────────

class EventLogResponse(BaseModel):
    """
    API response DTO for GET /events/{eventId}/logs.
    Exposes the raw audit events and worker logs for a pipeline event without
    leaking internal test scaffolding (ScenarioMetadata).
    ≈ EventLogResponse.cs
    """
    event_id: str
    """The pipeline EventId, e.g. 'evt-001'."""

    event_type: Optional[str] = None
    """The upstream service's domain event type. Null when never successfully parsed."""

    event_source: str
    """The upstream service that produced the original business event."""

    audit_events: list[EventLogAuditEvent]
    """Audit events recorded for this pipeline EventId."""

    worker_logs: list[EventLogWorkerLog]
    """Worker log entries associated with this pipeline EventId."""

    @classmethod
    def from_event_log(cls, log: EventLog) -> "EventLogResponse":
        """
        Projects a raw EventLog into an EventLogResponse,
        deliberately omitting EventLog.scenario_metadata to avoid
        leaking internal test labels to API consumers.
        ≈ EventLogResponse.FromEventLog() in C#.
        """
        return cls(
            event_id=log.event_id,
            event_type=log.event_type,
            event_source=log.event_source,
            audit_events=log.audit_events,
            worker_logs=log.worker_logs,
        )
