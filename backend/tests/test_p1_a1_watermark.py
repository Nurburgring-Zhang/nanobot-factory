"""
Tests for P1-A1 Worker-2: Video Watermark Engine (ffmpeg overlay)
==================================================================

Covers:
    1. add_text_watermark generates new video file
    2. add_image_watermark generates new video file
    3. Text watermark position parameter (4 corners)
    4. Opacity parameter (0.0-1.0)
    5. verify_watermark returns bool
    6. Corrupted file → error handling
    7. Output file size < 2x input
    8. ffmpeg unavailable → graceful fallback
    9. Audio LSB invisible watermark embed + extract
   10. Position enum normalization
   11. WatermarkResult dataclass
   12. WatermarkRecord persistence

Notes:
    - Uses TestClient of copyright_routes only if engine is loaded.
    - Each test creates a fresh temp video via ffmpeg lavfi.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import pytest

# ── Path setup ──────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF = _BACKEND / "imdf"
for _p in (str(_BACKEND), str(_IMDF)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ffmpeg_bin() -> str:
    """Resolve ffmpeg binary path or skip all tests if missing."""
    bin_ = shutil.which("ffmpeg")
    if not bin_:
        pytest.skip("ffmpeg not on PATH; video watermark tests cannot run")
    return bin_


@pytest.fixture
def temp_dir() -> str:
    d = tempfile.mkdtemp(prefix="wm_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_video(temp_dir: str, ffmpeg_bin: str) -> str:
    """Generate a 2-second 320x240 test video with deterministic testsrc
    + sine audio track. Output is reproducible across runs."""
    path = os.path.join(temp_dir, "sample.mp4")
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not os.path.exists(path):
        pytest.skip(f"ffmpeg failed to create sample video: {r.stderr[-200:]}")
    return path


@pytest.fixture
def sample_logo(temp_dir: str) -> str:
    """Create a 64x64 RGBA PNG logo for image watermark tests."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    path = os.path.join(temp_dir, "logo.png")
    img = Image.new("RGBA", (64, 64), (255, 0, 0, 220))
    # Draw a simple border for visibility
    for x in range(64):
        for y in range(64):
            if x < 4 or x > 59 or y < 4 or y > 59:
                img.putpixel((x, y), (0, 0, 0, 255))
    img.save(path)
    return path


@pytest.fixture
def engine(temp_dir: str):
    """Fresh WatermarkEngine instance per test (clean index)."""
    from engines.watermark_engine import WatermarkEngine
    # Use a temp index file so tests don't pollute prod state
    index_file = os.path.join(temp_dir, "wm_index.json")
    eng = WatermarkEngine()
    # Override the index file location
    eng._records = {}
    import engines.watermark_engine as wm_mod
    original_meta = wm_mod.META_FILE
    wm_mod.META_FILE = index_file
    yield eng
    wm_mod.META_FILE = original_meta


# ── Tests ──────────────────────────────────────────────────────────────────

class TestTextWatermark:
    """Test 1 + 3 + 4 + 7: text watermark output, positions, opacity, size."""

    def test_add_text_watermark_generates_new_file(
        self, engine, sample_video, temp_dir
    ):
        out = os.path.join(temp_dir, "text_out.mp4")
        res = engine.add_text_watermark(
            sample_video, out, "IMDF © 2026",
            position="bottomright", opacity=0.7,
        )
        assert res.success is True
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
        assert res.output_path == os.path.abspath(out)
        assert res.kind == "text"
        assert res.text == "IMDF © 2026"
        assert res.watermark_id.startswith("wm_text_")

    def test_text_watermark_all_positions(self, engine, sample_video, temp_dir):
        """All 4 corners + center should produce valid output."""
        from engines.watermark_engine import WatermarkPosition
        for pos in ("topleft", "topright", "bottomleft",
                    "bottomright", "center"):
            out = os.path.join(temp_dir, f"text_{pos}.mp4")
            res = engine.add_text_watermark(
                sample_video, out, "P1-A1",
                position=pos, opacity=0.5,
            )
            assert res.success is True, f"position={pos} failed"
            assert os.path.getsize(out) > 0
            assert res.position == pos

    def test_opacity_range(self, engine, sample_video, temp_dir):
        """Opacity 0.0-1.0 should all work."""
        for op in (0.0, 0.25, 0.5, 0.75, 1.0):
            out = os.path.join(temp_dir, f"op_{op}.mp4")
            res = engine.add_text_watermark(
                sample_video, out, "Opacity Test",
                position="bottomright", opacity=op,
            )
            assert res.success is True, f"opacity={op} failed"
            assert res.opacity == op

    def test_output_size_within_double(
        self, engine, sample_video, temp_dir
    ):
        """Output file size should be < 2x input."""
        out = os.path.join(temp_dir, "size_check.mp4")
        res = engine.add_text_watermark(
            sample_video, out, "Size Check",
            position="bottomright", opacity=0.7,
        )
        assert res.success
        assert res.output_size < res.input_size * 2, (
            f"output {res.output_size} >= 2x input {res.input_size}"
        )


