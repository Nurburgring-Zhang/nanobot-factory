"""P19 v5.1: Tests for the Panoptic Segmentation modality (COCO Panoptic JSON).

Verifies:
1. Modality registration.
2. Parser extracts images / annotations / categories counts.
3. Processor + validator.
4. 1024-dim embedder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from multimodal.panoptic import (
    PANOPTIC_MODALITY,
    _parse_panoptic,
)
from multimodal.business_modalities import (
    ModalityAsset,
    ModalityValidation,
    embed_asset,
    get_modality,
)


def _make_panoptic(n_images: int = 3, n_cats: int = 5,
                   is_thing: int = 1, segs_per_image: int = 2) -> bytes:
    images = [
        {"id": i, "file_name": f"img_{i:03d}.jpg", "height": 480, "width": 640}
        for i in range(n_images)
    ]
    annotations = []
    seg_id = 1
    for img in images:
        segs = []
        for s in range(segs_per_image):
            segs.append({
                "id": seg_id,
                "category_id": (seg_id % n_cats) + 1,
                "iscrowd": 0 if (seg_id % 2 == 0) else 1,
                "bbox": [s * 10, s * 10, 50, 50],
                "area": 2500.0,
            })
            seg_id += 1
        annotations.append({
            "image_id": img["id"],
            "file_name": img["file_name"].replace(".jpg", ".png"),
            "segments_info": segs,
        })
    categories = [
        {"id": i + 1, "name": f"class_{i}", "supercategory": "stuff" if is_thing == 0 else "thing",
         "isthing": is_thing if i % 2 == 0 else (1 - is_thing)}
        for i in range(n_cats)
    ]
    return json.dumps({
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }).encode("utf-8")


# ── 1. registration ──────────────────────────────────────────────────────
def test_panoptic_registered():
    m = get_modality("panoptic_segmentation")
    assert m is PANOPTIC_MODALITY
    assert "全景分割" in m.name["zh"]
    assert "Panoptic" in m.name["en"]
    assert ".json" in m.file_extensions


def test_panoptic_schema():
    s = PANOPTIC_MODALITY.schema
    for k in ("format", "n_images", "n_annotations", "n_categories",
              "n_thing_classes", "n_stuff_classes", "total_segments"):
        assert k in s


# ── 2. parsing ────────────────────────────────────────────────────────────
def test_parse_panoptic_basic():
    raw = _make_panoptic(n_images=3, n_cats=5, segs_per_image=2)
    info = _parse_panoptic(raw)
    assert info["format"] == "coco_panoptic"
    assert info["n_images"] == 3
    assert info["n_annotations"] == 3
    assert info["n_categories"] == 5
    assert info["total_segments"] == 6  # 3 images × 2 segs
    # thing/stuff split depends on alternating isthing in categories
    assert info["n_thing_classes"] + info["n_stuff_classes"] == 5


def test_parse_panoptic_categories_sample():
    raw = _make_panoptic(n_images=1, n_cats=3)
    info = _parse_panoptic(raw)
    assert len(info["categories_sample"]) == 3
    for c in info["categories_sample"]:
        assert "id" in c and "name" in c and "isthing" in c


def test_parse_panoptic_malformed():
    with pytest.raises(Exception):
        _parse_panoptic(b"{not-json")


# ── 3. processor ──────────────────────────────────────────────────────────
def _tmp(tmp_path: Path, name: str, raw: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(raw)
    return str(p)


def test_processor_panoptic_json(tmp_path):
    raw = _make_panoptic(n_images=4, n_cats=8, segs_per_image=3)
    p = _tmp(tmp_path, "annotations.panoptic.json", raw)
    asset = PANOPTIC_MODALITY.processor(path=p, raw=raw,
                                          filename="annotations.panoptic.json")
    assert asset.modality_id == "panoptic_segmentation"
    assert asset.metadata["n_images"] == 4
    assert "Panoptic" in asset.text
    assert "thing=" in asset.text


def test_processor_json(tmp_path):
    raw = _make_panoptic(n_images=1, n_cats=2, segs_per_image=1)
    p = _tmp(tmp_path, "pan.json", raw)
    asset = PANOPTIC_MODALITY.processor(path=p, raw=raw, filename="pan.json")
    assert asset.modality_id == "panoptic_segmentation"


# ── 4. validator ──────────────────────────────────────────────────────────
def test_validator_ok(tmp_path):
    raw = _make_panoptic(n_images=2, n_cats=4)
    p = _tmp(tmp_path, "good.panoptic.json", raw)
    asset = PANOPTIC_MODALITY.processor(path=p, raw=raw,
                                          filename="good.panoptic.json")
    v = PANOPTIC_MODALITY.validator(asset)
    assert v.ok is True


def test_validator_warns_on_zero_images():
    asset = ModalityAsset(
        asset_id="x", modality_id="panoptic_segmentation",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="",
        metadata={"format": "coco_panoptic", "n_images": 0,
                  "n_categories": 5},
    )
    v = PANOPTIC_MODALITY.validator(asset)
    assert v.ok is True
    assert any("zero images" in w for w in v.warnings)


# ── 5. preview ────────────────────────────────────────────────────────────
def test_preview_format():
    asset = ModalityAsset(
        asset_id="x", modality_id="panoptic_segmentation",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"n_images": 10, "n_categories": 25,
                                     "n_thing_classes": 12, "n_stuff_classes": 13},
    )
    p = PANOPTIC_MODALITY.preview(asset)
    assert "imgs=10" in p
    assert "cats=25" in p
    assert "12/13" in p


# ── 6. embedder 1024-dim ──────────────────────────────────────────────────
def test_embedder_returns_1024_dim(tmp_path):
    raw = _make_panoptic(n_images=5, n_cats=10, segs_per_image=4)
    p = _tmp(tmp_path, "pan.panoptic.json", raw)
    asset = PANOPTIC_MODALITY.processor(path=p, raw=raw,
                                          filename="pan.panoptic.json")
    vec = PANOPTIC_MODALITY.embedder(asset)
    assert len(vec) == 1024
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    assert 0.99 <= norm <= 1.01


def test_embed_asset_dispatch(tmp_path):
    raw = _make_panoptic()
    p = _tmp(tmp_path, "pan.panoptic.json", raw)
    asset = PANOPTIC_MODALITY.processor(path=p, raw=raw,
                                          filename="pan.panoptic.json")
    vec = embed_asset(asset)
    assert len(vec) == 1024


def test_determinism(tmp_path):
    raw = _make_panoptic()
    p = _tmp(tmp_path, "pan.panoptic.json", raw)
    a = PANOPTIC_MODALITY.processor(path=p, raw=raw,
                                      filename="pan.panoptic.json")
    v1 = PANOPTIC_MODALITY.embedder(a)
    v2 = PANOPTIC_MODALITY.embedder(a)
    assert v1 == v2