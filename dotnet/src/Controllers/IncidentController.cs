using System.Diagnostics;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Options;

/// <summary>
/// Handles all incident-related requests: browsing incident data and running
/// AI-powered investigations.
/// </summary>
[ApiController]
[Route("incidents")]
[Produces("application/json")]
[Authorize(Roles = "user")]
public class IncidentController : ControllerBase
{
    private readonly IIncidentRepository         _incidentData;
    private readonly IEventRepository            _eventRepository;
    private readonly IInvestigationService       _investigationService;
    private readonly ITelemetryRepository        _telemetryStore;
    private readonly RootCauseCatalogService     _rootCauseCatalog;
    private readonly ClaudeOptions               _claudeOptions;
    private readonly ILogger<IncidentController> _logger;

    public IncidentController(
        IIncidentRepository incidentData,
        IEventRepository eventRepository,
        IInvestigationService investigationService,
        ITelemetryRepository telemetryStore,
        RootCauseCatalogService rootCauseCatalog,
        IOptions<ClaudeOptions> claudeOptions,
        ILogger<IncidentController> logger)
    {
        _incidentData         = incidentData;
        _eventRepository      = eventRepository;
        _investigationService = investigationService;
        _telemetryStore       = telemetryStore;
        _rootCauseCatalog     = rootCauseCatalog;
        _claudeOptions        = claudeOptions.Value;
        _logger               = logger;
    }

    /// <summary>Returns all available incidents.</summary>
    [HttpGet]
    public ActionResult<IReadOnlyList<Incident>> GetAll()
        => Ok(_incidentData.GetIncidents());

    /// <summary>Returns the incident for a given incident ID.</summary>
    /// <param name="id">Incident ID.</param>
    [HttpGet("{id:int}")]
    public ActionResult<Incident> GetById(int id)
    {
        var entry = _incidentData.GetIncidents().FirstOrDefault(s => s.IncidentId == id);

        if (entry is null)
            return NotFound(new { message = $"Incident {id} not found." });

        return Ok(entry);
    }

    /// <summary>Returns the fully-assembled LLM investigation prompt for the given incident without invoking the LLM.</summary>
    /// <remarks>
    /// Useful for debugging, prompt iteration, and auditing exactly what data is sent to the external AI service.
    /// </remarks>
    /// <param name="id">Incident ID.</param>
    [HttpGet("{id:int}/prompt")]
    public ActionResult<object> GetPrompt(int id)
    {
        var incident = _incidentData.GetIncidents()
                                    .FirstOrDefault(s => s.IncidentId == id);

        if (incident is null)
            return NotFound(new { message = $"Incident {id} not found." });

        var eventLog = _eventRepository.GetEventLogById(incident.EventId);
        if (eventLog is null)
            return NotFound(new { message = $"EventLog for EventId '{incident.EventId}' not found." });

        try
        {
            var prompt = PromptHelper.BuildInvestigationPrompt(eventLog, _claudeOptions.MaxPromptChars);
            return Ok(new { prompt });
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "Prompt for IncidentId={IncidentId} exceeds MaxPromptChars limit", id);
            return UnprocessableEntity(new { message = ex.Message });
        }
    }

    /// <summary>
    /// Runs an AI-powered incident investigation for the given incident.
    /// </summary>
    /// <remarks>
    /// Looks up the incident by its IncidentId, resolves the associated EventLog,
    /// and returns a structured verdict from the configured LLM (Claude by default).
    /// No request body is required — all data needed for the investigation is stored
    /// in data/EventLogs.json. Results are cached in memory; the X-Cache response
    /// header indicates whether the result was served from cache (HIT) or freshly
    /// generated (MISS).
    /// </remarks>
    /// <param name="id">Incident ID to investigate.</param>
    [EnableRateLimiting("llm-investigation")]
    [HttpPost("{id:int}/investigations")]
    public async Task<ActionResult<InvestigationResponse>> Investigate(int id)
    {
        var incident = _incidentData.GetIncidents()
                                    .FirstOrDefault(s => s.IncidentId == id);

        if (incident is null)
            return NotFound(new { message = $"Incident {id} not found." });

        var eventLog = _eventRepository.GetEventLogById(incident.EventId);
        if (eventLog is null)
            return NotFound(new { message = $"EventLog for EventId '{incident.EventId}' not found." });

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
            var lineage = _eventRepository.GetEventLineage(incident.EventId);

            // Emit telemetry for observability and LLM accuracy tracking
            var telemetry = new InvestigationTelemetryEvent
            {
                TelemetryType = "InvestigationCompleted",
                Timestamp     = DateTimeOffset.UtcNow,
                IncidentId    = id,
                EventId       = incident.EventId,
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
                "Investigation telemetry recorded: IncidentId={IncidentId} RootCause={RootCause} Cached={Cached} ResponseTimeMs={ResponseTimeMs} EstimatedCostUsd={EstimatedCostUsd}",
                id, result.RootCause, fromCache, sw.ElapsedMilliseconds, llmUsage?.EstimatedCostUsd);

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
            _logger.LogError(ex, "LLM service unavailable for IncidentId={IncidentId}", id);
            return StatusCode(StatusCodes.Status502BadGateway,
                new { message = "LLM service unavailable." });
        }
        catch (InvalidOperationException ex)
        {
            sw.Stop();
            _logger.LogError(ex, "Investigation failed for IncidentId={IncidentId}", id);
            return StatusCode(StatusCodes.Status500InternalServerError,
                new { message = "Investigation failed." });
        }
    }

}
