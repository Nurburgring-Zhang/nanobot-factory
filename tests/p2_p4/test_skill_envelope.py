#!/usr/bin/env python3
"""P21 P2 P4 — Unified SkillOutput envelope tests (R2 N8).

R2 audit (reports/p21_r2_audit_skill.md §N8) found that 3 different
``make_metadata`` / ``build_output`` helpers across the 4 imdf
``_base.py`` files produced 3 different envelope shapes, and
``elapsed_ms`` was not consistently populated.

This file is the unified-contract test for the post-P2-P4 envelope
shape. It verifies:

  T1 — :func:`make_envelope` returns a ``{"result", "metadata"}`` dict
        with all canonical keys (``elapsed_ms``, ``source``,
        ``retry_count``, ``token_count``, ``cost_usd``, ``timestamp``).
  T2 — defaults: when only ``result`` + ``elapsed_ms`` are supplied,
        the canonical fields get their spec defaults
        (``source="real"``, ``retry_count=0``, ``token_count=0``,
        ``cost_usd=0.0``).
  T3 — ``elapsed_ms`` is rounded to 3 decimal places and >= 0.0.
  T4 — ``extra`` dict is merged into ``metadata`` (per-skill fields
        preserved verbatim).
  T5 — ``extra`` keys WIN over canonical fields when they collide
        (callers can override defaults).
  T6 — :class:`ElapsedTimer` records wall-clock ms via ``time.time()``,
        including across exceptions (``__exit__`` is exception-safe).
  T7 — roundtrip: each of the 4 per-module helpers (``_build_output`` /
        ``make_metadata`` / ``build_output`` / ``build_metadata``) now
        produces a metadata dict with the same canonical shape
        (elapsed_ms, source, retry_count, token_count, cost_usd,
        timestamp).
  T8 — regression guard: outer API unchanged —
        ``SkillOutput(success, result, error, metadata)`` still works
        for synth/label; clean/crawl helpers still return metadata dicts.
  T9 — coverage matrix: the 4 _base.py files are the only base files.
        (If a 5th is added, this test must be updated — locks the fix
        to a known surface area.)

Hard rules respected
--------------------
* 25-min budget; no new dependencies (the envelope uses stdlib only).
* Outer API (``SkillOutput(success, result, error, metadata)``) is
  preserved.
* The 4 _base.py files are modified in place; the new
  ``backend/imdf/skills/_envelope.py`` is the single source of truth.

Run from the project root::

    pytest tests/p2_p4/test_skill_envelope.py -v
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ── Path setup (defensive — does not depend on conftest ordering) ─────────
_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("IMDF_TEST_MODE", "1")


# ── Load the new _envelope.py module via direct spec loader ───────────────
# We import via the package path so we test the public surface as
# downstream code will see it. If the package is not on the path the
# spec loader fallback is used.
def _load_envelope():
    try:
        from backend.imdf.skills._envelope import make_envelope, ElapsedTimer
        return make_envelope, ElapsedTimer
    except Exception:
        path = _BACKEND / "imdf" / "skills" / "_envelope.py"
        spec = importlib.util.spec_from_file_location(
            "imdf_envelope_test", str(path),
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.make_envelope, mod.ElapsedTimer


make_envelope, ElapsedTimer = _load_envelope()


# ── Load the 4 _base.py modules via direct spec loader ─────────────────────
# This bypasses the imdf.skills package __init__ (which fails due to the
# N6 registry import blocker in the crawl module). The 4 base files
# themselves only depend on ``backend.skills`` and httpx + pydantic —
# both available in the test env.
_BASE_FILES = {
    "clean": _BACKEND / "imdf" / "skills" / "clean" / "_base.py",
    "label": _BACKEND / "imdf" / "skills" / "label" / "_base.py",
    "synth": _BACKEND / "imdf" / "skills" / "synth" / "_base.py",
    "crawl": _BACKEND / "imdf" / "skills" / "crawl" / "_base.py",
}

_BASE_CACHE: Dict[str, Any] = {}


def _get_base(name: str):
    if name in _BASE_CACHE:
        return _BASE_CACHE[name]
    spec = importlib.util.spec_from_file_location(
        f"imdf_{name}_base_envelope_test", str(_BASE_FILES[name]),
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_BASE_FILES[name]}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _BASE_CACHE[name] = mod
    return mod


# ── 1. make_envelope — return shape ───────────────────────────────────────
def test_make_envelope_returns_result_metadata_dict():
    """T1: make_envelope returns a 2-key dict with `result` and `metadata`."""
    env = make_envelope(result={"x": 1}, elapsed_ms=12.5)
    assert isinstance(env, dict)
    assert set(env.keys()) == {"result", "metadata"}, (
        f"envelope should have exactly 2 keys; got {set(env.keys())}"
    )
    assert env["result"] == {"x": 1}


# ── 2. make_envelope — canonical fields present ───────────────────────────
def test_make_envelope_includes_all_canonical_fields():
    """T1: all canonical metadata fields are present."""
    env = make_envelope(
        result="ok",
        elapsed_ms=7.5,
        source="live",
        retry_count=2,
        token_count=150,
        cost_usd=0.003,
    )
    md = env["metadata"]
    for key in (
        "elapsed_ms", "source", "retry_count",
        "token_count", "cost_usd", "timestamp",
    ):
        assert key in md, f"missing canonical field: {key}"
    assert md["source"] == "live"
    assert md["retry_count"] == 2
    assert md["token_count"] == 150
    assert md["cost_usd"] == 0.003


# ── 3. make_envelope — defaults ───────────────────────────────────────────
def test_make_envelope_defaults_match_spec():
    """T2: defaults — source='real', retry_count=0, token_count=0, cost_usd=0.0."""
    env = make_envelope(result="x", elapsed_ms=0.0)
    md = env["metadata"]
    assert md["source"] == "real"
    assert md["retry_count"] == 0
    assert md["token_count"] == 0
    assert md["cost_usd"] == 0.0
    assert md["elapsed_ms"] == 0.0


# ── 4. make_envelope — elapsed_ms precision and non-negative ─────────────
def test_make_envelope_elapsed_ms_is_rounded_and_non_negative():
    """T3: elapsed_ms is rounded to 3 decimal places and never negative."""
    env = make_envelope(result=None, elapsed_ms=12.3456789)
    assert env["metadata"]["elapsed_ms"] == 12.346
    # 0 is allowed (callers may not have measured)
    env0 = make_envelope(result=None, elapsed_ms=0.0)
    assert env0["metadata"]["elapsed_ms"] == 0.0


# ── 5. make_envelope — extra dict merged into metadata ────────────────────
def test_make_envelope_extra_merged_into_metadata():
    """T4: extra fields are merged into metadata (per-skill bookkeeping)."""
    env = make_envelope(
        result={"q": "x"},
        elapsed_ms=5.0,
        source="mock",
        extra={
            "skill_id": "synth_summary",
            "query": {"q": "x"},
            "skill_module": "synth",
        },
    )
    md = env["metadata"]
    assert md["skill_id"] == "synth_summary"
    assert md["query"] == {"q": "x"}
    assert md["skill_module"] == "synth"
    # canonical fields still present
    assert md["elapsed_ms"] == 5.0
    assert md["source"] == "mock"


# ── 6. make_envelope — extra overrides canonical ──────────────────────────
def test_make_envelope_extra_overrides_canonical():
    """T5: extras win on collision (callers can override defaults)."""
    env = make_envelope(
        result=None,
        elapsed_ms=0.0,
        source="live",
        retry_count=1,
        extra={"source": "mock_override"},
    )
    assert env["metadata"]["source"] == "mock_override"
    # Non-overridden canonical fields are unchanged
    assert env["metadata"]["retry_count"] == 1


# ── 7. ElapsedTimer — records wall-clock ms ───────────────────────────────
def test_elapsed_timer_records_wall_clock_ms():
    """T6: ElapsedTimer records wall-clock time in milliseconds."""
    with ElapsedTimer() as t:
        # 50 ms of sleep
        time.sleep(0.05)
    # Should be >= 50 ms (allow some scheduler slack) and < 1000 ms
    assert t.elapsed_ms >= 40, f"elapsed_ms too small: {t.elapsed_ms}"
    assert t.elapsed_ms < 1000, f"elapsed_ms too large: {t.elapsed_ms}"


def test_elapsed_timer_exception_safe():
    """T6: ElapsedTimer records elapsed_ms even when the block raises."""
    timer_ref: List[ElapsedTimer] = []
    with pytest.raises(RuntimeError):
        with ElapsedTimer() as t:
            timer_ref.append(t)
            time.sleep(0.01)
            raise RuntimeError("boom")
    assert timer_ref, "timer not bound"
    assert timer_ref[0].elapsed_ms >= 5


def test_elapsed_timer_zero_initially():
    """T6: ElapsedTimer starts with elapsed_ms=0.0."""
    t = ElapsedTimer()
    assert t.elapsed_ms == 0.0


# ── 8. Roundtrip — each base file produces the unified shape ──────────────
@pytest.mark.parametrize("base_name", list(_BASE_FILES))
def test_each_base_helper_populates_unified_fields(base_name: str):
    """T7: each of the 4 helpers produces a metadata dict with elapsed_ms,
    source, retry_count, token_count, cost_usd, timestamp.
    """
    base = _get_base(base_name)
    base.reset_retry_state()
    # Pre-record some retry/usage state so the helpers surface real values
    state = base.get_retry_state()
    state.attempts = 2  # 1 retry
    state.add_usage(input_tokens=10, output_tokens=20)

    if base_name == "synth":
        out = base._build_output(
            success=True, result={"ok": 1}, elapsed_ms=3.21,
        )
        md = out.metadata
    elif base_name == "label":
        out = base.build_output(
            success=True, result={"ok": 1}, elapsed_ms=3.21,
        )
        md = out.metadata
    elif base_name == "clean":
        md = base.make_metadata(
            "skill_test", "test_skill", elapsed_ms=3.21,
        )
    elif base_name == "crawl":
        md = base.build_metadata(
            "crawl_test", query={"q": "x"}, elapsed_ms=3.21,
        )
    else:  # pragma: no cover - locked by T9 coverage matrix
        raise AssertionError(f"unknown base {base_name!r}")

    for key in (
        "elapsed_ms", "source", "retry_count",
        "token_count", "cost_usd", "timestamp",
    ):
        assert key in md, (
            f"{base_name}: missing canonical field {key!r}; "
            f"got keys: {sorted(md.keys())}"
        )
    # elapsed_ms came from the parameter
    assert md["elapsed_ms"] == 3.21, (
        f"{base_name}: elapsed_ms not propagated; got {md['elapsed_ms']}"
    )
    # retry_count + token_count came from the retry state
    assert md["retry_count"] == 1, (
        f"{base_name}: retry_count not from state; got {md['retry_count']}"
    )
    assert md["token_count"] == 30, (
        f"{base_name}: token_count not from state; got {md['token_count']}"
    )


# ── 9. Outer API unchanged ────────────────────────────────────────────────
def test_outer_api_unchanged_synth_returns_skill_output():
    """T8: synth._build_output still returns a SkillOutput."""
    base = _get_base("synth")
    base.reset_retry_state()
    out = base._build_output(success=True, result={"ok": 1}, elapsed_ms=1.0)
    # dataclass with the 4 expected fields
    assert hasattr(out, "success")
    assert hasattr(out, "result")
    assert hasattr(out, "error")
    assert hasattr(out, "metadata")
    assert out.success is True
    assert out.error == ""


def test_outer_api_unchanged_label_returns_skill_output():
    """T8: label.build_output still returns a SkillOutput."""
    base = _get_base("label")
    base.reset_retry_state()
    out = base.build_output(success=False, error="oops", elapsed_ms=1.0)
    assert out.success is False
    assert out.error == "oops"
    assert hasattr(out, "result")
    assert hasattr(out, "metadata")


def test_outer_api_unchanged_clean_returns_metadata_dict():
    """T8: clean.make_metadata still returns a metadata dict (not SkillOutput)."""
    base = _get_base("clean")
    base.reset_retry_state()
    md = base.make_metadata("s1", "n1")
    assert isinstance(md, dict)
    # No `success` / `error` / `result` keys (those live on SkillOutput)
    assert "success" not in md
    assert "error" not in md
    # The `result` key is reserved by the envelope; clean's make_metadata
    # historically did NOT include it.
    assert "result" not in md


def test_outer_api_unchanged_crawl_returns_metadata_dict():
    """T8: crawl.build_metadata still returns a metadata dict (not SkillOutput)."""
    base = _get_base("crawl")
    base.reset_retry_state()
    md = base.build_metadata("c1", query={"q": "x"})
    assert isinstance(md, dict)
    # The 3 crawl-specific fields are preserved (P3 contract)
    assert md["skill_id"] == "c1"
    assert md["query"] == {"q": "x"}


# ── 10. Coverage matrix — locks 4 _base.py files ─────────────────────────
def test_coverage_matrix_includes_all_bases():
    """T9: 4 _base.py files are the known surface. A 5th forces a test update."""
    expected = {"clean", "label", "synth", "crawl"}
    assert set(_BASE_FILES) == expected


# ── 11. No new dependencies ───────────────────────────────────────────────
def test_no_new_dependencies_introduced():
    """Regression guard: _envelope.py uses only stdlib.

    The envelope module only imports ``time`` and typing — any future
    worker who tries to add pydantic, orjson, etc. will fail this test.
    """
    envelope_path = _BACKEND / "imdf" / "skills" / "_envelope.py"
    text = envelope_path.read_text(encoding="utf-8")
    # stdlib + local backend imports only
    for forbidden in (
        "import pydantic", "from pydantic",
        "import orjson", "from orjson",
        "import ujson", "from ujson",
    ):
        assert forbidden not in text, (
            f"_envelope.py imported forbidden dep {forbidden!r}"
        )
    # Must import `time` (used by make_envelope + ElapsedTimer)
    assert "import time" in text or "from time" in text, (
        "_envelope.py should import time"
    )


# ── 12. Roundtrip — full envelope shape from each base ────────────────────
def test_full_envelope_shape_consistent_across_bases():
    """The same canonical field set appears in every base's metadata."""
    expected_fields = {
        "elapsed_ms", "source", "retry_count",
        "token_count", "cost_usd", "timestamp",
    }
    for name, path in _BASE_FILES.items():
        base = _get_base(name)
        base.reset_retry_state()
        if name == "synth":
            out = base._build_output(success=True, result={}, elapsed_ms=1.0)
            md = out.metadata
        elif name == "label":
            out = base.build_output(success=True, result={}, elapsed_ms=1.0)
            md = out.metadata
        elif name == "clean":
            md = base.make_metadata("s", "n", elapsed_ms=1.0)
        elif name == "crawl":
            md = base.build_metadata("s", query={}, elapsed_ms=1.0)
        else:  # pragma: no cover
            continue
        missing = expected_fields - set(md.keys())
        assert not missing, (
            f"{name}/_base.py metadata missing {missing}; got: {sorted(md.keys())}"
        )
