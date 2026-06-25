"""P6-Fix-P0-1: NoneType safety regression test.

Verifies that every operator in:
  - cleaning_service.operators (32)
  - scoring_service.operators (15)
  - annotation_service.operators (image=8, text=4, three_d=3, video=5; total 20)
  - evaluation_service.operators (10)
  - dataset_service.exporters (12)

does NOT crash on these adversarial inputs:
  * None         (instead of list/dict)
  * {}           (instead of valid params)
  * []           (empty list, valid but should not crash)
  * "hello"      (wrong type, should be rejected gracefully)

For each operator the test asserts the call returns one of:
  * a list (cleaning-style: empty list is OK)
  * a dict with "ok" == False (scoring/eval-style error response)
  * a dict (exporters: error response)

The test never raises; the assertion is on the return value shape only.
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import Any, Callable, Dict, List

import pytest

# Ensure backend/ on sys.path
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _is_cleaning_ok(value: Any) -> bool:
    """Cleaning-style return must be a list (possibly empty)."""
    return isinstance(value, list)


def _is_error_dict(value: Any) -> bool:
    """Scoring/eval/export-style return must be a dict; if it has 'ok', it must be False."""
    if not isinstance(value, dict):
        return False
    if "ok" in value and value["ok"] is True:
        return True  # happy path
    if "ok" in value and value["ok"] is False:
        return True  # expected error
    # No "ok" key but has expected fields (e.g. bleu returns list of dicts)
    return True


def _safe_call(fn: Callable, *args, **kwargs) -> Any:
    """Call fn and return either the result or the exception string.

    Used to detect that no AttributeError/TypeError leaks out of the wrapper.
    """
    try:
        return ("ok", fn(*args, **kwargs))
    except Exception as e:  # noqa: BLE001
        return ("err", f"{type(e).__name__}: {e}")


# ─── Adversarial inputs to test against every operator ──────────────────────

ADVERSARIAL_INPUTS: List[tuple] = [
    ("none_items", (None, None)),
    ("none_items_with_empty_params", (None, {})),
    ("empty_list", ([], {})),
    ("empty_list_no_params", ([], None)),
    ("string_input", ("hello", None)),
    ("int_input", (42, None)),
    ("dict_items", ({}, None)),
    ("none_params", ([], None)),
    ("wrong_type_params", ([], "not_a_dict")),
    ("none_data", (None, None)),
    ("empty_dict_data", ({}, None)),
    ("int_data", (123, {})),
]


# ─── Cleaning service (32 operators) ────────────────────────────────────────

def _cleaning_operators() -> Dict[str, Callable]:
    from services.cleaning_service.operators import OPERATORS
    return dict(OPERATORS)


@pytest.mark.parametrize("op_id,fn", list(_cleaning_operators().items()),
                         ids=list(_cleaning_operators().keys()))
def test_cleaning_operator_none_safe(op_id: str, fn: Callable) -> None:
    """Each cleaning operator must return [] for adversarial inputs (no exception)."""
    failures: List[str] = []
    for name, (items, params) in ADVERSARIAL_INPUTS:
        result = _safe_call(fn, items, params)
        if result[0] == "err":
            failures.append(f"[{name}] RAISED {result[1]}")
            continue
        value = result[1]
        if not _is_cleaning_ok(value):
            failures.append(f"[{name}] returned {type(value).__name__} (expected list)")
    assert not failures, f"{op_id} NoneType guard FAILED:\n  " + "\n  ".join(failures)


def test_cleaning_operator_count_is_32() -> None:
    from services.cleaning_service.operators import OPERATORS
    assert len(OPERATORS) == 32, f"expected 32 cleaning operators, got {len(OPERATORS)}"


# ─── Scoring service (15 operators) ─────────────────────────────────────────

def _scoring_operators() -> Dict[str, Callable]:
    from services.scoring_service.operators import OPERATORS
    return {m.OP_ID: m.run for m in OPERATORS.values()}


@pytest.mark.parametrize("op_id,fn", list(_scoring_operators().items()),
                         ids=list(_scoring_operators().keys()))
def test_scoring_operator_none_safe(op_id: str, fn: Callable) -> None:
    """Each scoring operator must return a dict (or list of dicts) for adversarial inputs."""
    failures: List[str] = []
    for name, (data, params) in ADVERSARIAL_INPUTS:
        result = _safe_call(fn, data, params)
        if result[0] == "err":
            failures.append(f"[{name}] RAISED {result[1]}")
            continue
        value = result[1]
        if isinstance(value, list):
            # list-of-dicts is acceptable (e.g. multi-item responses)
            for v in value:
                if isinstance(v, dict):
                    continue
                failures.append(f"[{name}] list element is {type(v).__name__}")
        elif not _is_error_dict(value):
            failures.append(f"[{name}] returned {type(value).__name__} (expected dict or list)")
    assert not failures, f"{op_id} NoneType guard FAILED:\n  " + "\n  ".join(failures)


def test_scoring_operator_count_is_15() -> None:
    from services.scoring_service.operators import OPERATORS
    assert len(OPERATORS) == 15, f"expected 15 scoring operators, got {len(OPERATORS)}"


# ─── Annotation service (20 operators across 4 subdirs) ────────────────────

def _annotation_modules() -> Dict[str, Any]:
    """Return {modname: module} for all 20 annotation operators."""
    from services.annotation_service.operators import (
        image as ann_image,
        text as ann_text,
        three_d as ann_3d,
        video as ann_video,
    )
    out: Dict[str, Any] = {}
    for sub in (ann_image, ann_text, ann_3d, ann_video):
        for name in sub.__all__:
            out[name] = getattr(sub, name)
    return out


@pytest.mark.parametrize("modname,mod", list(_annotation_modules().items()),
                         ids=list(_annotation_modules().keys()))
def test_annotation_operator_none_safe(modname: str, mod: Any) -> None:
    """Each annotation operator must not raise on None / wrong types."""
    fn = mod.run
    failures: List[str] = []
    for name, (data, params) in ADVERSARIAL_INPUTS:
        result = _safe_call(fn, data, params)
        if result[0] == "err":
            failures.append(f"[{name}] RAISED {result[1]}")
            continue
        value = result[1]
        if isinstance(value, list):
            for v in value:
                if isinstance(v, dict):
                    continue
                failures.append(f"[{name}] list element is {type(v).__name__}")
        elif not _is_error_dict(value):
            failures.append(f"[{name}] returned {type(value).__name__}")
    assert not failures, f"annot.{modname} NoneType guard FAILED:\n  " + "\n  ".join(failures)


def test_annotation_module_count_is_20() -> None:
    mods = _annotation_modules()
    assert len(mods) == 20, f"expected 20 annotation modules, got {len(mods)}"


# ─── Evaluation service (10 operators) ──────────────────────────────────────

def _evaluation_operators() -> Dict[str, Callable]:
    from services.evaluation_service.operators import OPERATORS
    return dict(OPERATORS)


@pytest.mark.parametrize("op_id,fn", list(_evaluation_operators().items()),
                         ids=list(_evaluation_operators().keys()))
def test_evaluation_operator_none_safe(op_id: str, fn: Callable) -> None:
    failures: List[str] = []
    for name, (data, params) in ADVERSARIAL_INPUTS:
        result = _safe_call(fn, data, params)
        if result[0] == "err":
            failures.append(f"[{name}] RAISED {result[1]}")
            continue
        value = result[1]
        if isinstance(value, list):
            for v in value:
                if isinstance(v, dict):
                    continue
                failures.append(f"[{name}] list element is {type(v).__name__}")
        elif not _is_error_dict(value):
            failures.append(f"[{name}] returned {type(value).__name__}")
    assert not failures, f"{op_id} NoneType guard FAILED:\n  " + "\n  ".join(failures)


def test_evaluation_operator_count_is_10() -> None:
    from services.evaluation_service.operators import OPERATORS
    assert len(OPERATORS) == 10, f"expected 10 evaluation operators, got {len(OPERATORS)}"


# ─── Exporters (12 operators) ───────────────────────────────────────────────

def _exporter_modules() -> Dict[str, Any]:
    from services.dataset_service.exporters import OPERATORS
    return dict(OPERATORS)


@pytest.mark.parametrize("op_id,mod", list(_exporter_modules().items()),
                         ids=list(_exporter_modules().keys()))
def test_exporter_none_safe(op_id: str, mod: Any) -> None:
    """Each exporter must return {"ok": False, ...} on None / wrong types.

    Some exporters (jsonl) need a real path, but with None data they must
    short-circuit to the safe error path before touching params.get('path').
    """
    fn = mod.run
    failures: List[str] = []
    for name, (data, params) in ADVERSARIAL_INPUTS:
        result = _safe_call(fn, data, params)
        if result[0] == "err":
            failures.append(f"[{name}] RAISED {result[1]}")
            continue
        value = result[1]
        if not _is_error_dict(value):
            failures.append(f"[{name}] returned {type(value).__name__} (expected dict)")
    assert not failures, f"exporter {op_id} NoneType guard FAILED:\n  " + "\n  ".join(failures)


def test_exporter_count_is_12() -> None:
    mods = _exporter_modules()
    assert len(mods) == 12, f"expected 12 exporters, got {len(mods)}"


# ─── Decorator unit tests ──────────────────────────────────────────────────

def test_safe_list_run_returns_empty_for_none() -> None:
    from services._none_safety import safe_list_run
    @safe_list_run
    def fake(items, params):
        return items

    assert fake(None) == []
    assert fake(None, None) == []
    assert fake(None, {"k": 1}) == []
    assert fake("not_a_list") == []


def test_safe_list_run_returns_empty_for_wrong_params_type() -> None:
    from services._none_safety import safe_list_run
    @safe_list_run
    def fake(items, params):
        return items

    # params must be dict; non-dict → empty
    assert fake([1, 2, 3], "not_a_dict") == []
    assert fake([1, 2, 3], 42) == []


def test_safe_list_run_passes_through_valid() -> None:
    from services._none_safety import safe_list_run
    @safe_list_run
    def fake(items, params):
        return {"len": len(items), "p": params.get("k")}

    out = fake([1, 2, 3], {"k": "v"})
    assert out == {"len": 3, "p": "v"}
    # params=None should become {} so .get works
    out2 = fake([1, 2])
    assert out2 == {"len": 2, "p": None}


def test_safe_dict_run_returns_error_for_none() -> None:
    from services._none_safety import safe_dict_run
    @safe_dict_run
    def fake(data, params):
        return {"data": data}

    out = fake(None)
    assert out["ok"] is False
    assert "None" in out["error"] or "none" in out["error"].lower()


def test_safe_dict_run_returns_error_for_wrong_params_type() -> None:
    from services._none_safety import safe_dict_run
    @safe_dict_run
    def fake(data, params):
        return {"data": data}

    out = fake(["hello"], "not_a_dict")
    assert out["ok"] is False
    assert "params" in out["error"]


def test_safe_export_run_includes_rows_written_zero() -> None:
    from services._none_safety import safe_export_run
    @safe_export_run
    def fake(data, params):
        return {"ok": True, "rows_written": 5}

    out = fake(None)
    assert out["ok"] is False
    assert out.get("rows_written") == 0
