"""Tests for :mod:`engines.drama_harness` (P19-B4)."""
from __future__ import annotations

import os
import tempfile

import pytest

from engines.drama_harness import (
    DramaEngine,
    DramaHarnessState,
    DramaProjectRecord,
    DramaScene,
)


@pytest.fixture
def engine(tmp_path):
    output_dir = str(tmp_path / "dramas")
    os.makedirs(output_dir, exist_ok=True)
    return DramaEngine(output_dir=output_dir)


class TestDramaEngine:
    def test_instantiate(self, engine):
        s = engine.status()
        assert s["state"] == DramaHarnessState.IDLE.value
        assert s["projects"] == 0

    def test_lifecycle(self, engine):
        engine.start()
        assert engine.status()["state"] == DramaHarnessState.RUNNING.value
        engine.stop()
        assert engine.status()["state"] == DramaHarnessState.STOPPED.value

    def test_create_drama_project(self, engine):
        pid = engine.create_drama_project("My Drama", "a short about a hero", owner="alice")
        assert isinstance(pid, str)
        rec = engine.get_project(pid)
        assert isinstance(rec, DramaProjectRecord)
        assert rec.title == "My Drama"
        assert rec.phases.get("需求理解") == "completed"

    def test_create_drama_project_validates(self, engine):
        with pytest.raises(ValueError):
            engine.create_drama_project("", "logline")
        with pytest.raises(ValueError):
            engine.create_drama_project("title", "")

    def test_generate_script_default(self, engine):
        pid = engine.create_drama_project("t", "l")
        script = engine.generate_script(pid)
        assert isinstance(script, str)
        assert "t" in script or "l" in script
        rec = engine.get_project(pid)
        assert rec.phases["剧本生成"] == "completed"

    def test_generate_script_with_override(self, engine):
        pid = engine.create_drama_project("t", "l")
        engine.generate_script(pid, script="# my custom script")
        rec = engine.get_project(pid)
        assert rec.script == "# my custom script"

    def test_design_character(self, engine):
        pid = engine.create_drama_project("t", "l")
        name = engine.design_character(
            pid, name="Alice", appearance="red hair",
            personality="brave", voice_profile="zh-female",
        )
        assert name == "Alice"
        rec = engine.get_project(pid)
        assert any(c.name == "Alice" for c in rec.characters)
        assert rec.phases["角色锁定"] == "completed"

    def test_design_character_validates(self, engine):
        pid = engine.create_drama_project("t", "l")
        with pytest.raises(ValueError):
            engine.design_character(pid, name="")

    def test_design_scene_creates_shots(self, engine):
        pid = engine.create_drama_project("t", "l")
        sid = engine.design_scene(pid, title="Scene 1", setting="forest", mood="tense", shot_count=4)
        assert isinstance(sid, str)
        rec = engine.get_project(pid)
        assert len(rec.scenes) == 1
        scene = rec.scenes[0]
        assert isinstance(scene, DramaScene)
        assert scene.shot_count == 4
        assert len(scene.shots) == 4

    def test_design_scene_validates(self, engine):
        pid = engine.create_drama_project("t", "l")
        with pytest.raises(ValueError):
            engine.design_scene(pid, title="", shot_count=3)
        with pytest.raises(ValueError):
            engine.design_scene(pid, title="S", shot_count=0)

    def test_generate_shot(self, engine):
        pid = engine.create_drama_project("t", "l")
        engine.design_scene(pid, title="S", shot_count=2)
        out = engine.generate_shot(pid, 1, visual_style="cinematic", duration=7.5)
        assert out["visual_style"] == "cinematic"
        assert out["duration"] == 7.5

    def test_generate_shot_unknown_raises(self, engine):
        pid = engine.create_drama_project("t", "l")
        with pytest.raises(ValueError):
            engine.generate_shot(pid, 999)

    def test_generate_video_returns_path(self, engine):
        pid = engine.create_drama_project("t", "l")
        engine.design_scene(pid, title="S", shot_count=1)
        path = engine.generate_video(pid, 1)
        assert path.endswith(".mp4")
        assert engine.get_project(pid).output_path == ""

    def test_assemble_requires_shots(self, engine):
        pid = engine.create_drama_project("t", "l")
        with pytest.raises(ValueError):
            engine.assemble(pid)

    def test_assemble_writes_output(self, engine):
        pid = engine.create_drama_project("t", "l")
        engine.design_scene(pid, title="S", shot_count=2)
        path = engine.assemble(pid)
        assert path.endswith(".mp4")
        rec = engine.get_project(pid)
        assert rec.status == "composed"
        assert rec.output_path.endswith(".mp4")

    def test_full_flow(self, engine):
        pid = engine.create_drama_project("Demo", "a demo drama")
        engine.generate_script(pid)
        engine.design_character(pid, name="Bob")
        engine.design_scene(pid, title="Intro", shot_count=3)
        engine.generate_shot(pid, 1, visual_style="noir")
        engine.generate_video(pid, 1)
        engine.assemble(pid)
        rec = engine.get_project(pid)
        assert rec.status == "composed"
        assert "剧本生成" in rec.phases
        assert "角色锁定" in rec.phases
        assert "智能分镜" in rec.phases
        assert "逐镜头生成" in rec.phases
        assert "合成导出" in rec.phases