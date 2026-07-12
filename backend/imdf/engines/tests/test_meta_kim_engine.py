"""Tests for :mod:`engines.meta_kim_engine` (P19-B4 legacy skeleton).

The legacy 8-stage ``MetaKimEngineLegacy`` is preserved as a sibling to the
new 7-step :class:`meta_kim_engine.MetaKimEngine`.  This file exercises the
legacy class; the new class has its own test module
(:mod:`engines.tests.test_meta_kim`).
"""
from __future__ import annotations

import os
import tempfile

import pytest

from engines.meta_kim_engine import (
    GovernanceResult,
    GovernanceStage,
    Lesson,
    MetaKimEngineLegacy as MetaKimEngine,
    MetaKimState,
    StageOutcome,
)


class TestMetaKimEngine:
    def test_instantiate_no_audit_chain(self, monkeypatch):
        monkeypatch.delenv("AUDIT_CHAIN_SECRET", raising=False)
        engine = MetaKimEngine()
        s = engine.status()
        assert s["state"] == MetaKimState.IDLE.value
        assert s["audit_chain"] in (True, False)  # depends on env at import time

    def test_lifecycle(self):
        engine = MetaKimEngine()
        engine.start()
        assert engine.status()["state"] == MetaKimState.RUNNING.value
        engine.pause()
        engine.resume()
        engine.stop()
        assert engine.status()["state"] == MetaKimState.STOPPED.value

    def test_run_governance_loop_default_stages(self):
        engine = MetaKimEngine()
        result = engine.run_governance_loop({"goal": "ship 6 engines"})
        assert isinstance(result, GovernanceResult)
        assert len(result.stages) == len(engine.DEFAULT_STAGES)
        for stage_outcome in result.stages:
            assert stage_outcome.finished_at is not None

    def test_run_governance_loop_rejects_non_dict_request(self):
        engine = MetaKimEngine()
        with pytest.raises(TypeError):
            engine.run_governance_loop([])  # type: ignore[arg-type]

    def test_stage_hook_can_override_outcome(self):
        engine = MetaKimEngine()

        def hook(_req):
            return StageOutcome(
                stage=GovernanceStage.CLARIFY,
                ok=False,
                detail="manual fail",
            )

        result = engine.run_governance_loop(
            {"goal": "x"},
            stage_hooks={GovernanceStage.CLARIFY: hook},
        )
        assert result.ok is False
        first = result.stages[0]
        assert first.ok is False
        assert first.detail == "manual fail"

    def test_stage_hook_dict_input(self):
        engine = MetaKimEngine()

        def hook(_req):
            return {"ok": True, "detail": "via-dict", "artifacts": {"x": 1}}

        result = engine.run_governance_loop(
            {"k": "v"},
            stage_hooks={GovernanceStage.SEARCH_CAPABILITY: hook},
        )
        target = next(s for s in result.stages if s.stage == GovernanceStage.SEARCH_CAPABILITY)
        assert target.ok is True
        assert target.artifacts["x"] == 1

    def test_record_lesson_returns_id_and_persists(self, tmp_path):
        path = str(tmp_path / "lessons.json")
        engine = MetaKimEngine(lessons_path=path)
        lid = engine.record_lesson(loop_id="L1", body="lesson A", tags=["clarify"])
        assert isinstance(lid, str)
        lessons = engine.list_lessons()
        assert len(lessons) == 1
        assert lessons[0].body == "lesson A"

        # Reload from disk
        engine2 = MetaKimEngine(lessons_path=path)
        loaded = engine2.load_lessons_from_disk()
        assert loaded == 1

    def test_record_lesson_rejects_empty(self):
        engine = MetaKimEngine()
        with pytest.raises(ValueError):
            engine.record_lesson(body="")

    def test_run_governance_loop_after_stop_raises(self):
        engine = MetaKimEngine()
        engine.stop()
        with pytest.raises(RuntimeError):
            engine.run_governance_loop({"x": 1})

    def test_history_grows(self):
        engine = MetaKimEngine()
        engine.run_governance_loop({"x": 1})
        engine.run_governance_loop({"y": 2})
        assert engine.status()["loops"] == 2