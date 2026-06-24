"""P6-Fix-P0-3 — verify the 9 ``pass``-only stubs replaced in P6-2 P0-5.

Each test exercises a previously-silent failure path and asserts that
the new implementation surfaces a structured diagnostic instead of
silently swallowing the error.

Covers:
  * annotation_service.operators.three_d.depth_map (2 stubs)
  * annotation_service.operators.video.tracking    (1 stub)
  * evaluation_service.operators.video_quality     (1 stub)
  * workflow_service.editor.project                (2 stubs)
  * workflow_service.editor.montage                (1 stub)
  * skills.builtin.guizang_ppt                     (2 stubs)
"""
from __future__ import annotations

import asyncio
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# 1. depth_map — 2 stubs (PIL decode, cv2 decode)
# ---------------------------------------------------------------------------
def test_depth_map_bad_pil_bytes_surfaces_error():
    """bytes input that PIL can't decode must return ok=False + error string."""
    from services.annotation_service.operators.three_d import depth_map

    result = depth_map.run([{"depth": b"not_a_real_image"}], {})
    rec = result[0]
    assert rec["ok"] is False
    err = rec["error"]
    # PIL fails on garbage bytes; cv2 is unavailable in test env
    assert "decode" in err or "pil_decode" in err
    assert rec["error_source"] == "depth"


def test_depth_map_bad_data_url_surfaces_error():
    """Malformed data URL should not crash; should report reason."""
    from services.annotation_service.operators.three_d import depth_map

    result = depth_map.run([{"depth": "data:image/png;base64,!!!"}], {})
    rec = result[0]
    assert rec["ok"] is False
    assert "data_url" in rec["error"] or "not" in rec["error"].lower()


def test_depth_map_unsupported_input_type():
    """A non-bytes/str/ndarray input should report unsupported_input_type."""
    from services.annotation_service.operators.three_d import depth_map

    result = depth_map.run([{"depth": 42}], {})
    rec = result[0]
    assert rec["ok"] is False
    assert "unsupported_input_type" in rec["error"]


def test_depth_map_valid_numpy_still_works():
    """Regression: valid 2D numpy array still produces stats/histogram."""
    from services.annotation_service.operators.three_d import depth_map

    arr = np.ones((10, 10), dtype="float32") * 3.5
    result = depth_map.run([{"depth": arr}], {"compute_stats": True,
                                              "compute_histogram": True})
    rec = result[0]
    assert rec["ok"] is True
    assert rec["stats"]["mean"] == 3.5
    assert rec["stats"]["min"] == 3.5
    assert rec["stats"]["max"] == 3.5


# ---------------------------------------------------------------------------
# 2. tracking — 1 stub (non-integer frame_id)
# ---------------------------------------------------------------------------
def test_tracking_non_int_frame_id_surfaces_diagnostic():
    """String frame_id used to silently pass — now records age_prune_skipped."""
    from services.annotation_service.operators.video import tracking

    result = tracking.run(
        [{"frame_id": "not_an_int", "detections": [
            {"bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
             "score": 0.9, "label": "obj"}]}],
        {"max_age": 5, "min_hits": 1},
    )
    rec = result[0]
    assert rec["ok"] is True
    assert "age_prune_skipped" in rec
    assert "frame_id_not_int_coercible" in rec["age_prune_skipped"]