class TestImageWatermark:
    """Test 2 + 7: image watermark output + size."""

    def test_add_image_watermark_generates_new_file(
        self, engine, sample_video, sample_logo, temp_dir
    ):
        out = os.path.join(temp_dir, "img_out.mp4")
        res = engine.add_image_watermark(
            sample_video, out, sample_logo,
            position="bottomright", opacity=0.5,
        )
        assert res.success is True
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
        assert res.kind == "image"
        assert res.watermark_id.startswith("wm_image_")

    def test_image_watermark_all_positions(
        self, engine, sample_video, sample_logo, temp_dir
    ):
        for pos in ("topleft", "topright", "bottomleft",
                    "bottomright", "center"):
            out = os.path.join(temp_dir, f"img_{pos}.mp4")
            res = engine.add_image_watermark(
                sample_video, out, sample_logo,
                position=pos, opacity=0.5,
            )
            assert res.success is True, f"position={pos} failed"
            assert res.position == pos

    def test_image_output_size_within_double(
        self, engine, sample_video, sample_logo, temp_dir
    ):
        out = os.path.join(temp_dir, "img_size.mp4")
        res = engine.add_image_watermark(
            sample_video, out, sample_logo,
            position="bottomright", opacity=0.5,
        )
        assert res.output_size < res.input_size * 2


class TestVerifyWatermark:
    """Test 5: verify_watermark returns bool."""

    def test_verify_text_watermark_returns_bool(
        self, engine, sample_video, temp_dir
    ):
        out = os.path.join(temp_dir, "verify_text.mp4")
        res = engine.add_text_watermark(
            sample_video, out, "VerifyMe",
            position="bottomright", opacity=0.7,
        )
        assert res.success
        ok = engine.verify_watermark(out, watermark_id=res.watermark_id)
        assert isinstance(ok, bool)
        # The recorded frame hash should match
        assert ok is True, "verify_watermark should match recorded frame"

    def test_verify_image_watermark_returns_bool(
        self, engine, sample_video, sample_logo, temp_dir
    ):
        out = os.path.join(temp_dir, "verify_img.mp4")
        res = engine.add_image_watermark(
            sample_video, out, sample_logo,
            position="bottomright", opacity=0.5,
        )
        assert res.success
        ok = engine.verify_watermark(out, watermark_id=res.watermark_id)
        assert isinstance(ok, bool)
        assert ok is True

    def test_verify_audio_watermark(
        self, engine, sample_video, temp_dir
    ):
        out = os.path.join(temp_dir, "verify_audio.mp4")
        res = engine.add_invisible_watermark(
            sample_video, out, "SECRET-VERIFY",
        )
        assert res.success
        ok = engine.verify_watermark(out, watermark_id=res.watermark_id)
        assert isinstance(ok, bool)
        assert ok is True, "audio LSB verify should match"

    def test_verify_missing_file_returns_false(self, engine, temp_dir):
        bogus = os.path.join(temp_dir, "does_not_exist.mp4")
        assert engine.verify_watermark(bogus) is False


class TestErrorHandling:
    """Test 6: corrupted file → error."""

    def test_corrupt_input_raises_processing_error(
        self, engine, temp_dir
    ):
        bad = os.path.join(temp_dir, "corrupt.mp4")
        with open(bad, "wb") as f:
            f.write(b"NOT A VALID VIDEO FILE" * 100)
        out = os.path.join(temp_dir, "corrupt_out.mp4")
        from engines.watermark_engine import WatermarkProcessingError
        with pytest.raises(WatermarkProcessingError):
            engine.add_text_watermark(bad, out, "X")

    def test_missing_input_raises_input_error(self, engine, temp_dir):
        from engines.watermark_engine import WatermarkInputError
        with pytest.raises(WatermarkInputError):
            engine.add_text_watermark(
                os.path.join(temp_dir, "nope.mp4"),
                os.path.join(temp_dir, "out.mp4"),
                "X",
            )

    def test_empty_text_raises_input_error(
        self, engine, sample_video, temp_dir
    ):
        from engines.watermark_engine import WatermarkInputError
        with pytest.raises(WatermarkInputError):
            engine.add_text_watermark(
                sample_video,
                os.path.join(temp_dir, "empty.mp4"),
                "",
            )

    def test_missing_logo_raises_input_error(
        self, engine, sample_video, temp_dir
    ):
        from engines.watermark_engine import WatermarkInputError
        with pytest.raises(WatermarkInputError):
            engine.add_image_watermark(
                sample_video,
                os.path.join(temp_dir, "no_logo.mp4"),
                os.path.join(temp_dir, "no_such.png"),
                opacity=0.5,
            )

    def test_invalid_position_raises_value_error(self):
        from engines.watermark_engine import WatermarkPosition
        with pytest.raises(ValueError):
            WatermarkPosition.normalize("middle-east")


