"""
Pydantic Settings for the FinancialEventCollector Python service.
≈ ClaudeOptions.cs + CacheOptions.cs + appsettings.json

Defaults are loaded from shared/config/app-config.json (the canonical source
shared with the .NET runtime), then overridden by environment variables.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Load shared defaults ───────────────────────────────────────────────────────
# parents[0] = app/, parents[1] = python/, parents[2] = repo root
_SHARED_CONFIG_PATH = Path(__file__).parents[2] / "shared" / "config" / "app-config.json"

def _load_shared_config() -> dict:
    """Load shared/config/app-config.json; return empty dict if not found."""
    if _SHARED_CONFIG_PATH.exists():
        return json.loads(_SHARED_CONFIG_PATH.read_text(encoding="utf-8"))
    return {}

_shared = _load_shared_config()
_claude_defaults = _shared.get("Claude", {})
_cache_defaults  = _shared.get("Cache", {})


class ClaudeSettings(BaseSettings):
    """
    Configuration for the Anthropic Claude API.
    Env vars use the CLAUDE__ prefix (matches C# Claude:ApiKey → CLAUDE__APIKEY).
    ≈ ClaudeOptions.cs
    """
    apikey:           str = ""
    model:            str = _claude_defaults.get("Model",          "claude-sonnet-4-6")
    max_tokens:       int = _claude_defaults.get("MaxTokens",      1024)
    max_prompt_chars: int = _claude_defaults.get("MaxPromptChars", 600_000)
    api_base_url:     str = _claude_defaults.get("ApiBaseUrl",     "https://api.anthropic.com")
    api_version:      str = _claude_defaults.get("ApiVersion",     "2023-06-01")

    model_config = SettingsConfigDict(env_prefix="CLAUDE__")


class CacheSettings(BaseSettings):
    """
    Configuration for the investigation result cache.
    ≈ CacheOptions.cs
    """
    enabled:   bool = _cache_defaults.get("Enabled",  False)
    ttl_hours: int  = _cache_defaults.get("TtlHours", 24)

    model_config = SettingsConfigDict(env_prefix="CACHE__")


class ApiKeySettings(BaseSettings):
    """
    Pre-shared API key secrets used to authenticate callers via the X-Api-Key header.
    Defaults match the placeholder values in dotnet/src/appsettings.json so both
    runtimes accept the same demo keys out of the box.
    Override via APIKEY__USER_SECRET / APIKEY__ADMIN_SECRET env vars in production.
    ≈ ApiKey:UserSecret / ApiKey:AdminSecret in appsettings.json
    """
    user_secret:  str = "UserSecret"   # matches appsettings.json ApiKey:UserSecret
    admin_secret: str = "AdminSecret"  # matches appsettings.json ApiKey:AdminSecret

    model_config = SettingsConfigDict(env_prefix="APIKEY__")


class Settings(BaseSettings):
    """
    Top-level application settings.
    ≈ combination of appsettings.json sections
    """
    claude:  ClaudeSettings  = ClaudeSettings()
    cache:   CacheSettings   = CacheSettings()
    api_key: ApiKeySettings  = ApiKeySettings()

    model_config = SettingsConfigDict(env_nested_delimiter="__")
