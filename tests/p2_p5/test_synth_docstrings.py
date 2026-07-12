#!/usr/bin/env python3
"""P21 P2 P5 — Honest docstrings on the 10 working synth skills (R2 N9 fix verification).

R2 audit (reports/p21_r2_audit_skill.md §N9) found that all 10 working synth
skills (synth_caption_expand, synth_3d_caption, synth_audio_caption, synth_image_caption,
synth_image_edit_caption, synth_neg_prompt, synth_paraphrase, synth_style_transfer,
synth_translate_en, synth_translate_zh) had module-level docstrings that claimed
real synthesis / caption / translation behaviour, while the actual code:
  1. tries to POST to ``https://api.example.invalid/...`` (an unresolvable host —
     always fails DNS), and
  2. on failure falls back to a deterministic ``_mock()`` that returns
     ``{mock: True, module: 'synth_X', params: base, echo: 'synth:synth_X:offline'}``.

In other words: every call ends up echoing the input ``params`` back.  The old
docstrings ("短描述扩写为长描述", "英译中", "图像描述合成", etc.) misled callers into
expecting real LLM-backed output.  This test verifies the docstring fix.

The 10 working skills
---------------------
The "10 working" qualifier is important: the other 7 synth skills
(synth_summary / synth_seed_expand / synth_dialog_generate / synth_qa_generate /
synth_back_translate / synth_video_caption / synth_video_temporal) raise
``ValidationError`` on the harness's default ``params`` because their required
fields (e.g. ``max_words``, ``num_turns``, ``fps_sample``) have no defaults.
They are NOT in scope here — fixing them is the N2 work item, a separate P-task.

What the test asserts
---------------------
For each of the 10 working synth modules, after ``import``:

  T1 — the module's ``__doc__`` is non-empty (a docstring exists at all).
  T2 — the docstring is at least 100 characters long (rules out a 1-line
       placeholder like the original ``Synth skill — 短描述扩写为长描述.``).
  T3 — the docstring contains ``"MOCK"`` in some case form
       (case-insensitive substring check).
  T4 — the docstring does NOT contain ``"TODO"`` (case-insensitive).
  T5 — the docstring does NOT contain ``"real"`` unless the substring
       ``"mock"`` is also present (i.e. the only legitimate "real" mentions
       are in mock-qualified contexts such as
       "Real LLM-based caption expansion is NOT implemented").
  T6 — the docstring is a ``str`` (sanity check on the import).

In addition, structural checks (T7, T8) verify the rewrite is consistent
across the 10 modules rather than a one-off:
  T7 — every docstring starts with the module name (e.g. ``synth_caption_expand:``)
       so that ``help(module)`` is grep-friendly.
  T8 — the substring ``"synth:<module_name>:offline"`` appears (the exact
       ``echo`` value the ``_mock()`` function produces).

Hard rules respected
--------------------
* 25-min budget; no new dependencies (only stdlib + pytest).
* No function logic changes — only module-level docstrings were rewritten.
* All 10 files were rewritten in a single pass; this test pins the result.

Run from the project root::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    $env:PYTHONPATH = "D:\\Hermes\\生产平台\\nanobot-factory"
    & D:\\ComfyUI\\.ext\\python.exe -m pytest tests/p2_p5/test_synth_docstrings.py -v
"""
from __future__ import annotations

import importlib
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

# Make sure the synth skills don't try to hit the network during import.
os.environ.setdefault("SYNTH_OFFLINE", "1")
os.environ.setdefault("IMDF_TEST_MODE", "1")


