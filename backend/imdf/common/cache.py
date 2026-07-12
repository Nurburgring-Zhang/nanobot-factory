"""Cache facade re-exported for ``backend.imdf.common.cache``.

Why this shim exists
====================
The IMDF service tree historically imports ``from backend.imdf.common
import cache`` (see ``backend/imdf/agents/...``, ``backend/imdf/data``
and ``backend/imdf/intelligence`` modules).  The actual cache
implementation was developed in :mod:`backend.gateway.cache` during
P17-A2 and lives there for gateway-level routing concerns (TTL per
endpoint, ``CacheMiddleware``, hot-reload, Redis/fakeredis/memory
backends).

Rather than duplicating 700+ lines of code, this shim re-exports the
gateway cache module so existing IMDF imports keep working AND the
codebase has a single source of truth.

If you need to modify behaviour, change :mod:`backend.gateway.cache`
and re-run the gateway test suite.  This file is intentionally a
thin re-export.
"""
from backend.gateway.cache import (  # noqa: F401
    CacheConfig,
    CacheClient,
    CacheMiddleware,
    InvalidCacheKey,
    cache_get,
    cache_set,
    cache_stats,
    cached,
    get_cache,
    reset_cache_singleton,
)

__all__ = [
    "CacheConfig",
    "CacheClient",
    "CacheMiddleware",
    "InvalidCacheKey",
    "cache_get",
    "cache_set",
    "cache_stats",
    "cached",
    "get_cache",
    "reset_cache_singleton",
]