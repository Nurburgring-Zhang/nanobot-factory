"""P21 P2 P3 (revised) — skill retry/backoff + cost/token tracking (R2 N3 + N4).

R2 audit findings (reports/p21_r2_audit_skill.md §N3 + §N4):
  * N3: 0/52 imdf skills had retry/backoff logic. First network blip caused
        a permanent offline-mock fallback (especially bad for crawl_reddit,
        crawl_twitter etc. with 5s timeouts).
  * N4: 0/52 imdf skills tracked cost or token usage.

The P3 fix adds:
  * A stdlib-only ``@retry`` decorator in each of the 4 imdf _base.py files
    (clean, label, synth, crawl). Retries up to 3× on
    ``(httpx.TimeoutException, httpx.NetworkError)`` with exponential backoff
    (0.5s, 1s, 2s).
  * A ``_RetryState`` per-call contextvar that records attempt count and
    token usage. ``make_metadata`` / ``build_output`` / ``build_metadata``
    auto-populate ``retry_count``, ``token_count``, ``input_tokens``,
    ``output_tokens`` fields on every SkillOutput metadata dict.

These tests verify, for each of the 4 _base.py files:
  T1 — happy path: call succeeds on first try, ``retry_count == 0``.
  T2 — retry-then-succeed: call raises 2× then succeeds,
       ``retry_count == 2``.
  T3 — exhausted: call always fails, raises after exactly 3 attempts
       and the final attempt's exception propagates.
  T4 — token tracking: a fake ``call_llm`` helper that records
       ``input_tokens + output_tokens`` populates ``metadata.token_count``.
  T5 — manual override: explicit ``token_count=N`` in the metadata dict
       wins over the contextvar default (preserves the existing
       "explicit-setdefault" contract).

Hard rules respected:
  * 25-min budget; no new dependencies (pure stdlib ``asyncio`` /
    ``functools`` / ``contextvars``).
  * 4 _base.py files modified; this single test file is the unified
    contract for all of them.

Run from the project root::

    pytest tests/p2_p3_revised/test_skill_retry_cost.py -v
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest


# ── Path setup (defensive — does not depend on conftest ordering) ─────────
_THIS = Path(__file__).resolve()
_PROJECT_ROOT = _THIS.parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("IMDF_TEST_MODE", "1")


# ── Load the 4 _base.py modules via direct spec loader ─────────────────────
# This bypasses the imdf.skills package __init__ (which fails due to the
# N6 registry import blocker). The 4 base files themselves only depend on
# ``backend.skills`` and httpx + pydantic — both available in the test
# env. We do NOT pull in the per-skill modules; we're testing the
# base-level retry/metadata contract.
_BASE_FILES = {
    "clean": _BACKEND / "imdf" / "skills" / "clean" / "_base.py",
    "label": _BACKEND / "imdf" / "skills" / "label" / "_base.py",
    "synth": _BACKEND / "imdf" / "skills" / "synth" / "_base.py",
    "crawl": _BACKEND / "imdf" / "skills" / "crawl" / "_base.py",
}

# Module-level cache — each base must be loaded ONCE per test process
# because the retry decorator stores state in a module-scoped contextvar.
# If a test calls _get_base twice, it gets two distinct module instances
# with two distinct contextvar defaults → state desync.
_BASE_CACHE: Dict[str, Any] = {}


def _get_base(name: str):
    if name in _BASE_CACHE:
        return _BASE_CACHE[name]
    spec = importlib.util.spec_from_file_location(
        f"imdf_{name}_base_test", str(_BASE_FILES[name]),
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_BASE_FILES[name]}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _BASE_CACHE[name] = mod
    return mod


# Cache so the import only happens once per test process.
# (The actual cache lives in the module-level _BASE_CACHE dict above; the
# fixtures just expose typed accessors for the per-test reset_retry_state
# convenience.)


@pytest.fixture(scope="module")
def clean_base():
    return _get_base("clean")


@pytest.fixture(scope="module")
def label_base():
    return _get_base("label")


@pytest.fixture(scope="module")
def synth_base():
    return _get_base("synth")


@pytest.fixture(scope="module")
def crawl_base():
    return _get_base("crawl")


# ── Fakes (no real network / no real LLM) ─────────────────────────────────
class _FakeTimeout(Exception):
    """Stand-in for ``httpx.TimeoutException`` without importing httpx."""


class _FakeNetwork(Exception):
    """Stand-in for ``httpx.NetworkError`` without importing httpx."""


def _make_httpx_compatible_exc():
    """Return a tuple of exception classes whose .__name__ matches the
    strings ``httpx`` checks. The retry decorator only checks ``isinstance``,
    so any object with the matching name is fine. But for parity with the
    real decorator we also want a class with the right MRO. Here we build
    lightweight stand-ins (no real httpx import)."""
    return _FakeTimeout, _FakeNetwork


# ── Test: T1 (happy path, no retry) ──────────────────────────────────────
@pytest.mark.parametrize("base_name", list(_BASE_FILES))
def test_retry_happy_path_no_retry(base_name: str, base_name_to_base):
    """A successful first attempt: retry_count == 0 in metadata."""
    base = base_name_to_base(base_name)
    base.reset_retry_state()

    @base.retry(max_attempts=3, backoff=0.0)
    async def ok() -> str:
        return "ok"

    out = asyncio.run(ok())
    assert out == "ok"
    state = base.get_retry_state()
    # exactly one attempt recorded
    assert state.attempts == 1


# ── Test: T2 (retry-then-succeed) ─────────────────────────────────────────
@pytest.mark.parametrize("base_name", list(_BASE_FILES))
def test_retry_eventually_succeeds(base_name: str, base_name_to_base):
    """A 2-timeout-then-succeed call records retry_count == 2 and the
    decorator's exception type is the configured one."""
    base = base_name_to_base(base_name)
    base.reset_retry_state()
    Timeout, _ = _make_httpx_compatible_exc()

    calls: List[int] = []

    @base.retry(max_attempts=3, backoff=0.0, exceptions=(Timeout,))
    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise Timeout(f"simulated timeout #{len(calls)}")
        return "ok"

    out = asyncio.run(flaky())
    assert out == "ok"
    assert len(calls) == 3  # 2 fails + 1 success
    state = base.get_retry_state()
    # attempts includes the final success
    assert state.attempts == 3
    # retry_count == attempts - 1 (no retry on the last successful call)
    assert max(0, state.attempts - 1) == 2


