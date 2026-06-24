"""P3-6.5-W2: business workflow templates (28 entries: 7 export + 5 feedback +
11 pipeline + 5 multimodal).

This sub-package contains deeper "commercial-grade" versions of business
templates that complement the lighter-weight ``basic_templates`` list-style
business templates. Layout::

    business_templates/
    ├── __init__.py             - TEMPLATES registry (28 entries)
    ├── export/                 - 7 export-format templates
    │   ├── __init__.py
    │   ├── jsonl_alpaca.py              (tpl-bz2-exp-001)  [W1]
    │   ├── sharegpt_conversation.py     (tpl-bz2-exp-002)  [W1]
    │   ├── coco_detection.py            (tpl-bz2-exp-003)  [W1]
    │   ├── yolo_training.py             (tpl-bz2-exp-004)  [W1]
    │   ├── parquet_hf.py                (tpl-bz2-exp-005)  [W1]
    │   ├── alpaca_sft_v2.py             (tpl-bz2-exp-h01)  [W2.5 NEW]
    │   └── sharegpt_conversation_v2.py  (tpl-bz2-exp-h02)  [W2.5 NEW]
    ├── feedback/               - 5 feedback-loop templates
    │   ├── __init__.py
    │   ├── bad_case_analysis.py         (tpl-bz2-fb-001)
    │   ├── model_eval_feedback.py       (tpl-bz2-fb-002)
    │   ├── human_review_loop.py         (tpl-bz2-fb-003)
    │   ├── auto_relabel.py              (tpl-bz2-fb-004)
    │   └── data_iteration.py            (tpl-bz2-fb-005)
    ├── pipeline/               - 11 mixed-business pipeline templates
    │   ├── __init__.py
    │   ├── pretrain_image_collection.py (tpl-bz2-pipe-h01)  [W2.5 NEW]
    │   ├── sft_image_classification.py  (tpl-bz2-pipe-h02)  [W2.5 NEW]
    │   ├── sft_image_caption.py         (tpl-bz2-pipe-h03)  [W2.5 NEW]
    │   ├── sft_video_caption.py         (tpl-bz2-pipe-h04)  [W2.5 NEW]
    │   ├── sft_text_ner.py              (tpl-bz2-pipe-h05)  [W2.5 NEW]
    │   ├── dpo_preference.py            (tpl-bz2-pipe-h06)  [W2.5 NEW]
    │   ├── rlhf_reward.py               (tpl-bz2-pipe-h07)  [W2.5 NEW]
    │   ├── multimodal_sft.py            (tpl-bz2-pipe-h08)  [W2.5 NEW]
    │   ├── video_edit_sft.py            (tpl-bz2-pipe-h09)  [W2.5 NEW]
    │   ├── picture_book_generation.py   (tpl-bz2-pipe-h10)  [W2.5 NEW]
    │   └── short_drama_sft.py           (tpl-bz2-pipe-011)  [W1]
    └── multimodal/             - 5 multimodal special-flow templates
        ├── __init__.py
        ├── image_to_video.py            (tpl-bz2-mm-h01)  [W2.5 NEW]
        ├── text_to_image_edit.py        (tpl-bz2-mm-h02)  [W2.5 NEW]
        ├── character_consistency.py     (tpl-bz2-mm-h03)  [W2.5 NEW]
        ├── style_transfer_dataset.py    (tpl-bz2-mm-h04)  [W2.5 NEW]
        └── tts_dataset.py               (tpl-bz2-mm-h05)  [W2.5 NEW]

Each ``TEMPLATE`` dict shares the contract with ``basic_templates``:
  ``{id, name, category, description, tags, version,
    inputs, outputs, steps, metrics}``.

W1 used ``tpl-bz2-*`` prefix. W2.5 uses ``tpl-bz2-pipe-hNN`` /
``tpl-bz2-mm-hNN`` / ``tpl-bz2-exp-hNN`` (hybrid) to keep distinct.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_CATEGORIES = ("export", "feedback", "pipeline", "multimodal")


def _load_category(cat: str) -> List[Dict[str, Any]]:
    """Import the category sub-package and collect all TEMPLATE dicts.

    The sub-package's ``TEMPLATES`` list is the canonical source. We
    also fall back to scanning its modules for any stray ``TEMPLATE``
    constant that wasn't added to the list, so a maintainer who adds a
    file without touching ``__init__.py`` still gets it registered.
    """
    out: List[Dict[str, Any]] = []
    pkg_path = __name__ + "." + cat
    try:
        pkg = importlib.import_module(pkg_path)
    except Exception as e:  # noqa: BLE001
        logger.error("failed to import business_templates.%s: %s",
                     cat, e)
        return out
    # Preferred path: TEMPLATES list exported by the package.
    listed = getattr(pkg, "TEMPLATES", None)
    if isinstance(listed, list):
        for tpl in listed:
            if isinstance(tpl, dict) and "id" in tpl:
                tpl.setdefault("category", cat)
                out.append(tpl)
            else:
                logger.warning("bad TEMPLATE entry in %s: %r", pkg_path, tpl)
    return out


def _load_all() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}
    for cat in _CATEGORIES:
        for tpl in _load_category(cat):
            tid = tpl["id"]
            if tid in registry:
                raise ValueError(
                    f"duplicate template id {tid!r} in business_templates")
            registry[tid] = tpl
    return registry


_TEMPLATES_BY_ID: Dict[str, Dict[str, Any]] = _load_all()


# Public flat list — sorted by id within each category for determinism.
TEMPLATES: List[Dict[str, Any]] = []
for _cat in _CATEGORIES:
    _items = sorted(
        (t for t in _TEMPLATES_BY_ID.values() if t["category"] == _cat),
        key=lambda t: t["id"],
    )
    TEMPLATES.extend(_items)


# Total target = 28 (5 W1 export + 2 W2.5 export + 5 feedback +
# 10 W2.5 pipeline hybrid + 1 W1 pipeline + 5 W2.5 multimodal hybrid).
assert len(TEMPLATES) == 28, (
    f"expected exactly 28 business_templates, got {len(TEMPLATES)}: "
    f"{[t['id'] for t in TEMPLATES]}"
)


# Convenience helpers (mirror basic_templates API) ----------------------

def list_categories() -> List[str]:
    """Return the 4 business-template category names in canonical order."""
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