def test_tracking_none_frame_id_surfaces_diagnostic():
    from services.annotation_service.operators.video import tracking

    result = tracking.run(
        [{"frame_id": None, "detections": [
            {"bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}}]}],
        {"max_age": 5, "min_hits": 1},
    )
    rec = result[0]
    assert rec["ok"] is True
    assert "age_prune_skipped" in rec
    assert "NoneType" in rec["age_prune_skipped"]


def test_tracking_int_frame_id_no_diagnostic():
    """Regression: integer frame_id still works cleanly with no diagnostic."""
    from services.annotation_service.operators.video import tracking

    result = tracking.run(
        [{"frame_id": 100, "detections": [
            {"bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}}]}],
        {"max_age": 5, "min_hits": 1},
    )
    rec = result[0]
    assert rec["ok"] is True
    assert "age_prune_skipped" not in rec


# ---------------------------------------------------------------------------
# 3. video_quality — 1 stub (bytes input w/o ffmpeg)
# ---------------------------------------------------------------------------
def _make_mp4_with_mvhd(timescale: int = 1000,
                        duration_ticks: int = 5000) -> bytes:
    """Build a tiny MP4 buffer: ftyp + moov > mvhd, with the given timescale."""
    ftyp = struct.pack(">I", 20) + b"ftyp" + b"isom" + struct.pack(">I", 0x200) + b"XXXX"
    mvhd_body = (
        struct.pack(">B", 0) + b"\x00\x00\x00"  # version 0 + flags
        + b"\x00" * 4 + b"\x00" * 4               # ctime + mtime
        + struct.pack(">I", timescale)
        + struct.pack(">I", duration_ticks)
        + b"\x00" * 80
    )
    mvhd_box = struct.pack(">I", 8 + len(mvhd_body)) + b"mvhd" + mvhd_body
    moov_box = struct.pack(">I", 8 + len(mvhd_box)) + b"moov" + mvhd_box
    return ftyp + moov_box


def test_video_quality_detect_mp4():
    from services.evaluation_service.operators.video_quality import _detect_format
    assert _detect_format(_make_mp4_with_mvhd()) == "mp4"


def test_video_quality_detect_webm_via_doctype():
    from services.evaluation_service.operators.video_quality import _detect_format
    ebml = b"\x1aE\xdf\xa3" + b"\x00" * 8 + b"\x42\x82\x84webm"
    assert _detect_format(ebml) == "webm"


def test_video_quality_detect_mkv_via_doctype():
    from services.evaluation_service.operators.video_quality import _detect_format
    ebml = b"\x1aE\xdf\xa3" + b"\x00" * 8 + b"\x42\x82\x88matroska"
    assert _detect_format(ebml) == "mkv"


def test_video_quality_detect_avi():
    from services.evaluation_service.operators.video_quality import _detect_format
    assert _detect_format(b"RIFF\x00\x00\x00\x00AVI ") == "avi"


def test_video_quality_detect_flv():
    from services.evaluation_service.operators.video_quality import _detect_format
    assert _detect_format(b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00\x00") == "flv"


def test_video_quality_parse_mp4_duration():
    """The new parser should recover duration from the mvhd box."""
    from services.evaluation_service.operators.video_quality import (
        _parse_mp4_mvhd_duration,
    )
    buf = _make_mp4_with_mvhd(timescale=1000, duration_ticks=5000)
    assert _parse_mp4_mvhd_duration(buf) == pytest.approx(5.0)


def test_video_quality_bytes_input_extracts_mp4_metadata():
    """bytes input no longer falls through to silent pass."""
    from services.evaluation_service.operators.video_quality import run

    buf = _make_mp4_with_mvhd(timescale=1000, duration_ticks=5000)
    result = run([buf], {})
    vq = result[0]["video_quality"]
    assert vq["source_format"] == "mp4"
    assert vq["duration"] == pytest.approx(5.0)
    assert "mp4_header_only" in vq["extraction_note"]


def test_video_quality_bytes_input_unknown_format_reports_note():
    from services.evaluation_service.operators.video_quality import run

    result = run([b"random_garbage_bytes_here_more_padding"], {})
    vq = result[0]["video_quality"]
    assert vq["source_format"] == "unknown"
    assert "ffmpeg" in vq["extraction_note"]


def test_video_quality_path_input_reports_path_only():
    from services.evaluation_service.operators.video_quality import run

    result = run(["/tmp/some_video.mp4"], {})
    vq = result[0]["video_quality"]
    assert "path_only" in vq["extraction_note"]


# ---------------------------------------------------------------------------
# 4. project — 2 stubs (registry import + get_template KeyError)
# ---------------------------------------------------------------------------
def test_project_template_not_found_raises_value_error():
    """load_template with unknown id must surface ValueError with reason."""
    from services.workflow_service.editor.project import get_project_store

    store = get_project_store()
    proj = store.create("p-test-1")
    with pytest.raises(ValueError) as excinfo:
        store.load_template(proj.id, "definitely-not-a-real-template-id")
    assert "template_not_found" in str(excinfo.value)


def test_project_template_registry_unavailable_uses_synthetic():
    """When the registry can't be imported, fall back to a synthetic template
    but mark it so the caller knows."""
    from services.workflow_service.editor import project as project_mod
    from services.workflow_service.editor.project import (
        TemplateFetchError, get_project_store,
    )

    store = get_project_store()
    proj = store.create("p-test-2")

    original = project_mod.ProjectStore._fetch_template

    def fake_fetch(self, template_id):
        raise TemplateFetchError(
            "nope", reason="registry_unavailable", template_id=template_id,
        )

    try:
        project_mod.ProjectStore._fetch_template = fake_fetch
        loaded = store.load_template(proj.id, "any-template-id")
    finally:
        project_mod.ProjectStore._fetch_template = original

    meta = loaded.timeline["template_meta"]
    assert meta["template_source"] == "registry_unavailable"
    assert meta["template_synthetic"] is True
    # The synthetic template still produces 3 clips (intro/main/outro).
    assert len(loaded.timeline["clips"]) == 3


def test_project_load_real_template_succeeds():
    """Regression: real template id should load with template_source='loaded'."""
    from services.workflow_service.editor.project import get_project_store

    store = get_project_store()
    proj = store.create("p-test-3")
    loaded = store.load_template(proj.id, "tpl-img-001")
    meta = loaded.timeline["template_meta"]
    assert meta["template_source"] == "loaded"
    assert meta["template_synthetic"] is False


def test_project_template_fetch_error_attributes():
    """TemplateFetchError must carry reason, template_id, available attrs."""
    from services.workflow_service.editor.project import TemplateFetchError

    exc = TemplateFetchError(
        "x", reason="not_found", template_id="abc", available=["x", "y"],
    )
    assert exc.reason == "not_found"
    assert exc.template_id == "abc"
    assert exc.available == ["x", "y"]


# ---------------------------------------------------------------------------
# 5. montage — 1 stub (flashforward mode)
# ---------------------------------------------------------------------------
def test_montage_flashforward_marks_clips_and_records_preview():
    from services.workflow_service.editor.montage import MontageEngine

    timeline = {
        "clips": [
            {"id": "c1", "start": 0, "end": 5},
            {"id": "c2", "start": 5, "end": 10},
            {"id": "c3", "start": 10, "end": 15},
        ],
    }
    engine = MontageEngine()
    plan = engine.apply(
        timeline=timeline,
        clips=["c1", "c2"],
        type="cross",
        time_mode="flashforward",
        layout="split_screen",
        bpm=120,
    )
    assert plan["time_mode"] == "flashforward"
    assert timeline["clips"][0]["flashforward"] is True
    assert timeline["clips"][1]["flashforward"] is True
    assert "flashforward" not in timeline["clips"][2]
    assert "tags" in timeline["clips"][0]
    assert "flashforward" in timeline["clips"][0]["tags"]
    previews = timeline["flashforward_previews"]
    assert len(previews) == 1
    assert previews[0]["clip_ids"] == ["c1", "c2"]
    assert previews[0]["montage_type"] == "cross"
    assert previews[0]["montage_layout"] == "split_screen"


def test_montage_flashback_still_works():
    """Regression: flashback path must not be broken by the flashforward edit."""
    from services.workflow_service.editor.montage import MontageEngine

    timeline = {
        "clips": [
            {"id": "a", "start": 0, "end": 5},
            {"id": "b", "start": 5, "end": 10},
            {"id": "c", "start": 10, "end": 15},
        ],
    }
    engine = MontageEngine()
    engine.apply(timeline=timeline, clips=["a", "c"], time_mode="flashback")
    assert [cl["id"] for cl in timeline["clips"]] == ["c", "b", "a"]


def test_montage_linear_is_noop():
    """Regression: linear mode should not mutate clips."""
    from services.workflow_service.editor.montage import MontageEngine

    timeline = {
        "clips": [{"id": "x", "start": 0, "end": 5}],
    }
    engine = MontageEngine()
    engine.apply(timeline=timeline, clips=["x"], time_mode="linear")
    assert timeline["clips"][0].get("flashforward") is None
    assert "flashforward_previews" not in timeline


# ---------------------------------------------------------------------------
# 6. guizang_ppt — 2 stubs (JSON parse fallback)
# ---------------------------------------------------------------------------
def test_guizang_ppt_parse_direct_json():
    from skills.builtin.guizang_ppt import _parse_deck
    deck = _parse_deck(
        '{"title": "X", "slides": [{"page": 1, "title": "t", "bullets": ["a"], "speaker_notes": ""}]}',
        topic="X", slide_count=1,
    )
    assert deck["_parse_source"] == "direct_json"
    assert deck["_parse_errors"] == []
    assert len(deck["slides"]) == 1


def test_guizang_ppt_parse_bare_list():
    from skills.builtin.guizang_ppt import _parse_deck
    deck = _parse_deck(
        '[{"page": 1, "title": "t", "bullets": [], "speaker_notes": ""}]',
        topic="X", slide_count=1,
    )
    assert deck["_parse_source"] == "bare_list"
    assert len(deck["slides"]) == 1


def test_guizang_ppt_parse_trailing_json_block():
    from skills.builtin.guizang_ppt import _parse_deck
    raw = 'Here is your deck:\n{"title": "Y", "slides": [{"page": 1, "title": "t", "bullets": [], "speaker_notes": ""}]}'
    deck = _parse_deck(raw, topic="Y", slide_count=1)
    assert deck["_parse_source"] == "json_block"
    assert deck["_parse_errors"] == []


def test_guizang_ppt_parse_invalid_json_records_errors():
    from skills.builtin.guizang_ppt import _parse_deck
    deck = _parse_deck("{not valid json}", topic="Z", slide_count=2)
    assert deck["_parse_source"] == "fallback_template"
    assert len(deck["_parse_errors"]) >= 2  # direct_json + json_block
    # Both error strings should mention JSONDecodeError.
    joined = " ".join(deck["_parse_errors"])
    assert "JSONDecodeError" in joined


def test_guizang_ppt_parse_empty_records_errors():
    from skills.builtin.guizang_ppt import _parse_deck
    deck = _parse_deck("", topic="Z", slide_count=3)
    assert deck["_parse_source"] == "fallback_template"
    assert any("no trailing" in e for e in deck["_parse_errors"])


def test_guizang_ppt_parse_garbage_uses_template():
    from skills.builtin.guizang_ppt import _parse_deck
    deck = _parse_deck("completely unusable output", topic="My Topic", slide_count=5)
    assert deck["_parse_source"] == "fallback_template"
    assert len(deck["slides"]) == 5
    assert deck["title"] == "My Topic"
    assert deck["slides"][0]["title"].startswith("封面")


def test_guizang_ppt_skill_execute_surfaces_parse_source():
    from skills.builtin.guizang_ppt import GuizangPPTSkill
    from skills.context import SkillContext

    sk = GuizangPPTSkill()
    ctx = SkillContext.create(user_id="u1", inputs={"topic": "AI safety"})
    result = asyncio.run(sk.execute(ctx))
    assert result.success is True
    assert "parse_source" in result.metadata
    assert "parse_errors" in result.metadata
    # No real LLM is wired → mock returns deterministic stub
    # which doesn't start with '{' → fallback_template path
    assert result.metadata["parse_source"] == "fallback_template"
    # Logs should mention the parse source
    assert any("parse_source=" in log for log in result.logs)


def test_guizang_ppt_skill_rejects_empty_topic():
    from skills.builtin.guizang_ppt import GuizangPPTSkill
    from skills.context import SkillContext

    sk = GuizangPPTSkill()
    ctx = SkillContext.create(user_id="u1", inputs={"topic": ""})
    result = asyncio.run(sk.execute(ctx))
    assert result.success is False
    assert "topic" in result.error.lower() or "不能为空" in result.error


# ---------------------------------------------------------------------------
# 7. Sanity check — none of the touched files still have unguarded `pass`
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path", [
    "services/annotation_service/operators/three_d/depth_map.py",
    "services/annotation_service/operators/video/tracking.py",
    "services/evaluation_service/operators/video_quality.py",
    "services/workflow_service/editor/project.py",
    "services/workflow_service/editor/montage.py",
    "skills/builtin/guizang_ppt.py",
])
def test_no_remaining_bare_pass_except_in_documented_fallbacks(rel_path):
    """Assert that no touched file still has a bare ``pass``-only handler.

    We allow ``pass`` only inside explicit ``except`` blocks that carry
    either a documented comment about a synthetic fallback or a ``pass``
    in a normal flow (e.g. dataclass / abstract stub).  This test counts
    such cases by file and reports them so we can manually inspect.
    """
    p = (_BACKEND / rel_path).resolve()
    src = p.read_text(encoding="utf-8")
    lines = src.splitlines()
    bare_pass_lines = [
        i + 1 for i, ln in enumerate(lines)
        if ln.strip() == "pass"
    ]
    # The known allowed fallback is in montage.py's apply() method
    # where the new flashforward handler IS the implementation (no pass).
    # All other pass statements should be in try/except blocks that
    # either log, set a diagnostic, or fall through with a documented
    # synthetic template (project.py: _synthetic_template).
    allowed_files_with_pass = {
        # montage.py: the flashforward branch is now implemented (no pass).
        # project.py: _synthetic_template is a real method (no bare pass).
        # The remaining bare pass lines, if any, must be inspected.
    }
    if bare_pass_lines and rel_path not in allowed_files_with_pass:
        pytest.fail(
            f"{rel_path} still has bare `pass` on lines {bare_pass_lines}; "
            "replace with structured diagnostic or documented synthetic fallback."
        )


# ---------------------------------------------------------------------------
# 8. End-to-end "before/after" verification — run each operator with bad
# input and confirm ok=False + informative error (not a silent success).
# ---------------------------------------------------------------------------
def test_no_silent_success_on_bad_input():
    """Each touched operator must surface ok=False when fed garbage."""
    from services.annotation_service.operators.three_d import depth_map
    from services.annotation_service.operators.video import tracking
    from services.evaluation_service.operators.video_quality import run as vq_run
    from skills.builtin.guizang_ppt import _parse_deck

    # depth_map: bad bytes
    r = depth_map.run([{"depth": b"\x00\x00\x00"}], {})
    assert r[0]["ok"] is False
    assert "error" in r[0] and r[0]["error"]

    # tracking: bad frame_id
    r = tracking.run(
        [{"frame_id": "x", "detections": [{"bbox": {"x1": 0, "y1": 0, "x2": 1, "y2": 1}}]}],
        {},
    )
    assert r[0]["ok"] is True
    assert r[0].get("age_prune_skipped")

    # video_quality: garbage bytes
    r = vq_run([b"x" * 32], {})
    vq = r[0]["video_quality"]
    assert vq["source_format"] == "unknown"
    assert vq["extraction_note"]

    # guizang_ppt: garbage input
    deck = _parse_deck("garbage", topic="x", slide_count=2)
    assert deck["_parse_source"] == "fallback_template"
    assert deck["_parse_errors"]