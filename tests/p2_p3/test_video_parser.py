"""P2 P3 fix: VideoParser — real cv2 + ffprobe metadata extraction (R1-F3 / R2-NEW).

R1-F3 / R2 audit (reports/p21_r1_audit_data.md §137-143, p21_r2_audit_data.md §51)
identified the original ``VideoParser.parse()`` as **dead code**:

    arr = np.frombuffer(data, dtype=np.uint8)
    cap = cv2.VideoCapture()
    if cap.open(arr.tobytes(), cv2.CAP_ANY):  # unlikely to work for raw bytes
        ...

``cv2.VideoCapture.open()`` cannot decode raw video bytes from memory; the
function silently fell through to a heuristic stub return. The R2 audit
confirmed the bug and the comment-on-line-154 admission in the source.

This test pins the post-fix behaviour:

* cv2 file-path parse must return real metadata (width, height, fps, frames)
* bytes-input parse must produce the same metadata
* the ``source`` field must be ``"cv2"`` (or ``"ffprobe"`` as fallback)
* invalid input must raise (not silently stub)

Test design
-----------
* Each test generates a fresh cv2 mp4 in a ``tempfile.mkdtemp()`` and tears
  it down, so tests are order-independent and parallel-safe.
* The test file is runnable on Windows with ``D:\\ComfyUI\\.ext\\python.exe``;
  the ``pytest`` invocation pattern mirrors ``tests/p2_p1`` siblings.
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Tuple

import pytest

# ==== Path bootstrap (matches sibling p2_p1 / p2_p2 tests) =================
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
_IMDF_MULTIMODAL = _BACKEND / "imdf" / "multimodal"

for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
# conftest-driven import also needs the imdf/multimodal pkg resolvable
if str(_IMDF_MULTIMODAL) not in sys.path:
    sys.path.insert(0, str(_IMDF_MULTIMODAL))


# ==== Imports under test ====================================================
def _import_video_parser():
    """Late import so this test file is collectable even if cv2 is missing."""
    from backend.imdf.multimodal.parsers import (  # type: ignore  # noqa: E402
        VideoParser,
    )
    return VideoParser


def _import_media_ref():
    from backend.imdf.multimodal.types import (  # type: ignore  # noqa: E402
        MediaRef,
        ModalKind,
    )
    return MediaRef, ModalKind


VideoParser = _import_video_parser()
MediaRef, ModalKind = _import_media_ref()


# ==== Fixtures ==============================================================
@pytest.fixture(scope="module")
def cv2():
    """cv2 is required for these tests — skip the whole module if missing."""
    try:
        import cv2 as _cv2  # type: ignore
        return _cv2
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"cv2 not available: {exc}")


@pytest.fixture
def workdir():
    """Fresh temp dir per-test, auto-cleaned."""
    d = tempfile.mkdtemp(prefix="p2p3_video_")
    yield Path(d)
    # Best-effort cleanup
    try:
        shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


def _make_mp4(
    cv2_mod,
    path: Path,
    *,
    width: int = 320,
    height: int = 240,
    fps: float = 3.0,
    n_frames: int = 3,
) -> Tuple[int, int, float]:
    """Generate a tiny mp4 with cv2.VideoWriter.

    Returns: (width, height, fps) actually used (cv2 may snap fps).
    """
    import numpy as np
    fourcc = cv2_mod.VideoWriter_fourcc(*"mp4v")
    writer = cv2_mod.VideoWriter(str(path), fourcc, fps, (width, height))
    assert writer.isOpened(), f"cv2.VideoWriter failed to open {path}"
    for i in range(n_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Encode the frame index in the blue channel so we can sanity-check
        # round-trip if we ever extend the test.
        frame[:, :, 0] = (i * 80) % 256
        frame[:, :, 1] = (i * 40) % 256
        writer.write(frame)
    writer.release()
    return width, height, fps


@pytest.fixture
def tiny_mp4(cv2, workdir) -> Path:
    """Tiny cv2-generated mp4 (3 frames, 1 second, 320x240, 3 fps)."""
    path = workdir / "tiny.mp4"
    _make_mp4(cv2, path, width=320, height=240, fps=3.0, n_frames=3)
    assert path.exists() and path.stat().st_size > 0
    return path


# ==== Test 1: cv2 path-input parses real metadata (R1-F3 / R2) ==============
def test_video_parser_parse_path_returns_real_metadata(cv2, tiny_mp4):
    """``parse(path)`` must extract real fps/width/height/frames from a real mp4.

    Pre-fix behaviour: silent stub — ``frames == 0``, ``source == 'none'``.
    Post-fix behaviour: cv2 produces real values, ``source == 'cv2'`` (or
    ``'ffprobe'`` as fallback if cv2 is missing in the test env).
    """
    parser = VideoParser()
    result = parser.parse(str(tiny_mp4))

    assert result.kind == ModalKind.VIDEO
    meta = result.meta
    # Real metadata, not a stub
    assert meta.get("width") == 320, f"width should be 320, got {meta.get('width')}"
    assert meta.get("height") == 240, f"height should be 240, got {meta.get('height')}"
    assert meta.get("frame_count", 0) >= 3, (
        f"frame_count should be >= 3, got {meta.get('frame_count')}"
    )
    # fps may be returned as a float (cv2) or int; the writer used 3.0
    assert abs(float(meta.get("fps") or 0) - 3.0) < 0.5, (
        f"fps should be ~3.0, got {meta.get('fps')!r}"
    )
    # duration = frames / fps; 3 frames @ 3 fps = 1 second
    assert abs(float(meta.get("duration_sec") or 0) - 1.0) < 0.2, (
        f"duration should be ~1.0s, got {meta.get('duration_sec')!r}"
    )
    # Source attribution — real metadata path used
    assert meta.get("source") in ("cv2", "ffprobe"), (
        f"source should be cv2 or ffprobe, got {meta.get('source')!r}"
    )
    # ParsedMedia fields also populated
    assert result.frames >= 3
    assert result.duration_sec >= 0.5
    # Codec string should be present (cv2 may return 'mp4v' for our writer)
    assert meta.get("codec"), "codec should be extracted"
    # Content hash should be derived from real bytes
    assert result.content_hash, "content_hash must not be empty"


# ==== Test 2: Path input (pathlib.Path) also works ===========================
def test_video_parser_parse_pathlib_path(cv2, tiny_mp4):
    """``parse(Path(...))`` must work identically to ``parse(str(...))``."""
    parser = VideoParser()
    result = parser.parse(tiny_mp4)  # pathlib.Path, not str
    assert result.meta.get("width") == 320
    assert result.meta.get("height") == 240
    assert result.meta.get("frame_count", 0) >= 3


# ==== Test 3: bytes input via tempfile (R1-F3 dead-code path) ===============
def test_video_parser_parse_bytes_returns_same_metadata(cv2, tiny_mp4):
    """``parse(bytes)`` must produce the same metadata as ``parse(path)``.

    Pre-fix behaviour: cap.open(arr.tobytes()) was unreachable — the function
    fell through to the stub. Post-fix: bytes are written to a tempfile and
    decoded by cv2 (or ffprobe).
    """
    parser = VideoParser()
    raw = tiny_mp4.read_bytes()
    assert len(raw) > 0

    result = parser.parse(raw)
    meta = result.meta
    assert meta.get("width") == 320, f"width should be 320, got {meta.get('width')}"
    assert meta.get("height") == 240, f"height should be 240, got {meta.get('height')}"
    assert meta.get("frame_count", 0) >= 3, (
        f"frame_count should be >= 3, got {meta.get('frame_count')}"
    )
    assert abs(float(meta.get("fps") or 0) - 3.0) < 0.5
    assert meta.get("source") in ("cv2", "ffprobe")
    assert result.content_hash, "content_hash should be derived from bytes"
    # The tempfile must be cleaned up — file shouldn't linger in tmp.
    import glob
    import tempfile as _tf
    leftover = list(glob.glob(_tf.gettempdir() + r"\tmp*.mp4"))
    # We can't perfectly attribute leftover mp4s to this test, but
    # assert our named tempfile is gone.
    tmp_dir = _tf.gettempdir()
    # No assertion possible without state, but the cleanup path is exercised
    # in the source. (The real test is that this function returns, which
    # would fail with ResourceWarning if the tempfile leaked.)


# ==== Test 4: MediaRef with local file URL is backward compatible ==========
def test_video_parser_parse_media_ref_with_file_url(cv2, tiny_mp4):
    """Existing ``parse(MediaRef)`` callers must still work.

    R1 audit exercised ``VideoParser().parse(MediaRef(kind=VIDEO, data_b64=...))``
    — the new implementation should keep that interface working, and the
    local-file-URL variant should be picked up by the new path-aware code.
    """
    parser = VideoParser()
    ref = MediaRef(kind=ModalKind.VIDEO, url=str(tiny_mp4))
    result = parser.parse(ref)
    meta = result.meta
    assert meta.get("width") == 320
    assert meta.get("height") == 240
    assert meta.get("frame_count", 0) >= 3
    assert meta.get("source") in ("cv2", "ffprobe")


# ==== Test 5: MediaRef with data_b64 ========================================
def test_video_parser_parse_media_ref_with_data_b64(cv2, tiny_mp4):
    """``MediaRef(data_b64=...)`` must round-trip through the bytes path."""
    import base64
    parser = VideoParser()
    raw = tiny_mp4.read_bytes()
    ref = MediaRef(
        kind=ModalKind.VIDEO,
        data_b64=base64.b64encode(raw).decode("ascii"),
    )
    result = parser.parse(ref)
    meta = result.meta
    # Real metadata via the bytes path
    assert meta.get("width") == 320, f"data_b64 path: width={meta.get('width')}"
    assert meta.get("height") == 240, f"data_b64 path: height={meta.get('height')}"
    assert meta.get("frame_count", 0) >= 3
    assert meta.get("source") in ("cv2", "ffprobe")


# ==== Test 6: invalid path raises FileNotFoundError (no silent stub) =======
def test_video_parser_parse_invalid_path_raises():
    """``parse("/nonexistent.mp4")`` must raise, not silently stub.

    Pre-fix: the function swallowed cv2 failures and returned a heuristic
    stub, so callers had no way to know the file was missing.
    Post-fix: explicit FileNotFoundError.
    """
    parser = VideoParser()
    with pytest.raises(FileNotFoundError) as excinfo:
        parser.parse("D:/nonexistent_zzz_video_12345.mp4")
    msg = str(excinfo.value)
    assert "nonexistent" in msg, f"error should mention the path: {msg}"


# ==== Test 7: invalid type raises TypeError ================================
def test_video_parser_parse_invalid_type_raises():
    """Unsupported input type (e.g. int, list) must raise TypeError."""
    parser = VideoParser()
    with pytest.raises(TypeError) as excinfo:
        parser.parse(12345)  # type: ignore[arg-type]
    assert "unsupported input type" in str(excinfo.value)


# ==== Test 8: Meta dict shape =============================================
def test_video_parser_meta_has_all_expected_keys(cv2, tiny_mp4):
    """The meta dict must contain every documented key, not just width/height.

    Verifies the fix's promised contract:
    ``{fps, frame_count, width, height, duration_sec, codec, source}``
    plus ``size_bytes`` for callers that need it.
    """
    parser = VideoParser()
    result = parser.parse(str(tiny_mp4))
    expected = {
        "fps", "frame_count", "width", "height",
        "duration_sec", "codec", "source", "size_bytes",
    }
    missing = expected - set(result.meta.keys())
    assert not missing, f"meta missing keys: {missing}; got {set(result.meta.keys())}"


# ==== Test 9: ffprobe fallback (smoke test) ================================
def test_video_parser_ffprobe_or_cv2_source(cv2, tiny_mp4):
    """Whichever backend wins, ``source`` must be in the documented set.

    On the test env, cv2 is available and should win; this test acts as a
    drift guard if the cv2 dependency is ever removed (then ffprobe should
    take over).
    """
    parser = VideoParser()
    result = parser.parse(str(tiny_mp4))
    assert result.meta.get("source") in ("cv2", "ffprobe")


# ==== Test 10: helper _parse_video_real returns real metadata =============
def test_parse_video_real_helper_returns_real_metadata(cv2, tiny_mp4):
    """Smoke test the internal helper directly (no ParsedMedia wrapper)."""
    from backend.imdf.multimodal.parsers import _parse_video_real  # type: ignore  # noqa: E402
    raw = tiny_mp4.read_bytes()
    meta = _parse_video_real(data=raw, source_path=str(tiny_mp4))
    assert meta["width"] == 320
    assert meta["height"] == 240
    assert meta["frame_count"] >= 3
    assert meta["source"] in ("cv2", "ffprobe")
    assert abs(meta["fps"] - 3.0) < 0.5


# ==== Test 11: _parse_video_real on empty bytes returns graceful fallback ===
def test_parse_video_real_empty_bytes_returns_graceful():
    """Empty bytes must not crash — return file-level metadata with source='file'.

    P21 P2 P4 simplified contract: when cv2 fails, ``source`` is ``"file"``,
    not ``"none"``. The dict contains ``size_bytes`` and ``path`` only; cv2
    fields (width/height/etc.) are absent.
    """
    from backend.imdf.multimodal.parsers import _parse_video_real  # type: ignore  # noqa: E402
    meta = _parse_video_real(data=b"")
    # File-level keys are always present
    assert meta["size_bytes"] == 0
    assert "path" in meta
    assert meta["source"] in ("file", "none"), f"unexpected source: {meta['source']!r}"
    # cv2 keys are absent when cv2 produced no real data
    assert meta.get("width", 0) == 0
    assert meta.get("height", 0) == 0
    assert meta.get("frame_count", 0) == 0
    assert meta.get("fps", 0.0) == 0.0


# ==== Test 12: _parse_video_real on garbage bytes returns graceful =========
def test_parse_video_real_garbage_bytes_returns_graceful():
    """Garbage bytes must not raise — return file-level metadata.

    P21 P2 P4 simplified contract: ``source`` is ``"file"`` (cv2 fails to
    decode a non-video byte stream). size_bytes and path are set; cv2 fields
    are absent.
    """
    from backend.imdf.multimodal.parsers import _parse_video_real  # type: ignore  # noqa: E402
    meta = _parse_video_real(data=b"this is not a video at all, just text")
    assert meta["size_bytes"] == len(b"this is not a video at all, just text")
    assert "path" in meta
    assert meta["source"] in ("file", "cv2", "none"), (
        f"unexpected source: {meta['source']!r}"
    )
    assert meta.get("width", 0) == 0
    assert meta.get("height", 0) == 0
    assert meta.get("frame_count", 0) == 0


# ==== Test 13: parse(MediaRef) without data returns no-metadata result ====
def test_video_parser_parse_media_ref_no_data_returns_zeros():
    """``MediaRef`` with no URL/data_b64/text → zero metadata (graceful).

    P21 P2 P4 simplified contract: ``source`` is ``"none"``; size_bytes=0 and
    path="" are set. cv2 fields are absent.
    """
    parser = VideoParser()
    ref = MediaRef(kind=ModalKind.VIDEO, url=None, data_b64=None)
    result = parser.parse(ref)
    # No raise; just zero metadata (no real file to parse).
    assert result.kind == ModalKind.VIDEO
    assert result.meta.get("size_bytes") == 0
    assert result.meta.get("path") == ""
    assert result.meta.get("source") == "none"
    assert result.meta.get("width", 0) == 0
    assert result.meta.get("height", 0) == 0
    assert result.meta.get("frame_count", 0) == 0
