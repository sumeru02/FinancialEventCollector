"""
Anthropic Claude implementation of the LLM service.
≈ ClaudeService.cs + ILlmService.cs
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class LlmCompletionResult:
    """
    Provider-agnostic result returned by the LLM service.
    ≈ LlmCompletionResult.cs
    """
    text: str
    model: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    cached_tokens: int = 0


class ClaudeService:
    """
    Anthropic Claude implementation of the LLM service.
    Uses httpx for async HTTP calls.
    ≈ ClaudeService.cs
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.claude.api_base_url,
            headers={
                "x-api-key":         settings.claude.apikey,
                "anthropic-version": settings.claude.api_version,
                "content-type":      "application/json",
            },
            timeout=120.0,
        )

    async def complete_async(self, prompt: str) -> LlmCompletionResult:
        """
        Sends the prompt to Claude and returns the completion result.
        ≈ ClaudeService.CompleteAsync()
        """
        body = {
            "model":      self._settings.claude.model,
            "max_tokens": self._settings.claude.max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }

        logger.debug(
            "Calling Claude model=%s max_tokens=%d",
            self._settings.claude.model,
            self._settings.claude.max_tokens,
        )

        response = await self._client.post("v1/messages", json=body)
        response.raise_for_status()

        data = response.json()
        text = next(
            (block["text"] for block in data.get("content", []) if block.get("type") == "text"),
            None,
        )

        if not text:
            raise ValueError("Claude returned an empty or missing text content block.")

        usage = data.get("usage", {})
        logger.debug(
            "Claude response: model=%s input_tokens=%s output_tokens=%s",
            data.get("model"),
            usage.get("input_tokens"),
            usage.get("output_tokens"),
        )

        return LlmCompletionResult(
            text=text,
            model=data.get("model"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cached_tokens=usage.get("cache_read_input_tokens", 0),
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