# ---------------------------------------------------------------------------
# The 10 working synth skills (in scope for R2 N9 docstring rewrite).
# ---------------------------------------------------------------------------
# Tuple of (importable module name, the basename used in the echo string).
WORKING_SYNTH_SKILLS = [
    ("backend.imdf.skills.synth.synth_caption_expand",     "synth_caption_expand"),
    ("backend.imdf.skills.synth.synth_3d_caption",         "synth_3d_caption"),
    ("backend.imdf.skills.synth.synth_audio_caption",      "synth_audio_caption"),
    ("backend.imdf.skills.synth.synth_image_caption",      "synth_image_caption"),
    ("backend.imdf.skills.synth.synth_image_edit_caption", "synth_image_edit_caption"),
    ("backend.imdf.skills.synth.synth_neg_prompt",         "synth_neg_prompt"),
    ("backend.imdf.skills.synth.synth_paraphrase",         "synth_paraphrase"),
    ("backend.imdf.skills.synth.synth_style_transfer",     "synth_style_transfer"),
    ("backend.imdf.skills.synth.synth_translate_en",       "synth_translate_en"),
    ("backend.imdf.skills.synth.synth_translate_zh",       "synth_translate_zh"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_synth_module(module_name: str):
    """Import the synth module and return it; skip with a clear message on failure.

    We use ``importlib.import_module`` so we get a fresh module object
    even if a prior test has cached it.
    """
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover — defensive
        pytest.skip(f"cannot import {module_name!r}: {exc!r}")


@pytest.fixture(scope="module")
def synth_modules():
    """Import all 10 working synth modules once per test session.

    Returns a dict of ``{module_name: module}`` so the per-test assertions
    can iterate without re-importing.
    """
    out = {}
    for module_name, _basename in WORKING_SYNTH_SKILLS:
        out[module_name] = _import_synth_module(module_name)
    return out


# ===========================================================================
# T1 — every module has a non-empty docstring
# ===========================================================================

def test_each_module_has_docstring(synth_modules):
    """Every rewritten module exposes a non-empty ``__doc__``."""
    for module_name, mod in synth_modules.items():
        doc = getattr(mod, "__doc__", None)
        assert doc is not None, f"{module_name} has no __doc__ at all"
        assert doc.strip(), f"{module_name} has an empty/whitespace-only __doc__"


# ===========================================================================
# T2 — every docstring is at least 100 chars (rules out a 1-line placeholder)
# ===========================================================================

def test_each_docstring_is_substantive(synth_modules):
    """The original docstrings were ~30-50 chars; rewritten ones must be >= 100."""
    MIN_LEN = 100
    for module_name, mod in synth_modules.items():
        doc = mod.__doc__ or ""
        assert len(doc) >= MIN_LEN, (
            f"{module_name} docstring is {len(doc)} chars; "
            f"expected >= {MIN_LEN} (forces a non-trivial rewrite)"
        )


# ===========================================================================
# T3 — every docstring contains "MOCK" (case-insensitive)
# ===========================================================================

def test_each_docstring_admits_being_a_mock(synth_modules):
    """The literal ``mock`` substring (case-insensitive) must appear in every docstring."""
    for module_name, mod in synth_modules.items():
        doc_lower = (mod.__doc__ or "").lower()
        assert "mock" in doc_lower, (
            f"{module_name} docstring does not mention 'mock' anywhere — "
            f"callers will still think this is a real implementation. "
            f"Docstring: {doc_lower!r}"
        )


# ===========================================================================
# T4 — every docstring does NOT contain "TODO"
# ===========================================================================

def test_each_docstring_has_no_todo(synth_modules):
    """No module-level docstring may contain ``TODO`` (case-insensitive)."""
    for module_name, mod in synth_modules.items():
        doc_lower = (mod.__doc__ or "").lower()
        assert "todo" not in doc_lower, (
            f"{module_name} docstring still contains 'TODO' — fix or remove it"
        )


# ===========================================================================
# T5 — "real" only allowed when "mock" qualifier is also present
# ===========================================================================

def test_each_docstring_real_only_with_mock_qualifier(synth_modules):
    """If the docstring mentions 'real', it must also mention 'mock' somewhere.

    The original docstrings never said "real" — they just claimed the
    behaviour as if it were implemented.  The new docstrings are free to
    mention "real" in mock-qualified contexts (e.g. "Real LLM-based caption
    expansion is NOT implemented") — but a bare "real" promise with no mock
    qualifier is the same bug we are fixing.
    """
    for module_name, mod in synth_modules.items():
        doc_lower = (mod.__doc__ or "").lower()
        if "real" in doc_lower:
            assert "mock" in doc_lower, (
                f"{module_name} docstring mentions 'real' but has no 'mock' "
                f"qualifier — this is the misleading-claim bug we are fixing. "
                f"Docstring: {doc_lower!r}"
            )


# ===========================================================================
# T6 — the docstring is a real str (sanity check on the import)
# ===========================================================================

def test_each_docstring_is_str_type(synth_modules):
    """``__doc__`` must be a ``str`` (not bytes, not None)."""
    for module_name, mod in synth_modules.items():
        doc = getattr(mod, "__doc__", None)
        assert isinstance(doc, str), (
            f"{module_name}.__doc__ is {type(doc).__name__}, expected str"
        )


# ===========================================================================
# T7 — every docstring starts with the module's basename (grep-friendly help())
# ===========================================================================

def test_each_docstring_starts_with_module_basename(synth_modules):
    """``help(module)`` should immediately reveal which skill this is."""
    for module_name, basename in WORKING_SYNTH_SKILLS:
        mod = synth_modules[module_name]
        doc = mod.__doc__ or ""
        first_line = doc.split("\n", 1)[0].strip()
        assert first_line.startswith(basename + ":") or first_line.startswith(basename + " "), (
            f"{module_name} docstring first line is {first_line!r}; "
            f"expected it to start with the module basename {basename!r} so "
            f"that ``help(module)`` is grep-friendly"
        )


# ===========================================================================
# T8 — every docstring mentions the exact echo string the _mock() produces
# ===========================================================================

def test_each_docstring_advertises_exact_mock_echo(synth_modules):
    """The exact ``synth:<module_name>:offline`` echo string must appear.

    This pins the contract the caller sees: when the live API is unreachable
    (which is always, since the URL is ``api.example.invalid``), the result
    carries ``result.echo == f"synth:{basename}:offline"``.  The docstring
    must document this so callers can detect the mock branch.
    """
    for module_name, basename in WORKING_SYNTH_SKILLS:
        mod = synth_modules[module_name]
        doc = mod.__doc__ or ""
        expected_echo = f"synth:{basename}:offline"
        assert expected_echo in doc, (
            f"{module_name} docstring does not mention the exact echo string "
            f"{expected_echo!r} that the _mock() function produces"
        )


# ===========================================================================
# T9 — coverage matrix: lock the set of 10 modules (catches accidental scope drift)
# ===========================================================================

def test_coverage_matrix_locks_exactly_10_modules():
    """If anyone adds/removes a module from the rewrite scope, this fails."""
    assert len(WORKING_SYNTH_SKILLS) == 10, (
        f"WORKING_SYNTH_SKILLS has {len(WORKING_SYNTH_SKILLS)} entries; "
        f"expected exactly 10.  Adding an 11th requires updating this list and "
        f"the docstring rewrite in the corresponding synth_*.py file."
    )
    basenames = [b for _m, b in WORKING_SYNTH_SKILLS]
    assert len(set(basenames)) == 10, "duplicate module basename in WORKING_SYNTH_SKILLS"