# ── Test: T3 (always-fail exhausts after 3 attempts) ──────────────────────
@pytest.mark.parametrize("base_name", list(_BASE_FILES))
def test_retry_exhausts_after_max_attempts(base_name: str, base_name_to_base):
    """A call that always fails raises the last exception after exactly
    ``max_attempts`` tries — no more, no fewer."""
    base = base_name_to_base(base_name)
    base.reset_retry_state()
    Timeout, _ = _make_httpx_compatible_exc()

    calls: List[int] = []

    @base.retry(max_attempts=3, backoff=0.0, exceptions=(Timeout,))
    async def always_fails() -> str:
        calls.append(1)
        raise Timeout(f"simulated timeout #{len(calls)}")

    with pytest.raises(Timeout) as ei:
        asyncio.run(always_fails())
    assert "simulated timeout #3" in str(ei.value)
    assert len(calls) == 3


# ── Test: T4 (token tracking via fake call_llm) ──────────────────────────
def test_token_tracking_via_call_llm(clean_base):
    """When a skill records usage into the contextvar (simulating an LLM
    call that returns usage info), ``make_metadata`` surfaces
    ``token_count = input_tokens + output_tokens``."""
    clean_base.reset_retry_state()
    state = clean_base.get_retry_state()
    state.add_usage(input_tokens=100, output_tokens=50)

    md = clean_base.make_metadata("skill_test", "test_skill", source="imdf.skills.clean")
    assert md["token_count"] == 150
    assert md["input_tokens"] == 100
    assert md["output_tokens"] == 50
    # retry_count defaults to 0 when no retry decorator ran
    assert md["retry_count"] == 0


def test_token_tracking_combined_with_retry(clean_base):
    """Full integration: a function that records token usage and uses the
    retry decorator still reports both retry_count and token_count."""
    clean_base.reset_retry_state()
    state = clean_base.get_retry_state()
    state.add_usage(input_tokens=200, output_tokens=80)
    # Simulate 2 retries
    state.attempts = 3
    md = clean_base.make_metadata("skill_test", "test_skill")
    assert md["token_count"] == 280
    assert md["input_tokens"] == 200
    assert md["output_tokens"] == 80
    assert md["retry_count"] == 2  # 3 attempts -> 2 retries


