"""
Assembles the full LLM prompt for an incident investigation.
≈ PromptHelper.cs

Accepts an EventLog (from data/EventLogs.json) as input, mirroring the .NET
implementation which uses EventLog as the primary investigation source.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Load shared config files once at module import ────────────────────────────

# parents[0] = app/helpers, parents[1] = app, parents[2] = python/, parents[3] = repo root.
# The shared/ directory lives at the repo root.
_SHARED_DIR = Path(__file__).parents[3] / "shared"

_pipeline_config: dict = json.loads(
    (_SHARED_DIR / "config" / "pipeline-config.json").read_text(encoding="utf-8")
)
_llm_schema: dict = json.loads(
    (_SHARED_DIR / "config" / "llm-response-schema.json").read_text(encoding="utf-8")
)
_prompt_template: str = (
    _SHARED_DIR / "prompts" / "investigation-prompt.md"
).read_text(encoding="utf-8")

# Resolve placeholders once
_RESOLVED_SYSTEM_PROMPT: str = (
    _prompt_template
    .replace(
        "{{sla.publishLatencyThresholdMinutes}}",
        str(_pipeline_config["sla"]["publishLatencyThresholdMinutes"]),
    )
    .replace(
        "{{llm_response_schema}}",
        json.dumps(_llm_schema, indent=2),
    )
)

# Build lookup structures from pipeline config
_AUDIT_STAGE_MAP: dict[str, dict] = _pipeline_config["auditEventStageMap"]
_WORKER_STAGE_KEYWORDS: list[dict] = _pipeline_config["workerStageKeywords"]
_WORKER_LOG_LEVELS: set[str] = set(_pipeline_config["workerLogLevelsToInclude"])


# ── Public API ────────────────────────────────────────────────────────────────

def build_investigation_prompt(
    event_log: "EventLog",
    max_prompt_chars: int = 600_000,
) -> str:
    """
    Builds the complete prompt string to send to the LLM.
    Merges and sorts the event log's audit events and worker logs internally.

    Raises ValueError if the assembled prompt exceeds *max_prompt_chars*
    (derived from the model context window; ~4 chars per token).
    ≈ PromptHelper.BuildInvestigationPrompt()
    """
    from app.models.event_log import EventLog

    lines: list[str] = [
        _RESOLVED_SYSTEM_PROMPT,
        "",
        "INVESTIGATION DETAILS:",
        f"EventId: {event_log.event_id}",
        f"ScenarioDescription: {event_log.scenario_metadata.scenario_description if event_log.scenario_metadata else 'No description provided.'}",
        "",
        "MERGED EVENT LOG (sorted by timestamp, benign exceptions already filtered):",
        json.dumps(_build_merged_log(event_log), indent=2, default=_json_default),
    ]
    prompt = "\n".join(lines)

    if len(prompt) > max_prompt_chars:
        raise ValueError(
            f"Prompt for event_id={event_log.event_id} exceeds max_prompt_chars limit "
            f"({len(prompt):,} > {max_prompt_chars:,}). Reduce the event log size."
        )

    return prompt


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_merged_log(log: "EventLog") -> list[dict]:
    """
    Merges audit events and worker logs into a unified list sorted ascending
    by timestamp.  Only Error and Warning worker logs are included.
    ≈ PromptHelper.BuildMergedLog() in C#.
    """
    from app.models.event_log import EventLog, EventLogAuditEvent, EventLogWorkerLog

    entries: list[dict] = []

    for audit in log.audit_events:
        stage, timestamp = _resolve_audit_stage(audit)
        entries.append({
            "timestamp":     (timestamp or audit.source_event_timestamp).isoformat(),
            "stage":         stage,
            "telemetryType": audit.telemetry_type,
            "eventSource":   log.event_source,
            "name":          audit.name,
            "eventType":     log.event_type,
            "eventId":       log.event_id,
            "message":       audit.exception_message,
        })

    for wlog in log.worker_logs:
        if wlog.level in _WORKER_LOG_LEVELS:
            entries.append({
                "timestamp":     wlog.timestamp.isoformat(),
                "stage":         _resolve_worker_stage(wlog.worker_name),
                "telemetryType": "ExceptionTelemetry",
                "eventSource":   wlog.worker_name,
                "name":          wlog.level,
                "eventId":       wlog.event_id or log.event_id,
                "message":       wlog.message,
            })

    entries.sort(key=lambda e: e["timestamp"])
    return entries


def _resolve_audit_stage(
    audit: "EventLogAuditEvent",
) -> tuple[str, Optional[datetime]]:
    """
    Resolves the pipeline stage and relevant timestamp for an audit event
    using the auditEventStageMap from pipeline-config.json.
    ≈ PromptHelper.ResolveAuditStage() in C#.
    """
    mapping = _AUDIT_STAGE_MAP.get(audit.name)
    if mapping:
        field = mapping["timestampField"]
        timestamp_map = {
            "ingestionTimestamp":  audit.ingestion_timestamp,
            "indexingTimestamp":   audit.indexing_timestamp,
            "publishingTimestamp": audit.publishing_timestamp,
        }
        return mapping["stage"], timestamp_map.get(field)
    return "Unknown", audit.collector_stage_timestamp


def _resolve_worker_stage(worker_name: str) -> str:
    """
    Resolves the pipeline stage for a worker log entry
    using the workerStageKeywords from pipeline-config.json.
    ≈ PromptHelper.ResolveWorkerStage() in C#.
    """
    lower = worker_name.lower()
    for kw in _WORKER_STAGE_KEYWORDS:
        if kw["keyword"].lower() in lower:
            return kw["stage"]
    return "Unknown"


def _json_default(obj: object) -> str:
    """Fallback JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
