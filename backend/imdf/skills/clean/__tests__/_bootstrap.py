from __future__ import annotations

"""Light-weight shim that loads clean/* modules directly from the
filesystem so tests don't have to trigger the broken
``backend.imdf.skills.__init__`` import chain.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

_CLEAN_DIR = Path(
    r"D:\Hermes\生产平台\nanobot-factory\backend\imdf\skills\clean"
).resolve()
_BACKEND_DIR = _CLEAN_DIR.parents[2]
_PROJECT_DIR = _BACKEND_DIR.parent

if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ── Skill contract shims (avoid triggering broken backend.imdf.skills) ──
class SkillInput:
    def __init__(self, params=None, prompt="", context=None):
        self.prompt = prompt or ""
        self.params = params or {}
        self.context = context or {}


class SkillOutput:
    def __init__(self, success, result=None, error="", metadata=None):
        self.success = bool(success)
        self.result = result
        self.error = error or ""
        self.metadata = metadata or {}


# Stub ``backend.skills`` so per-skill modules can import ``SkillInput,
# SkillOutput`` without needing the real package chain.  We install this
# *before* any clean/* file is loaded.
_backend_skills_stub = types.ModuleType("backend.skills")
_backend_skills_stub.SkillInput = SkillInput
_backend_skills_stub.SkillOutput = SkillOutput
sys.modules.setdefault("backend.skills", _backend_skills_stub)


# ── Stub the broken ``backend.imdf.skills`` parent package ─────────────
def _stub_parent() -> None:
    """Install stubs for ``backend``, ``backend.imdf``,
    ``backend.imdf.skills``, and a synthetic ``backend.imdf.skills.clean``
    package that points at the real directory.  Once these stubs are in
    place, ``import backend.imdf.skills.clean.X`` resolves to our real
    files on disk without ever executing the broken
    ``backend.imdf.skills.__init__``.
    """
    if "backend" not in sys.modules:
        m = types.ModuleType("backend")
        m.__path__ = [str(_BACKEND_DIR)]
        m.__file__ = str(_BACKEND_DIR / "__init__.py")
        sys.modules["backend"] = m
    if "backend.imdf" not in sys.modules:
        m = types.ModuleType("backend.imdf")
        m.__path__ = [str(_BACKEND_DIR / "imdf")]
        m.__file__ = str(_BACKEND_DIR / "imdf" / "__init__.py")
        sys.modules["backend.imdf"] = m
    if "backend.imdf.skills" not in sys.modules:
        m = types.ModuleType("backend.imdf.skills")
        m.__path__ = [str(_BACKEND_DIR / "imdf" / "skills")]
        sys.modules["backend.imdf.skills"] = m
    if "backend.imdf.skills.clean" not in sys.modules:
        m = types.ModuleType("backend.imdf.skills.clean")
        m.__path__ = [str(_CLEAN_DIR)]
        m.__file__ = str(_CLEAN_DIR / "__init__.py")
        sys.modules["backend.imdf.skills.clean"] = m
    if "backend.imdf.skills.clean._base" not in sys.modules:
        # Load _base once, directly from disk, so subsequent
        # ``from ._base import …`` resolves to the same module object.
        spec = importlib.util.spec_from_file_location(
            "backend.imdf.skills.clean._base",
            str(_CLEAN_DIR / "_base.py"),
        )
        m = importlib.util.module_from_spec(spec)
        sys.modules["backend.imdf.skills.clean._base"] = m
        spec.loader.exec_module(m)


_stub_parent()


# ── Module loader ────────────────────────────────────────────────────────
def import_skill_module(name: str):
    """Load ``clean/<name>.py`` as a standalone module without going
    through the broken package's `__init__`.
    """
    path = _CLEAN_DIR / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(path)
    full_name = f"backend.imdf.skills.clean.{name}"
    spec = importlib.util.spec_from_file_location(full_name, str(path))
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "backend.imdf.skills.clean"  # enable relative imports
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def build_skill_input(params=None, prompt="") -> SkillInput:
    return SkillInput(params=params or {}, prompt=prompt)


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
