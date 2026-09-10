using System.Diagnostics;

/// <summary>
/// Runs every incident scenario through the investigation pipeline and compares
/// the LLM's verdict against the human-authored ground-truth label stored in
/// ScenarioMetadata.ExpectedRootCause on the associated EventLog.
///
/// Useful for regression testing the LLM prompt and for measuring overall
/// accuracy and cost across the full scenario suite.
/// </summary>
public class ValidationService : IValidationService
{
    private readonly IIncidentRepository          _incidentData;
    private readonly IEventRepository             _eventRepository;
    private readonly IInvestigationService        _investigationService;
    private readonly ILogger<ValidationService>   _logger;

    public ValidationService(
        IIncidentRepository incidentData,
        IEventRepository eventRepository,
        IInvestigationService investigationService,
        ILogger<ValidationService> logger)
    {
        _incidentData         = incidentData;
        _eventRepository      = eventRepository;
        _investigationService = investigationService;
        _logger               = logger;
    }

    /// <inheritdoc/>
    public async Task<ValidationRunResponse> RunAsync(int limit, CancellationToken ct = default)
    {
        var incidents = _incidentData.GetIncidents().Take(limit).ToList();
        var results   = new List<ValidationScenarioResult>(incidents.Count);
        double totalCostUsd = 0.0;

        foreach (var incident in incidents)
        {
            var eventLog = _eventRepository.GetEventLogById(incident.EventId);
            if (eventLog is null)
            {
                _logger.LogWarning(
                    "Validation: IncidentId={IncidentId} skipped — EventLog for EventId '{EventId}' not found.",
                    incident.IncidentId, incident.EventId);
                continue;
            }

            var sw = Stopwatch.StartNew();
            var (result, fromCache, llmMetadata) = await _investigationService.InvestigateAsync(eventLog, bypassCache: true, ct);
            sw.Stop();

            double? scenarioCostUsd = null;
            if (!fromCache && llmMetadata is not null)
            {
                scenarioCostUsd = LlmCostHelper.CalculateClaudeSonnetCostUsd(llmMetadata);
                if (scenarioCostUsd.HasValue)
                    totalCostUsd += scenarioCostUsd.Value;
            }

            var expected       = eventLog.ScenarioMetadata?.ExpectedRootCause;
            var rootCauseMatch = expected.HasValue ? expected.Value == result.RootCause : (bool?)null;

            results.Add(new ValidationScenarioResult
            {
                IncidentId        = incident.IncidentId,
                ScenarioName      = eventLog.ScenarioMetadata?.ScenarioName,
                ExpectedRootCause = expected,
                ActualRootCause   = result.RootCause,
                RootCauseMatch    = rootCauseMatch,
                Confidence        = result.Confidence,
                FromCache         = fromCache,
                ResponseTimeMs    = sw.ElapsedMilliseconds,
                EstimatedCostUsd  = scenarioCostUsd
            });

            _logger.LogInformation(
                "Validation: IncidentId={IncidentId} Expected={Expected} Actual={Actual} Match={Match} Cached={Cached}",
                incident.IncidentId, expected, result.RootCause, rootCauseMatch, fromCache);
        }

        var labelledResults = results.Where(r => r.RootCauseMatch.HasValue).ToList();
        int? correctCount   = labelledResults.Count > 0 ? labelledResults.Count(r => r.RootCauseMatch == true)  : null;
        int? labelledCount  = labelledResults.Count > 0 ? labelledResults.Count : null;
        double? accuracy    = labelledCount > 0
            ? Math.Round((double)correctCount!.Value / labelledCount.Value * 100.0, 1)
            : null;

        return new ValidationRunResponse
        {
            Results            = results.AsReadOnly(),
            TotalScenarios     = results.Count,
            LabelledScenarios  = labelledCount ?? 0,
            CorrectPredictions = correctCount ?? 0,
            AccuracyPercent    = accuracy,
            TotalCostUsd       = Math.Round(totalCostUsd, 4)
        };
    }
}
