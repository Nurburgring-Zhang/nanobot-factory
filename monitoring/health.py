"""Layer 7 — 20-service deep health checks.

Two endpoints:

* ``GET /healthz``     — liveness (always 200 if the process is up)
* ``GET /readyz``      — readiness (DB ping only — legacy from P3-8)
* ``GET /healthz/deep`` — aggregated check across 20 named services

Each named service is represented by a probe in :mod:`monitoring.health_checks`.
A probe implements ``async def probe(timeout: float) -> ProbeResult``.

If a probe is missing (service not registered in this deployment), a default
``deferred`` result is returned so the JSON shape stays stable.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Default registry of 20 services. Order matters for dashboard rendering.
DEFAULT_SERVICES: List[str] = [
    # core 13 backend microservices
    "agent",
    "annotation",
    "asset",
    "cleaning",
    "collection",
    "dataset",
    "evaluation",
    "notification",
    "scoring",
    "search",
    "user",
    "workflow",
    "billing",
    # main + cross-cutting
    "imdf_main",
    "audit_chain",
    "model_gateway",
    # infrastructure
    "postgres",
    "redis",
    "oss_storage",
    "queue",
]


@dataclass
class ProbeResult:
    service: str
    healthy: bool
    latency_ms: float
    detail: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp))
        return d


ProbeFn = Callable[[float], Awaitable[ProbeResult]]


class HealthRegistry:
    """Holds the per-service probe functions + cache."""

    def __init__(self, default_timeout: float = 2.0,
                 cache_ttl_seconds: float = 5.0) -> None:
        self.default_timeout = default_timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self._probes: Dict[str, ProbeFn] = {}
        self._last_results: Dict[str, ProbeResult] = {}
        self._lock = asyncio.Lock()
        # TTL cache — protects the 20 probes from being hammered on every request.
        self._cache_ts: float = 0.0
        self._cache_results: List[ProbeResult] = []
        self._cache_aggregate: Dict[str, Any] = {}

    def register(self, service: str, fn: ProbeFn) -> None:
        self._probes[service] = fn

    def services(self) -> List[str]:
        return list(DEFAULT_SERVICES)

    def invalidate_cache(self) -> None:
        """Force the next deep_check to re-probe (tests use this)."""
        self._cache_ts = 0.0
        self._cache_results = []
        self._cache_aggregate = {}

    async def probe_one(self, service: str, *, timeout: Optional[float] = None,
                        force: bool = False) -> ProbeResult:
        timeout = timeout if timeout is not None else self.default_timeout
        fn = self._probes.get(service)
        if fn is None:
            return ProbeResult(
                service=service,
                healthy=True,  # unknown services are reported as "not instrumented" but healthy
                latency_ms=0.0,
                detail="not-instrumented",
                meta={"registered": False},
            )
        start = time.perf_counter()
        try:
            res = await asyncio.wait_for(fn(timeout), timeout=timeout)
        except asyncio.TimeoutError:
            res = ProbeResult(
                service=service, healthy=False,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                detail=f"timeout after {timeout}s",
            )
        except Exception as exc:  # noqa: BLE001
            res = ProbeResult(
                service=service, healthy=False,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                detail=f"{exc.__class__.__name__}: {exc}",
            )
        self._last_results[service] = res
        if force:
            self.invalidate_cache()
        return res

    async def probe_all(self, *, timeout: Optional[float] = None) -> List[ProbeResult]:
        coros = [self.probe_one(s, timeout=timeout) for s in self.services()]
        return await asyncio.gather(*coros)

    def aggregate(self, results: List[ProbeResult]) -> Dict[str, Any]:
        healthy = sum(1 for r in results if r.healthy)
        unhealthy = [r.service for r in results if not r.healthy]
        avg_lat = (sum(r.latency_ms for r in results) / len(results)) if results else 0.0
        # Status: ok / degraded / down
        if not results:
            status = "unknown"
        elif not unhealthy:
            status = "ok"
        elif healthy == 0:
            status = "down"
        else:
            status = "degraded"
        # P19-E3 HB-1: publish per-service status + latency to Prometheus
        # so the Grafana dashboard / alert rules have a real metric to render.
        self._publish_probe_metrics(results)
        return {
            "status": status,
            "checked_at": time.time(),
            "total": len(results),
            "healthy": healthy,
            "unhealthy": len(unhealthy),
            "unhealthy_services": unhealthy,
            "avg_latency_ms": round(avg_lat, 2),
            "results": [r.to_dict() for r in results],
        }

    def _publish_probe_metrics(self, results: List[ProbeResult]) -> None:
        """Update Prometheus gauges for every probed service.

        Called from :meth:`aggregate` so any entry-point (deep_check, the FastAPI
        route, the dashboard widget, the alert rule) sees a fresh sample.

        Probe detail tags that mean "module not loaded / not instrumented" are
        surfaced as ``status=2`` (UNKNOWN) instead of UP, so a missing service
        shows up on the dashboard as a third color (gray) and triggers the
        HealthProbeDown alert (since the alert only fires on ``status=0`` DOWN,
        this also keeps false-positives under control).
        """
        # Lazy import — observability pulls in threading which is fine for the
        # server process, but the health module is also imported by tools that
        # only want the dataclass definitions.
        try:
            from monitoring.observability import (
                set_health_probe,
                HEALTH_STATUS_DOWN,
                HEALTH_STATUS_UP,
                HEALTH_STATUS_UNKNOWN,
            )
        except Exception:  # noqa: BLE001
            # If the metrics module is unavailable (extremely minimal CI),
            # fall back to a no-op so probe results still flow.
            return

        for r in results:
            detail = (r.detail or "").lower()
            # Anything tagged "not-instrumented" / "not-loaded" / "not-mounted"
            # is genuinely a 3rd-state (UNKNOWN) — not a green UP — and must
            # show up on the dashboard as a separate visual cue.
            unknown_markers = (
                "not-instrumented",
                "not-loaded",
                "not-mounted",
                "module-not-loaded",
                "module-not-mounted",
                "no-engine-configured",
                "no-redis-url",
                "no-celery",
                "oss-manager-not-loaded",
                "audit-chain-not-loaded",
                "model-gateway-not-loaded",
                "celery-app-empty",
            )
            if r.healthy and any(m in detail for m in unknown_markers):
                set_health_probe(
                    r.service,
                    status=HEALTH_STATUS_UNKNOWN,
                    latency_ms=r.latency_ms,
                )
            elif r.healthy:
                set_health_probe(
                    r.service,
                    status=HEALTH_STATUS_UP,
                    latency_ms=r.latency_ms,
                )
            else:
                set_health_probe(
                    r.service,
                    status=HEALTH_STATUS_DOWN,
                    latency_ms=r.latency_ms,
                )

    async def deep_check(self, *, force: bool = False,
                         bypass_cache: bool = False) -> Dict[str, Any]:
        """Run all probes (or return cached aggregate if TTL not expired).

        Parameters
        ----------
        force: bypass the TTL cache and re-probe every service.
        bypass_cache: alias used by some tests / hot paths.
        """
        if bypass_cache:
            force = True
        now = time.monotonic()
        if not force and self._cache_ts and (now - self._cache_ts) < self.cache_ttl_seconds:
            return dict(self._cache_aggregate)
        async with self._lock:
            results = await self.probe_all()
        agg = self.aggregate(results)
        self._cache_ts = now
        self._cache_results = results
        self._cache_aggregate = agg
        return agg

    # -- aggregated endpoint -------------------------------------------------- #
    async def deep_aggregated(self, *, force: bool = False) -> Dict[str, Any]:
        """Compatibility wrapper for ``/health/deep/aggregated`` — same shape as
        :func:`deep_check` but adds an explicit ``aggregated`` field summarising
        status / counts / unhealthy services so the dashboard can render a
        single card without iterating ``results``."""
        agg = await self.deep_check(force=force)
        aggregated = {
            "status": agg.get("status"),
            "healthy": agg.get("healthy"),
            "unhealthy": agg.get("unhealthy"),
            "total": agg.get("total"),
            "unhealthy_services": agg.get("unhealthy_services"),
            "avg_latency_ms": agg.get("avg_latency_ms"),
        }
        out = dict(agg)
        out["aggregated"] = aggregated
        return out


# --------------------------------------------------------------------------- #
# Process-level singleton + lazy default probes
# --------------------------------------------------------------------------- #
_REGISTRY: Optional[HealthRegistry] = None


def get_registry() -> HealthRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = HealthRegistry()
        _install_default_probes(_REGISTRY)
    return _REGISTRY


def _install_default_probes(reg: HealthRegistry) -> None:
    """Install lightweight probes that don't import heavy dependencies.

    The probes that need the real services (DB / Redis / OSS / queue) are
    defined in :mod:`monitoring.health_checks` and registered lazily on first
    call. They all share the same fallback pattern: any ImportError or
    environment gap is reported as ``deferred`` and the registry still works.
    """
    from monitoring.health_checks import (  # noqa: WPS433 (lazy import intentional)
        probe_imdf_main,
        probe_postgres,
        probe_redis,
        probe_oss_storage,
        probe_queue,
        probe_model_gateway,
        probe_audit_chain,
    )
    from monitoring.health_checks import probes as service_probes  # 13 backend services

    for name, fn in service_probes.items():
        reg.register(name, fn)
    reg.register("imdf_main", probe_imdf_main)
    reg.register("postgres", probe_postgres)
    reg.register("redis", probe_redis)
    reg.register("oss_storage", probe_oss_storage)
    reg.register("queue", probe_queue)
    reg.register("model_gateway", probe_model_gateway)
    reg.register("audit_chain", probe_audit_chain)


# --------------------------------------------------------------------------- #
# FastAPI route helpers (consumed by :mod:`monitoring.api`)
# --------------------------------------------------------------------------- #
async def deep_check_endpoint() -> Dict[str, Any]:
    return await get_registry().deep_check()


async def liveness_endpoint() -> Dict[str, Any]:
    return {"status": "ok", "pid": os.getpid(), "ts": time.time()}
