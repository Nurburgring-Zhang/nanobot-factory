"""P4-4-W2 lineage tracking hooks (P4-1 common lib integration).

Two flavors:

  1. :func:`track_lineage` — decorator that records an edge after the
     wrapped function returns. Use::

         @track_lineage(operator_id="clean.image.dedupe",
                        edge_type="cleaned_by",
                        inputs_arg="dataset_path",
                        outputs_arg="output_path")
         def dedupe(dataset_path: str, ...) -> str:
             ...
             return output_path

     The decorator inspects the call's return value as the *outputs*
     list (when a string) and the *inputs* list from the named arg
     (when a string). It can also be told to read multi-arg lists via
     ``inputs_arg`` / ``outputs_arg`` accepting a list argument.

  2. :func:`track_lineage_ctx` — context manager for inline use::

         with track_lineage_ctx(operator_id="score.quality",
                                inputs=[ds_name],
                                outputs=[out_path],
                                edge_type="scored_by"):
             out_path = run_scoring(ds_name)

Both flavors are best-effort: they never raise into the wrapped code;
failures are logged and swallowed so a missing lineage DB never blocks
the production path.
"""
from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from . import collector

logger = logging.getLogger(__name__)


def _coerce_to_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def track_lineage(
    operator_id: str,
    edge_type: str = "cleaned_by",
    inputs_arg: Optional[str] = None,
    outputs_arg: Optional[str] = None,
    pipeline_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Callable:
    """Decorator: record an edge between the wrapped fn's input and output.

    If ``inputs_arg`` / ``outputs_arg`` are given, they refer to
    parameter names. Otherwise the decorator uses the function's
    positional + return value.
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            inputs: List[str] = []
            outputs: List[str] = []
            try:
                result = fn(*args, **kwargs)
            except Exception:
                # Don't block the production path on lineage errors
                logger.exception("track_lineage: wrapped fn %s raised", fn.__name__)
                raise
            try:
                if inputs_arg and inputs_arg in kwargs:
                    inputs = _coerce_to_list(kwargs[inputs_arg])
                if outputs_arg and outputs_arg in kwargs:
                    outputs = _coerce_to_list(kwargs[outputs_arg])
                if not inputs and args:
                    inputs = _coerce_to_list(args[0])
                if not outputs:
                    outputs = _coerce_to_list(result)
                if inputs and outputs:
                    collector.record_operator(
                        operator_id=operator_id,
                        inputs=inputs,
                        outputs=outputs,
                        edge_type=edge_type,
                        pipeline_id=pipeline_id,
                        extra=extra or {},
                    )
            except Exception:  # noqa: BLE001
                logger.warning("track_lineage: collect failed for %s", fn.__name__)
            return result

        return wrapper

    return deco


@contextmanager
def track_lineage_ctx(
    operator_id: str,
    inputs: Sequence[str] = (),
    outputs: Sequence[str] = (),
    edge_type: str = "cleaned_by",
    pipeline_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
):
    """Context manager variant of :func:`track_lineage`."""
    try:
        yield
        if inputs and outputs:
            try:
                collector.record_operator(
                    operator_id=operator_id,
                    inputs=list(inputs),
                    outputs=list(outputs),
                    edge_type=edge_type,
                    pipeline_id=pipeline_id,
                    extra=extra or {},
                )
            except Exception:  # noqa: BLE001
                logger.warning("track_lineage_ctx: collect failed for %s", operator_id)
    except Exception:
        # Bubble the wrapped exception; the after-yield code still
        # didn't run, so we just exit cleanly.
        raise


__all__ = ["track_lineage", "track_lineage_ctx"]
