"""Tests for :mod:`engines.engine_router` 6-engine integration (P19-B4)."""
from __future__ import annotations

import pytest

from engines import engine_router


@pytest.fixture(autouse=True)
def _reset_singletons():
    engine_router.reset_engine_singletons()
    yield
    engine_router.reset_engine_singletons()


class TestEngineRouterIntegration:
    def test_get_engine_for_each_kind(self):
        for name in ("crawler", "agent", "octo", "vida", "meta_kim", "drama"):
            eng = engine_router.get_engine(name)
            assert eng is not None
            # Get again → same singleton
            assert engine_router.get_engine(name) is eng

    def test_unknown_engine_raises(self):
        with pytest.raises(KeyError):
            engine_router.get_engine("not-a-real-engine")

    def test_start_and_stop_all(self):
        statuses = engine_router.start_all_engines()
        assert set(statuses.keys()) == {"crawler", "agent", "octo", "vida", "meta_kim", "drama"}
        # every status dict should have a state
        for name, s in statuses.items():
            assert "state" in s
            assert s["state"] == "running"

        stopped = engine_router.stop_all_engines()
        for name, s in stopped.items():
            assert s["state"] == "stopped"

    def test_each_engine_exposes_status_method(self):
        for name in ("crawler", "agent", "octo", "vida", "meta_kim", "drama"):
            eng = engine_router.get_engine(name)
            assert hasattr(eng, "status")
            assert hasattr(eng, "start")
            assert hasattr(eng, "stop")