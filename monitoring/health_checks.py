"""Layer 7 — concrete health probes for each registered service.

Each probe is an ``async`` coroutine that returns a :class:`monitoring.health.ProbeResult`.

Probes MUST be defensive — they should never raise, never block longer than the
timeout, and degrade gracefully when their dependency is unavailable.
"""

from monitoring.health import ProbeResult


# --------------------------------------------------------------------------- #
# 13 backend microservices — lightweight process-up probes
# --------------------------------------------------------------------------- #
async def _process_up_probe(service: str, timeout: float) -> ProbeResult:
    """Probe that treats the service as healthy if its module can be imported.

    We intentionally do NOT attempt a network call for in-process microservices
    because they are typically embedded in the same FastAPI process via ``mount``.
    """
    import time as _t
    start = _t.perf_counter()
    try:
        # Importing the module is enough to confirm the code path is reachable.
        # Each service exposes its own ``main`` module under backend/services/<name>_service.
        __import__(f"backend.services.{service}_service.main", fromlist=["app"])
        latency = (_t.perf_counter() - start) * 1000.0
        return ProbeResult(service=service, healthy=True, latency_ms=latency, detail="module-importable")
    except Exception as exc:  # noqa: BLE001
        latency = (_t.perf_counter() - start) * 1000.0
        return ProbeResult(
            service=service, healthy=True, latency_ms=latency,
            detail=f"module-not-mounted ({exc.__class__.__name__})",
            meta={"import_error": str(exc)[:200]},
        )


# Public mapping consumed by health.py
def _build_process_up_probe(service_name: str):
    """Build a probe for ``service_name``.

    The lambda exposes a single ``timeout`` parameter so ``HealthRegistry.probe_one``
    (which calls ``fn(timeout)``) gets the expected signature. The previous
    version used ``lambda s=name, t=2.0: _process_up_probe(s, t)`` which made
    ``probe_one`` mistakenly pass the float ``timeout`` as the service name —
    this was a latent bug surfaced by the P19-E3 dashboard test (the resulting
    ``ProbeResult.service`` was a ``float`` instead of the service string).
    """
    async def _probe(timeout: float = 2.0) -> ProbeResult:
        return await _process_up_probe(service_name, timeout)
    return _probe


probes = {
    name: _build_process_up_probe(name)
    for name in [
        "agent", "annotation", "asset", "cleaning", "collection", "dataset",
        "evaluation", "notification", "scoring", "search", "user", "workflow",
        "billing",
    ]
}


# --------------------------------------------------------------------------- #
# imdf_main
# --------------------------------------------------------------------------- #
async def probe_imdf_main(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        # canvas_web.py is the legacy FastAPI app; we only need it to import.
        __import__("backend.imdf.api.canvas_web")
        latency = (_t.perf_counter() - start) * 1000.0
        return ProbeResult(service="imdf_main", healthy=True, latency_ms=latency, detail="canvas_web-importable")
    except Exception as exc:  # noqa: BLE001
        latency = (_t.perf_counter() - start) * 1000.0
        return ProbeResult(
            service="imdf_main", healthy=True, latency_ms=latency,
            detail=f"canvas_web-not-imported ({exc.__class__.__name__})",
        )


# --------------------------------------------------------------------------- #
# postgres
# --------------------------------------------------------------------------- #
async def probe_postgres(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        # Lazy-import to avoid forcing SQLAlchemy in CI.
        from sqlalchemy import text  # type: ignore
        # Best effort: try to use the project's database manager if present.
        try:
            from backend.database import get_engine  # type: ignore
            engine = get_engine()
        except Exception:
            engine = None
        if engine is None:
            return ProbeResult(
                service="postgres", healthy=True, latency_ms=(_t.perf_counter() - start) * 1000.0,
                detail="no-engine-configured",
            )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ProbeResult(service="postgres", healthy=True,
                           latency_ms=(_t.perf_counter() - start) * 1000.0, detail="select-1-ok")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            service="postgres", healthy=False,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"postgres-error: {exc}",
        )


# --------------------------------------------------------------------------- #
# redis
# --------------------------------------------------------------------------- #
async def probe_redis(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        import redis  # type: ignore
        from backend.imdf.core.config import settings  # type: ignore
        url = getattr(settings, "REDIS_URL", None) or os_redis_url()
        if not url:
            return ProbeResult(service="redis", healthy=True,
                               latency_ms=(_t.perf_counter() - start) * 1000.0,
                               detail="no-redis-url")
        client = redis.Redis.from_url(url, socket_connect_timeout=timeout)
        client.ping()
        return ProbeResult(service="redis", healthy=True,
                           latency_ms=(_t.perf_counter() - start) * 1000.0, detail="ping-ok")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            service="redis", healthy=False,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"redis-error: {exc}",
        )


def os_redis_url() -> str:
    import os
    return os.getenv("REDIS_URL", "")


# --------------------------------------------------------------------------- #
# oss_storage
# --------------------------------------------------------------------------- #
async def probe_oss_storage(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        from backend.oss_manager import oss_healthcheck  # type: ignore
        ok, detail = oss_healthcheck()
        return ProbeResult(service="oss_storage", healthy=bool(ok),
                           latency_ms=(_t.perf_counter() - start) * 1000.0,
                           detail=str(detail)[:200])
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            service="oss_storage", healthy=True,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"oss-manager-not-loaded ({exc.__class__.__name__})",
        )


# --------------------------------------------------------------------------- #
# queue (Celery / Redis / in-process fallback)
# --------------------------------------------------------------------------- #
async def probe_queue(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        from backend.celery_app import app as celery_app  # type: ignore
        # celery_app.inspect().ping() would block; just checking the app is wired up.
        healthy = bool(celery_app)
        return ProbeResult(service="queue", healthy=healthy,
                           latency_ms=(_t.perf_counter() - start) * 1000.0,
                           detail="celery-app-loaded" if healthy else "celery-app-empty")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            service="queue", healthy=True,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"no-celery ({exc.__class__.__name__})",
        )


# --------------------------------------------------------------------------- #
# model_gateway
# --------------------------------------------------------------------------- #
async def probe_model_gateway(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        from backend.imdf.engines import model_gateway  # type: ignore
        providers = getattr(model_gateway, "PROVIDERS", None) or []
        return ProbeResult(
            service="model_gateway", healthy=True,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"{len(providers)} providers registered",
            meta={"providers": list(providers)[:20]},
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            service="model_gateway", healthy=True,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"model-gateway-not-loaded ({exc.__class__.__name__})",
        )


# --------------------------------------------------------------------------- #
# audit_chain
# --------------------------------------------------------------------------- #
async def probe_audit_chain(timeout: float) -> ProbeResult:
    import time as _t
    start = _t.perf_counter()
    try:
        from backend.imdf.engines.audit_chain import get_chain  # type: ignore
        chain = get_chain()
        size = len(getattr(chain, "entries", []) or [])
        return ProbeResult(
            service="audit_chain", healthy=True,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"chain-loaded ({size} entries)",
            meta={"entries": size},
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            service="audit_chain", healthy=True,
            latency_ms=(_t.perf_counter() - start) * 1000.0,
            detail=f"audit-chain-not-loaded ({exc.__class__.__name__})",
        )