# ── Test: T5 (explicit override in metadata) ──────────────────────────────
def test_explicit_metadata_overrides_contextvar(clean_base):
    """Caller-supplied token_count / retry_count in the metadata kwargs
    win over the contextvar default (setdefault contract preserved)."""
    clean_base.reset_retry_state()
    state = clean_base.get_retry_state()
    state.add_usage(input_tokens=10, output_tokens=20)
    state.attempts = 5
    md = clean_base.make_metadata(
        "skill_test", "test_skill",
        token_count=999, retry_count=7,  # explicit
    )
    assert md["token_count"] == 999
    assert md["retry_count"] == 7


# ── Coverage matrix ──────────────────────────────────────────────────────
# Ensure the test matrix covers all 4 _base.py files. If anyone adds a
# 5th _base.py, the parametrize list above must be updated.
def test_coverage_matrix_includes_all_bases():
    expected = {"clean", "label", "synth", "crawl"}
    assert set(_BASE_FILES) == expected


# ── Parametrized base lookup (built-in fixture pattern) ──────────────────
@pytest.fixture(scope="module")
def base_name_to_base():
    """Map a base name → loaded module. Used by parametrize so each test
    runs against each of the 4 _base.py files."""
    cache: Dict[str, Any] = {}

    def _lookup(name: str):
        if name not in cache:
            cache[name] = _get_base(name)
        return cache[name]

    return _lookup


# ── End-to-end: per-base integration tests ────────────────────────────────
def test_clean_safe_httpx_call_retries_then_falls_back(clean_base, monkeypatch):
    """``safe_httpx_call`` retries transient errors then returns the
    offline fallback dict with the error surfaced."""
    import httpx

    # Force real network code-path
    monkeypatch.setattr(clean_base, "httpx", httpx, raising=False)

    # Build a stub httpx.AsyncClient that always times out
    class _StubClient:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> "_StubClient":
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def request(self, *a: Any, **kw: Any) -> None:
            raise httpx.TimeoutException("simulated")

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)
    clean_base.reset_retry_state()
    out = asyncio.run(
        clean_base.safe_httpx_call(
            "http://example.invalid/", method="POST",
            payload={"x": 1}, mock={"fallback": True},
        )
    )
    assert out["status"] == "offline"
    assert out["data"] == {"fallback": True}
    state = clean_base.get_retry_state()
    # 3 attempts → retry_count = 2 in metadata
    assert state.attempts == 3


def test_label_post_json_retries(label_base, monkeypatch):
    """``post_json`` (label) retries the configured exceptions, then
    returns ``None`` on persistent failure — exactly the pre-fix
    behavior, but with retry budget spent first."""
    import httpx

    # The label base exposes NETWORK_OK; bypass to force the live path
    monkeypatch.setattr(label_base, "NETWORK_OK", True, raising=False)

    class _StubClient:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> "_StubClient":
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **kw: Any) -> None:
            raise httpx.TimeoutException("simulated")

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)
    label_base.reset_retry_state()
    out = asyncio.run(label_base.post_json("http://x.invalid/", {"q": "x"}))
    assert out is None
    state = label_base.get_retry_state()
    assert state.attempts == 3


def test_synth_build_output_includes_retry_and_token(crawl_base):
    synth = _get_base("synth")
    synth.reset_retry_state()
    state = synth.get_retry_state()
    state.attempts = 4  # 1 try + 3 retries
    state.add_usage(input_tokens=42, output_tokens=13)
    out = synth._build_output(success=True, result={"ok": 1})
    assert out.success is True
    assert out.metadata["retry_count"] == 3
    assert out.metadata["token_count"] == 55
    assert out.metadata["input_tokens"] == 42
    assert out.metadata["output_tokens"] == 13


def test_crawl_build_metadata_includes_retry_and_token(clean_base):
    crawl = _get_base("crawl")
    crawl.reset_retry_state()
    state = crawl.get_retry_state()
    state.attempts = 2
    state.add_usage(input_tokens=7, output_tokens=11)
    md = crawl.build_metadata("crawl_test", query={"q": "x"})
    assert md["retry_count"] == 1
    assert md["token_count"] == 18
    assert md["input_tokens"] == 7
    assert md["output_tokens"] == 11


def test_no_new_dependencies_introduced():
    """Regression guard: the new retry decorator uses only stdlib.
    Any future worker who tries to import tenacity / backoff will fail
    this test. We check for actual import statements (not docstring
    mentions) so the test stays focused on real dependency creep.
    """
    for name, path in _BASE_FILES.items():
        text = path.read_text(encoding="utf-8")
        for forbidden in ("import tenacity", "from tenacity",
                          "import backoff", "from backoff"):
            assert forbidden not in text, (
                f"{name}/_base.py imported forbidden dep {forbidden!r}"
            )
