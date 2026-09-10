namespace FinancialEventCollector.Tests;

[TestClass]
public class IntegrationTests : TestBase
{
    [ClassInitialize]
    public static void ClassInitialize(TestContext _) => InitialiseService();

    // ── Validation tests ──────────────────────────────────────────────────────

    /// <summary>
    /// Runs the full validation pipeline via <see cref="ValidationService"/> and
    /// asserts that every labelled incident's root cause is correctly identified
    /// by the LLM (RootCauseMatch == true).
    /// </summary>
    [TestMethod]
    public async Task ValidationRun_Incidents_RootCauseMatchIsTrue()
    {
        var response = await ValidationService.RunAsync(limit: 10);

        response.Log();

        var labelledResults = response.Results
            .Where(r => r.RootCauseMatch.HasValue)
            .ToList();

        foreach (var scenario in labelledResults)
        {
            Assert.IsTrue(scenario.RootCauseMatch == true,
                $"RootCauseMatch failed for IncidentId={scenario.IncidentId} " +
                $"Scenario={scenario.ScenarioName}: " +
                $"Expected={scenario.ExpectedRootCause}, Actual={scenario.ActualRootCause}");
        }
    }
}
