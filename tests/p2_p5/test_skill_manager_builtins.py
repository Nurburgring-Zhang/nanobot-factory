#!/usr/bin/env python3
"""P21 P2 P5 — SkillManager wiring to 50 builtin specs (R2 N7 fix verification).

R2 audit (reports/p21_r2_audit_skill.md §N7) found that
``SkillManager`` in ``backend/skills/legacy.py`` only registered 5 hardcoded
``BaseSkill`` subclasses, completely ignoring the 50 ``SkillSpec`` metadata
objects in ``backend/skills_builtin.py::BUILTIN_SKILLS``.  The 50 builtin
specs were NEVER discoverable via ``get_all_skills()`` — a P0 registry gap.

This test verifies the fix:

  T1 — :data:`backend.skills_builtin.BUILTIN_SKILLS` still has exactly 50
        entries (no regression in the source list).
  T2 — :func:`backend.skills.get_skill_manager` returns a singleton (existing
        contract preserved).
  T3 — :meth:`SkillManager.get_all_skills` now returns >= 55 entries
        (5 real + 50 metadata_only).  Was 5 before the fix.
  T4 — The 5 original real skills are still present (backward compat).
  T5 — 5 spot-checked builtin IDs from each of 5 different categories are
        present in the registry (was always 0/5 before the fix).
  T6 — Every builtin entry has ``type='metadata_only'`` and
        ``metadata_only=True``; every real entry has ``type='real'`` and NO
        ``metadata_only`` key.
  T7 — Every builtin entry exposes the full SkillSpec shape (id, name,
        description, category, enabled, version, trigger_phrases, inputs,
        outputs, dependencies).
  T8 — The 50 builtin IDs are unique (no duplicates from the 11-category
        aggregation).
  T9 — :meth:`SkillManager.get_real_skills` returns exactly 5 entries; all
        ``type='real'``.
  T10 — :meth:`SkillManager.get_builtin_skill_specs` returns exactly 50
         entries; all ``type='metadata_only'``.
  T11 — :meth:`SkillManager.execute_skill` for a metadata-only builtin ID
         returns ``success=False`` with a structured error mentioning
         ``metadata_only`` (not a generic "Skill不存在" message).
  T12 — :meth:`SkillManager.execute_skill` for a real skill still works
         end-to-end (backward compat).
  T13 — :meth:`SkillManager.execute_skill` for a totally unknown skill id
         returns ``success=False`` with the legacy "Skill不存在" message.
  T14 — Coverage matrix: the 11 category counts sum to 50 (catches accidental
         re-categorization).

Hard rules respected
--------------------
* 25-min budget; no new dependencies (the fix only uses existing modules
  ``backend.skills`` and ``backend.skills_builtin``).
* The 50 ``BUILTIN_SKILLS`` structure is unchanged — the fix is purely
  in ``SkillManager.get_all_skills()`` (and a small ``execute_skill``
  enhancement for better error messages).
* No regression in the 5 real skills.

Run from the project root::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    $env:PYTHONPATH = "D:\\Hermes\\生产平台\\nanobot-factory"
    & D:\\ComfyUI\\.ext\\python.exe -m pytest tests/p2_p5/test_skill_manager_builtins.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — make ``backend.*`` importable when running this file alone.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory")
BACKEND_DIR = PROJECT_ROOT / "backend"

for p in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Mirror the global test env so backend imports that read env at import time
# do not fail.
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "x" * 64)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 5 spot-check IDs from 5 different categories, so we exercise that the
# 11-category aggregation preserves all entries.
SPOT_CHECK_IDS = [
    "skill_crawl_web",      # category: crawl
    "skill_dedupe",         # category: process
    "skill_agent_chat",     # category: agent
    "skill_octo_bot_create",  # category: octo
    "skill_drama_script",   # category: drama
]


def _id_set(entries):
    return {e["id"] for e in entries}


# ===========================================================================
# T1 — BUILTIN_SKILLS has exactly 50 entries
# ===========================================================================

def test_builtin_skills_count_is_50():
    """The 50-spec source list is unchanged."""
    from backend.skills_builtin import BUILTIN_SKILLS
    assert len(BUILTIN_SKILLS) == 50, (
        f"expected 50 builtin skills, got {len(BUILTIN_SKILLS)}"
    )


def test_builtin_skills_all_have_skill_spec_shape():
    """Every builtin entry is a ``SkillSpec`` instance with the canonical fields."""
    from backend.skills import SkillSpec
    from backend.skills_builtin import BUILTIN_SKILLS

    for spec in BUILTIN_SKILLS:
        assert isinstance(spec, SkillSpec), f"{spec!r} is not a SkillSpec"
        # Required fields
        assert spec.id and isinstance(spec.id, str)
        assert spec.name and isinstance(spec.name, str)
        assert spec.category and isinstance(spec.category, str)
        assert isinstance(spec.trigger_phrases, list)
        assert isinstance(spec.inputs, dict)
        assert isinstance(spec.outputs, dict)
        # enabled default True
        assert spec.enabled is True
        # version string
        assert isinstance(spec.version, str) and spec.version


# ===========================================================================
# T2 — get_skill_manager() is a singleton
# ===========================================================================

def test_get_skill_manager_is_singleton():
    from backend.skills import get_skill_manager
    m1 = get_skill_manager()
    m2 = get_skill_manager()
    assert m1 is m2, "get_skill_manager() must return the same instance"


# ===========================================================================
# T3 — get_all_skills() now returns >= 55 (the actual fix)
# ===========================================================================

def test_get_all_skills_returns_at_least_55():
    """Was 5 before the fix; should be 5+50=55 after."""
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    all_skills = m.get_all_skills()
    assert len(all_skills) >= 55, (
        f"expected >= 55 (5 real + 50 builtin), got {len(all_skills)}"
    )
    # Exact: 5 real + 50 metadata-only
    real_count = sum(1 for s in all_skills if s.get("type") == "real")
    meta_count = sum(1 for s in all_skills if s.get("type") == "metadata_only")
    assert real_count == 5, f"expected 5 real skills, got {real_count}"
    assert meta_count == 50, f"expected 50 metadata_only skills, got {meta_count}"


# ===========================================================================
# T4 — The 5 original real skills are still present (backward compat)
# ===========================================================================

def test_real_skills_backward_compat():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    ids = _id_set(m.get_all_skills())
    for real_id in (
        "prompt_optimizer",
        "prompt_generator",
        "batch_production",
        "media_production",
        "data_analysis",
    ):
        assert real_id in ids, f"real skill {real_id!r} missing from registry"


def test_real_skills_have_type_real():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    for s in m.get_all_skills():
        if s["id"] in {
            "prompt_optimizer", "prompt_generator", "batch_production",
            "media_production", "data_analysis",
        }:
            assert s["type"] == "real", f"{s['id']!r} should be type='real'"
            assert "metadata_only" not in s, (
                f"real skill {s['id']!r} should NOT have metadata_only key"
            )


# ===========================================================================
# T5 — 5 spot-checked builtin IDs from 5 different categories
# ===========================================================================

@pytest.mark.parametrize("builtin_id", SPOT_CHECK_IDS)
def test_builtin_id_present(builtin_id):
    """Each spot-check builtin ID is now in the registry (was missing before)."""
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    ids = _id_set(m.get_all_skills())
    assert builtin_id in ids, (
        f"builtin {builtin_id!r} missing from SkillManager registry"
    )


# ===========================================================================
# T6 — Schema: real vs metadata_only flags
# ===========================================================================

def test_metadata_only_entries_have_correct_flags():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    for s in m.get_all_skills():
        if s.get("type") == "metadata_only":
            assert s.get("metadata_only") is True, (
                f"metadata_only entry {s['id']!r} should set metadata_only=True"
            )
            assert s["type"] == "metadata_only"
        elif s.get("type") == "real":
            assert "metadata_only" not in s, (
                f"real entry {s['id']!r} should not have metadata_only field"
            )


# ===========================================================================
# T7 — Every builtin entry has the full SkillSpec shape
# ===========================================================================

def test_metadata_only_entries_have_full_skill_spec_shape():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    for s in m.get_all_skills():
        if s.get("type") != "metadata_only":
            continue
        # Required spec fields
        for key in (
            "id", "name", "description", "category", "enabled", "version",
            "trigger_phrases", "inputs", "outputs", "dependencies",
        ):
            assert key in s, f"metadata_only {s.get('id')!r} missing {key!r}"
        # Types
        assert isinstance(s["trigger_phrases"], list)
        assert isinstance(s["inputs"], dict)
        assert isinstance(s["outputs"], dict)
        assert isinstance(s["dependencies"], list)
        assert isinstance(s["enabled"], bool)
        assert isinstance(s["version"], str)


# ===========================================================================
# T8 — All 50 builtin IDs are unique
# ===========================================================================

def test_builtin_ids_are_unique():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    builtin = m.get_builtin_skill_specs()
    ids = [s["id"] for s in builtin]
    assert len(ids) == len(set(ids)), (
        f"duplicate builtin ids: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )
    assert len(ids) == 50


# ===========================================================================
# T9 — get_real_skills() helper
# ===========================================================================

def test_get_real_skills_returns_5():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    real = m.get_real_skills()
    assert len(real) == 5
    assert all(s["type"] == "real" for s in real)


# ===========================================================================
# T10 — get_builtin_skill_specs() helper
# ===========================================================================

def test_get_builtin_skill_specs_returns_50():
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    builtin = m.get_builtin_skill_specs()
    assert len(builtin) == 50
    assert all(s["type"] == "metadata_only" for s in builtin)
    assert all(s.get("metadata_only") is True for s in builtin)


# ===========================================================================
# T11 — execute_skill for metadata-only returns structured error
# ===========================================================================

def test_execute_skill_metadata_only_returns_structured_error():
    from backend.skills import get_skill_manager, SkillInput
    m = get_skill_manager()
    out = asyncio.run(
        m.execute_skill("skill_crawl_web", SkillInput(prompt="test"))
    )
    assert out.success is False
    assert "metadata-only" in out.error.lower(), (
        f"error should mention 'metadata-only'; got: {out.error!r}"
    )
    # Structured metadata flag (helps callers / UI render correctly)
    assert out.metadata.get("type") == "metadata_only"
    assert out.metadata.get("skill_id") == "skill_crawl_web"


# ===========================================================================
# T12 — Real skill still executes end-to-end
# ===========================================================================

def test_execute_skill_real_skill_still_works():
    from backend.skills import get_skill_manager, SkillInput
    m = get_skill_manager()
    out = asyncio.run(
        m.execute_skill(
            "prompt_optimizer",
            SkillInput(prompt="a cat", params={"style": "cinematic"}),
        )
    )
    assert out.success is True, f"real skill failed: {out.error}"
    assert out.result is not None
    assert "optimized" in out.result


# ===========================================================================
# T13 — Unknown skill still returns legacy "Skill不存在" error
# ===========================================================================

def test_execute_skill_unknown_returns_legacy_error():
    from backend.skills import get_skill_manager, SkillInput
    m = get_skill_manager()
    out = asyncio.run(
        m.execute_skill("nonexistent_skill_xyz", SkillInput(prompt="x"))
    )
    assert out.success is False
    assert "Skill不存在" in out.error


# ===========================================================================
# T14 — Coverage matrix: 11 category counts sum to 50
# ===========================================================================

def test_builtin_category_coverage_matrix():
    """Lock the 11-category structure so accidental re-categorization fails the test."""
    from backend.skills import get_skill_manager
    m = get_skill_manager()
    builtin = m.get_builtin_skill_specs()

    counts: dict = {}
    for s in builtin:
        counts[s["category"]] = counts.get(s["category"], 0) + 1

    # Per skills_builtin.py header: 11 categories
    expected = {
        "crawl": 10,
        "process": 5,
        "agent": 8,
        "octo": 4,
        "vida": 2,
        "meta_kim": 3,
        "drama": 5,
        "comfy": 3,
        "redfox": 3,
        "reach": 4,
        "agency": 3,
    }
    assert counts == expected, (
        f"category count drift: expected {expected}, got {counts}"
    )
    assert sum(expected.values()) == 50


# ===========================================================================
# T15 — Regression guard: no new dependencies
# ===========================================================================

def test_no_new_dependencies_in_modified_files():
    """The fix only uses stdlib + the existing 2 modules."""
    legacy_path = BACKEND_DIR / "skills" / "legacy.py"
    src = legacy_path.read_text(encoding="utf-8")
    # The only new import the fix introduces is the lazy ``from backend.skills_builtin``
    # inside ``get_all_skills``.  No third-party deps added.
    forbidden = ("import requests", "import httpx", "import aiohttp",
                 "import sqlalchemy", "import fastapi", "import pydantic",
                 "import numpy", "import pandas")
    for needle in forbidden:
        assert needle not in src, (
            f"forbidden new dependency {needle!r} in legacy.py"
        )
    # And no ``pip install``-like patterns
    assert "pip install" not in src
