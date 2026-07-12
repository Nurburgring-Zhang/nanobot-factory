"""Pytest bootstrap for ``backend.imdf.skills.synth``.

Strategy:
1. Add both ``backend/`` and ``backend/imdf/`` to sys.path so:
   - ``import backend.skills`` works (for SkillInput/SkillOutput dataclass)
   - ``import imdf.creative.redfox.skills`` works (transitively needed by parent __init__)
2. Install a stub for ``backend.imdf.skills`` (the heavy registry __init__.py
   that imports ``imdf.creative.redfox.skills``); if upstream fails or if
   we want to skip the heavy parent, the stub provides ``__path__`` so
   sub-imports resolve.
3. Set ``SYNTH_OFFLINE=1`` so the skills use deterministic mocks (no
   network attempts).

Notes
-----
- Tests import via ``from imdf.skills.synth.<x> import <fn>`` (NOT
  ``from backend.imdf.skills.synth``) to avoid the broken
  ``backend/imdf/skills/__init__.py`` chain.
- The synth subpackage is ``backend/imdf/skills/synth/``.  When ``backend/imdf/``
  is on sys.path, the module name ``imdf.skills.synth`` resolves to that
  directory — same files, just imported via the ``imdf`` alias.
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
    """Put both ``backend/`` and ``backend/imdf/`` on sys.path.

    - ``backend/`` lets ``from backend.skills import SkillInput`` resolve.
    - ``backend/imdf/`` lets ``from imdf.skills.synth...`` resolve and also
      makes the heavy ``backend.imdf.skills.__init__`` chain (which imports
      ``imdf.creative.redfox.skills``) succeed if upstream is intact.
    """
    here = pathlib.Path(__file__).resolve()
    # conftest.py -> __tests__/ -> synth/ -> skills/ -> imdf/ -> backend/ -> project_root/
    backend_dir = here.parents[3]      # backend/
    imdf_dir = here.parents[2]         # backend/imdf/
    project_root = here.parents[4]     # nanobot-factory/

    for path in (project_root, backend_dir, imdf_dir):
        sp = str(path)
        if sp in sys.path:
            sys.path.remove(sp)
        sys.path.insert(0, sp)


def _install_imdf_skills_stub() -> None:
    """If ``backend.imdf.skills`` import fails, install a stub with __path__.

    The synth sub-package lives under ``backend/imdf/skills/synth/``.
    By giving the stub a ``__path__`` that points at
    ``backend/imdf/skills/``, sub-imports like ``backend.imdf.skills.synth``
    resolve correctly even when the real parent package can't be loaded.
    """
    try:
        __import__(_UPSTREAM_BACKEND)
        return  # upstream loaded cleanly, nothing to do
    except Exception:
        pass

    here = pathlib.Path(__file__).resolve()
    backend_skills_dir = here.parents[2] / "skills"  # backend/imdf/skills/
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
os.environ.setdefault("SYNTH_OFFLINE", "1")
os.environ.setdefault("IMDF_TEST_MODE", "1")