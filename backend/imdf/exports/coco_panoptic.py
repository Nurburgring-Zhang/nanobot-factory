"""P19 v5.1-D3: COCO Panoptic Segmentation exporter.

COCO Panoptic JSON 顶层结构::

    {
      "images":      [ {id, file_name, height, width}, ... ],
      "annotations": [ {image_id, file_name, segments_info: [...]}, ... ],
      "categories":  [ {id, name, supercategory, isthing}, ... ]
    }

其中:
- ``annotations[i].file_name``: PNG mask 相对路径 (e.g. ``masks/{i}.png``)
- ``annotations[i].segments_info``: 每段一个 {id, category_id, isthing, bbox, area}
- 类别区分 thing (object instance) vs stuff (background)

PNG mask: 每个像素存其所属 segment_id, RGB 编码 = (R*256*256 + G*256 + B).
"""
from __future__ import annotations

import json
import os
import struct
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image


def _encode_panoptic_png(seg_ids: List[int], width: int, height: int) -> bytes:
    """编码 panoptic mask PNG: 像素 = segment_id, RGB encoding.

    若 PIL 可用, 用 PIL 写出, 保证 PNG 格式合法;
    否则 fallback 纯 Python 写 PNG (zlib + IHDR + IDAT + IEND).
    """
    if not seg_ids or width <= 0 or height <= 0:
        seg_ids = [0] * (width * height if width > 0 and height > 0 else 0)
    # 构造 RGB image: segment_id -> R = (id >> 16) & 0xFF, G = (id >> 8) & 0xFF, B = id & 0xFF
    try:
        img = Image.new("RGB", (width, height), color=(0, 0, 0))
        pixels = img.load()
        for idx, sid in enumerate(seg_ids):
            x = idx % width
            y = idx // width
            r = (sid >> 16) & 0xFF
            g = (sid >> 8) & 0xFF
            b = sid & 0xFF
            pixels[x, y] = (r, g, b)
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # fallback: 极简 PNG 写 (RGB only), 此路径不应被触发
        return _fallback_png_rgb(seg_ids, width, height)


