/// <summary>
/// Pure static helper for calculating the USD cost of a single LLM completion
/// using claude-sonnet-4-6 pricing:
/// <list type="bullet">
///   <item>Input tokens:       $3.00 / 1M tokens</item>
///   <item>Output tokens:      $15.00 / 1M tokens</item>
///   <item>Cache-read tokens:  $0.30 / 1M tokens (billed instead of the full input rate)</item>
/// </list>
/// </summary>
public static class LlmCostHelper
{
    private const double InputCostPerToken     = 3.00  / 1_000_000.0;
    private const double OutputCostPerToken    = 15.00 / 1_000_000.0;
    private const double CacheReadCostPerToken = 0.30  / 1_000_000.0;

    /// <summary>
    /// Calculates the USD cost of the given LLM completion result using claude-sonnet-4-6 pricing.
    /// Returns null when token counts are unavailable.
    /// </summary>
    public static double? CalculateClaudeSonnetCostUsd(LlmCompletionResult llm)
    {
        if (llm.InputTokens is null || llm.OutputTokens is null)
            return null;

        var nonCachedInput = Math.Max(0, llm.InputTokens.Value - llm.CachedTokens);

        return (nonCachedInput         * InputCostPerToken)
             + (llm.OutputTokens.Value * OutputCostPerToken)
             + (llm.CachedTokens       * CacheReadCostPerToken);
    }

    /// <summary>
    /// Calculates the USD cost of the given LLM completion result and rounds it to
    /// <paramref name="decimals"/> decimal places for display (e.g. 0.52, 0.07).
    /// Returns null when token counts are unavailable.
    /// </summary>
    public static double? CalculateRoundedCostUsd(LlmCompletionResult llm, int decimals = 2)
    {
        var cost = CalculateClaudeSonnetCostUsd(llm);
        return cost.HasValue ? Math.Round(cost.Value, decimals) : null;
    }
}
