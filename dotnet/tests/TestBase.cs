using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;

namespace FinancialEventCollector.Tests;

/// <summary>
/// Base class for all test classes that need a fully-initialised
/// <see cref="IncidentRepository"/> backed by the real JSON data files.
/// </summary>
public abstract class TestBase
{
    protected static IncidentRepository     Service              { get; private set; } = null!;
    protected static EventRepository        EventRepository      { get; private set; } = null!;
    protected static InvestigationService   InvestigationService { get; private set; } = null!;
    protected static ValidationService      ValidationService    { get; private set; } = null!;

    /// <summary>
    /// Call this from a [ClassInitialize] method in every derived test class.
    /// </summary>
    protected static void InitialiseService()
    {
        // IncidentRepository and EventRepository read from <ContentRootPath>/data.
        // The test csproj copies the JSON files to the output directory under data\.
        var env = new FakeWebHostEnvironment(AppContext.BaseDirectory);
        Service         = new IncidentRepository(env);
        EventRepository = new EventRepository(env);

        // Build Claude options — shared/config/app-config.json provides canonical defaults,
        // appsettings.json and environment variables override (API key must be present there
        // or in environment variables / user-secrets at test run time).
        var sharedConfigPath = Path.GetFullPath(
            Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "shared", "config", "app-config.json"));

        var configBuilder = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory);

        if (File.Exists(sharedConfigPath))
            configBuilder.AddJsonFile(sharedConfigPath, optional: false, reloadOnChange: false);

        var config = configBuilder
            .AddJsonFile("appsettings.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var claudeOptions = new ClaudeOptions();
        config.GetSection(ClaudeOptions.SectionName).Bind(claudeOptions);

        var httpClient = new HttpClient
        {
            BaseAddress = new Uri(claudeOptions.ApiBaseUrl)
        };
        httpClient.DefaultRequestHeaders.Add("x-api-key",           claudeOptions.ApiKey);
        httpClient.DefaultRequestHeaders.Add("anthropic-version",   claudeOptions.ApiVersion);

        var claudeService = new ClaudeService(
            httpClient,
            Options.Create(claudeOptions),
            NullLogger<ClaudeService>.Instance);

        InvestigationService = new InvestigationService(
            claudeService,
            new MemoryCache(new MemoryCacheOptions()),
            Options.Create(new CacheOptions()),
            Options.Create(claudeOptions),
            NullLogger<InvestigationService>.Instance);

        ValidationService = new ValidationService(
            Service,
            EventRepository,
            InvestigationService,
            NullLogger<ValidationService>.Instance);
    }

    // -------------------------------------------------------------------------
    // Fake IWebHostEnvironment
    // -------------------------------------------------------------------------

    /// <summary>
    /// Minimal <see cref="IWebHostEnvironment"/> that points
    /// <see cref="IHostingEnvironment.ContentRootPath"/> at the supplied directory
    /// so that <see cref="IncidentRepository"/> can locate the Data sub-folder.
    /// </summary>
    protected sealed class FakeWebHostEnvironment : IWebHostEnvironment
    {
        public FakeWebHostEnvironment(string contentRootPath)
        {
            ContentRootPath = contentRootPath;
            ContentRootFileProvider = new PhysicalFileProvider(contentRootPath);
        }

        public string WebRootPath { get; set; } = string.Empty;
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        public string ApplicationName { get; set; } = "FinancialEventCollector.Tests";
        public IFileProvider ContentRootFileProvider { get; set; }
        public string ContentRootPath { get; set; }
        public string EnvironmentName { get; set; } = "Test";
    }
}

public static class ObjectExtensions
{
    public static void Log(this object obj)
    {
        var settings = new JsonSerializerSettings
        {
            Formatting = Formatting.Indented,
            Converters = { new StringEnumConverter() }
        };
        Console.WriteLine(JsonConvert.SerializeObject(obj, settings));
    }
}

