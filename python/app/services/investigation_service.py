"""
Orchestrates an incident investigation: builds the LLM prompt, calls the LLM,
deserializes the response, and caches results.
≈ InvestigationService.cs
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import jsonschema
from cachetools import TTLCache

from app.helpers.prompt_helper import build_investigation_prompt
from app.models.investigation import InvestigationResult
from app.models.root_cause import RootCause
from app.services.llm_service import ClaudeService, LlmCompletionResult

logger = logging.getLogger(__name__)

# Load LLM response schema for validation
from pathlib import Path
# parents[0] = app/services, parents[1] = app, parents[2] = python/, parents[3] = repo root.
# The shared/ directory lives at the repo root.
_SHARED_DIR = Path(__file__).parents[3] / "shared"
_LLM_SCHEMA: dict = json.loads((_SHARED_DIR / "config" / "llm-response-schema.json").read_text(encoding="utf-8"))


@dataclass
class InvestigationCacheEntry:
    result: InvestigationResult


class InvestigationService:
    """
    Orchestrates incident investigations with optional TTL caching.
    Accepts an EventLog (mirrors .NET InvestigationService which takes EventLog).
    Cache key: "investigation:event:{event_id}" — mirrors .NET.
    ≈ InvestigationService.cs
    """

    def __init__(
        self,
        llm: ClaudeService,
        cache_enabled: bool = False,
        ttl_hours: int = 24,
        max_prompt_chars: int = 600_000,
    ) -> None:
        self._llm              = llm
        self._cache_enabled    = cache_enabled
        self._max_prompt_chars = max_prompt_chars
        self._cache: TTLCache[str, InvestigationResult] = TTLCache(
            maxsize=1000,
            ttl=ttl_hours * 3600,
        )
        self._lock = asyncio.Lock()

    async def investigate_async(
        self,
        event_log: "EventLog",
        bypass_cache: bool = False,
    ) -> tuple[InvestigationResult, bool, Optional[LlmCompletionResult]]:
        """
        Investigates the event log and returns (result, from_cache, llm_metadata).
        When bypass_cache=True the in-memory cache is skipped for both reads and writes.

        Cache key mirrors the .NET implementation:
          "investigation:event:{event_id}"  (InvestigationService.cs:56)
        ≈ InvestigationService.InvestigateAsync()
        """
        from app.models.event_log import EventLog

        cache_key = f"investigation:event:{event_log.event_id}"

        # Check cache (only when caching is enabled and not bypassed)
        if not bypass_cache and self._cache_enabled:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info(
                    "Cache HIT for event_id=%s",
                    event_log.event_id,
                )
                return cached, True, None

        # Build prompt
        prompt = build_investigation_prompt(event_log, self._max_prompt_chars)

        logger.info(
            "Cache MISS — starting LLM investigation for event_id=%s scenario=%s",
            event_log.event_id,
            event_log.scenario_metadata.scenario_name if event_log.scenario_metadata else "N/A",
        )

        # Call LLM
        llm_completion = await self._llm.complete_async(prompt)

        logger.debug("LLM raw response for event_id=%s: %s", event_log.event_id, llm_completion.text)

        # Strip markdown code fences if the LLM wrapped the JSON in ```json ... ```
        # Mirrors InvestigationService.cs lines 78-87 exactly:
        #   1. Trim whitespace.
        #   2. If the string starts with ```, slice off the opening fence line.
        #   3. If the string then ends with ```, slice off the trailing fence.
        raw_json = llm_completion.text.strip()
        if raw_json.startswith("```"):
            first_newline = raw_json.find("\n")
            if first_newline >= 0:
                raw_json = raw_json[first_newline + 1:]
            if raw_json.endswith("```"):
                raw_json = raw_json[:-3].rstrip()

        # Parse and validate against schema
        parsed = json.loads(raw_json)
        jsonschema.validate(parsed, _LLM_SCHEMA)

        result = InvestigationResult(
            root_cause=RootCause(parsed["rootCause"]),
            explanation=parsed["explanation"],
            confidence=parsed["confidence"],
        )

        logger.info(
            "Investigation complete for event_id=%s: root_cause=%s confidence=%s model=%s",
            event_log.event_id,
            result.root_cause,
            result.confidence,
            llm_completion.model,
        )

        # Cache the result (only when caching is enabled and not bypassed)
        if not bypass_cache and self._cache_enabled:
            async with self._lock:
                self._cache[cache_key] = result

        return result, False, llm_completion
