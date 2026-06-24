"""backend/common/config — shared service configuration loader (P4-1-W1).

Pulls together:
  * ``IMDF_WEB_HOST`` / ``IMDF_WEB_PORT``         (server bind)
  * ``SERVICE_NAME`` / per-service port table      (microservice identification)
  * CORS / CSRF allow-list                        (security)
  * JWT secret + algorithm                        (auth)
  * DB URL / data dir / log dir                    (storage)
  * Per-service feature flags                      (debug, eager, rate limit)

The loader is deliberately tiny — no Pydantic, no pydantic-settings — so the
12 service ``main.py`` files can ``from common import get_service_config``
and walk away with a frozen dataclass.

Usage::

    cfg = get_service_config("user_service")
    cfg.port             # 8001
    cfg.jwt_secret       # str (auto-fail if not set in prod)
    cfg.cors_origins     # list[str]
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ── Project root discovery ─────────────────────────────────────────────────
def _find_project_root() -> Path:
    """Walk upward from this file until we find ``backend/`` parent.

    The common package lives at ``backend/common/``; we resolve the absolute
    backend dir by going three levels up. This keeps the loader robust to
    where the user runs the service from.
    """
    anchor = Path(__file__).resolve().parent.parent  # backend/
    return anchor


PROJECT_ROOT: Path = _find_project_root()


# ── .env loader (no external deps) ─────────────────────────────────────────
def _load_dotenv(dotenv_path: Optional[Path] = None) -> dict:
    """Tiny ``KEY=VAL`` parser; honours ``#`` comments and ``KEY='VAL'`` quotes."""
    if dotenv_path is None:
        dotenv_path = PROJECT_ROOT / ".env"
    if not dotenv_path.exists():
        return {}
    result: dict = {}
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip("'\"")
    return result


_DOTENV_VALUES = _load_dotenv()


def _get(key: str, default: str = "") -> str:
    """Resolve ``KEY`` from .env → os.environ → default."""
    if key in _DOTENV_VALUES:
        return _DOTENV_VALUES[key]
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    return default


