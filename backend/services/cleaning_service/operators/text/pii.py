"""clean.text.pii — PII detection/redaction using imdf.pii_engine.

Wraps imdf.engines.pii_engine.PIIEngine for in-process redaction.
"""
from __future__ import annotations

from typing import Any, Dict, List

try:
    from imdf.engines.pii_engine import PIIEngine
    _HAS_PII = True
except Exception:  # noqa: BLE001
    _HAS_PII = False

_ENGINE = None


def _get_engine():
    global _ENGINE
    if not _HAS_PII:
        return None
    if _ENGINE is None:
        _ENGINE = PIIEngine(use_ml=False)
    return _ENGINE


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """For each item: detect PII matches and (optionally) redact.

    params:
        strategy: str = "mask"  (mask | replace | hash | remove | detect_only)
    """
    strategy = str(params.get("strategy", "mask"))
    engine = _get_engine()
    out = []
    for x in items:
        s = x if isinstance(x, str) else repr(x)
        if engine is None:
            out.append({"item": x, "pii_detected": False,
                        "note": "pii_engine unavailable; pass-through"})
            continue
        try:
            matches = engine.detect(s)
            rec = {"item": x, "pii_detected": bool(matches),
                   "matches": [m.to_dict() for m in matches]}
            if strategy != "detect_only":
                rec["redacted"] = engine.redact(s, strategy=strategy)
                rec["strategy"] = strategy
            out.append(rec)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"pii_failed: {e}"})
    return out