"""
API key authentication dependency.
≈ dotnet/src/Auth/ApiKeyAuthHandler.cs

Callers must supply a valid pre-shared key in the X-Api-Key request header.
The comparison uses hmac.compare_digest (constant-time) to prevent timing attacks,
mirroring CryptographicOperations.FixedTimeEquals used in the .NET handler.

Roles:
  admin — presented the AdminSecret key
  user  — presented the UserSecret key

Usage (router-level, equivalent to class-level [Authorize]):
    router = APIRouter(dependencies=[Depends(verify_api_key)])
"""
from __future__ import annotations

import hmac
import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings

logger = logging.getLogger(__name__)

# Declares the X-Api-Key header in the OpenAPI schema so the Swagger UI
# "Authorize" button appears — equivalent to AddSecurityDefinition() in Program.cs.
_X_API_KEY_HEADER = APIKeyHeader(name="X-Api-Key", auto_error=False)


def _get_settings() -> Settings:
    """Default dependency — overridden in main.py with the application singleton."""
    return Settings()


def verify_api_key(
    api_key: str | None = Security(_X_API_KEY_HEADER),
    settings: Settings  = Depends(_get_settings),
) -> str:
    """
    FastAPI security dependency that validates the X-Api-Key header.

    Returns the matched role string ('admin' or 'user') on success.
    Raises HTTP 401 if the header is absent or the key does not match.

    ≈ ApiKeyAuthHandler.HandleAuthenticateAsync() + HandleChallengeAsync()
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Api-Key header is required.",
            headers={"WWW-Authenticate": 'ApiKey realm="FinancialEventCollector"'},
        )

    # Mirror ApiKeyAuthHandler.cs lines 49-55: if UserSecret is null/empty, reject every
    # request and log a warning — the server is misconfigured.
    if not settings.api_key.user_secret:
        logger.warning(
            "api_key.user_secret is not configured — all API key authentication will fail."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication is not configured on the server.",
            headers={"WWW-Authenticate": 'ApiKey realm="FinancialEventCollector"'},
        )

    provided = api_key.encode()

    # Check admin key first — admin is a superset of user access.
    # ≈ ApiKeyAuthHandler lines 61-66
    if settings.api_key.admin_secret and hmac.compare_digest(
        provided, settings.api_key.admin_secret.encode()
    ):
        return "admin"

    # ≈ ApiKeyAuthHandler lines 68-72
    if settings.api_key.user_secret and hmac.compare_digest(
        provided, settings.api_key.user_secret.encode()
    ):
        return "user"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key.",
        headers={"WWW-Authenticate": 'ApiKey realm="FinancialEventCollector"'},
    )


def require_role(role: str) -> Callable[[str], str]:
    """
    Returns a FastAPI dependency that enforces a minimum role.

    admin keys satisfy both require_role("admin") and require_role("user")
    because admin is a superset of user — mirroring the .NET behaviour where
    [Authorize(Roles = "user")] is satisfied by any authenticated principal
    whose role claim includes "user", and the ApiKeyAuthHandler grants admin
    keys the "admin" role only (not "user"), so admin keys are explicitly
    allowed through the user-role check here as well.

    ≈ [Authorize(Roles = "admin")] / [Authorize(Roles = "user")] on .NET controllers.

    Usage:
        router = APIRouter(dependencies=[Depends(require_role("admin"))])
    """
    def _check(actual_role: str = Depends(verify_api_key)) -> str:
        # admin is a superset: an admin key may access user-role endpoints.
        if actual_role == role or (role == "user" and actual_role == "admin"):
            return actual_role
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' required.",
        )
    return _check
