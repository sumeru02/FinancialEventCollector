using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;

/// <summary>
/// ASP.NET Core authentication handler that validates a pre-shared API key
/// supplied in the X-Api-Key request header.
///
/// Protects cost-incurring endpoints (e.g. POST /incidents/{id}/investigations)
/// from unauthenticated callers who could otherwise trigger unbounded LLM API spend.
///
/// Configuration: set ApiKey:UserSecret and ApiKey:AdminSecret in
/// appsettings.json (or environment variables / secret manager in production).
/// Callers presenting the admin key receive the admin role; those presenting
/// the user key receive the user role. The comparison uses
/// CryptographicOperations.FixedTimeEquals to prevent timing attacks.
/// </summary>
public class ApiKeyAuthHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
    /// <summary>The HTTP request header name callers must populate.</summary>
    public const string HeaderName = "X-Api-Key";

    /// <summary>The authentication scheme name registered in DI.</summary>
    public const string SchemeName = "ApiKey";

    private readonly IConfiguration _configuration;

    public ApiKeyAuthHandler(
        IOptionsMonitor<AuthenticationSchemeOptions> options,
        ILoggerFactory logger,
        UrlEncoder encoder,
        IConfiguration configuration)
        : base(options, logger, encoder)
    {
        _configuration = configuration;
    }

    /// <inheritdoc/>
    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        if (!Request.Headers.TryGetValue(HeaderName, out var headerValues))
            return Task.FromResult(AuthenticateResult.NoResult());

        var providedKey = headerValues.ToString();
        var adminKey    = _configuration["ApiKey:AdminSecret"];
        var userKey     = _configuration["ApiKey:UserSecret"];
        
        if (string.IsNullOrEmpty(userKey))
        {
            Logger.LogWarning(
                "ApiKey:UserSecret is not configured — all API key authentication will fail.");
            return Task.FromResult(
                AuthenticateResult.Fail("API key authentication is not configured on the server."));
        }

        // Constant-time comparison prevents timing-based key enumeration attacks.
        // FixedTimeEquals only guarantees constant time when both spans have the SAME length;
        // differing lengths cause an immediate false return, leaking key length via timing.
        // Fix: HMAC-SHA256 both sides with a fixed internal key to produce equal-length digests
        // before comparing, making the comparison length-independent and truly constant-time.
        var providedHash = ComputeKeyHash(providedKey);

        // Check admin key first — admin is a superset of user access.
        if (!string.IsNullOrEmpty(adminKey) &&
            CryptographicOperations.FixedTimeEquals(providedHash, ComputeKeyHash(adminKey)))
        {
            return Task.FromResult(AuthenticateResult.Success(BuildTicket("AdminClient", "admin")));
        }

        if (CryptographicOperations.FixedTimeEquals(providedHash, ComputeKeyHash(userKey)))
        {
            return Task.FromResult(AuthenticateResult.Success(BuildTicket("ApiKeyClient", "user")));
        }

        return Task.FromResult(AuthenticateResult.Fail("Invalid API key."));
    }

    /// <summary>
    /// Produces a fixed-length HMAC-SHA256 digest of <paramref name="key"/> so that
    /// <see cref="CryptographicOperations.FixedTimeEquals"/> always receives equal-length
    /// spans, eliminating the key-length timing side-channel.
    /// The HMAC key is a static internal constant — its purpose is length normalisation,
    /// not additional secrecy (the API key itself is the secret).
    /// </summary>
    private static ReadOnlySpan<byte> ComputeKeyHash(string key)
    {
        // Static HMAC key used solely to produce a fixed-length digest.
        // Not a secret — its only role is to make both digests the same length.
        ReadOnlySpan<byte> hmacKey = "ApiKeyAuthHandler.FixedLengthComparison"u8;
        return HMACSHA256.HashData(hmacKey, Encoding.UTF8.GetBytes(key));
    }

    private AuthenticationTicket BuildTicket(string name, string role)
    {
        // Admin is a superset of user: grant both claims so that controllers
        // protected with [Authorize(Roles = "user")] remain accessible to admins
        // without having to enumerate "admin,user" on every such controller.
        var claims = role == "admin"
            ? new Claim[] {
                new(ClaimTypes.Name, name),
                new(ClaimTypes.Role, "admin"),
                new(ClaimTypes.Role, "user")
              }
            : new Claim[] {
                new(ClaimTypes.Name, name),
                new(ClaimTypes.Role, role)
              };

        var identity = new ClaimsIdentity(claims, SchemeName);
        return new AuthenticationTicket(new ClaimsPrincipal(identity), SchemeName);
    }

    /// <inheritdoc/>
    protected override Task HandleChallengeAsync(AuthenticationProperties properties)
    {
        Response.StatusCode  = StatusCodes.Status401Unauthorized;
        Response.Headers["WWW-Authenticate"] = $"{SchemeName} realm=\"FinancialEventCollector\"";
        return Task.CompletedTask;
    }
}
