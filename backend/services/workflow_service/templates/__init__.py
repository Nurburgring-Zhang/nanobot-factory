"""P3-6-W2: workflow template registry (legacy `services.workflow_service.templates` shim).

The implementation lives in ``basic_templates`` (renamed by W1 to free
this namespace). This module re-exports the routes.py-compatible API:

  * ``WORKFLOW_TEMPLATES``  - canonical flat list of all templates
  * ``by_category(cat)``    - filter by category
  * ``categories()``        - distinct category names
  * ``get_template(tid)``   - lookup by id (raises KeyError on miss)
  * ``business_templates()``- only the 25 P3-6-W2 export/pipeline/multimodal/feedback

The full registry aggregates:
  * 53 legacy ``_base`` templates (image/video/audio/annotation/cleaning/...)
  * 25 W1 basic templates (collection/cleaning/annotation/scoring/filter)
  * 25 W2 business templates (export/pipeline/multimodal/feedback)

ID collisions between W1 and the legacy ``_base`` (e.g. ``tpl-ann-001``)
are resolved by giving W1 priority (newer schema) and renaming the
legacy conflicting IDs to ``tpl-base-*-NNN`` via ``_LEGACY_REMAP``.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Re-export the W1 basic registry so ``basic_templates.list_categories``,
# ``list_by_category``, ``get`` keep working without importing the
# basic_templates package directly.
from services.workflow_service.basic_templates import (
    TEMPLATES, categories_with_count, get, list_by_category,
    list_categories,
)

from services.workflow_service.basic_templates._base import _BASE_TEMPLATES
from services.workflow_service.basic_templates.export import _EXPORT_TEMPLATES
from services.workflow_service.basic_templates.feedback import _FEEDBACK_TEMPLATES
from services.workflow_service.basic_templates.multimodal import _MULTIMODAL_TEMPLATES
from services.workflow_service.basic_templates.pipeline import _PIPELINE_TEMPLATES

# P3-6-W1: 11 deeper "commercial-grade" business templates
# (5 export + 5 feedback + 1 pipeline). ID prefix ``tpl-bz2-*``.
from services.workflow_service.business_templates import (
    TEMPLATES as _BIZ2_TEMPLATES,
)


# ---- ID remap: legacy _base templates that collide with W1 basic ----
# W1 templates win on collision (newer schema, richer metadata). We
# rename the legacy IDs to ``tpl-base-*-NNN`` so both stay accessible.

_LEGACY_REMAP: Dict[str, str] = {
    "tpl-ann-001": "tpl-base-ann-001",
    "tpl-ann-002": "tpl-base-ann-002",
    "tpl-ann-003": "tpl-base-ann-003",
    "tpl-ann-004": "tpl-base-ann-004",
    "tpl-ann-005": "tpl-base-ann-005",
    "tpl-ann-006": "tpl-base-ann-006",
    "tpl-ann-007": "tpl-base-ann-007",
    "tpl-ann-008": "tpl-base-ann-008",
    "tpl-cln-001": "tpl-base-cln-001",
    "tpl-cln-002": "tpl-base-cln-002",
    "tpl-cln-003": "tpl-base-cln-003",
    "tpl-cln-004": "tpl-base-cln-004",
    "tpl-cln-005": "tpl-base-cln-005",
    "tpl-cln-006": "tpl-base-cln-006",
    "tpl-scr-001": "tpl-base-scr-001",
    "tpl-scr-002": "tpl-base-scr-002",
    "tpl-scr-003": "tpl-base-scr-003",
    "tpl-scr-004": "tpl-base-scr-004",
    "tpl-scr-005": "tpl-base-scr-005",
}


def _remap_legacy(t: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with the id remapped to ``tpl-base-*`` if needed."""
    new_id = _LEGACY_REMAP.get(t["id"])
    if new_id is None:
        return t
    # Deep-copy to avoid mutating shared _BASE_TEMPLATES list entries.
    out = dict(t)
    out["id"] = new_id
    return out


# Build the canonical flat registry:
#   53 legacy (remapped) + 25 W1 + 25 W2 + 11 W1_v2 = 114
_WORKFLOW_TEMPLATES: List[Dict[str, Any]] = (
    [_remap_legacy(t) for t in _BASE_TEMPLATES]
    + list(TEMPLATES)  # W1 (25) — IDs win on collision
    + list(_EXPORT_TEMPLATES)
    + list(_PIPELINE_TEMPLATES)
    + list(_MULTIMODAL_TEMPLATES)
    + list(_FEEDBACK_TEMPLATES)
    + list(_BIZ2_TEMPLATES)  # P3-6-W1: 11 deeper business templates
)

# Defensive: enforce unique ids across the merged registry.
_seen_ids: set = set()
for _t in _WORKFLOW_TEMPLATES:
    if _t["id"] in _seen_ids:
        raise ValueError(f"duplicate template id in merged registry: {_t['id']!r}")
    _seen_ids.add(_t["id"])

WORKFLOW_TEMPLATES: List[Dict[str, Any]] = list(_WORKFLOW_TEMPLATES)


# ---- routes.py-compatible helpers ----------------------------------

def categories() -> List[str]:
    """Distinct categories in registry order (first occurrence wins)."""
    seen: List[str] = []
    for t in WORKFLOW_TEMPLATES:
        if t["category"] not in seen:
            seen.append(t["category"])
    return seen


def by_category(cat: str) -> List[Dict[str, Any]]:
    return [t for t in WORKFLOW_TEMPLATES if t["category"] == cat]


def get_template(template_id: str) -> Dict[str, Any]:
    for t in WORKFLOW_TEMPLATES:
        if t["id"] == template_id:
            return t
    raise KeyError(template_id)


def business_templates() -> List[Dict[str, Any]]:
    """Return the 36 P3-6 business templates (25 W2 + 11 W1_v2)."""
    biz_ids = (
        {t["id"] for t in _EXPORT_TEMPLATES}
        | {t["id"] for t in _PIPELINE_TEMPLATES}
        | {t["id"] for t in _MULTIMODAL_TEMPLATES}
        | {t["id"] for t in _FEEDBACK_TEMPLATES}
        | {t["id"] for t in _BIZ2_TEMPLATES}
    )
    return [t for t in WORKFLOW_TEMPLATES if t["id"] in biz_ids]


__all__ = [
    # routes.py-compatible API
    "WORKFLOW_TEMPLATES",
    "categories",
    "by_category",
    "get_template",
    "business_templates",
    # Re-exports for templates_routes.py / W1 callers
    "TEMPLATES",
    "list_categories",
    "list_by_category",
    "get",
    "categories_with_count",
]