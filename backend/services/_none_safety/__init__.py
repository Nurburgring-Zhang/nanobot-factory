"""Shared None-safety decorators for all operator run() functions.

P6-Fix-P0-1: 40+ operator functions in this codebase assumed valid (non-None)
inputs and crashed with `AttributeError: 'NoneType' object has no attribute 'get'`
when called with None / wrong types.

This module provides three decorator factories:
  - ``safe_list_run``: for cleaning-style ``run(items, params) -> list``
  - ``safe_dict_run``: for scoring/eval-style ``run(data, params) -> dict|list``
  - ``safe_export_run``: for exporter-style ``run(data, params) -> dict``

Each decorator:
  1. Normalises ``None`` items/data to a safe empty value
  2. Normalises ``None`` params to ``{}`` (so ``params.get(...)`` works)
  3. Rejects wrong-type params (returns a safe error or empty list)
  4. Preserves ``__name__`` and ``__doc__`` (introspection-friendly)

Usage at the registry level (preferred — single line per operator):

    from services._none_safety import safe_list_run

    OPERATORS = {entry["id"]: safe_list_run(entry["run"]) for entry in _META_TABLE}
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable


def _norm_params(params: Any) -> tuple[dict | None, str | None]:
    """Normalise params to dict.

    Returns (params, None) on success, ({}, error_message) on type error.
    Always returns at least an empty dict so the caller can use ``.get``.
    """
    if params is None:
        return {}, None
    if isinstance(params, dict):
        return params, None
    return {}, f"params must be dict, got {type(params).__name__}"


def safe_list_run(fn: Callable) -> Callable:
    """Decorator for cleaning-style run(items, params) -> list.

    Behaviour:
      * items is None            -> returns []
      * items is not a list      -> returns []
      * params is None           -> params becomes {}
      * params is not a dict     -> returns [] (do not pass wrong type through)
    """
    @wraps(fn)
    def wrapped(items: Any = None, params: Any = None) -> list:
        if items is None:
            return []
        if not isinstance(items, list):
            return []
        p, err = _norm_params(params)
        if err is not None:
            return []
        return fn(items, p)
    return wrapped


def safe_dict_run(fn: Callable) -> Callable:
    """Decorator for scoring-style run(data, params) -> dict | list.

    Behaviour:
      * data is None             -> returns {"ok": False, "error": "input data is None"}
      * data is not dict|list|str|bytes -> safe error (most inner funcs only
        handle these; primitives like int/float crash inside)
      * params is None           -> params becomes {}
      * params is not a dict     -> returns {"ok": False, "error": "params must be dict"}
      * inner call raises        -> returns {"ok": False, "error": "exception: <class>: <msg>"}
    """
    @wraps(fn)
    def wrapped(data: Any = None, params: Any = None) -> Any:
        if data is None:
            return {"ok": False, "error": "input data is None"}
        # Reject primitives that inner functions can't process (int, float, bool, None already handled)
        if not isinstance(data, (dict, list, str, bytes, bytearray, tuple)):
            return {"ok": False, "error": f"data must be dict/list/str/bytes, got {type(data).__name__}"}
        p, err = _norm_params(params)
        if err is not None:
            return {"ok": False, "error": err}
        try:
            return fn(data, p)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"operator_exception: {type(exc).__name__}: {exc}"}
    return wrapped


def safe_export_run(fn: Callable) -> Callable:
    """Decorator for exporter-style run(data, params) -> dict.

    Identical to ``safe_dict_run`` but the empty-data return also includes
    a ``rows_written: 0`` hint so callers can distinguish 0-row output
    from a hard error.
    """
    @wraps(fn)
    def wrapped(data: Any = None, params: Any = None) -> Any:
        if data is None:
            return {"ok": False, "error": "input data is None", "rows_written": 0}
        if not isinstance(data, (dict, list, str, bytes, bytearray, tuple)):
            return {"ok": False, "error": f"data must be dict/list/str/bytes, got {type(data).__name__}",
                    "rows_written": 0}
        p, err = _norm_params(params)
        if err is not None:
            return {"ok": False, "error": err, "rows_written": 0}
        try:
            return fn(data, p)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"operator_exception: {type(exc).__name__}: {exc}",
                    "rows_written": 0}
    return wrapped


__all__ = ["safe_list_run", "safe_dict_run", "safe_export_run"]
