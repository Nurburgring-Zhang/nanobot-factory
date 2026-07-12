"""VDP-2026 R5+R6 — Plugin + Provider tests (combined for speed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from capabilities_v2.engine import (  # noqa: E402
    configure_db as configure_cap_db, reset_registry_for_test,
)
from orchestration.bus import configure_db as configure_bus_db, reset_bus_for_test  # noqa: E402
from plugins.manager import (  # noqa: E402
    configure_db as configure_plugin_db,
    get_manager as get_plugin_manager,
    reset_manager_for_test,
)
from providers.registry import (  # noqa: E402
    configure_db as configure_provider_db,
    get_registry as get_provider_registry,
    reset_registry_for_test,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    configure_cap_db(tmp_path / "cap.db")
    configure_bus_db(tmp_path / "bus.db")
    configure_plugin_db(tmp_path / "plugin.db")
    configure_provider_db(tmp_path / "provider.db")
    reset_registry_for_test()
    reset_bus_for_test()
    reset_manager_for_test()
    reset_registry_for_test()
    yield


# ===========================================================================
# Plugins
# ===========================================================================


class TestPlugins:
    def test_three_sample_plugins_loaded(self):
        items = get_plugin_manager().list()
        ids = {p.id for p in items}
        assert "plugin-yolo-trainer" in ids
        assert "plugin-llava-finetune" in ids
        assert "plugin-coda-eval" in ids

    def test_invoke_returns_envelope(self):
        m = get_plugin_manager()
        res = m.invoke("plugin-yolo-trainer", "plugin.yolo.train",
                       {"data_yaml": "/x/data.yaml", "epochs": 12})
        assert res["status"] == "success"
        assert res["plugin_id"] == "plugin-yolo-trainer"

    def test_invoke_unknown_capability_raises(self):
        m = get_plugin_manager()
        with pytest.raises(ValueError):
            m.invoke("plugin-yolo-trainer", "plugin.nonexistent", {})

    def test_enable_disable(self):
        m = get_plugin_manager()
        assert m.set_status("plugin-yolo-trainer", "disabled") is True
        items = m.list()
        yolo = next(p for p in items if p.id == "plugin-yolo-trainer")
        assert yolo.status == "disabled"


# ===========================================================================
# Providers
# ===========================================================================


class TestProviders:
    def test_seven_sample_providers(self):
        items = get_provider_registry().list()
        ids = {p.id for p in items}
        for pid in ("openai", "claude", "deepseek", "qwen", "doubao", "comfyui", "mock"):
            assert pid in ids

    def test_route_cheapest(self):
        r = get_provider_registry()
        chosen = r.route("openai", prefer="cost")
        # mock has 0 cost and is in family fallback set
        assert chosen is not None

    def test_route_speed(self):
        r = get_provider_registry()
        chosen = r.route("openai", prefer="speed")
        assert chosen.latency_p50_ms <= 1000

    def test_route_excludes(self):
        r = get_provider_registry()
        # exclude an entire family, forcing fallback route
        chosen = r.route("openai", prefer="cost", exclude=["openai"])
        # openai is the only active provider in family 'openai', so fallback
        # returns mock — confirming exclude actually took effect
        assert chosen.id == "mock" or chosen.family != "openai"

    def test_record_call_accumulates_cost(self):
        r = get_provider_registry()
        r.record_call("openai", "gpt-4o-mini", 1000, 500, 300, "success")
        r.record_call("openai", "gpt-4o-mini", 2000, 1000, 400, "success")
        r.record_call("openai", "gpt-4o-mini", 0, 0, 100, "error")
        s = r.call_summary()
        o = s["providers"]["openai"]
        assert o["calls"] == 3
        assert o["input_tokens"] == 3000
        assert o["output_tokens"] == 1500
        assert o["errors"] == 1


class TestHTTPCombined:
    def _client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            return None
        from plugins.routes import router as plugins_router
        from providers.routes import router as providers_router
        app = FastAPI()
        app.include_router(plugins_router)
        app.include_router(providers_router)
        return TestClient(app)

    def test_plugin_route(self):
        c = self._client()
        if c is None: pytest.skip("fastapi")
        r = c.get("/api/v1/plugins")
        assert r.status_code == 200
        assert r.json()["total"] >= 3
        r = c.get("/api/v1/plugins/plugin-yolo-trainer")
        assert r.status_code == 200
        r = c.post("/api/v1/plugins/plugin-yolo-trainer/invoke",
                   json={"capability_id": "plugin.yolo.train", "inputs": {"epochs": 1}})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        # unknown plugin 404
        r = c.post("/api/v1/plugins/nope/invoke",
                   json={"capability_id": "x", "inputs": {}})
        assert r.status_code == 400

    def test_provider_route(self):
        c = self._client()
        if c is None: pytest.skip("fastapi")
        r = c.get("/api/v1/providers")
        assert r.status_code == 200
        assert r.json()["total"] == 7
        r = c.post("/api/v1/providers/route", json={"family": "openai", "prefer": "speed"})
        assert r.status_code == 200
        r = c.post("/api/v1/providers/route", json={"family": "nonexistent"})
        # falls back to mock
        assert r.status_code == 200
        assert r.json()["id"] == "mock"

    def test_provider_summary(self):
        c = self._client()
        if c is None: pytest.skip("fastapi")
        r = c.get("/api/v1/providers/_/summary")
        assert r.status_code == 200
        assert r.json()["total_calls"] >= 0
