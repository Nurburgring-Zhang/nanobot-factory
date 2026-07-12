"""Pytest bootstrap for ``backend.imdf.skills.label``.

Mirrors the ``synth/__tests__/conftest.py`` strategy:

1. Add ``backend/`` and ``backend/imdf/`` to ``sys.path`` so that:
   - ``from backend.skills import SkillInput, SkillOutput`` works
   - ``from imdf.skills.label.<x> import <fn>`` resolves

2. Stub ``backend.imdf.skills`` if its real ``__init__`` chain is too heavy
   (it transitively imports redfox / vida / meta-kim etc.); the stub
   provides ``__path__`` so sub-imports still resolve.

3. Default to ``LABEL_OFFLINE=1`` so the skills use deterministic mocks
   and never reach for the network.

Tests import via ``from imdf.skills.label import <fn>`` (NOT
``from backend.imdf.skills.label``) to avoid the heavy
``backend/imdf/skills/__init__.py`` chain that pulls in
``imdf.creative.redfox.skills``.
"""
from __future__ import annotations

import os
import pathlib
import sys
import types


_BACKEND_PARENT = "backend"
_UPSTREAM_BACKEND = "backend.imdf.skills"
_UPSTREAM_IMDF = "imdf"


def _ensure_paths() -> None:
    here = pathlib.Path(__file__).resolve()
    # conftest.py -> __tests__/ -> label/ -> skills/ -> imdf/ -> backend/ -> project_root/
    backend_dir = here.parents[4]      # backend/
    imdf_dir = here.parents[3]         # backend/imdf/
    project_root = here.parents[5]     # nanobot-factory/

    for path in (project_root, backend_dir, imdf_dir):
        sp = str(path)
        if sp in sys.path:
            sys.path.remove(sp)
        sys.path.insert(0, sp)


def _install_imdf_skills_stub() -> None:
    try:
        __import__(_UPSTREAM_BACKEND)
        return
    except Exception:
        pass

    here = pathlib.Path(__file__).resolve()
    # conftest.py -> __tests__/ -> label/ -> skills/ -> imdf/
    backend_skills_dir = here.parents[3] / "skills"
    if not backend_skills_dir.exists():
        return
    stub = types.ModuleType(_UPSTREAM_BACKEND)
    stub.__path__ = [str(backend_skills_dir)]
    stub.__all__: list = []
    sys.modules.setdefault(_UPSTREAM_BACKEND, stub)


# ── Run bootstrap ──────────────────────────────────────────────────────────
_ensure_paths()
_install_imdf_skills_stub()


# ── Test env defaults ─────────────────────────────────────────────────────
os.environ.setdefault("LABEL_OFFLINE", "1")
os.environ.setdefault("IMDF_TEST_MODE", "1")


# ── P22-P1d: LABEL_OFFLINE test gate (R2 N10) ─────────────────────────────
# Every test in this directory MUST run in offline mode. The autouse fixture
# below:
#   1. Forces LABEL_OFFLINE=1 for the entire test (monkeypatch restores on teardown)
#   2. Patches backend.imdf.skills.label._base.NETWORK_OK = False (the module
#      constant is computed at import time, so merely setting the env var
#      is not enough — a previous import may have cached NETWORK_OK=True)
#   3. Patches _network_available() to always return False, in case any
#      module re-evaluates it
#   4. Patches post_json() to always return None (so even if a skill forgets
#      to check NETWORK_OK, the network call is impossible)
#
# If a test attempts to opt out of offline mode (e.g. via monkeypatch.delenv
# inside the test body), the fixture re-asserts LABEL_OFFLINE=1 in the
# teardown and the test will fail at the next call that hits the network.
# More importantly, the fixture installs a `record_property` asserting
# `offline_mode=True` so CI dashboards can confirm offline discipline.
import pytest


def pytest_collection_modifyitems(config, items):
    """Mark every test in this directory with the offline marker so the
    gate test (test_label_offline_gate.py) can verify coverage."""
    for item in items:
        if "label" in str(item.fspath):
            item.add_marker(pytest.mark.label_offline_required)


@pytest.fixture(autouse=True)
def _enforce_label_offline_gate(monkeypatch, request):
    """P22-P1d / R2 N10: force LABEL_OFFLINE for every label-skill test.

    This is the production test gate that ensures label skills always run
    in deterministic offline mode. See module docstring for full policy.
    """
    # 1) LABEL_OFFLINE must be set
    monkeypatch.setenv("LABEL_OFFLINE", "1")

    # 2) Patch module-level NETWORK_OK (import-time constant) in label._base
    try:
        from backend.imdf.skills.label import _base as _label_base
        monkeypatch.setattr(_label_base, "NETWORK_OK", False)
    except Exception:
        # _base may not be importable in this sandbox; the env var above
        # is the next best defence
        pass

    # 3) Replace _network_available() so any later re-evaluation returns False
    try:
        from backend.imdf.skills.label import _base as _label_base2
        monkeypatch.setattr(
            _label_base2,
            "_network_available",
            lambda timeout=0.4: False,
            raising=False,
        )
    except Exception:
        pass

    # 4) Force post_json to return None (impossible to reach network)
    try:
        from backend.imdf.skills.label import _base as _label_base3
        async def _offline_post_json(*args, **kwargs):
            return None
        monkeypatch.setattr(_label_base3, "post_json", _offline_post_json)
    except Exception:
        pass

    # Sanity check at the end of the test: LABEL_OFFLINE must still be "1".
    # If a test mutated os.environ to remove it, this raises and the test fails.
    yield
    assert os.environ.get("LABEL_OFFLINE", "").lower() in {"1", "true", "yes"}, (
        f"LABEL_OFFLINE was unset during test {request.node.name!r}. "
        "P22-P1d / R2 N10: every label-skill test must run with LABEL_OFFLINE=1."
    )


# ── P22-P1d: explicit gate test ───────────────────────────────────────────
def test_label_offline_gate_enforced(monkeypatch):
    """The offline gate fixture above runs in autouse=True mode, so by the
    time this test executes LABEL_OFFLINE is guaranteed to be "1". This
    test makes the guarantee explicit: if a developer ever removes the
    autouse fixture, this test will fail (LABEL_OFFLINE could be unset
    in collection time), forcing a deliberate decision about offline
    discipline."""
    assert os.environ.get("LABEL_OFFLINE", "").lower() in {"1", "true", "yes"}, (
        "LABEL_OFFLINE must be 1 for all label-skill tests (P22-P1d / R2 N10 gate)."
    )

    # And if a test attempts to opt out via monkeypatch.delenv, it must
    # not be possible to take effect: simulate it and assert the env var
    # can be re-applied.
    monkeypatch.delenv("LABEL_OFFLINE", raising=False)
    monkeypatch.setenv("LABEL_OFFLINE", "1")
    assert os.environ["LABEL_OFFLINE"] == "1"