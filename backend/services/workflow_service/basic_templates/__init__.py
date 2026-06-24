"""P3-6-W1: 25 basic workflow templates (collection/cleaning/annotation/scoring/filter).

This sub-package exposes a flat registry ``TEMPLATES`` of 25 ready-to-run
workflow templates organised in 5 categories:

    - collection  (5)  采集类: web/youtube/wikipedia/HF/Kaggle
    - cleaning    (5)  清洗类: image/video/text-PII/audio/multimodal
    - annotation  (5)  标注类: classification/bbox/video-caption/NER+QA/3D
    - scoring     (5)  评分类: aesthetic+tech/DPO/multimodal/safety/diversity
    - filter      (5)  筛选类: top-k/balance/curriculum/domain/preference

Each template file exports a ``TEMPLATE`` dict with the contract::

    {
      "id": "tpl-<cat>-<NNN>",
      "name": "<human-readable>",
      "category": "<collection|cleaning|annotation|scoring|filter>",
      "description": "<what it does>",
      "tags": [<free-form>],
      "version": "<semver>",
      "inputs": {<param>: {type, required?, default?, ...}},
      "outputs": [<output artifacts>],
      "steps": [{id, name, operator, config, depends_on?}],
      "metrics": [<metrics emitted>],
    }

The registry is consumed by ``routes.py`` (which serves
``/api/v1/workflow/templates`` and ``/run``).
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_CATEGORIES = ("collection", "cleaning", "annotation", "scoring", "filter")


def _load_category(cat: str) -> List[Dict[str, Any]]:
    """Import all modules in templates/<cat>/ and collect TEMPLATE dicts."""
    out: List[Dict[str, Any]] = []
    pkg_path = __name__ + "." + cat
    try:
        pkg = importlib.import_module(pkg_path)
    except Exception as e:  # noqa: BLE001
        logger.error("failed to import category package %s: %s", pkg_path, e)
        return out
    for _finder, mod_name, _is_pkg in pkgutil.iter_modules(pkg.__path__):
        full = f"{pkg_path}.{mod_name}"
        try:
            mod = importlib.import_module(full)
        except Exception as e:  # noqa: BLE001
            logger.error("failed to import %s: %s", full, e)
            continue
        tpl = getattr(mod, "TEMPLATE", None)
        if isinstance(tpl, dict) and "id" in tpl:
            out.append(tpl)
        else:
            logger.warning("module %s has no TEMPLATE dict, skipping", full)
    return out


def _load_all() -> Dict[str, Dict[str, Any]]:
    """Walk every category and return a {id: template} map (deterministic)."""
    registry: Dict[str, Dict[str, Any]] = {}
    for cat in _CATEGORIES:
        for tpl in _load_category(cat):
            tid = tpl["id"]
            if tid in registry:
                # Should never happen — IDs are namespaced by category prefix.
                raise ValueError(
                    f"duplicate template id {tid!r} in category {cat!r}")
            # Defensive: enforce category = directory name
            tpl["category"] = cat
            registry[tid] = tpl
    return registry


# Eager import at package load time so failures surface early.
_TEMPLATES_BY_ID: Dict[str, Dict[str, Any]] = _load_all()


# Public registry — flat list, ordered by category then filename.
TEMPLATES: List[Dict[str, Any]] = []
for _cat in _CATEGORIES:
    _items = sorted(
        (t for t in _TEMPLATES_BY_ID.values() if t["category"] == _cat),
        key=lambda t: t["id"],
    )
    TEMPLATES.extend(_items)

assert len(TEMPLATES) == 25, (
    f"expected exactly 25 templates, got {len(TEMPLATES)}: "
    f"{[t['id'] for t in TEMPLATES]}"
)


def list_categories() -> List[str]:
    """Return the 5 category names in canonical order."""
    return list(_CATEGORIES)


def list_by_category(cat: str) -> List[Dict[str, Any]]:
    if cat not in _CATEGORIES:
        return []
    return [t for t in TEMPLATES if t["category"] == cat]


def get(template_id: str) -> Optional[Dict[str, Any]]:
    return _TEMPLATES_BY_ID.get(template_id)


def categories_with_count() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for t in TEMPLATES:
        out[t["category"]] = out.get(t["category"], 0) + 1
    return out


__all__ = [
    "TEMPLATES",
    "list_categories",
    "list_by_category",
    "get",
    "categories_with_count",
]