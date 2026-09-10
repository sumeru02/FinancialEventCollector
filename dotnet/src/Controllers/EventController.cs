using System.Diagnostics;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Options;

/// <summary>
/// Handles all event requests: browsing event lineage data, inspecting raw event logs,
/// and running AI-powered investigations directly against an event (without requiring an incident).
/// </summary>
[ApiController]
[Route("events")]
[Produces("application/json")]
[Authorize(Roles = "user")]
public class EventController : ControllerBase
{
    private readonly IEventRepository          _eventRepository;
    private readonly IInvestigationService     _investigationService;
    private readonly ITelemetryRepository      _telemetryStore;
    private readonly RootCauseCatalogService   _rootCauseCatalog;
    private readonly ClaudeOptions             _claudeOptions;
    private readonly ILogger<EventController>  _logger;

    public EventController(
        IEventRepository eventRepository,
        IInvestigationService investigationService,
        ITelemetryRepository telemetryStore,
        RootCauseCatalogService rootCauseCatalog,
        IOptions<ClaudeOptions> claudeOptions,
        ILogger<EventController> logger)
    {
        _eventRepository      = eventRepository;
        _investigationService = investigationService;
        _telemetryStore       = telemetryStore;
        _rootCauseCatalog     = rootCauseCatalog;
        _claudeOptions        = claudeOptions.Value;
        _logger               = logger;
    }

    /// <summary>Returns the data lineage view for a given event ID.</summary>
    /// <param name="eventId">Pipeline event ID (e.g. "evt-001").</param>
    [HttpGet("{eventId}/lineage")]
    public ActionResult<EventLineage> GetLineageByEventId(string eventId)
    {
        var lineage = _eventRepository.GetEventLineage(eventId);
        return lineage is null
            ? NotFound(new { message = $"Event '{eventId}' not found." })
            : Ok(lineage);
    }

    /// <summary>Returns the raw audit events and worker logs for a given event ID.</summary>
    /// <remarks>
    /// Exposes the underlying pipeline telemetry records that feed the data lineage projection
    /// and the LLM investigation prompt. Internal test scenario metadata is excluded.
    /// </remarks>
    /// <param name="eventId">Pipeline event ID (e.g. "evt-001").</param>
    [HttpGet("{eventId}/logs")]
    public ActionResult<EventLogResponse> GetLogsByEventId(string eventId)
    {
        var eventLog = _eventRepository.GetEventLogById(eventId);
        return eventLog is null
            ? NotFound(new { message = $"Event '{eventId}' not found." })
            : Ok(EventLogResponse.FromEventLog(eventLog));
    }

    /// <summary>Returns the fully-assembled LLM investigation prompt for the given event without invoking the LLM.</summary>
    /// <remarks>
    /// Useful for debugging, prompt iteration, and auditing exactly what data is sent to the external AI service.
    /// </remarks>
    /// <param name="eventId">Pipeline event ID (e.g. "evt-001").</param>
    [HttpGet("{eventId}/prompt")]
    public ActionResult<object> GetPrompt(string eventId)
    {
        var eventLog = _eventRepository.GetEventLogById(eventId);
        if (eventLog is null)
            return NotFound(new { message = $"Event '{eventId}' not found." });

        try
        {
            var prompt = PromptHelper.BuildInvestigationPrompt(eventLog, _claudeOptions.MaxPromptChars);
            return Ok(new { prompt });
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "Prompt for EventId={EventId} exceeds MaxPromptChars limit", eventId);
            return UnprocessableEntity(new { message = ex.Message });
        }
    }

    /// <summary>
    /// Runs an AI-powered investigation for the given pipeline event.
    /// </summary>
    /// <remarks>
    /// Looks up the event by its EventId and returns a structured verdict from the configured
    /// LLM (Claude by default). No request body is required — all data needed for the
    /// investigation is stored in data/EventLogs.json. Results are cached in memory; the
    /// X-Cache response header indicates whether the result was served from cache (HIT) or
    /// freshly generated (MISS).
    /// </remarks>
    /// <param name="eventId">Pipeline event ID to investigate (e.g. "evt-001").</param>
    [EnableRateLimiting("llm-investigation")]
    [HttpPost("{eventId}/investigations")]
    public async Task<ActionResult<InvestigationResponse>> Investigate(string eventId)
    {
        var eventLog = _eventRepository.GetEventLogById(eventId);
        if (eventLog is null)
            return NotFound(new { message = $"Event '{eventId}' not found." });

        var sw = Stopwatch.StartNew();

        try
        {
            var (result, fromCache, llmMetadata) = await _investigationService.InvestigateAsync(eventLog);
            sw.Stop();

            // Indicate cache status to callers via standard X-Cache header
            Response.Headers["X-Cache"] = fromCache ? "HIT" : "MISS";

            // Build LLM usage telemetry (null on cache hit — no LLM call was made)
            var llmUsage = llmMetadata is null ? null : new LlmUsageTelemetry
            {
                Model            = llmMetadata.Model,
                InputTokens      = llmMetadata.InputTokens,
                OutputTokens     = llmMetadata.OutputTokens,
                CachedTokens     = llmMetadata.CachedTokens,
                EstimatedCostUsd = LlmCostHelper.CalculateRoundedCostUsd(llmMetadata)
            };

            // Resolve the projected lineage — passed through as EventContext so callers
            // can correlate the LLM verdict with structured pipeline stage data.
            var lineage = _eventRepository.GetEventLineage(eventId);

            // Emit telemetry for observability and LLM accuracy tracking
            var telemetry = new InvestigationTelemetryEvent
            {
                TelemetryType = "InvestigationCompleted",
                Timestamp     = DateTimeOffset.UtcNow,
                IncidentId    = null,   // no incident — event-driven investigation
                EventId       = eventId,
                Response      = new InvestigationResponseTelemetry
                {
                    ResponseTimeMs = sw.ElapsedMilliseconds,
                    Cached         = fromCache,
                    Confidence     = result.Confidence,
                    RootCause      = result.RootCause,
                    LlmUsage       = llmUsage
                },
                Validation = new InvestigationValidationTelemetry
                {
                    ExpectedRootCause = eventLog.ScenarioMetadata?.ExpectedRootCause,
                    ActualRootCause   = result.RootCause,
                    RootCauseMatch    = eventLog.ScenarioMetadata?.ExpectedRootCause.HasValue == true
                                           ? eventLog.ScenarioMetadata.ExpectedRootCause == result.RootCause
                                           : null
                }
            };

            _telemetryStore.Add(telemetry);

            _logger.LogInformation(
                "Investigation telemetry recorded: EventId={EventId} RootCause={RootCause} Cached={Cached} ResponseTimeMs={ResponseTimeMs} EstimatedCostUsd={EstimatedCostUsd}",
                eventId, result.RootCause, fromCache, sw.ElapsedMilliseconds, llmUsage?.EstimatedCostUsd);

            return Ok(new InvestigationResponse
            {
                Investigation = result,
                EventContext  = lineage,
                RootCauseCatalog = _rootCauseCatalog,
                LlmUsage      = llmUsage
            });
        }
        catch (HttpRequestException ex)
        {
            sw.Stop();
            _logger.LogError(ex, "LLM service unavailable for EventId={EventId}", eventId);
            return StatusCode(StatusCodes.Status502BadGateway, new { message = "LLM service unavailable." });
        }
        catch (InvalidOperationException ex)
        {
            sw.Stop();
            _logger.LogError(ex, "Investigation failed for EventId={EventId}", eventId);
            return StatusCode(StatusCodes.Status500InternalServerError, new { message = "Investigation failed." });
        }
    }

}
