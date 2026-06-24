"""dataset_service/operators — 10 筛选算子注册表.

每个 .py 文件导出 OP_ID, NAME, CATEGORY, DESCRIPTION, PARAMS, run() 函数.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import (
    top_k,
    percentile,
    threshold,
    diversity_filter,
    balance_filter,
    language_filter,
    domain_filter,
    quality_filter,
    random_sample,
    rule_based,
)


def _build_registry() -> Dict[str, Any]:
    modules = [
        top_k,
        percentile,
        threshold,
        diversity_filter,
        balance_filter,
        language_filter,
        domain_filter,
        quality_filter,
        random_sample,
        rule_based,
    ]
    reg: Dict[str, Any] = {}
    for m in modules:
        assert hasattr(m, "OP_ID"), f"{m.__name__} missing OP_ID"
        assert hasattr(m, "run"), f"{m.__name__} missing run()"
        assert callable(m.run), f"{m.__name__}.run not callable"
        reg[m.OP_ID] = m
    return reg


OPERATORS: Dict[str, Any] = _build_registry()


def list_operators() -> List[Dict[str, Any]]:
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