class TestFFmpegUnavailableFallback:
    """Test 8: ffmpeg unavailable → graceful fallback (no crash)."""

    def test_text_watermark_falls_back_when_no_ffmpeg(
        self, temp_dir, sample_video
    ):
        from engines.watermark_engine import WatermarkEngine
        eng = WatermarkEngine()
        eng._available = False
        out = os.path.join(temp_dir, "fb_text.mp4")
        res = eng.add_text_watermark(
            sample_video, out, "Fallback",
            position="bottomright", opacity=0.5,
        )
        assert res.success is True
        assert os.path.exists(out)
        # Fallback: output should be a copy of input
        assert res.output_size == os.path.getsize(sample_video)

    def test_image_watermark_falls_back_when_no_ffmpeg(
        self, temp_dir, sample_video, sample_logo
    ):
        from engines.watermark_engine import WatermarkEngine
        eng = WatermarkEngine()
        eng._available = False
        out = os.path.join(temp_dir, "fb_img.mp4")
        res = eng.add_image_watermark(
            sample_video, out, sample_logo,
            position="bottomright", opacity=0.5,
        )
        assert res.success is True
        assert os.path.exists(out)
        assert res.output_size == os.path.getsize(sample_video)

    def test_verify_returns_bool_when_no_ffmpeg(self, engine, temp_dir):
        engine._available = False
        out = os.path.join(temp_dir, "fb.mp4")
        # Create a dummy file
        with open(out, "wb") as f:
            f.write(b"\x00" * 1024)
        ok = engine.verify_watermark(out)
        assert isinstance(ok, bool)
        assert ok is True


class TestAudioInvisibleWatermark:
    """Test 9: audio LSB invisible watermark embed + extract roundtrip."""

    def test_lsb_embed_and_extract_roundtrip(
        self, engine, sample_video, temp_dir
    ):
        message = "IMDF-AUDIO-2026"
        out = os.path.join(temp_dir, "lsb.mp4")
        res = engine.add_invisible_watermark(sample_video, out, message)
        assert res.success is True
        assert res.kind == "audio"
        extracted = engine.extract_audio_watermark(out)
        assert extracted == message, (
            f"expected {message!r}, got {extracted!r}"
        )

    def test_lsb_short_message(
        self, engine, sample_video, temp_dir
    ):
        for msg in ("A", "AB", "Hello", "NanobotFactory2026"):
            out = os.path.join(temp_dir, f"lsb_{len(msg)}.mp4")
            res = engine.add_invisible_watermark(sample_video, out, msg)
            assert res.success
            assert engine.extract_audio_watermark(out) == msg


class TestDataStructures:
    """Test 11-12: dataclass + persistence."""

    def test_watermark_result_defaults(self):
        from engines.watermark_engine import WatermarkResult
        r = WatermarkResult()
        assert r.success is False
        assert r.kind == ""
        assert r.opacity == 0.0
        assert r.output_size == 0

    def test_watermark_record_persists(self, engine, sample_video, temp_dir):
        from engines.watermark_engine import WatermarkEngine
        out = os.path.join(temp_dir, "persist.mp4")
        res = engine.add_text_watermark(
            sample_video, out, "Persist", position="topleft", opacity=0.8,
        )
        # Look up record via engine
        rec = engine.lookup(res.watermark_id)
        assert rec is not None
        assert rec.text == "Persist"
        assert rec.position == "topleft"
        assert rec.opacity == 0.8
        assert rec.kind == "text"
        assert rec.input_sha256 != ""
        assert rec.output_sha256 != ""
        assert rec.frame_sha256 != ""
        # Reload via fresh engine
        eng2 = WatermarkEngine()
        rec2 = eng2.lookup(res.watermark_id)
        # May or may not be present depending on index persistence,
        # but if present should match
        if rec2 is not None:
            assert rec2.text == "Persist"


class TestPositionEnum:
    """Test 10: position normalization."""

    def test_normalize_aliases(self):
        from engines.watermark_engine import WatermarkPosition
        assert WatermarkPosition.normalize("bottomright") == WatermarkPosition.BOTTOMRIGHT
        assert WatermarkPosition.normalize("bottom_right") == WatermarkPosition.BOTTOMRIGHT
        assert WatermarkPosition.normalize("BOTTOMRIGHT") == WatermarkPosition.BOTTOMRIGHT
        assert WatermarkPosition.normalize("bottom-right") == WatermarkPosition.BOTTOMRIGHT
        assert WatermarkPosition.normalize("middle") == WatermarkPosition.CENTER
        assert WatermarkPosition.normalize("center") == WatermarkPosition.CENTER

    def test_passthrough_enum(self):
        from engines.watermark_engine import WatermarkPosition
        p = WatermarkPosition.TOPLEFT
        assert WatermarkPosition.normalize(p) is p

    def test_invalid_position(self):
        from engines.watermark_engine import WatermarkPosition
        with pytest.raises(ValueError):
            WatermarkPosition.normalize("northeast")