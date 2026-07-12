"""P19-D1 — 20-service health probe tests.

Covers:
* All 20 DEFAULT_SERVICES probe (returns a ProbeResult for each).
* Aggregated endpoint aggregates status (ok / degraded / down).
* 5-second TTL cache: second call within 5s returns identical aggregate without
  re-probing (we assert by patching probe_one and counting calls).
* 1 deliberately failing service → aggregated status degrades, unhealthy list
  contains it.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitoring import health as health_mod  # noqa: E402


@pytest.fixture
def fresh_registry():
    reg = health_mod.HealthRegistry(cache_ttl_seconds=5.0)
    return reg


async def _always_ok(timeout: float = 2.0, service: str = "unknown"):
    return health_mod.ProbeResult(
        service=service, healthy=True, latency_ms=0.5, detail="ok",
    )


async def _always_fail(timeout: float = 2.0, service: str = "unknown"):
    return health_mod.ProbeResult(
        service=service, healthy=False, latency_ms=1.0, detail="intentional-fail",
    )


def _make_ok_for(svc: str):
    async def _probe(timeout: float = 2.0):
        return health_mod.ProbeResult(service=svc, healthy=True, latency_ms=0.5, detail="ok")
    return _probe


def _make_fail_for(svc: str):
    async def _probe(timeout: float = 2.0):
        return health_mod.ProbeResult(service=svc, healthy=False, latency_ms=1.0, detail="intentional-fail")
    return _probe


@pytest.mark.asyncio
async def test_default_services_count_is_20():
    reg = health_mod.get_registry()
    assert len(reg.services()) == 20
    # Spot-check: must include all 13 backend microservices + 7 cross-cutting.
    expected_subset = {
        "agent", "annotation", "asset", "cleaning", "collection",
        "dataset", "evaluation", "notification", "scoring", "search",
        "user", "workflow", "billing",
        "imdf_main", "audit_chain", "model_gateway",
        "postgres", "redis", "oss_storage", "queue",
    }
    assert set(reg.services()) == expected_subset


@pytest.mark.asyncio
async def test_all_probes_return_when_all_healthy(fresh_registry):
    for svc in fresh_registry.services():
        fresh_registry.register(svc, _make_ok_for(svc))
    agg = await fresh_registry.deep_check(force=True)
    assert agg["status"] == "ok"
    assert agg["healthy"] == 20
    assert agg["unhealthy"] == 0
    assert agg["unhealthy_services"] == []
    assert len(agg["results"]) == 20


@pytest.mark.asyncio
async def test_one_failing_service_marks_aggregated_down(fresh_registry):
    for svc in fresh_registry.services():
        if svc == "redis":
            fresh_registry.register(svc, _make_fail_for(svc))
        else:
            fresh_registry.register(svc, _make_ok_for(svc))
    agg = await fresh_registry.deep_aggregated(force=True)
    assert agg["status"] in ("degraded", "down")  # 1/20 fail → degraded (not down)
    assert "redis" in agg["unhealthy_services"]
    assert agg["unhealthy"] == 1
    assert agg["healthy"] == 19
    assert agg["aggregated"]["unhealthy_services"] == agg["unhealthy_services"]


@pytest.mark.asyncio
async def test_all_failing_marks_status_down(fresh_registry):
    for svc in fresh_registry.services():
        fresh_registry.register(svc, _make_fail_for(svc))
    agg = await fresh_registry.deep_check(force=True)
    assert agg["status"] == "down"
    assert agg["healthy"] == 0
    assert agg["unhealthy"] == 20


@pytest.mark.asyncio
async def test_ttl_cache_returns_same_aggregate_within_5s(fresh_registry):
    """Second call within 5s must return the cached aggregate."""
    calls = {"n": 0}

    async def counting_probe(timeout: float = 2.0):
        calls["n"] += 1
        return health_mod.ProbeResult(
            service="agent", healthy=True, latency_ms=0.1, detail="ok",
        )

    # Register a probe that counts how many times it's been called.
    for svc in fresh_registry.services():
        fresh_registry.register(svc, counting_probe)

    # First call: probes run once per service.
    a = await fresh_registry.deep_check(force=True)
    first_calls = calls["n"]
    assert first_calls == 20  # 20 probes called once
    # Second call within 5s → cache hit → no probes re-run.
    b = await fresh_registry.deep_check(force=False)
    assert calls["n"] == first_calls  # unchanged
    assert b["status"] == a["status"]
    assert b["healthy"] == a["healthy"]
    assert b["unhealthy"] == a["unhealthy"]


@pytest.mark.asyncio
async def test_ttl_cache_expires_after_5s(fresh_registry, monkeypatch):
    """Force-monotonic control: after the TTL expires, probes run again."""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake_now["t"])

    calls = {"n": 0}

    async def counting_probe(timeout: float = 2.0):
        calls["n"] += 1
        return health_mod.ProbeResult(service="agent", healthy=True,
                                      latency_ms=0.1, detail="ok")

    for svc in fresh_registry.services():
        fresh_registry.register(svc, counting_probe)

    await fresh_registry.deep_check(force=True)
    assert calls["n"] == 20

    # Move fake clock forward — still within TTL (5s).
    fake_now["t"] = 1003.0
    await fresh_registry.deep_check(force=False)
    assert calls["n"] == 20  # still cached

    # Move past TTL.
    fake_now["t"] = 1010.0
    await fresh_registry.deep_check(force=False)
    assert calls["n"] == 40  # probes ran again


@pytest.mark.asyncio
async def test_force_bypasses_cache(fresh_registry):
    calls = {"n": 0}

    async def counting_probe(timeout: float = 2.0):
        calls["n"] += 1
        return health_mod.ProbeResult(service="agent", healthy=True,
                                      latency_ms=0.1, detail="ok")

    for svc in fresh_registry.services():
        fresh_registry.register(svc, counting_probe)

    await fresh_registry.deep_check(force=True)
    await fresh_registry.deep_check(force=True)  # force=True → re-probe
    await fresh_registry.deep_check(force=True)
    assert calls["n"] == 60  # 20 * 3


@pytest.mark.asyncio
async def test_invalidate_cache_resets(fresh_registry):
    calls = {"n": 0}

    async def counting_probe(timeout: float = 2.0):
        calls["n"] += 1
        return health_mod.ProbeResult(service="agent", healthy=True,
                                      latency_ms=0.1, detail="ok")

    for svc in fresh_registry.services():
        fresh_registry.register(svc, counting_probe)

    await fresh_registry.deep_check(force=True)
    assert calls["n"] == 20
    fresh_registry.invalidate_cache()
    await fresh_registry.deep_check(force=False)
    assert calls["n"] == 40