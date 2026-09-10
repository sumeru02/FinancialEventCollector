using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Options;
using Microsoft.OpenApi.Models;
using System.Text.Json.Serialization;
using System.Threading.RateLimiting;

var builder = WebApplication.CreateBuilder(args);

// ── Shared config (canonical defaults for both .NET and Python runtimes) ──────
// Load shared/config/app-config.json first so appsettings.json can override.
// The shared file uses camelCase sections ("claude", "cache") which are mapped
// to the same "Claude" / "Cache" binding keys used by ClaudeOptions / CacheOptions.
var sharedConfigPath = Path.GetFullPath(
    Path.Combine(builder.Environment.ContentRootPath, "..", "..", "..", "shared", "config", "app-config.json"));

if (File.Exists(sharedConfigPath))
{
    builder.Configuration.AddJsonFile(sharedConfigPath, optional: false, reloadOnChange: false);
}

// ── Existing services ─────────────────────────────────────────────────────────
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        // Serialize all enums (e.g. RootCause) as their string names rather than
        // integer ordinals in both API responses and request deserialization.
        options.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter());
    });
builder.Services.AddMemoryCache();
builder.Services.AddSingleton<IIncidentRepository, IncidentRepository>();
builder.Services.AddSingleton<IEventRepository, EventRepository>();
builder.Services.AddSingleton<RootCauseCatalogService>();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new OpenApiInfo
    {
        Title       = "FinancialEventCollector",
        Version     = "1.0.0",
        Description = "Financial event ingestion, indexing, and publishing service with endpoints for data lineage lookup and missing event investigation"
    });

    // Teach Swagger UI about the X-Api-Key header so the "Authorize" button
    // appears and callers can authenticate directly from the UI.
    c.AddSecurityDefinition(ApiKeyAuthHandler.SchemeName, new OpenApiSecurityScheme
    {
        Type        = SecuritySchemeType.ApiKey,
        In          = ParameterLocation.Header,
        Name        = ApiKeyAuthHandler.HeaderName,
        Description = "API key required for protected endpoints. " +
                      "Use ApiKey:UserSecret for standard access, or ApiKey:AdminSecret for admin endpoints. " +
                      "Supply via environment variables APIKEY__USERSECRET / APIKEY__ADMINSECRET in production."
    });
    c.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        {
            new OpenApiSecurityScheme
            {
                Reference = new OpenApiReference
                    { Type = ReferenceType.SecurityScheme, Id = ApiKeyAuthHandler.SchemeName }
            },
            Array.Empty<string>()
        }
    });
    c.OperationFilter<RoleTagOperationFilter>();
    c.DocumentFilter<TagDescriptionDocumentFilter>();

    // Wire up the XML doc file so <summary> tags appear as endpoint descriptions in Swagger UI
    var xmlFile = $"{System.Reflection.Assembly.GetExecutingAssembly().GetName().Name}.xml";
    var xmlPath = Path.Combine(AppContext.BaseDirectory, xmlFile);
    c.IncludeXmlComments(xmlPath);
});

// ── API Key authentication ────────────────────────────────────────────────────
// Protects cost-incurring endpoints from unauthenticated callers.
// Key is read from ApiKey:Secret in configuration (appsettings.json / env var).
builder.Services.AddAuthentication(ApiKeyAuthHandler.SchemeName)
    .AddScheme<AuthenticationSchemeOptions, ApiKeyAuthHandler>(
        ApiKeyAuthHandler.SchemeName, _ => { });
builder.Services.AddAuthorization();

// ── Rate limiting ─────────────────────────────────────────────────────────────
// Fixed-window limiter on the LLM investigation endpoint: 10 calls/minute per IP.
// Prevents quota exhaustion and runaway cost even from authenticated callers.
builder.Services.AddRateLimiter(options =>
{
    options.AddFixedWindowLimiter("llm-investigation", o =>
    {
        o.PermitLimit         = 10;
        o.Window              = TimeSpan.FromMinutes(1);
        o.QueueProcessingOrder = QueueProcessingOrder.OldestFirst;
        o.QueueLimit          = 0; // Reject immediately when limit is reached
    });
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
});

// ── Claude / LLM configuration ────────────────────────────────────────────────
builder.Services.Configure<ClaudeOptions>(
    builder.Configuration.GetSection(ClaudeOptions.SectionName));

// ── Cache configuration ───────────────────────────────────────────────────────
builder.Services.Configure<CacheOptions>(
    builder.Configuration.GetSection(CacheOptions.SectionName));

// Typed HttpClient for Claude — base address and auth headers set once here.
// To switch to a different LLM provider, replace ClaudeService with another
// ILlmService implementation and update the HttpClient registration below.
builder.Services.AddHttpClient<ILlmService, ClaudeService>((sp, client) =>
{
    var opts = sp.GetRequiredService<IOptions<ClaudeOptions>>().Value;
    client.BaseAddress = new Uri(opts.ApiBaseUrl);
    client.DefaultRequestHeaders.Add("x-api-key", opts.ApiKey);
    client.DefaultRequestHeaders.Add("anthropic-version", opts.ApiVersion);
});

// ── Investigation service ─────────────────────────────────────────────────────
builder.Services.AddScoped<IInvestigationService, InvestigationService>();

// ── Validation service ────────────────────────────────────────────────────────
builder.Services.AddScoped<IValidationService, ValidationService>();

// ── Telemetry repository ──────────────────────────────────────────────────────
// Singleton so events persist across requests for the application lifetime.
builder.Services.AddSingleton<ITelemetryRepository, TelemetryRepository>();

// ── Build and configure pipeline ──────────────────────────────────────────────
var app = builder.Build();

// ── Startup secret guard ──────────────────────────────────────────────────────
// Fail fast if API key secrets are not configured in non-Development environments.
// In Development the empty defaults are tolerated so the app can start without secrets.
if (!app.Environment.IsDevelopment())
{
    var userSecret  = app.Configuration["ApiKey:UserSecret"];
    var adminSecret = app.Configuration["ApiKey:AdminSecret"];

    if (string.IsNullOrWhiteSpace(userSecret))
        throw new InvalidOperationException(
            "ApiKey:UserSecret must be set via environment variable APIKEY__USERSECRET " +
            "or a secrets manager. Do not store secrets in appsettings.json.");

    if (string.IsNullOrWhiteSpace(adminSecret))
        throw new InvalidOperationException(
            "ApiKey:AdminSecret must be set via environment variable APIKEY__ADMINSECRET " +
            "or a secrets manager. Do not store secrets in appsettings.json.");
}

app.UseSwagger();
app.UseSwaggerUI(c =>
{
    c.SwaggerEndpoint("/swagger/v1/swagger.json", "FinancialEventCollector 1.0.0");
    c.RoutePrefix = string.Empty; // Serve Swagger UI at root "/"
    // Hide the Swagger/SmartBear top banner to match the cleaner Python/FastAPI look.
    c.HeadContent = "<style>.swagger-ui .topbar { display: none !important; }</style>";
});

app.UseAuthentication();
app.UseAuthorization();
app.UseRateLimiter();

app.MapControllers();

app.Run();
