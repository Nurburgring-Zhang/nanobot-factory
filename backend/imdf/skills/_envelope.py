"""Unified SkillOutput metadata envelope — P21 P2 P4 (R2 N8 fix).

R2 audit (reports/p21_r2_audit_skill.md §N8) found 3 different
``make_metadata`` / ``build_output`` helpers across the 4 ``_base.py``
files (``synth/`` / ``clean/`` / ``label/`` / ``crawl/``) producing 3
different envelope shapes, with ``elapsed_ms`` not consistently populated.
Cost attribution per skill was therefore impossible.

This module centralises the envelope construction so every skill returns
the same ``{result, metadata}`` shape with the same canonical metadata
fields:

    {
        "result": <user-defined payload>,
        "metadata": {
            "elapsed_ms":   <float, always populated>,
            "source":       <str, "real" | "mock" | "live_api" | "label" | "synth" | ...>,
            "retry_count":  <int>,
            "token_count":  <int>,
            "cost_usd":     <float>,
            "timestamp":    <float, time.time()>,
            ... extra per-skill fields ...
        },
    }

The 4 per-module ``_base.py`` files keep their public helpers
(``_build_output`` / ``make_metadata`` / ``build_output`` /
``build_metadata``) so that all 50+ existing call sites continue to
work unchanged. Internally each helper now calls ``make_envelope`` so
the envelope is always built from a single source of truth.

Public API
----------
* :func:`make_envelope` — the unified envelope builder.
* :class:`ElapsedTimer` — context manager that records wall-clock ms via
  ``time.time()`` before/after the work, so callers can pass
  ``t.elapsed_ms`` to ``make_envelope`` without re-implementing
  ``time.time()`` deltas in every skill module.

Hard rules respected
-------------------
* No new dependencies (stdlib only — ``time``).
* The outer API (``SkillOutput(success, result, error, metadata)``) is
  unchanged. ``make_envelope`` returns the inner envelope dict
  (``result`` + ``metadata``); the per-module helpers wrap it in
  ``SkillOutput`` when applicable.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


def make_envelope(
    result: Any = None,
    elapsed_ms: float = 0.0,
    *,
    source: str = "real",
    retry_count: int = 0,
    token_count: int = 0,
    cost_usd: float = 0.0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the unified skill envelope: ``{"result": ..., "metadata": ...}``.

    The returned dict has exactly two top-level keys:

      * ``"result"``   — the user-defined payload (any JSON-serialisable type)
      * ``"metadata"`` — a dict with the canonical envelope fields below,
                         plus any extra fields merged in from ``extra``.

    Canonical metadata fields
    -------------------------
    ==============  ======  ==================================================
    Field           Type    Description
    ==============  ======  ==================================================
    elapsed_ms      float   Wall-clock duration of the skill invocation (ms).
                           Always populated; ``0.0`` when the caller didn't
                           measure (e.g. mock / fast-path).
    source          str     Origin tag — ``"real"`` / ``"mock"`` /
                           ``"live_api"`` / module-specific default.
    retry_count     int     Number of retries performed (0 on first-try
                           success; 2 after 2 transient failures, etc.).
    token_count     int     Sum of ``input_tokens + output_tokens`` from
                           any LLM call sites.
    cost_usd        float   Estimated USD cost of the invocation (0.0 when
                           no LLM was used).
    timestamp       float   ``time.time()`` (seconds since epoch) recorded
                           at envelope construction.
    ==============  ======  ==================================================

    Any keys present in ``extra`` are merged into ``metadata`` AFTER the
    canonical fields, so they win on collision. This lets per-skill
    modules add their own bookkeeping (e.g. ``"skill_id"``, ``"query"``,
    ``"confidence"``) without losing the canonical fields.

    Notes
    -----
    * ``elapsed_ms`` is rounded to 3 decimal places (microsecond
      precision) for stable serialisation.
    * The function does NOT touch ``SkillOutput`` — the per-module
      helpers wrap the envelope in ``SkillOutput`` when they need
      ``success`` / ``error`` fields.
    * No new dependencies: only ``time`` from the stdlib.
    """
    meta: Dict[str, Any] = {
        "elapsed_ms": round(float(elapsed_ms), 3),
        "source": str(source),
        "retry_count": int(retry_count),
        "token_count": int(token_count),
        "cost_usd": float(cost_usd),
        "timestamp": time.time(),
    }
    if extra:
        # extras win over canonical fields (per-skill modules may override)
        for k, v in extra.items():
            if v is not None or k not in meta:
                meta[k] = v
    return {"result": result, "metadata": meta}


class ElapsedTimer:
    """Context manager — records wall-clock elapsed time in milliseconds.

    Usage::

        with ElapsedTimer() as t:
            result = do_work()
        envelope = make_envelope(result=result, elapsed_ms=t.elapsed_ms)

    The timer starts on ``__enter__`` and stops on ``__exit__`` (the
    ``__exit__`` is exception-safe — it always records the final
    ``elapsed_ms`` even if the wrapped block raised). ``elapsed_ms`` is
    rounded to 3 decimal places to match ``make_envelope``'s precision.

    Implementation uses ``time.time()`` per the R2 N8 fix requirement.
    For high-resolution profiling use ``time.perf_counter()`` directly,
    but ``time.time()`` is sufficient for cost attribution and aligns
    with the rest of the imdf skill base.
    """

    __slots__ = ("_start", "elapsed_ms")

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "ElapsedTimer":
        self._start = time.time()
        self.elapsed_ms = 0.0
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.elapsed_ms = round((time.time() - self._start) * 1000.0, 3)


__all__ = ["make_envelope", "ElapsedTimer"]
