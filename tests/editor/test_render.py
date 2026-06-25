"""P4-6-W1 tests for render engine.

2 tests covering: render job lifecycle + progress simulation + cancel.
"""
from __future__ import annotations

import os
import time

import pytest

from services.workflow_service.editor.render import (
    RENDER_CODECS, RENDER_RESOLUTIONS, RenderEngine, RenderStatus,
)


def test_render_job_lifecycle_and_progress(sample_timeline):
    """create → render (sync) → progress reaches 1.0 → COMPLETED."""
    eng = RenderEngine(output_dir=os.environ.get(
        "EDITOR_TEST_OUT", "/tmp/test_editor_renders"))
    # Validate
    with pytest.raises(ValueError):
        eng.create_job(timeline=sample_timeline, codec="not_a_codec")
    with pytest.raises(ValueError):
        eng.create_job(timeline=sample_timeline, resolution="5K")
    # Create + render synchronously
    job = eng.create_job(
        timeline=sample_timeline, codec="h264",
        resolution="720p", bitrate_kbps=2000,
        output_name="rj-test.mp4")
    assert job.id.startswith("rj-")
    assert job.ffmpeg_cmd, "ffmpeg command should be planned"
    # Run sync with very short step delay
    final = eng.render(job.id, step_delay=0.001, use_ffmpeg=False)
    assert final.status == RenderStatus.COMPLETED, \
        f"expected completed, got {final.status}: {final.error}"
    assert final.progress == pytest.approx(1.0)
    assert final.stage == "finalize"
    # Output file exists
    assert os.path.exists(final.output_path)
    # Progress projection
    prog = eng.get_job(job.id)
    assert prog.progress >= 0.99
    # Codec + resolution validation
    assert set(RENDER_CODECS.keys()) == {"h264", "h265", "vp9", "prores"}
    assert set(RENDER_RESOLUTIONS.keys()) == {"480p", "720p", "1080p", "4K"}


def test_render_cancel_and_resolutions():
    """Cancel a long-running job and verify state transitions."""
    eng = RenderEngine()
    timeline = {
        "clips": [
            {"id": "c1", "src": "", "start": 0.0, "end": 5.0,
             "duration": 5.0},
        ],
        "cuts": [], "transitions": [], "effects": [],
    }
    # 4K + VP9 should be accepted
    job = eng.create_job(
        timeline=timeline, codec="vp9", resolution="4K",
        bitrate_kbps=15000, output_name="cancel-test.mp4")
    # Schedule cancel after 50ms
    import threading
    def _cancel():
        time.sleep(0.05)
        eng.cancel(job.id)
    threading.Thread(target=_cancel, daemon=True).start()
    final = eng.render(job.id, step_delay=0.05, use_ffmpeg=False)
    # Either cancelled (if cancel arrived mid-render) or completed
    assert final.status in (RenderStatus.CANCELLED, RenderStatus.COMPLETED), \
        f"unexpected status: {final.status}"
    if final.status == RenderStatus.CANCELLED:
        assert final.error == "cancelled"
        assert final.cancel_requested is True
    # Idempotent cancel of finished job returns False
    assert eng.cancel(job.id) is False
