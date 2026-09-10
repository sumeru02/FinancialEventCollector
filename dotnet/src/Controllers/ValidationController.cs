using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

/// <summary>
/// Runs every incident scenario through the investigation pipeline and compares
/// the LLM's verdict against the human-authored ground-truth label stored in
/// IncidentTestMetadata.ExpectedRootCause.
///
/// Useful for regression testing the LLM prompt and for measuring overall
/// accuracy and cost across the full scenario suite.
/// </summary>
[ApiController]
[Route("validation")]
[Produces("application/json")]
[Authorize(Roles = "admin")]
public class ValidationController : ControllerBase
{
    /// <summary>Hard cap on the number of incidents processed per validation run.</summary>
    private const int MaxLimit = 10;

    private readonly IValidationService _validationService;

    public ValidationController(IValidationService validationService)
    {
        _validationService = validationService;
    }

    /// <summary>
    /// Executes the investigation pipeline for every incident scenario and returns
    /// a per-incident comparison of the expected vs. actual root cause, plus the
    /// aggregated LLM cost across all non-cached calls.
    /// </summary>
    /// <remarks>
    /// Incidents without a TestMetadata.ExpectedRootCause label are still included;
    /// their expectedRootCause and rootCauseMatch fields will be null.
    /// Every incident is always sent directly to the LLM endpoint; the cache is never used.
    /// </remarks>
    /// <param name="limit">
    /// Maximum number of incidents to process (1–10). Defaults to 10.
    /// </param>
    [EnableRateLimiting("llm-investigation")]
    [HttpPost("run")]
    public async Task<ActionResult<ValidationRunResponse>> Run(
        [FromQuery] int limit = MaxLimit)
    {
        if (limit < 1 || limit > MaxLimit)
            return BadRequest(new { message = $"'limit' must be between 1 and {MaxLimit}. Received: {limit}." });

        var response = await _validationService.RunAsync(limit, HttpContext.RequestAborted);
        return Ok(response);
    }
}

