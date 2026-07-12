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