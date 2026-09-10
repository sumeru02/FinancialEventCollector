"""
Shared rate-limiter instance.

Defined in its own module to avoid circular imports between main.py and routers.
≈ ASP.NET Core rate-limiting middleware
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
