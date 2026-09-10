"""
Pure helper for calculating the USD cost of a single LLM completion.
≈ dotnet/src/Helper/LlmCostHelper.cs

Pricing (claude-sonnet-4-6):
  Input tokens:       $3.00 / 1M tokens
  Output tokens:      $15.00 / 1M tokens
  Cache-read tokens:  $0.30 / 1M tokens (billed instead of the full input rate)
"""
from __future__ import annotations

# Pricing constants for claude-sonnet-4-6 (USD per million tokens).
_INPUT_COST_PER_M: float       = 3.00   # $3.00 / 1M input tokens
_OUTPUT_COST_PER_M: float      = 15.00  # $15.00 / 1M output tokens
_CACHE_READ_COST_PER_M: float  = 0.30   # $0.30 / 1M cache-read tokens


def calculate_claude_sonnet_cost_usd(
    input_tokens: int | None,
    cached_tokens: int,
    output_tokens: int | None,
) -> float | None:
    """
    Calculates the USD cost of the given LLM completion using claude-sonnet-4-6 pricing.
    Returns None when token counts are unavailable.
    ≈ LlmCostHelper.CalculateClaudeSonnetCostUsd()
    """
    if input_tokens is None or output_tokens is None:
        return None

    non_cached_input = max(0, input_tokens - cached_tokens)
    return (
        non_cached_input / 1_000_000 * _INPUT_COST_PER_M
        + cached_tokens  / 1_000_000 * _CACHE_READ_COST_PER_M
        + output_tokens  / 1_000_000 * _OUTPUT_COST_PER_M
    )
