"""
IMDF Unified Settings — 统一配置中心
=====================================
加载顺序: 默认值 → .env文件 → 环境变量覆盖
所有配置项有类型验证和合理默认值。
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field


# ── Project root discovery ────────────────────────────────────────────────
def _find_project_root() -> Path:
    """Walk upward from this file to find project root."""
    anchor = Path(__file__).resolve().parent  # config/
    for parent in [anchor, *anchor.parents]:
        if (parent / ".git").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "api" / "canvas_web.py").exists():
            return parent
    return anchor.parent.resolve()


PROJECT_ROOT: Path = _find_project_root()


# ── .env 加载 ─────────────────────────────────────────────────────────────
def _load_dotenv(dotenv_path: Optional[Path] = None) -> dict:
    """Minimal .env loader — no external dependencies."""
    if dotenv_path is None:
        dotenv_path = PROJECT_ROOT / ".env"
    result = {}
    if dotenv_path.exists():
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                result[key] = val
    return result


_DOTENV_VALUES = _load_dotenv()


def _get(key: str, default: str = "") -> str:
    """Resolve config value: .env → os.environ → default."""
    if key in _DOTENV_VALUES:
        return _DOTENV_VALUES[key]
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    return default


# ── Type-safe config helpers ──────────────────────────────────────────────
def _int(key: str, default: int = 0, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    val_str = _get(key, str(default))
    try:
        val = int(val_str)
    except (ValueError, TypeError):
        val = default
    if min_val is not None:
        val = max(val, min_val)
    if max_val is not None:
        val = min(val, max_val)
    return val


def _float(key: str, default: float = 0.0) -> float:
    val_str = _get(key, str(default))
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return default


def _bool(key: str, default: bool = False) -> bool:
    val_str = _get(key, str(default).lower())
    return val_str.lower() in ("true", "1", "yes", "on")


def _path(key: str, default: str) -> Path:
    return Path(_get(key, default)).resolve()


# ═══════════════════════════════════════════════════════════════════════════
#  Server Settings
# ═══════════════════════════════════════════════════════════════════════════

IMDF_WEB_HOST: str = _get("IMDF_WEB_HOST", "0.0.0.0")
IMDF_WEB_PORT: int = _int("IMDF_WEB_PORT", 8765, min_val=1, max_val=65535)

# uvicorn workers
UVICORN_WORKERS: int = _int("UVICORN_WORKERS", 1, min_val=1, max_val=32)
UVICORN_LOG_LEVEL: str = _get("UVICORN_LOG_LEVEL", "info")

# ═══════════════════════════════════════════════════════════════════════════
#  Robustness / Protection
# ═══════════════════════════════════════════════════════════════════════════

MAX_CONCURRENT_REQUESTS: int = _int("MAX_CONCURRENT_REQUESTS", 100, min_val=1, max_val=10000)
REQUEST_TIMEOUT_SECONDS: int = _int("REQUEST_TIMEOUT_SECONDS", 30, min_val=1, max_val=300)
ENABLE_ROBUSTNESS_MIDDLEWARE: bool = _bool("ENABLE_ROBUSTNESS_MIDDLEWARE", True)

# ═══════════════════════════════════════════════════════════════════════════
#  Rate Limiting (SlowAPI)
# ═══════════════════════════════════════════════════════════════════════════

RATE_LIMIT_DEFAULT: str = _get("RATE_LIMIT_DEFAULT", "100/minute")  # R9.5-W1: 收紧默认限流
RATE_LIMIT_ENABLED: bool = _bool("RATE_LIMIT_ENABLED", True)

# ═══════════════════════════════════════════════════════════════════════════
#  CORS
# ═══════════════════════════════════════════════════════════════════════════

CORS_ALLOW_ORIGINS: List[str] = [
    o.strip() for o in _get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
]

# ═══════════════════════════════════════════════════════════════════════════
#  Audit Chain (OWASP A08:2021 — Software & Data Integrity Failures) P2-3-W3
# ═══════════════════════════════════════════════════════════════════════════
# HMAC-SHA256 签名链用的 secret. 缺失 / 太短会让 audit_chain.AuditChain 启动时 raise
# (fail-fast, 不允许 silent default, 否则签名验证毫无意义).
# 生产环境必须通过 K8s Secret / Vault 注入, 长度 ≥ 32 字节随机.
AUDIT_CHAIN_SECRET: str = _get("AUDIT_CHAIN_SECRET", "")
AUDIT_CHAIN_DB_PATH: Path = _path("AUDIT_CHAIN_DB_PATH", str(PROJECT_ROOT / "data" / "audit_chain.db"))

# ═══════════════════════════════════════════════════════════════════════════
#  Celery / Redis Async Queue (P2-1-W2)
# ═══════════════════════════════════════════════════════════════════════════

# Broker & result backend — both share the same Redis instance by default
REDIS_URL: str = _get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL: str = _get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND: str = _get("CELERY_RESULT_BACKEND", REDIS_URL)

# Result TTL: 24h (long enough for human inspection, short enough to bound memory)
CELERY_RESULT_EXPIRES: int = _int("CELERY_RESULT_EXPIRES", 86400, min_val=60, max_val=604800)

# Worker tuning
CELERY_TASK_TIME_LIMIT: int = _int("CELERY_TASK_TIME_LIMIT", 600, min_val=10, max_val=86400)
CELERY_TASK_SOFT_TIME_LIMIT: int = _int("CELERY_TASK_SOFT_TIME_LIMIT", 540, min_val=10, max_val=86400)
CELERY_WORKER_PREFETCH_MULTIPLIER: int = _int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1, min_val=1, max_val=32)
CELERY_WORKER_MAX_TASKS_PER_CHILD: int = _int("CELERY_WORKER_MAX_TASKS_PER_CHILD", 200, min_val=10, max_val=10000)

# Task queues — route by task type for SLA isolation
CELERY_TASK_DEFAULT_QUEUE: str = _get("CELERY_TASK_DEFAULT_QUEUE", "imdf.default")
CELERY_TASK_ROUTES: dict = {
    "imdf.tasks.render_video.*": {"queue": "imdf.video"},
    "imdf.tasks.score_aesthetic.*": {"queue": "imdf.cpu"},
    "imdf.tasks.ocr_extract.*": {"queue": "imdf.cpu"},
    "imdf.tasks.watermark_embed.*": {"queue": "imdf.video"},
    "imdf.tasks.vector_index.*": {"queue": "imdf.index"},
    "imdf.tasks.model_gateway.*": {"queue": "imdf.network"},
    "imdf.tasks.stats_aggregate.*": {"queue": "imdf.cpu"},
    # P6-Fix-C-5: SLA breach monitor — 30min beat schedule, low-priority queue
    "tickets.tasks.sla_monitor.*": {"queue": "imdf.cpu"},
}

# Celery beat periodic schedule (P6-Fix-C-5 adds the SLA breach scan)
CELERY_BEAT_SCHEDULE: dict = {
    "sla-breach-check-every-30min": {
        "task": "tickets.tasks.sla_monitor.run_sla_breach_check",
        "schedule": 1800.0,  # 30 min in seconds
        "options": {"queue": "imdf.cpu"},
    },
}

# Eager mode for tests / dev (no broker roundtrip)
CELERY_TASK_ALWAYS_EAGER: bool = _bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES: bool = _bool("CELERY_TASK_EAGER_PROPAGATES", True)

# Toggle for the /api/queue/health endpoint when broker is unavailable
CELERY_HEALTH_REQUIRED: bool = _bool("CELERY_HEALTH_REQUIRED", True)

# ═══════════════════════════════════════════════════════════════════════════
#  Data & Storage
# ═══════════════════════════════════════════════════════════════════════════

DATA_DIR: Path = _path("IMDF_DATA_DIR", str(PROJECT_ROOT / "data"))
LOGS_DIR: Path = _path("IMDF_LOGS_DIR", str(PROJECT_ROOT / "logs"))

# ── P2-1-W3: Object Storage (OSS / MinIO) ──
# Auto-detected: explicit OSS_BACKEND wins; else infer from env; else mock.
# When credentials are missing the runtime auto-falls-back to in-memory mock
# (no 500), so dev/CI never breaks.
OSS_BACKEND: str = _get("OSS_BACKEND", "auto")  # auto | oss2 | minio | mock
OSS_ENDPOINT: str = _get("OSS_ENDPOINT", "")
OSS_BUCKET: str = _get("OSS_BUCKET", "imdf-objects")
OSS_REGION: str = _get("OSS_REGION", "cn-hangzhou")
OSS_ACCESS_KEY_ID: str = _get("OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET: str = _get("OSS_ACCESS_KEY_SECRET", "")
OSS_SECURE: bool = _bool("OSS_SECURE", True)
OSS_PRESIGN_EXPIRES: int = _int("OSS_PRESIGN_EXPIRES", 3600, min_val=60, max_val=86400)

# MinIO 专用 (若 MINIO_* 未设, fallback 到 OSS_* 便于同一份 .env 通用)
MINIO_ENDPOINT: str = _get("MINIO_ENDPOINT", OSS_ENDPOINT)
MINIO_BUCKET: str = _get("MINIO_BUCKET", OSS_BUCKET)
MINIO_ACCESS_KEY: str = _get("MINIO_ACCESS_KEY", OSS_ACCESS_KEY_ID)
MINIO_SECRET_KEY: str = _get("MINIO_SECRET_KEY", OSS_ACCESS_KEY_SECRET)
MINIO_REGION: str = _get("MINIO_REGION", "us-east-1")
MINIO_SECURE: bool = _bool("MINIO_SECURE", False)

# ═══════════════════════════════════════════════════════════════════════════
#  Memory Limits
# ═══════════════════════════════════════════════════════════════════════════

MEMORY_MAX_MB: int = _int("MEMORY_MAX_MB", 2048, min_val=128, max_val=65536)
MEMORY_HIGH_MB: int = _int("MEMORY_HIGH_MB", 1536, min_val=64, max_val=65536)

# ═══════════════════════════════════════════════════════════════════════════
#  systemd Watchdog
# ═══════════════════════════════════════════════════════════════════════════

WATCHDOG_SEC: int = _int("WATCHDOG_SEC", 30, min_val=5, max_val=300)
WATCHDOG_ENABLED: bool = _bool("WATCHDOG_ENABLED", True)

# ═══════════════════════════════════════════════════════════════════════════
#  Debug / Development
# ═══════════════════════════════════════════════════════════════════════════

DEBUG: bool = _bool("IMDF_DEBUG", False)
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO" if not _bool("IMDF_DEBUG", False) else "DEBUG")

# ═══════════════════════════════════════════════════════════════════════════
#  Startup Summary
# ═══════════════════════════════════════════════════════════════════════════


def print_config_summary() -> None:
    """Print a formatted config summary at startup."""
    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        "║          IMDF Configuration Summary                         ║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Project Root:      {str(PROJECT_ROOT):<44s} ║",
        f"║  Server:            {IMDF_WEB_HOST}:{IMDF_WEB_PORT:<44d} ║",
        f"║  Workers:           {UVICORN_WORKERS:<44d} ║",
        f"║  Log Level:         {LOG_LEVEL:<44s} ║",
        f"║  Debug Mode:        {str(DEBUG):<44s} ║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Max Concurrent:    {MAX_CONCURRENT_REQUESTS:<44d} ║",
        f"║  Request Timeout:   {REQUEST_TIMEOUT_SECONDS}s{'':>42s} ║",
        f"║  Robustness:        {'ENABLED' if ENABLE_ROBUSTNESS_MIDDLEWARE else 'DISABLED':<44s} ║",
        f"║  Rate Limit:        {RATE_LIMIT_DEFAULT if RATE_LIMIT_ENABLED else 'DISABLED':<44s} ║",
        f"║  Watchdog:          {'ENABLED' if WATCHDOG_ENABLED else 'DISABLED'} ({WATCHDOG_SEC}s){'':>30s} ║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Data Dir:          {str(DATA_DIR):<44s} ║",
        f"║  Logs Dir:          {str(LOGS_DIR):<44s} ║",
        f"║  Memory Max:        {MEMORY_MAX_MB} MB{'':>40s} ║",
        f"║  Memory High:       {MEMORY_HIGH_MB} MB{'':>40s} ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
    ]
    for line in lines:
        print(line, flush=True)


def to_dict() -> dict:
    """Export all settings as a dict."""
    return {
        "project_root": str(PROJECT_ROOT),
        "host": IMDF_WEB_HOST,
        "port": IMDF_WEB_PORT,
        "workers": UVICORN_WORKERS,
        "log_level": UVICORN_LOG_LEVEL,
        "debug": DEBUG,
        "max_concurrent_requests": MAX_CONCURRENT_REQUESTS,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "robustness_enabled": ENABLE_ROBUSTNESS_MIDDLEWARE,
        "rate_limit": RATE_LIMIT_DEFAULT if RATE_LIMIT_ENABLED else "disabled",
        "watchdog_sec": WATCHDOG_SEC if WATCHDOG_ENABLED else 0,
        "data_dir": str(DATA_DIR),
        "logs_dir": str(LOGS_DIR),
        "memory_max_mb": MEMORY_MAX_MB,
        "memory_high_mb": MEMORY_HIGH_MB,
        "cors_origins": CORS_ALLOW_ORIGINS,
        # P2-1-W2 async queue
        "celery_broker_url": CELERY_BROKER_URL,
        "celery_result_backend": CELERY_RESULT_BACKEND,
        "celery_default_queue": CELERY_TASK_DEFAULT_QUEUE,
        # P2-1-W3 object storage
        "oss_backend": OSS_BACKEND,
        "oss_endpoint": OSS_ENDPOINT,
        "oss_bucket": OSS_BUCKET,
        "oss_region": OSS_REGION,
        "oss_secure": OSS_SECURE,
        "oss_presign_expires": OSS_PRESIGN_EXPIRES,
        "minio_endpoint": MINIO_ENDPOINT,
        "minio_bucket": MINIO_BUCKET,
        # P2-3-W3 audit chain (OWASP A08)
        "audit_chain_secret_set": bool(AUDIT_CHAIN_SECRET),
        "audit_chain_db_path": str(AUDIT_CHAIN_DB_PATH),
    }


# Ensure directories
os.makedirs(str(DATA_DIR), exist_ok=True)
os.makedirs(str(LOGS_DIR), exist_ok=True)
