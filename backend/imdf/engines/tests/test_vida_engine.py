"""Tests for :mod:`engines.vida_engine` (P19-B4)."""
from __future__ import annotations

import pytest

from engines.vida_engine import (
    VidaContext,
    VidaEngine,
    VidaEngineState,
    VidaExecution,
    VidaPrediction,
    VidaScreen,
)


class TestVidaEngine:
    def test_instantiate_with_mock(self):
        engine = VidaEngine(prefer_mock=True)
        status = engine.status()
        assert status["state"] == VidaEngineState.IDLE.value
        assert status["prefer_mock"] is True

    def test_lifecycle(self):
        engine = VidaEngine(prefer_mock=True)
        engine.start()
        assert engine.status()["state"] == VidaEngineState.RUNNING.value
        engine.stop()
        assert engine.status()["state"] == VidaEngineState.STOPPED.value

    def test_capture_mock_returns_screen(self):
        engine = VidaEngine(prefer_mock=True)
        screen = engine.capture()
        assert isinstance(screen, VidaScreen)
        assert screen.width > 0 and screen.height > 0
        assert screen.focused_window == "mock-window"

    def test_analyze_without_capture_raises(self):
        engine = VidaEngine(prefer_mock=True)
        with pytest.raises(ValueError):
            engine.analyze()

    def test_analyze_default_context(self):
        engine = VidaEngine(prefer_mock=True)
        engine.capture()
        ctx = engine.analyze()
        assert isinstance(ctx, VidaContext)
        assert ctx.app_focus == "mock-window"

    def test_analyze_with_hook(self):
        engine = VidaEngine(prefer_mock=True)
        screen = engine.capture()

        def hook(s: VidaScreen) -> VidaContext:
            return VidaContext(
                context_id="ignored",
                screen_id=s.screen_id,
                detected_text="hello",
                detected_language="zh",
            )

        ctx = engine.analyze(screen, hook=hook)
        assert ctx.detected_text == "hello"
        assert ctx.detected_language == "zh"

    def test_predict_returns_prediction(self):
        engine = VidaEngine(prefer_mock=True)
        engine.capture()
        engine.analyze()
        pred = engine.predict()
        assert isinstance(pred, VidaPrediction)
        assert 0.0 <= pred.confidence <= 1.0

    def test_predict_without_context_raises(self):
        engine = VidaEngine(prefer_mock=True)
        with pytest.raises(ValueError):
            engine.predict()

    def test_execute_dry_run(self):
        engine = VidaEngine(prefer_mock=True)
        ex = engine.execute("click", {"x": 100, "y": 200}, dry_run=True)
        assert isinstance(ex, VidaExecution)
        assert ex.status == "ok"

    def test_execute_unknown_action(self):
        engine = VidaEngine(prefer_mock=True)
        ex = engine.execute("unknown-action", {}, dry_run=False)
        assert ex.status == "failed"
        assert "unknown action" in ex.error

    def test_stop_blocks_capture(self):
        engine = VidaEngine(prefer_mock=True)
        engine.stop()
        with pytest.raises(RuntimeError):
            engine.capture()

    def test_set_mock_screen_helper(self):
        engine = VidaEngine(prefer_mock=True)
        screen = VidaScreen(
            screen_id="manual-1",
            timestamp="2026-01-01T00:00:00",
            width=800,
            height=600,
            focused_window="terminal",
        )
        engine._set_mock_screen(screen)
        ctx = engine.analyze()
        assert ctx.app_focus == "terminal"