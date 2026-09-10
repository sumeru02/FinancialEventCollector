using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using System.Reflection;

/// <summary>
/// Exposes runtime configuration for observability: environment, application version,
/// LLM settings (API key redacted), cache settings, and the complete RootCause enum catalog.
/// </summary>
[ApiController]
[Route("admin")]
[Produces("application/json")]
[Authorize(Roles = "admin")]
public class AdminController : ControllerBase
{
    private readonly ClaudeOptions            _claudeOptions;
    private readonly CacheOptions             _cacheOptions;
    private readonly IWebHostEnvironment      _env;
    private readonly RootCauseCatalogService  _rootCauseCatalog;

    public AdminController(
        IOptions<ClaudeOptions> claudeOptions,
        IOptions<CacheOptions> cacheOptions,
        IWebHostEnvironment env,
        RootCauseCatalogService rootCauseCatalog)
    {
        _claudeOptions    = claudeOptions.Value;
        _cacheOptions     = cacheOptions.Value;
        _env              = env;
        _rootCauseCatalog = rootCauseCatalog;
    }

    /// <summary>Returns a full snapshot of the current runtime configuration.</summary>
    /// <remarks>
    /// Includes environment, application version, LLM settings (API key redacted),
    /// cache settings, and the complete RootCause enum catalog.
    /// </remarks>
    [HttpGet("config")]
    public ActionResult<AdminConfigResponse> GetConfig()
    {
        var version = Assembly.GetExecutingAssembly()
                              .GetName()
                              .Version
                              ?.ToString() ?? "unknown";

        return Ok(new AdminConfigResponse(
            Environment:    _env.EnvironmentName,
            Application:    "FinancialEventCollector",
            Version:        version,
            Llm: new LlmConfigSnapshot(
                Model:      _claudeOptions.Model,
                MaxTokens:  _claudeOptions.MaxTokens,
                ApiBaseUrl: _claudeOptions.ApiBaseUrl,
                ApiVersion: _claudeOptions.ApiVersion
            ),
            Cache: new CacheConfigSnapshot(
                Enabled:  _cacheOptions.Enabled,
                TtlHours: _cacheOptions.TtlHours
            ),
            RootCauseValues: BuildRootCauseCatalog()
        ));
    }

    // ── Private helpers ────────────────────────────────────────────────────────

    /// <summary>
    /// Builds the catalog response from the loaded RootCauseCatalogService.
    /// Replaces the previous hardcoded dictionary.
    /// </summary>
    private IReadOnlyList<RootCauseEntry> BuildRootCauseCatalog()
        => _rootCauseCatalog.AllEntries
            .Select(e => new RootCauseEntry(
                Name:        e.Name,
                Description: e.Description
            ))
            .ToList()
            .AsReadOnly();
}

// ── Response models ────────────────────────────────────────────────────────────

/// <summary>Full config snapshot returned by GET /admin/config.</summary>
public record AdminConfigResponse(
    string                        Environment,
    string                        Application,
    string                        Version,
    LlmConfigSnapshot             Llm,
    CacheConfigSnapshot           Cache,
    IReadOnlyList<RootCauseEntry> RootCauseValues
);

/// <summary>LLM configuration values (API key intentionally excluded).</summary>
public record LlmConfigSnapshot(
    string Model,
    int    MaxTokens,
    string ApiBaseUrl,
    string ApiVersion
);

/// <summary>Cache configuration in use.</summary>
public record CacheConfigSnapshot(
    bool Enabled,
    int  TtlHours
);

/// <summary>A single entry in the RootCause enum catalog.</summary>
public record RootCauseEntry(
    string Name,
    string Description
);
