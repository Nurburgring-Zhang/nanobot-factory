"""scoring_service/operators — 15 评分算子注册表.

每个 .py 文件导出 OP_ID, NAME, CATEGORY, DESCRIPTION, PARAMS, run() 函数.
"""
from __future__ import annotations

from typing import Any, Dict, List

from services._none_safety import safe_dict_run  # P6-Fix-P0-1: NoneType guard

# Import each operator module so its .run() registers itself in OPERATORS.
from . import (
    aesthetic,
    technical,
    clarity,
    composition,
    color_harmony,
    resolution_score,
    noise_score,
    text_quality,
    diversity,
    safety,
    relevance,
    preference,
    difficulty,
    creativity,
    consistency,
)


def _build_registry() -> Dict[str, Any]:
    """Build {op_id: module} dict, validating each module has the required interface."""
    modules = [
        aesthetic,
        technical,
        clarity,
        composition,
        color_harmony,
        resolution_score,
        noise_score,
        text_quality,
        diversity,
        safety,
        relevance,
        preference,
        difficulty,
        creativity,
        consistency,
    ]
    reg: Dict[str, Any] = {}
    for m in modules:
        assert hasattr(m, "OP_ID"), f"{m.__name__} missing OP_ID"
        assert hasattr(m, "run"), f"{m.__name__} missing run()"
        assert callable(m.run), f"{m.__name__}.run not callable"
        # P6-Fix-P0-1: wrap with None-safety guard so call sites
        # get {"ok": False, "error": ...} instead of AttributeError.
        m.run = safe_dict_run(m.run)  # type: ignore[attr-defined]
        reg[m.OP_ID] = m
    return reg


OPERATORS: Dict[str, Any] = _build_registry()


def list_operators() -> List[Dict[str, Any]]:
    """Return list of operator metadata dicts."""
    out: List[Dict[str, Any]] = []
    for op_id, m in OPERATORS.items():
        out.append({
            "id": m.OP_ID,
            "name": m.NAME,
            "category": m.CATEGORY,
            "description": m.DESCRIPTION,
            "params": list(getattr(m, "PARAMS", []) or []),
        })
    out.sort(key=lambda x: x["id"])
    return out


def get_operator(op_id: str):
    return OPERATORS.get(op_id)


__all__ = ["OPERATORS", "list_operators", "get_operator"]
