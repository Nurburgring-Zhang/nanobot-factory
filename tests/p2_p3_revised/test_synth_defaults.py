"""P21 P2 P3 (revised) — synth skill required-field defaults.

R2 audit finding (N2): 7/17 synth skills have required fields with NO defaults,
causing ``ValidationError`` on ``params={}`` (or any call that doesn't pass the
exact expected key list).  This module verifies that for each of the 7 audit
fields, a default value is now present so the Input model can be validated with
the OTHER required fields only.

Coverage matrix
---------------

| # | File:line                       | Field            | Default | Input model             | Skill function       |
|---|---------------------------------|------------------|---------|-------------------------|----------------------|
| 1 | synth_back_translate.py         | ``rounds``       | 2       | BackTranslateInput      | back_translate       |
| 2 | synth_dialog_generate.py        | ``num_turns``    | 3       | DialogGenerateInput     | dialog_generate      |
| 3 | synth_qa_generate.py            | ``num_qa``       | 5       | QaGenerateInput         | qa_generate          |
| 4 | synth_seed_expand.py            | ``seed_words``   | 10 items| SeedExpandInput         | seed_expand          |
| 5 | synth_summary.py                | ``max_words``    | 50      | SummaryInput            | summary              |
| 6 | synth_video_caption.py          | ``fps_sample``   | 1       | VideoCaptionInput       | video_caption        |
| 7 | synth_video_temporal.py         | ``num_segments`` | 4       | VideoTemporalInput      | video_temporal       |

For each row the test:
  1. Asserts the audit field has a default (``Field(default=...)`` or factory)
  2. Asserts ``InputClass.model_validate(<minimal valid params>)`` succeeds
  3. Calls ``await <skill_fn>(SkillInput(params=<minimal valid params>))`` and
     asserts the function runs to completion (no ``ValidationError``) and
     returns a structured ``SkillOutput`` with ``success=True`` (mock data).

Test infrastructure
-------------------
This file lives at ``tests/p2_p3_revised/`` and is run via the project root
pytest.ini (``pythonpath = backend/imdf``).  The conftest at
``backend/imdf/skills/synth/__tests__/conftest.py`` is NOT auto-loaded (it
lives under a sibling path), so we re-do the same path injection here in a
defensive preamble (mirrors ``tests/p2_p2/test_provider_retry.py``).

Run from the project root with::

    pytest tests/p2_p3_revised/test_synth_defaults.py -v
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import pytest


# ── Path setup ──────────────────────────────────────────────────────────
_THIS = Path(__file__).resolve()
# tests/p2_p3_revised/test_synth_defaults.py → project root is parents[2]
_PROJECT_ROOT = _THIS.parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
_IMDF = _BACKEND / "imdf"

# Mirror the strategy from backend/imdf/skills/synth/__tests__/conftest.py
for p in (str(_PROJECT_ROOT), str(_BACKEND), str(_IMDF)):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

# Defence in depth — avoid the conftest hook rotating sys.path under us.
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("SYNTH_OFFLINE", "1")
os.environ.setdefault("JWT_SECRET", "x" * 64)


from pydantic_core import PydanticUndefined  # noqa: E402

from backend.skills import SkillInput, SkillOutput  # noqa: E402


# ── Coverage matrix ────────────────────────────────────────────────────
# Tuple: (module_dotted_path, attr_skill_fn, attr_input_cls, audit_field,
#         minimal_valid_params, expected_default)
# - module_dotted_path: import via the ``imdf`` alias (``backend/imdf`` on path)
# - minimal_valid_params: dict containing only the OTHER required fields;
#   the audit field is OMITTED so the test exercises the default path
# - expected_default: literal default value expected from ``Field(default=...)``
#   (``None`` is treated as "default is set, exact value is asserted separately")

_COVERAGE: List[Tuple[str, str, str, str, Dict[str, Any], Any]] = [
    # (module,                skill_fn,            input_cls,           field,         minimal_params,            expected_default)
    (
        "imdf.skills.synth.synth_summary",
        "summary",
        "SummaryInput",
        "max_words",
        {"text": "a long article about cats that needs summarization"},
        50,
    ),
    (
        "imdf.skills.synth.synth_back_translate",
        "back_translate",
        "BackTranslateInput",
        "rounds",
        {"text": "hello world"},
        2,
    ),
    (
        "imdf.skills.synth.synth_dialog_generate",
        "dialog_generate",
        "DialogGenerateInput",
        "num_turns",
        {"topic": "weather"},
        3,
    ),
    (
        "imdf.skills.synth.synth_qa_generate",
        "qa_generate",
        "QaGenerateInput",
        "num_qa",
        {"context": "a paragraph of facts"},
        5,
    ),
    (
        "imdf.skills.synth.synth_seed_expand",
        "seed_expand",
        "SeedExpandInput",
        "seed_words",
        {},  # all fields are optional now; the audit field is ``seed_words`` itself
        None,  # seed_words uses default_factory; assert it's a 10-item list below
    ),
    (
        "imdf.skills.synth.synth_video_caption",
        "video_caption",
        "VideoCaptionInput",
        "fps_sample",
        {"video_ref": "video://abc.mp4"},
        1,
    ),
    (
        "imdf.skills.synth.synth_video_temporal",
        "video_temporal",
        "VideoTemporalInput",
        "num_segments",
        {"video_ref": "video://abc.mp4"},
        4,
    ),
]

# Lock the matrix size — drift-proof: future workers who add a 8th audit row
# to _COVERAGE MUST update this assert (or vice-versa, remove the entry).
assert len(_COVERAGE) == 7, (
    f"_COVERAGE size changed (expected 7, got {len(_COVERAGE)}). "
    "If you added/removed a synth skill fix, update this assert."
)


# ── Helpers ────────────────────────────────────────────────────────────

def _load_module_attr(module_path: str, attr: str):
    """Import module_path and return ``getattr(module, attr)`` (function or class)."""
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


# ── Test 1: each audit field has a default ────────────────────────────

@pytest.mark.parametrize(
    "module_path,skill_fn,input_cls,field,minimal_params,expected_default",
    _COVERAGE,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_audit_field_has_default(
    module_path: str,
    skill_fn: str,
    input_cls: str,
    field: str,
    minimal_params: Dict[str, Any],
    expected_default: Any,
):
    """The audit field is no longer required — verify a default is set.

    For ``Field(default=N)`` the default is the integer N.
    For ``Field(default_factory=...)`` (e.g. ``seed_words``) the default is
    ``PydanticUndefined`` but the factory is callable; the factory result is
    asserted in :func:`test_default_factory_runs`.
    """
    cls = _load_module_attr(module_path, input_cls)
    field_info = cls.model_fields[field]
    has_default = field_info.default is not PydanticUndefined
    has_factory = field_info.default_factory is not None
    assert has_default or has_factory, (
        f"{input_cls}.{field} has no default and no default_factory; "
        "the audit finding N2 is NOT closed for this row."
    )

    # If we expect a literal default (Field(default=N)), verify it matches.
    if expected_default is not None:
        assert has_default, (
            f"{input_cls}.{field} uses default_factory, but a literal "
            f"default of {expected_default!r} was expected."
        )
        assert field_info.default == expected_default, (
            f"{input_cls}.{field} default is {field_info.default!r}, "
            f"expected {expected_default!r}"
        )


# ── Test 2: each Input model validates with minimal params ────────────

@pytest.mark.parametrize(
    "module_path,skill_fn,input_cls,field,minimal_params,expected_default",
    _COVERAGE,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_input_model_validates_with_minimal_params(
    module_path: str,
    skill_fn: str,
    input_cls: str,
    field: str,
    minimal_params: Dict[str, Any],
    expected_default: Any,
):
    """``InputClass.model_validate(<minimal params>)`` succeeds — no ValidationError."""
    cls = _load_module_attr(module_path, input_cls)
    # The whole point of the fix: this should NOT raise.
    instance = cls.model_validate(minimal_params)
    assert isinstance(instance, cls)


# ── Test 3: each skill function runs end-to-end with minimal params ───

@pytest.mark.parametrize(
    "module_path,skill_fn,input_cls,field,minimal_params,expected_default",
    _COVERAGE,
    ids=lambda v: v if isinstance(v, str) else "",
)
@pytest.mark.asyncio
async def test_skill_runs_with_minimal_params(
    module_path: str,
    skill_fn: str,
    input_cls: str,
    field: str,
    minimal_params: Dict[str, Any],
    expected_default: Any,
):
    """``await <skill_fn>(SkillInput(params=...))`` returns a structured SkillOutput.

    The function must not raise (the audit's whole claim is that it used to
    raise ``ValidationError`` on default params).  We assert the function runs
    to completion and returns a ``SkillOutput`` with ``success=True`` (mock
    data path) — that is the post-fix contract.
    """
    fn = _load_module_attr(module_path, skill_fn)
    out = await fn(SkillInput(prompt="test", params=minimal_params))
    assert isinstance(out, SkillOutput)
    assert out.success is True, (
        f"{skill_fn} returned success=False with error={out.error!r}; "
        "the function must accept the minimal params and run to mock-fallback."
    )
    assert out.error == "", f"unexpected error: {out.error!r}"
    assert isinstance(out.result, dict), f"result should be a dict, got {type(out.result)}"
    # Source can be 'live' or 'mock' depending on network; both are valid post-fix.
    src = out.metadata.get("source") if out.metadata else None
    assert src in ("live", "mock"), f"unexpected source: {src!r}"


# ── Test 4: seed_words default_factory returns 10 items ───────────────

def test_seed_words_default_factory_runs():
    """The ``seed_words`` field uses ``default_factory``; verify it returns 10 items.

    The audit suggested default of ``10`` is interpreted as "10 seed words" —
    the factory returns a 10-element list of common English words so the
    ``seed_expand`` skill has realistic default input.
    """
    cls = _load_module_attr(
        "imdf.skills.synth.synth_seed_expand", "SeedExpandInput"
    )
    field_info = cls.model_fields["seed_words"]
    assert field_info.default_factory is not None, (
        "SeedExpandInput.seed_words should use default_factory"
    )
    factory_value = field_info.default_factory()
    assert isinstance(factory_value, list), (
        f"default_factory() should return a list, got {type(factory_value)}"
    )
    assert len(factory_value) == 10, (
        f"default_factory() should return 10 seed words, got {len(factory_value)}"
    )


# ── Test 5: the static "params={} would have crashed" regression ───

# Before this fix, ``synth_seed_expand`` was the only one that actually
# crashed on ``params={}`` (the other 6 had default values, just different
# from the suggested).  We still assert seed_expand specifically: the
# Input model must validate with NO fields at all (i.e. the audit's
# headline claim about ``params={}`` is closed for at least this row).

def test_seed_expand_with_completely_empty_params():
    """The headline N2 claim was ``params={}`` raises ValidationError; verify it's closed."""
    cls = _load_module_attr(
        "imdf.skills.synth.synth_seed_expand", "SeedExpandInput"
    )
    instance = cls.model_validate({})  # must not raise
    assert isinstance(instance, cls)
    # The default 10-word list must be present
    assert len(instance.seed_words) == 10