def _bool(key: str, default: bool = False) -> bool:
    val = _get(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


def _int(key: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    try:
        v = int(_get(key, str(default)))
    except (ValueError, TypeError):
        v = default
    if min_val is not None:
        v = max(v, min_val)
    if max_val is not None:
        v = min(v, max_val)
    return v


# ── Per-service port table (kept in sync with services/*/PORT constants) ───
SERVICE_PORTS: dict = {
    "user_service": 8001,
    "asset_service": 8002,
    "annotation_service": 8003,
    "cleaning_service": 8004,
    "scoring_service": 8005,
    "dataset_service": 8006,
    "evaluation_service": 8007,
    "agent_service": 8008,
    "workflow_service": 8009,
    "notification_service": 8010,
    "search_service": 8011,
    "collection_service": 8012,
}


# ── ServiceConfig dataclass ────────────────────────────────────────────────
@dataclass(frozen=True)
class ServiceConfig:
    """Frozen view of all knobs that a microservice might need.

    Built once per service (or once per test) via :func:`get_service_config`.
    Frozen so accidental writes inside request handlers raise loudly.
    """

    name: str
    host: str
    port: int
    log_level: str
    debug: bool

    cors_origins: List[str]
    cors_allow_credentials: bool

    jwt_secret: str
    jwt_algorithm: str
    jwt_access_ttl_minutes: int
    jwt_refresh_ttl_days: int

    db_url: str
    data_dir: Path
    logs_dir: Path

    request_timeout_seconds: int
    max_concurrent_requests: int
    rate_limit_enabled: bool
    rate_limit_default: str

    metrics_enabled: bool

    @property
    def cors_origins_str(self) -> str:
        return ",".join(self.cors_origins)


def load_config(service_name: str) -> ServiceConfig:
    """Build a :class:`ServiceConfig` for *service_name*.

    Precedence for any knob: ``os.environ`` (highest) → ``.env`` → default.
    """
    name = (service_name or _get("SERVICE_NAME", "")).strip().lower() or "unknown_service"

    host = _get("IMDF_WEB_HOST", "0.0.0.0")
    port = _int(
        "SERVICE_PORT",
        SERVICE_PORTS.get(name, _int("IMDF_WEB_PORT", 8000)),
        min_val=1, max_val=65535,
    )

    log_level = _get("LOG_LEVEL", "INFO").upper()
    debug = _bool("IMDF_DEBUG", False)

    cors_origins = [
        o.strip() for o in _get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
    ] or ["*"]
    cors_allow_credentials = _bool("CORS_ALLOW_CREDENTIALS", True)

    jwt_secret = _get("JWT_SECRET", "")
    if not jwt_secret or jwt_secret == "change-me-in-production":
        if _bool("IMDF_TEST_MODE", False):
            jwt_secret = "test-secret-DO-NOT-USE-IN-PROD-" + secrets.token_hex(8)
        else:
            jwt_secret = ""  # downstream get_current_user will reject missing
    jwt_algorithm = _get("JWT_ALGORITHM", "HS256")
    jwt_access_ttl = _int("JWT_ACCESS_TTL_MINUTES", 30, min_val=1, max_val=24 * 60)
    jwt_refresh_ttl = _int("JWT_REFRESH_TTL_DAYS", 7, min_val=1, max_val=365)

    db_url = _get("IMDF_P2_DB_URL", "") or _get(
        "DATABASE_URL", f"sqlite:///{(PROJECT_ROOT / 'data' / 'imdf_p2.db').as_posix()}"
    )
    data_dir = Path(_get("IMDF_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
    logs_dir = Path(_get("IMDF_LOGS_DIR", str(PROJECT_ROOT / "logs"))).resolve()

    request_timeout = _int("REQUEST_TIMEOUT_SECONDS", 30, min_val=1, max_val=300)
    max_concurrent = _int("MAX_CONCURRENT_REQUESTS", 100, min_val=1, max_val=10000)
    rate_limit_enabled = _bool("RATE_LIMIT_ENABLED", False)  # default OFF for services
    rate_limit_default = _get("RATE_LIMIT_DEFAULT", "100/minute")
    metrics_enabled = _bool("METRICS_ENABLED", True)

    # Ensure directories exist (cheap; idempotent)
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    return ServiceConfig(
        name=name,
        host=host,
        port=port,
        log_level=log_level,
        debug=debug,
        cors_origins=cors_origins,
        cors_allow_credentials=cors_allow_credentials,
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_access_ttl_minutes=jwt_access_ttl,
        jwt_refresh_ttl_days=jwt_refresh_ttl,
        db_url=db_url,
        data_dir=data_dir,
        logs_dir=logs_dir,
        request_timeout_seconds=request_timeout,
        max_concurrent_requests=max_concurrent,
        rate_limit_enabled=rate_limit_enabled,
        rate_limit_default=rate_limit_default,
        metrics_enabled=metrics_enabled,
    )


# ── Per-process singleton ───────────────────────────────────────────────────
_SERVICE_CONFIG_CACHE: dict = {}


def get_service_config(service_name: str) -> ServiceConfig:
    """Return a cached :class:`ServiceConfig` for *service_name*.

    Calling this twice in the same process returns the same object so the
    JWT secret etc. stay consistent across routes.
    """
    if service_name not in _SERVICE_CONFIG_CACHE:
        _SERVICE_CONFIG_CACHE[service_name] = load_config(service_name)
    return _SERVICE_CONFIG_CACHE[service_name]


def reset_cache() -> None:
    """Drop the cached config — used by tests that mutate ``os.environ``."""
    _SERVICE_CONFIG_CACHE.clear()


__all__ = [
    "ServiceConfig",
    "SERVICE_PORTS",
    "get_service_config",
    "load_config",
    "reset_cache",
    "PROJECT_ROOT",
]