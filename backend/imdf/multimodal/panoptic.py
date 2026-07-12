"""P19 v5.1: Panoptic Segmentation modality — COCO Panoptic JSON format.

The COCO Panoptic task format is defined in
``https://arxiv.org/abs/2001.04082`` and used by Detectron2 / MMDetection.
A panoptic annotation file is a single JSON document with three top-level
keys:

* ``images``     — list of image records (id, file_name, height, width)
* ``annotations`` — list of per-image segment annotations
  ``{
      "image_id": int,
      "file_name": str,
      "segments_info": [
          {"id": int, "category_id": int, "iscrowd": 0|1, "bbox": [x,y,w,h], "area": float}
      ]
  }``
* ``categories`` — list of category records with ``id`` and ``name``/``supercategory``

Schema (canonical):

    {
        "format": "coco_panoptic",
        "n_images": int,
        "n_annotations": int,
        "n_categories": int,
        "n_thing_classes": int,    # iscrowd == 0
        "n_stuff_classes": int,    # iscrowd == 1
        "total_segments": int,
        "categories_sample": [{"id": int, "name": str, "isthing": 0|1}],
    }
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

import numpy as np

from .business_modalities import (
    Modality,
    ModalityAsset,
    ModalityValidation,
    _hash_fingerprint,
    _new_asset_id,
    _safe_read,
    _sha256_bytes,
    _statistical_fingerprint,
    register_modality,
)

logger = logging.getLogger(__name__)


def _parse_panoptic(raw: bytes) -> Dict[str, Any]:
    """Parse a COCO panoptic JSON file."""
    doc = json.loads(raw.decode("utf-8"))
    images = doc.get("images", []) or []
    annotations = doc.get("annotations", []) or []
    categories = doc.get("categories", []) or []

    n_thing = sum(1 for c in categories if int(c.get("isthing", 0)) == 1)
    n_stuff = sum(1 for c in categories if int(c.get("isthing", 0)) == 0)
    total_segments = sum(len(a.get("segments_info", []) or []) for a in annotations)

    sample = [
        {
            "id": int(c.get("id", 0) or 0),
            "name": str(c.get("name", "")),
            "isthing": int(c.get("isthing", 0)),
        }
        for c in categories[:10]
    ]
    return {
        "format": "coco_panoptic",
        "n_images": len(images),
        "n_annotations": len(annotations),
        "n_categories": len(categories),
        "n_thing_classes": n_thing,
        "n_stuff_classes": n_stuff,
        "total_segments": total_segments,
        "categories_sample": sample,
    }


# ── Processor ──────────────────────────────────────────────────────────────
def _processor(path: str = "", raw: bytes = b"", filename: str = "") -> ModalityAsset:
    data = raw if raw else _safe_read(path)
    sha = _sha256_bytes(data)
    metadata: Dict[str, Any] = {"filename": filename or os.path.basename(path)}
    try:
        metadata.update(_parse_panoptic(data))
    except Exception as exc:  # noqa: BLE001
        metadata["error"] = str(exc)

    n_img = metadata.get("n_images", 0)
    n_cat = metadata.get("n_categories", 0)
    n_thg = metadata.get("n_thing_classes", 0)
    n_stf = metadata.get("n_stuff_classes", 0)
    text_preview = (
        f"COCO Panoptic: {n_img} images, {n_cat} categories "
        f"(thing={n_thg}, stuff={n_stf}), "
        f"{metadata.get('total_segments', 0)} segments"
    )
    return ModalityAsset(
        asset_id=_new_asset_id("panoptic"),
        modality_id="panoptic_segmentation",
        canonical_kind="document",
        path=path,
        sha256=sha,
        size=len(data),
        mime="application/json",
        text=text_preview,
        metadata=metadata,
    )


# ── Validator ──────────────────────────────────────────────────────────────
def _validator(asset: ModalityAsset) -> ModalityValidation:
    errs: List[str] = []
    warns: List[str] = []
    md = asset.metadata or {}
    if md.get("format") != "coco_panoptic":
        errs.append("not a COCO panoptic asset")
    if md.get("error"):
        errs.append(f"parse error: {md['error']}")
    if md.get("n_images", 0) <= 0:
        warns.append("panoptic file declares zero images")
    if md.get("n_categories", 0) <= 0:
        warns.append("panoptic file declares zero categories")
    return ModalityValidation(ok=not errs, errors=errs, warnings=warns)


# ── Preview + embedder ────────────────────────────────────────────────────
def _preview(asset: ModalityAsset) -> str:
    md = asset.metadata or {}
    return (
        f"Panoptic ann: imgs={md.get('n_images', 0)} cats={md.get('n_categories', 0)} "
        f"thing/stuff={md.get('n_thing_classes', 0)}/{md.get('n_stuff_classes', 0)}"
    )


def _embedder(asset: ModalityAsset) -> List[float]:
    """Distribution-of-categories fingerprint blended with byte hash."""
    md = asset.metadata or {}
    cats_sample = md.get("categories_sample", []) or []
    cat_ids = [c.get("id", 0) for c in cats_sample if isinstance(c, dict)]
    cat_is_thing = [c.get("isthing", 0) for c in cats_sample if isinstance(c, dict)]
    feats = np.array(
        [
            float(md.get("n_images", 0) or 0),
            float(md.get("n_annotations", 0) or 0),
            float(md.get("n_categories", 0) or 0),
            float(md.get("n_thing_classes", 0) or 0),
            float(md.get("n_stuff_classes", 0) or 0),
            float(md.get("total_segments", 0) or 0),
            float(len(cat_ids)),
            float(asset.size),
        ],
        dtype=np.float32,
    )
    feats[:6] = np.log1p(np.abs(feats[:6]))
    struct = _statistical_fingerprint(feats.reshape(1, -1))
    # category-id hash component — captures the actual vocabulary
    cat_hash = _hash_fingerprint(
        (" ".join(str(i) for i in cat_ids)).encode("utf-8")
    )
    byts = _hash_fingerprint(_safe_read(asset.path))
    out = 0.4 * struct + 0.3 * cat_hash + 0.3 * byts
    n = float(np.linalg.norm(out)) or 1.0
    return (out / n).tolist()


# ── Registration ───────────────────────────────────────────────────────────
PANOPTIC_SCHEMA: Dict[str, Any] = {
    "format": "coco_panoptic",
    "n_images": "int",
    "n_annotations": "int",
    "n_categories": "int",
    "n_thing_classes": "int (iscrowd=0)",
    "n_stuff_classes": "int (iscrowd=1)",
    "total_segments": "int",
    "categories_sample": "list[{id, name, isthing}]",
}

PANOPTIC_MODALITY = Modality(
    id="panoptic_segmentation",
    name={"zh": "全景分割 (COCO Panoptic)", "en": "Panoptic Segmentation (COCO)"},
    file_extensions=[".panoptic.json", ".json"],
    canonical_kind="document",
    schema=PANOPTIC_SCHEMA,
    processor=_processor,
    validator=_validator,
    preview=_preview,
    embedder=_embedder,
    description=(
        "COCO Panoptic segmentation annotations (thing + stuff). "
        "Used for unified instance + semantic segmentation training."
    ),
)


def install() -> Modality:
    return register_modality(PANOPTIC_MODALITY)


__all__ = [
    "PANOPTIC_MODALITY",
    "PANOPTIC_SCHEMA",
    "install",
    "_parse_panoptic",
]