def _fallback_png_rgb(values: List[int], width: int, height: int) -> bytes:
    """极简 PNG RGB 写入 (无 PIL 时使用, 不保证兼容性, 但格式正确)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: None
        for x in range(width):
            idx = y * width + x
            v = values[idx] if idx < len(values) else 0
            raw.extend([(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    return out


def _default_categories() -> List[Dict[str, Any]]:
    """默认 7 thing + 4 stuff 类别 (COCO-2017 panoptic 风格)."""
    return [
        {"id": 1, "name": "person",       "supercategory": "person",       "isthing": 1, "color": [220, 20, 60]},
        {"id": 2, "name": "bicycle",      "supercategory": "vehicle",      "isthing": 1, "color": [119, 11, 32]},
        {"id": 3, "name": "car",          "supercategory": "vehicle",      "isthing": 1, "color": [0, 0, 142]},
        {"id": 4, "name": "motorcycle",   "supercategory": "vehicle",      "isthing": 1, "color": [0, 0, 230]},
        {"id": 5, "name": "airplane",     "supercategory": "vehicle",      "isthing": 1, "color": [106, 0, 228]},
        {"id": 6, "name": "bus",          "supercategory": "vehicle",      "isthing": 1, "color": [0, 60, 100]},
        {"id": 7, "name": "train",        "supercategory": "vehicle",      "isthing": 1, "color": [0, 80, 100]},
        {"id": 8,  "name": "road",         "supercategory": "flat",         "isthing": 0, "color": [128, 64, 128]},
        {"id": 9,  "name": "sidewalk",     "supercategory": "flat",         "isthing": 0, "color": [244, 35, 232]},
        {"id": 10, "name": "vegetation",   "supercategory": "nature",       "isthing": 0, "color": [107, 142, 35]},
        {"id": 11, "name": "sky",          "supercategory": "sky",          "isthing": 0, "color": [70, 130, 180]},
    ]


def _derive_segment_id(image_idx: int, seg_idx: int, category_id: int) -> int:
    """生成 segment_id = (image_idx * 1000 + seg_idx) | (category_id << 21).
    这样 RGB 编码可保留类别信息.
    """
    return ((image_idx * 1000 + seg_idx) & 0x1FFFFF) | (category_id << 21)


def export(dataset, output: str, image_width: int = 64, image_height: int = 64,
           **kwargs) -> str:
    """导出 COCO Panoptic JSON + PNG masks.

    Args:
        dataset: DatasetVersion, 含 .files (image paths)
        output:  目标路径 (实际写出 ``output`` JSON + ``<output>_masks/`` PNG 目录)
        image_width: mock image width
        image_height: mock image height

    Returns:
        写入的 JSON 路径.
    """
    files: List[Any] = []
    if dataset is not None:
        files = list(getattr(dataset, "files", []) or [])

    out_path = output or "panoptic.json"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    masks_dir = os.path.splitext(out_path)[0] + "_masks"
    Path(masks_dir).mkdir(parents=True, exist_ok=True)

    categories = _default_categories()
    thing_cats = [c for c in categories if c["isthing"] == 1]
    stuff_cats = [c for c in categories if c["isthing"] == 0]

    images: List[Dict[str, Any]] = []
    annotations: List[Dict[str, Any]] = []
    seg_id = 1

    for i, f in enumerate(files):
        path = getattr(f, "path", "")
        images.append({
            "id": i,
            "file_name": os.path.basename(path) if path else f"image_{i:06d}.jpg",
            "height": image_height,
            "width": image_width,
            "modality_id": getattr(f, "modality_id", ""),
        })
        # 每张 image 假设 2 thing (人 + 车) + 2 stuff (路 + 天空)
        segs: List[Dict[str, Any]] = []
        n_pixels = image_width * image_height
        seg_ids_pixels = [0] * n_pixels
        # 简单 mock: 不同区域 (左半 / 右半 / 上半 / 下半) 分配不同 segment_id
        for kind, cat, frac in [
            ("thing", thing_cats[0], 0.25),  # person 1/4
            ("thing", thing_cats[2], 0.10),  # car 1/10
            ("stuff", stuff_cats[0], 0.30),  # road
            ("stuff", stuff_cats[3], 0.35),  # sky (top)
        ]:
            sid = _derive_segment_id(i, seg_id, cat["id"])
            seg_id += 1
            bbox = [0, 0, image_width, int(image_height * frac)]
            area = int(n_pixels * frac)
            segs.append({
                "id": sid,
                "category_id": cat["id"],
                "isthing": cat["isthing"],
                "bbox": bbox,
                "area": area,
            })
            # 给像素填 segment_id
            if kind == "thing":
                # 矩形区域 (1/4 居中)
                x_start = image_width // 4
                x_end = x_start + image_width // 4
                y_start = image_height // 4
                y_end = y_start + int(image_height * frac)
                for y in range(y_start, min(y_end, image_height)):
                    for x in range(x_start, min(x_end, image_width)):
                        seg_ids_pixels[y * image_width + x] = sid
            else:
                # stuff 占整行 (road bottom, sky top)
                if cat["name"] == "sky":
                    y_end = int(image_height * frac)
                    for y in range(0, y_end):
                        for x in range(image_width):
                            seg_ids_pixels[y * image_width + x] = sid
                else:
                    y_start = image_height - int(image_height * frac)
                    for y in range(y_start, image_height):
                        for x in range(image_width):
                            seg_ids_pixels[y * image_width + x] = sid

        png_filename = f"mask_{i:06d}.png"
        png_path = os.path.join(masks_dir, png_filename)
        png_bytes = _encode_panoptic_png(seg_ids_pixels, image_width, image_height)
        with open(png_path, "wb") as fh:
            fh.write(png_bytes)
        annotations.append({
            "image_id": i,
            "file_name": png_filename,
            "segments_info": segs,
        })

    doc = {
        "info": {
            "description": "COCO Panoptic Segmentation (nanobot-factory export)",
            "version": "1.0",
            "year": 2026,
        },
        "licenses": [{"id": 0, "name": "unknown", "url": ""}],
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out_path


def validate_coco_panoptic(doc: Dict[str, Any]) -> Dict[str, Any]:
    """验证 dict 是否为合法 COCO Panoptic JSON. 用于测试."""
    if not isinstance(doc, dict):
        return {"ok": False, "error": "not a dict"}
    for k in ("images", "annotations", "categories"):
        if k not in doc:
            return {"ok": False, "error": f"missing key: {k}"}
    images = doc["images"]
    annotations = doc["annotations"]
    categories = doc["categories"]
    if not isinstance(images, list) or not isinstance(annotations, list):
        return {"ok": False, "error": "images/annotations not lists"}
    n_thing = sum(1 for c in categories if c.get("isthing") == 1)
    n_stuff = sum(1 for c in categories if c.get("isthing") == 0)
    total_segments = sum(len(a.get("segments_info", [])) for a in annotations)
    return {
        "ok": True,
        "n_images": len(images),
        "n_annotations": len(annotations),
        "n_categories": len(categories),
        "n_thing_classes": n_thing,
        "n_stuff_classes": n_stuff,
        "total_segments": total_segments,
        "sample_categories": [c["name"] for c in categories[:5]],
    }


__all__ = ["export", "validate_coco_panoptic"]