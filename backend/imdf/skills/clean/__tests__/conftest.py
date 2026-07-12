"""Pytest bootstrap for backend.imdf.skills.clean.

Mirrors synth/__tests__/conftest.py strategy plus an extra fallback for
``backend.skills`` (which the project's broken parent import chain can
make hard to reach in this checkout).

1. Add backend/ and backend/imdf/ to sys.path so
   from imdf.skills.clean.X import fn resolves directly.
2. Install a stub for backend.imdf.skills (registry __init__ broken
   in this checkout) so sub-imports resolve to real files on disk.
3. Default test environment to offline mode.
"""
from __future__ import annotations

import os
import pathlib
import sys
import types


def _ensure_paths() -> None:
    here = pathlib.Path(__file__).resolve()
    backend_dir = here.parents[3]
    imdf_dir = here.parents[2]
    project_root = here.parents[4]
    for path in (project_root, backend_dir, imdf_dir):
        sp = str(path)
        if sp in sys.path:
            sys.path.remove(sp)
        sys.path.insert(0, sp)


def _install_imdf_skills_stub() -> None:
    upstream = "backend.imdf.skills"
    try:
        __import__(upstream)
        return
    except Exception:
        pass
    here = pathlib.Path(__file__).resolve()
    backend_skills_dir = here.parents[2] / "skills"
    if not backend_skills_dir.exists():
        return
    stub = types.ModuleType(upstream)
    stub.__path__ = [str(backend_skills_dir)]
    stub.__all__ = []
    sys.modules.setdefault(upstream, stub)


def _ensure_backend_skills_alias() -> None:
    """Ensure ``backend.skills`` is importable with SkillInput/SkillOutput/SkillSpec.

    When the real ``backend/skills/__init__.py`` (small, exports SkillSpec)
    is reachable via sys.path, prefer it.  Otherwise install a shim that
    exports the dataclass contracts + a minimal SkillSpec.
    """
    # Try the real one first.
    real_path = pathlib.Path(__file__).resolve().parents[3] / "skills"
    real_init = real_path / "__init__.py"
    if real_init.exists() and "backend.skills" not in sys.modules:
        try:
            __import__("backend.skills")
            return
        except Exception:
            pass

    # Fallback — install a stub.
    from dataclasses import dataclass, field as _field
    from typing import Any as _Any, Dict as _Dict, List as _List

    @dataclass
    class _SkillInput:
        prompt: str = ""
        params: _Dict[str, _Any] = _field(default_factory=dict)
        context: _Dict[str, _Any] = _field(default_factory=dict)

    @dataclass
    class _SkillOutput:
        success: bool
        result: _Any = None
        error: str = ""
        metadata: _Dict[str, _Any] = _field(default_factory=dict)

    @dataclass
    class _SkillSpec:
        id: str
        name: str = ""
        category: str = ""
        trigger_phrases: _List[str] = _field(default_factory=list)
        inputs: _Dict[str, _Any] = _field(default_factory=dict)
        outputs: _Dict[str, _Any] = _field(default_factory=dict)
        description: str = ""
        enabled: bool = True
        version: str = "1.0.0"
        dependencies: _List[str] = _field(default_factory=list)

    stub = types.ModuleType("backend.skills")
    stub.SkillInput = _SkillInput
    stub.SkillOutput = _SkillOutput
    stub.SkillSpec = _SkillSpec
    sys.modules["backend.skills"] = stub


_ensure_paths()
_install_imdf_skills_stub()
_ensure_backend_skills_alias()

os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CLEAN_OFFLINE", "1")

