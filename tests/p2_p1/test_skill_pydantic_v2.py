"""P21 P2 P1 — R2 §N1 fix verification test.

Tests that all 16 skill modules (8 clean + 8 label) affected by the
Pydantic v2 + ``from __future__ import annotations`` issue now:

  1. Import cleanly (no ImportError).
  2. Have a working ``*Input`` Pydantic model that accepts the minimal
     valid payload without raising ``PydanticUserError``.
  3. Have a working ``*Output`` Pydantic model (clean skills) that can
     be instantiated with default values without raising
     ``PydanticUserError``.
  4. Run end-to-end via ``asyncio.run(skill_fn(SkillInput(params=...)))``
     and return a ``SkillOutput`` (no PydanticUserError, no
     ModuleNotFoundError from the broken ``backend.imdf.skills.__init__``).

The 16 skills under test (per R2 audit, ``reports/p21_r2_audit_skill.md`` §N1):

  Clean (8):
    clean_dedupe_embed, clean_dedupe_hash, clean_face_blur,
    clean_html_strip, clean_json_validate, clean_nsfw_detect,
    clean_pii_remove, clean_plate_blur

  Label (8):
    label_clip_multi, label_clip_zero, label_entity_ner,
    label_glm4v, label_gpt4v_label, label_llava_chat,
    label_sam_segment, label_yolo_detect

Run with:
    cd D:\\Hermes\\生产平台\\nanobot-factory
    $env:PYTHONPATH = "D:\\Hermes\\生产平台\\nanobot-factory"
    & D:\\ComfyUI\\.ext\\python.exe -m pytest tests/p2_p1/test_skill_pydantic_v2.py -v
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — bypass the broken ``backend.imdf.skills.__init__`` chain.
# ---------------------------------------------------------------------------
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CLEAN_OFFLINE", "1")
os.environ.setdefault("LABEL_OFFLINE", "1")
os.environ.setdefault("PYTHONHASHSEED", "0")

PROJECT_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory")
BACKEND = PROJECT_ROOT / "backend"
IMDF_SKILLS = BACKEND / "imdf" / "skills"
CLEAN_DIR = IMDF_SKILLS / "clean"
LABEL_DIR = IMDF_SKILLS / "label"


def _ensure_paths() -> None:
    for p in (str(PROJECT_ROOT), str(BACKEND), str(IMDF_SKILLS),
              str(CLEAN_DIR), str(LABEL_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _install_stubs() -> None:
    """Stub the broken ``backend.imdf.skills`` parent package so that
    ``from backend.imdf.skills.clean.X import …`` resolves to our real
    files on disk without ever executing the broken
    ``backend.imdf.skills.__init__``.
    """
    if "backend" not in sys.modules:
        m = types.ModuleType("backend")
        m.__path__ = [str(BACKEND)]
        sys.modules["backend"] = m
    if "backend.imdf" not in sys.modules:
        m = types.ModuleType("backend.imdf")
        m.__path__ = [str(BACKEND / "imdf")]
        sys.modules["backend.imdf"] = m
    if "backend.imdf.skills" not in sys.modules:
        m = types.ModuleType("backend.imdf.skills")
        m.__path__ = [str(IMDF_SKILLS)]
        sys.modules["backend.imdf.skills"] = m


_ensure_paths()
_install_stubs()

# Real SkillInput / SkillOutput from backend.skills.legacy
from backend.skills.legacy import SkillInput, SkillOutput  # noqa: E402

from pydantic import BaseModel  # noqa: E402
from pydantic import PydanticUserError  # noqa: E402


# ---------------------------------------------------------------------------
# Module loader — same shape as backend.imdf.skills.clean.__tests__._bootstrap
# ---------------------------------------------------------------------------
def _load_skill_module(skills_dir: Path, skill_name: str, subpkg: str):
    """Load ``{subpkg}/{skill_name}.py`` as a standalone module.

    Sets ``__package__`` so the module's relative imports
    (``from ._base import …``) resolve correctly.
    """
    pkg_name = f"backend.imdf.skills.{subpkg}"
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [str(skills_dir)]
        m.__file__ = str(skills_dir / "__init__.py")
        sys.modules[pkg_name] = m
    base_name = f"{pkg_name}._base"
    if base_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            base_name, str(skills_dir / "_base.py"))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = pkg_name
        sys.modules[base_name] = mod
        spec.loader.exec_module(mod)

    full_name = f"{pkg_name}.{skill_name}"
    path = skills_dir / f"{skill_name}.py"
    spec = importlib.util.spec_from_file_location(full_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg_name
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Per-skill test definitions
#
# Each entry: (subpkg, skill_name, callable_name, InputModel, OutputModel,
#              minimal_params for the skill function)
#
# The ``minimal_params`` are the absolute minimum valid input the skill's
# ``*Input`` model accepts.  All 16 modules are affected by R2-N1.
# ---------------------------------------------------------------------------
# A URL we use to satisfy image-based skills — must NOT be a private IP
# to keep any SSRF guard happy (skills use safe_httpx_call which falls
# back to offline mock anyway in CI).
_TEST_URL = "https://example.com/test.jpg"


CLEAN_SKILLS = [
    # subpkg, skill_fn, minimal_params
    ("clean", "clean_dedupe_embed", {"items": ["a", "b", "c"]}),
    ("clean", "clean_dedupe_hash", {"image_url": _TEST_URL}),
    ("clean", "clean_face_blur",   {"image_url": _TEST_URL}),
    ("clean", "clean_html_strip",  {"html": "<p>hello <b>world</b></p>"}),
    ("clean", "clean_json_validate", {"document": {"a": 1}, "schema": {}}),
    ("clean", "clean_nsfw_detect", {"image_url": _TEST_URL}),
    ("clean", "clean_pii_remove",  {"text": "email me at test@example.com please"}),
    ("clean", "clean_plate_blur",  {"image_url": _TEST_URL}),
]

LABEL_SKILLS = [
    # subpkg, skill_fn, minimal_params
    ("label", "label_clip_multi",   {"image": _TEST_URL,
                                     "candidates": ["cat", "dog", "bird"]}),
    ("label", "label_clip_zero",    {"image": _TEST_URL,
                                     "candidates": ["cat", "dog", "bird"]}),
    ("label", "label_entity_ner",   {"text": "Apple Inc. was founded in 1976."}),
    ("label", "label_glm4v",        {"image": _TEST_URL,
                                     "task": "caption",
                                     "prompt": "describe the image"}),
    ("label", "label_gpt4v_label",  {"image": _TEST_URL}),
    ("label", "label_llava_chat",   {"turns": [{"role": "user",
                                                "content": "hi",
                                                "image": _TEST_URL}]}),
    ("label", "label_sam_segment",  {"image": _TEST_URL, "mode": "auto"}),
    ("label", "label_yolo_detect",  {"image": _TEST_URL}),
]

ALL_SKILLS = CLEAN_SKILLS + LABEL_SKILLS
assert len(ALL_SKILLS) == 16, f"expected 16 skills, got {len(ALL_SKILLS)}"


# ---------------------------------------------------------------------------
# Helper — locate the *Input / *Output Pydantic classes on a module.
# ---------------------------------------------------------------------------
def _find_pydantic_models(module, base_name_hint: str):
    """Find the *Input and (if present) *Output BaseModel subclasses.

    We pick the first two BaseModel subclasses in the module; or pick the
    one whose class name contains the hint (e.g. "Nsfw" for clean_nsfw_detect).
    """
    models = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            models.append((attr_name, obj))
    return models


# ---------------------------------------------------------------------------
# pytest tests
# ---------------------------------------------------------------------------
def test_fix_removed_future_annotations():
    """The 16 target files must no longer contain ``from __future__ import annotations``.

    This is the actual surgical fix — a future-annotations-free module
    avoids the Pydantic v2 forward-ref pitfall and is the recommended
    remediation per the R2 audit.
    """
    targets = [
        CLEAN_DIR / "clean_dedupe_embed.py",
        CLEAN_DIR / "clean_dedupe_hash.py",
        CLEAN_DIR / "clean_face_blur.py",
        CLEAN_DIR / "clean_html_strip.py",
        CLEAN_DIR / "clean_json_validate.py",
        CLEAN_DIR / "clean_nsfw_detect.py",
        CLEAN_DIR / "clean_pii_remove.py",
        CLEAN_DIR / "clean_plate_blur.py",
        LABEL_DIR / "label_clip_multi.py",
        LABEL_DIR / "label_clip_zero.py",
        LABEL_DIR / "label_entity_ner.py",
        LABEL_DIR / "label_glm4v.py",
        LABEL_DIR / "label_gpt4v_label.py",
        LABEL_DIR / "label_llava_chat.py",
        LABEL_DIR / "label_sam_segment.py",
        LABEL_DIR / "label_yolo_detect.py",
    ]
    leaked = []
    for p in targets:
        text = p.read_text(encoding="utf-8")
        if "from __future__ import annotations" in text:
            leaked.append(str(p))
    assert not leaked, (
        f"the following files still have `from __future__ import annotations`: {leaked}"
    )


def test_all_16_skills_import_cleanly():
    """Every target module must import without ImportError."""
    for subpkg, skill_name, _ in ALL_SKILLS:
        skills_dir = CLEAN_DIR if subpkg == "clean" else LABEL_DIR
        try:
            mod = _load_skill_module(skills_dir, skill_name, subpkg)
        except Exception as exc:  # pragma: no cover
            raise AssertionError(
                f"failed to import {subpkg}/{skill_name}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        assert hasattr(mod, skill_name), (
            f"{subpkg}/{skill_name}.py has no `{skill_name}` function"
        )


def _instantiate_all_models(mod):
    """Find every Pydantic model on the module, instantiate each with no
    args; return list of (name, model, error_str_or_None)."""
    results = []
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
            continue
        if obj is BaseModel:
            continue
        try:
            inst = obj()
            results.append((attr_name, inst, None))
        except Exception as exc:
            results.append((attr_name, None, f"{type(exc).__name__}: {exc}"))
    return results


def test_clean_skill_models_instantiate_without_pydantic_user_error():
    """Every clean/* model must default-construct without PydanticUserError."""
    for subpkg, skill_name, _ in CLEAN_SKILLS:
        mod = _load_skill_module(CLEAN_DIR, skill_name, subpkg)
        results = _instantiate_all_models(mod)
        assert results, f"{subpkg}/{skill_name} exposes no Pydantic models"
        for name, inst, err in results:
            if err is not None:
                # ValidationError is OK if a field is required with no
                # default — the *Output* classes all have defaults.  We
                # only fail hard on PydanticUserError (the R2-N1 issue).
                # Required-Input errors are caught separately by the
                # per-skill test below.
                if "PydanticUserError" in err:
                    raise AssertionError(
                        f"{subpkg}/{skill_name}.{name} raised "
                        f"PydanticUserError on default-construct: {err}"
                    )
            else:
                # Successfully constructed — verify model_dump works too
                # (this is the second Pydantic-v2 forward-ref surface).
                try:
                    inst.model_dump()
                except PydanticUserError as exc:  # pragma: no cover
                    raise AssertionError(
                        f"{subpkg}/{skill_name}.{name}.model_dump() "
                        f"raised PydanticUserError: {exc}"
                    ) from exc


def test_label_skill_models_instantiate_without_pydantic_user_error():
    """Every label/* model must default-construct without PydanticUserError.

    Note: most label skills only define *Input models, and several of
    those inputs have required fields with no default.  We therefore
    only assert that *no PydanticUserError* is raised on construction;
    ValidationError for required fields is acceptable and caught in
    the per-skill call test below.
    """
    for subpkg, skill_name, _ in LABEL_SKILLS:
        mod = _load_skill_module(LABEL_DIR, skill_name, subpkg)
        results = _instantiate_all_models(mod)
        assert results, f"{subpkg}/{skill_name} exposes no Pydantic models"
        for name, _inst, err in results:
            if err is not None and "PydanticUserError" in err:
                raise AssertionError(
                    f"{subpkg}/{skill_name}.{name} raised "
                    f"PydanticUserError: {err}"
                )


def _run_skill(subpkg: str, skill_name: str, params: dict):
    """Run a single skill end-to-end and return its SkillOutput."""
    skills_dir = CLEAN_DIR if subpkg == "clean" else LABEL_DIR
    mod = _load_skill_module(skills_dir, skill_name, subpkg)
    fn = getattr(mod, skill_name)
    out = asyncio.run(fn(SkillInput(params=params)))
    return out


def test_clean_skill_functions_run_end_to_end():
    """All 8 clean skill functions must execute and return SkillOutput."""
    for subpkg, skill_name, params in CLEAN_SKILLS:
        try:
            out = _run_skill(subpkg, skill_name, params)
        except PydanticUserError as exc:
            raise AssertionError(
                f"{subpkg}/{skill_name} raised PydanticUserError: {exc}"
            ) from exc
        except Exception as exc:
            raise AssertionError(
                f"{subpkg}/{skill_name} raised "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        assert isinstance(out, SkillOutput), (
            f"{subpkg}/{skill_name} returned {type(out).__name__}, "
            f"expected SkillOutput"
        )
        assert out.success is True, (
            f"{subpkg}/{skill_name} returned success=False: {out.error}"
        )
        assert out.result is not None, (
            f"{subpkg}/{skill_name} returned None result"
        )


def test_label_skill_functions_run_end_to_end():
    """All 8 label skill functions must execute and return SkillOutput."""
    for subpkg, skill_name, params in LABEL_SKILLS:
        try:
            out = _run_skill(subpkg, skill_name, params)
        except PydanticUserError as exc:
            raise AssertionError(
                f"{subpkg}/{skill_name} raised PydanticUserError: {exc}"
            ) from exc
        except Exception as exc:
            raise AssertionError(
                f"{subpkg}/{skill_name} raised "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        assert isinstance(out, SkillOutput), (
            f"{subpkg}/{skill_name} returned {type(out).__name__}, "
            f"expected SkillOutput"
        )
        assert out.success is True, (
            f"{subpkg}/{skill_name} returned success=False: {out.error}"
        )
        assert out.result is not None, (
            f"{subpkg}/{skill_name} returned None result"
        )


def test_no_future_annotations_in_clean_skills():
    """Sanity check — defensive: ALL clean/*.py files (not just the 8)
    should ideally not use ``from __future__ import annotations`` either
    once the project is on Python 3.11+.  This test is informational:
    it reports which files still have it, but does not fail the suite.

    The 8 N1-affected files MUST be clean (verified by
    ``test_fix_removed_future_annotations``)."""
    remaining = []
    for p in sorted(CLEAN_DIR.glob("*.py")):
        if "from __future__ import annotations" in p.read_text(encoding="utf-8"):
            remaining.append(str(p))
    # The N1 8 must be gone (other 10 may still have it — out of scope).
    n1_clean = [
        CLEAN_DIR / f"{n}.py" for n in
        ("clean_dedupe_embed", "clean_dedupe_hash", "clean_face_blur",
         "clean_html_strip", "clean_json_validate", "clean_nsfw_detect",
         "clean_pii_remove", "clean_plate_blur")
    ]
    leftover = [str(p) for p in n1_clean if p in [Path(r) for r in remaining]]
    assert not leftover, f"N1 clean skills still have future import: {leftover}"


def test_no_future_annotations_in_label_skills():
    """Same as above for the 8 N1 label files."""
    remaining = []
    for p in sorted(LABEL_DIR.glob("*.py")):
        if "from __future__ import annotations" in p.read_text(encoding="utf-8"):
            remaining.append(str(p))
    n1_label = [
        LABEL_DIR / f"{n}.py" for n in
        ("label_clip_multi", "label_clip_zero", "label_entity_ner",
         "label_glm4v", "label_gpt4v_label", "label_llava_chat",
         "label_sam_segment", "label_yolo_detect")
    ]
    leftover = [str(p) for p in n1_label if p in [Path(r) for r in remaining]]
    assert not leftover, f"N1 label skills still have future import: {leftover}"


# ---------------------------------------------------------------------------
# Self-test when invoked directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Run as plain script — exercise every assertion manually.
    failures = []
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:
                msg = f"FAIL  {name}: {type(exc).__name__}: {exc}"
                print(msg)
                failures.append(msg)
    print()
    print(f"Total: {sum(1 for n in globals() if n.startswith('test_') and callable(globals()[n]))} tests, "
          f"{len(failures)} failures")
    sys.exit(1 if failures else 0)
