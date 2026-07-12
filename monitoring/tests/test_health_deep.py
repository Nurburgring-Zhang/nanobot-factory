"""Layer 7 — Health checks tests."""

from __future__ import annotations

import asyncio
import pytest

from monitoring import health as health_mod
from monitoring.health import ProbeResult


@pytest.fixture(autouse=True)
def _reset_registry():
    health_mod._REGISTRY = None
    yield
    health_mod._REGISTRY = None


def test_default_services_has_20():
    assert len(health_mod.DEFAULT_SERVICES) == 20


def test_register_and_probe_one_unknown_service():
    reg = health_mod.HealthRegistry()
    res = asyncio.run(reg.probe_one("nope"))
    assert res.healthy is True
    assert res.detail == "not-instrumented"


def test_register_custom_probe():
    reg = health_mod.HealthRegistry()

    async def my_probe(timeout: float) -> ProbeResult:
        return ProbeResult(service="my-svc", healthy=True, latency_ms=1.0, detail="ok")

    reg.register("my-svc", my_probe)
    res = asyncio.run(reg.probe_one("my-svc"))
    assert res.healthy is True
    assert res.detail == "ok"


def test_aggregate_reports_unhealthy():
    reg = health_mod.HealthRegistry()

    async def ok_probe(timeout: float) -> ProbeResult:
        return ProbeResult(service="agent", healthy=True, latency_ms=1.0)

    async def bad_probe(timeout: float) -> ProbeResult:
        return ProbeResult(service="annotation", healthy=False, latency_ms=2.0, detail="down")

    reg.register("agent", ok_probe)
    reg.register("annotation", bad_probe)
    results = asyncio.run(reg.probe_all())
    agg = reg.aggregate(results)
    assert agg["unhealthy"] == 1
    assert "annotation" in agg["unhealthy_services"]
    assert agg["status"] == "degraded"


def test_probe_timeout_marks_unhealthy():
    reg = health_mod.HealthRegistry(default_timeout=0.05)

    async def slow_probe(timeout: float) -> ProbeResult:
        await asyncio.sleep(0.5)
        return ProbeResult(service="agent", healthy=True, latency_ms=0)

    reg.register("agent", slow_probe)
    res = asyncio.run(reg.probe_one("agent"))
    assert res.healthy is False
    assert "timeout" in res.detail


def test_liveness_endpoint_returns_ok():
    out = asyncio.run(health_mod.liveness_endpoint())
    assert out["status"] == "ok"
    assert "pid" in out
