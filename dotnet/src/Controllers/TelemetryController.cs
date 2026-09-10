using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

/// <summary>
/// Exposes the in-memory telemetry store for observability and LLM accuracy inspection.
/// </summary>
[ApiController]
[Route("telemetry")]
[Produces("application/json")]
[Authorize(Roles = "user")]
public class TelemetryController : ControllerBase
{
    private readonly ITelemetryRepository _telemetryStore;

    public TelemetryController(ITelemetryRepository telemetryStore)
    {
        _telemetryStore = telemetryStore;
    }

    /// <summary>
    /// Returns the most recent investigation telemetry events in ascending chronological order.
    /// </summary>
    /// <param name="limit">
    /// Maximum number of events to return. Defaults to 10. Clamped to [1, 100].
    /// </param>
    [HttpGet]
    public ActionResult<IReadOnlyList<InvestigationTelemetryEvent>> GetRecent(
        [FromQuery] int limit = 10)
        => Ok(_telemetryStore.GetRecent(limit));
}
