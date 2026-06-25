"""Tests for render engine — final FFmpeg composite render."""
import os
import tempfile
import pytest

from services.workflow_service.editor.render import (
    RenderEngine, RenderStatus, RenderJob,
    RENDER_CODECS, RENDER_RESOLUTIONS,
)


@pytest.fixture
def engine(tmp_path):
    out_dir = tmp_path / "renders"
    out_dir.mkdir()
    return RenderEngine(output_dir=str(out_dir))


def test_render_codecs():
    assert "h264" in RENDER_CODECS
    assert "h265" in RENDER_CODECS
    assert "vp9" in RENDER_CODECS
    assert "prores" in RENDER_CODECS


def test_render_resolutions():
    assert "480p" in RENDER_RESOLUTIONS
    assert "720p" in RENDER_RESOLUTIONS
    assert "1080p" in RENDER_RESOLUTIONS
    assert "4K" in RENDER_RESOLUTIONS
    # 4K should be 3840x2160
    assert RENDER_RESOLUTIONS["4K"]["width"] == 3840
    assert RENDER_RESOLUTIONS["4K"]["height"] == 2160


def test_create_job_default_params(engine):
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    job = engine.create_job(timeline)
    assert job.status == RenderStatus.PENDING
    assert job.codec == "h264"
    assert job.resolution == "1080p"
    assert job.bitrate_kbps == 5000
    assert job.id.startswith("rj-")
    assert len(engine.list_jobs()) == 1


def test_create_job_invalid_codec(engine):
    timeline = {"clips": []}
    with pytest.raises(ValueError, match="unknown codec"):
        engine.create_job(timeline, codec="magic_codec")


def test_create_job_invalid_resolution(engine):
    timeline = {"clips": []}
    with pytest.raises(ValueError, match="unknown resolution"):
        engine.create_job(timeline, resolution="8K")


def test_get_job(engine):
    timeline = {"clips": []}
    job = engine.create_job(timeline)
    fetched = engine.get_job(job.id)
    assert fetched is job


def test_get_job_unknown_returns_none(engine):
    assert engine.get_job("nope") is None


def test_cancel_running_job(engine):
    timeline = {"clips": []}
    job = engine.create_job(timeline)
    # Set cancel before render
    ok = engine.cancel(job.id)
    assert ok is True
    rendered = engine.render(job.id, step_delay=0.001)
    assert rendered.status == RenderStatus.CANCELLED


def test_cancel_completed_returns_false(engine):
    timeline = {"clips": []}
    job = engine.create_job(timeline)
    engine.render(job.id, step_delay=0.001)
    ok = engine.cancel(job.id)
    assert ok is False


def test_render_simulated_progress(engine):
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    job = engine.create_job(timeline)
    rendered = engine.render(job.id, step_delay=0.001)
    assert rendered.status == RenderStatus.COMPLETED
    assert rendered.progress == 1.0
    assert os.path.exists(rendered.output_path)


def test_render_progress_stages(engine):
    timeline = {"clips": [{"id": "c1"}]}
    job = engine.create_job(timeline)
    rendered = engine.render(job.id, step_delay=0.001)
    stages = [log.split(":")[0] for log in rendered.log]
    assert "analyzing" in stages
    assert "loading_clips" in stages
    assert "composing_filter_graph" in stages
    assert "applying_effects" in stages
    assert "rendering_transitions" in stages
    assert "muxing" in stages
    assert "finalize" in stages


def test_render_unknown_job_raises(engine):
    with pytest.raises(ValueError, match="job not found"):
        engine.render("nope")


def test_render_idempotent_on_completed(engine):
    timeline = {"clips": []}
    job = engine.create_job(timeline)
    engine.render(job.id, step_delay=0.001)
    # Re-rendering a completed job should be a no-op
    again = engine.render(job.id, step_delay=0.001)
    assert again.status == RenderStatus.COMPLETED


def test_to_dict_includes_essentials(engine):
    timeline = {"clips": [{"id": "c1"}]}
    job = engine.create_job(timeline)
    d = job.to_dict()
    assert d["id"] == job.id
    assert d["status"] == "pending"
    assert "codec" in d
    assert "resolution" in d
    assert "bitrate_kbps" in d
    assert "ffmpeg_cmd" in d


def test_render_falls_back_to_lavfi_when_no_real_sources(engine):
    """Without real clip src files, render still completes (placeholder)."""
    timeline = {"clips": [{"id": "c1", "duration": 5.0}]}  # no 'src'
    job = engine.create_job(timeline)
    # ffmpeg_cmd should fall back to lavfi pattern
    assert "lavfi" in " ".join(job.ffmpeg_cmd)
    rendered = engine.render(job.id, step_delay=0.001)
    assert rendered.status == RenderStatus.COMPLETED
    # placeholder file exists
    assert os.path.exists(rendered.output_path)
    # placeholder content has NANOBOT marker
    with open(rendered.output_path, "rb") as f:
        content = f.read()
    assert b"NANOBOT_PLACEHOLDER_RENDER" in content


def test_get_render_engine_singleton():
    from services.workflow_service.editor.render import (
        get_render_engine, _engine,
    )
    e1 = get_render_engine()
    e2 = get_render_engine()
    assert e1 is e2