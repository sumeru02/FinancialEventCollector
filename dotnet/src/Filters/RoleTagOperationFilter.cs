using Microsoft.AspNetCore.Authorization;
using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

/// <summary>
/// Swashbuckle operation filter that appends the minimum required role to each
/// controller's Swagger UI tag, e.g. "Admin (role: admin)" or "Incident (role: user)".
/// Reads the AuthorizeAttribute.Roles value directly from the controller
/// class so the label always stays in sync with the actual policy.
/// Note: admin callers also satisfy "user"-tagged endpoints because the
/// ApiKeyAuthHandler grants both claims to the admin key.
/// </summary>
public class RoleTagOperationFilter : IOperationFilter
{
    public void Apply(OpenApiOperation operation, OperationFilterContext context)
    {
        var authorizeAttr = context.MethodInfo.DeclaringType?
            .GetCustomAttributes(true)
            .OfType<AuthorizeAttribute>()
            .FirstOrDefault();

        if (authorizeAttr is null) return; // No [Authorize] on this controller — leave tag unchanged

        var controllerName = context.MethodInfo.DeclaringType!.Name
            .Replace("Controller", string.Empty);

        var role = authorizeAttr.Roles ?? "user";
        operation.Tags = [new OpenApiTag { Name = $"{controllerName} (role: {role})" }];
    }
}
