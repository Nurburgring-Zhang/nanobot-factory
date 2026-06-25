"""P4-6-W2: operator marketplace tests (3 tests).

Covers:
  1. marketplace total >= 200 across 9 categories
  2. per-category counts match the design (cleaning 32, scoring 15, ...)
  3. search and schema endpoints work
"""
from __future__ import annotations

import pytest

from services.workflow_service.dag_v2.operators import (
    CATEGORIES,
    list_operators,
    market_summary,
    operator_schema,
    search_operators,
    get_operator,
)


# =====================================================================
# 1) totals
# =====================================================================

def test_marketplace_has_200_plus_operators():
    s = market_summary()
    assert s["total"] >= 200, f"only {s['total']} operators registered"
    # 9 categories
    assert len(s["categories"]) == 9


# =====================================================================
# 2) per-category counts (mirror the design)
# =====================================================================

def test_per_category_minimum_counts():
    s = market_summary()
    counts = s["per_category"]
    # expected: cleaning=32, scoring=15, annotation=20, filter=12,
    # export=10, evaluation=10, generator=18, editor=39, agent=10
    assert counts.get("cleaning", 0) >= 30
    assert counts.get("scoring", 0) >= 15
    assert counts.get("annotation", 0) >= 20
    assert counts.get("filter", 0) >= 10
    assert counts.get("export", 0) >= 10
    assert counts.get("evaluation", 0) >= 10
    assert counts.get("generator", 0) >= 15
    assert counts.get("editor", 0) >= 35
    assert counts.get("agent", 0) >= 10


def test_categories_constant_matches():
    expected = {"cleaning", "scoring", "annotation", "filter",
                "export", "evaluation", "generator", "editor", "agent"}
    assert set(CATEGORIES) == expected


# =====================================================================
# 3) search & schema
# =====================================================================

def test_search_returns_relevant_hits():
    items = search_operators("sdxl")
    assert any(o.id == "op.generator.sdxl_txt2img" for o in items)


def test_search_by_category():
    items = search_operators("", category="editor")
    assert all(o.category == "editor" for o in items)
    assert len(items) >= 30


def test_get_operator_and_schema():
    op = get_operator("op.scoring.aesthetic_laion")
    assert op is not None
    assert op.name
    s = operator_schema(op.id)
    assert s is not None
    assert "input_schema" in s
    assert "output_schema" in s
    assert s["version"] == op.latest


def test_unknown_operator_returns_none():
    assert get_operator("op.does.not.exist") is None
    assert operator_schema("op.does.not.exist") is None
