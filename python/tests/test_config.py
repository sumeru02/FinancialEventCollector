"""
Tests for shared config loading — root-causes.json, pipeline-config.json, llm-response-schema.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.root_cause import ROOT_CAUSE_CATALOG, ROOT_CAUSE_CATALOG_LIST, RootCause

# parents[0] = tests, parents[1] = python/, parents[2] = repo root.
# The shared/ directory lives at the repo root.
_SHARED_DIR = Path(__file__).parents[2] / "shared"


class TestRootCauseCatalog:
    def test_all_enum_values_in_catalog(self) -> None:
        """Every RootCause enum value must have a catalog entry."""
        for rc in RootCause:
            assert rc in ROOT_CAUSE_CATALOG, f"Missing catalog entry for {rc}"

    def test_catalog_list_ordered_by_ordinal(self) -> None:
        """Catalog list should be sorted by ordinal."""
        ordinals = [e.ordinal for e in ROOT_CAUSE_CATALOG_LIST]
        assert ordinals == sorted(ordinals)

    def test_recommended_actions_non_empty(self) -> None:
        """Every catalog entry should have a non-empty recommended action."""
        for entry in ROOT_CAUSE_CATALOG_LIST:
            assert entry.recommended_action, f"Empty recommended_action for {entry.name}"

    def test_descriptions_non_empty(self) -> None:
        """Every catalog entry should have a non-empty description."""
        for entry in ROOT_CAUSE_CATALOG_LIST:
            assert entry.description, f"Empty description for {entry.name}"


class TestPipelineConfig:
    def test_pipeline_config_loads(self) -> None:
        """pipeline-config.json should load and contain required keys."""
        config = json.loads((_SHARED_DIR / "config" / "pipeline-config.json").read_text())
        assert "sla" in config
        assert "auditEventStageMap" in config
        assert "workerStageKeywords" in config
        assert config["sla"]["publishLatencyThresholdMinutes"] > 0

    def test_audit_stage_map_has_three_events(self) -> None:
        """auditEventStageMap should have entries for all three audit event types."""
        config = json.loads((_SHARED_DIR / "config" / "pipeline-config.json").read_text())
        stage_map = config["auditEventStageMap"]
        assert "IngestAuditEvent" in stage_map
        assert "IndexAuditEvent" in stage_map
        assert "PublishAuditEvent" in stage_map


class TestLlmResponseSchema:
    def test_schema_loads(self) -> None:
        """llm-response-schema.json should load and be a valid JSON Schema."""
        schema = json.loads((_SHARED_DIR / "config" / "llm-response-schema.json").read_text())
        assert schema.get("type") == "object"
        assert "rootCause" in schema.get("properties", {})

    def test_schema_root_cause_enum_matches_python_enum(self) -> None:
        """The rootCause enum in the schema should match the Python RootCause enum values."""
        schema = json.loads((_SHARED_DIR / "config" / "llm-response-schema.json").read_text())
        schema_values = set(schema["properties"]["rootCause"]["enum"])
        python_values = {rc.value for rc in RootCause}
        assert schema_values == python_values, (
            f"Schema/enum mismatch: schema={schema_values}, python={python_values}"
        )
