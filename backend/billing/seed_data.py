"""Seed data for billing module — 5 plans + 12 features.

Drop-in seeder: imports plans.py and emits the canonical SEED_PLANS list.
This module is the single source of truth for first-run / test fixture data.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .plans import (
    FEATURE_DIMENSIONS, FEATURE_LABELS, PLAN_CATALOG, PLAN_CONFIGS, SEED_PLANS,
    get_plan_with_config,
)


def get_seed_plans() -> List[Dict[str, Any]]:
    """Return the 5 plans in canonical order."""
    return [get_plan_with_config(p.plan_id) for p in PLAN_CATALOG]


def get_feature_dimensions() -> List[str]:
    """Return the canonical 12 feature dimensions (used by quotas/admin)."""
    return list(FEATURE_DIMENSIONS)


def get_feature_labels() -> Dict[str, str]:
    """Return the human-readable labels for the 12 dimensions."""
    return dict(FEATURE_LABELS)


def get_seed_plan_ids() -> List[str]:
    """Return the 5 plan_ids in canonical order."""
    return [p.plan_id for p in PLAN_CATALOG]


__all__ = [
    "get_seed_plans", "get_feature_dimensions", "get_feature_labels",
    "get_seed_plan_ids",
    "FEATURE_DIMENSIONS", "FEATURE_LABELS", "PLAN_CATALOG", "PLAN_CONFIGS", "SEED_PLANS",
]
