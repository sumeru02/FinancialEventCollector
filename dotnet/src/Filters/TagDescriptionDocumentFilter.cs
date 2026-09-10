using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

/// <summary>
/// Swashbuckle document filter that registers top-level OpenAPI tag objects with
/// human-readable descriptions. Swagger UI renders these descriptions next to each
/// controller group header (e.g. "Admin (role: admin)  Admin-only configuration endpoints.").
///
/// Tag names must exactly match those produced by RoleTagOperationFilter
/// so Swagger UI merges the description into the correct group.
///
/// The insertion order of TagDescriptions controls the display order
/// of controller groups in the Swagger UI.
/// </summary>
public class TagDescriptionDocumentFilter : IDocumentFilter
{
    /// <summary>
    /// Maps each tag name (as produced by RoleTagOperationFilter) to its
    /// human-readable group description shown in the Swagger UI sidebar.
    /// </summary>
    private static readonly Dictionary<string, string> TagDescriptions = new()
    {
        ["Admin (role: admin)"]      = "Admin-only configuration endpoints.",
        ["Event (role: user)"]       = "Event lineage and AI investigation endpoints.",
        ["Incident (role: user)"]    = "Incident retrieval and AI investigation endpoints.",
        ["Telemetry (role: user)"]   = "In-memory investigation telemetry endpoints.",
        ["Validation (role: admin)"] = "Batch validation / regression-test endpoints.",
    };

    /// <inheritdoc />
    public void Apply(OpenApiDocument swaggerDoc, DocumentFilterContext context)
    {
        foreach (var (name, description) in TagDescriptions)
        {
            swaggerDoc.Tags.Add(new OpenApiTag
            {
                Name        = name,
                Description = description,
            });
        }
    }
}
