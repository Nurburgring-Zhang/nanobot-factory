"""annot.image.polygon — polygon annotation operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'polygons'?: [poly,...]}
    params:
        min_area: float = 4.0      — drop polygons below this area
        simplify: float = 0.0     — Douglas-Peucker tolerance (0 disables)
        max_vertices: int = 1000  — cap per polygon
        auto_contour: bool = False — auto-extract contours via cv2.findContours

Each polygon must have 'points': [(x,y),...]. Optional: label, score, holes.

Returns per-image: {image_index, ok, count, polygons, image_shape}.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, ensure_numpy_bgr, load_image_any, polygon_area


def _validate(poly: Dict[str, Any]) -> Dict[str, Any]:
    pts = poly.get("points") or []
    out = {
        "id": poly.get("id") or f"poly_{uuid.uuid4().hex[:8]}",
        "label": str(poly.get("label", "region")),
        "score": float(poly.get("score", 1.0)),
        "points": [tuple(map(float, p)) for p in pts],
        "holes": [[tuple(map(float, p)) for p in h] for h in poly.get("holes", [])] or [],
    }
    return out


def _simplify(points: list, tol: float) -> list:
    if tol <= 0 or len(points) < 3:
        return points
    if not _HAS_CV2:
        return points
    try:
        arr = __import__("numpy").asarray(points, dtype="float32").reshape(-1, 1, 2)
        simp = cv2.approxPolyDP(arr, tol, True)
        return [tuple(map(float, p[0])) for p in simp]
    except Exception:  # noqa: BLE001
        return points


def _auto_contours(img: Any, min_area: float) -> List[Dict[str, Any]]:
    if not _HAS_CV2:
        return []
    arr = ensure_numpy_bgr(img)
    if arr is None:
        return []
    try:
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 200)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except Exception:  # noqa: BLE001
        return []
    out: List[Dict[str, Any]] = []
    for c in contours:
        pts = [(float(p[0][0]), float(p[0][1])) for p in c]
        if polygon_area(pts) >= min_area:
            out.append({"points": pts, "label": "auto_contour", "score": 1.0})
    return out


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_area = float(params.get("min_area", 4.0))
    simplify = float(params.get("simplify", 0.0))
    max_v = int(params.get("max_vertices", 1000))
    auto = bool(params.get("auto_contour", False))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        img_input = item.get("image") if isinstance(item, dict) and "image" in item else (
            {k: v for k, v in item.items() if k != "polygons"}
            if isinstance(item, dict) else item
        )
        img, meta = load_image_any(img_input)
        rec: Dict[str, Any] = {"image_index": i, "image_meta": meta}
        if img is None:
            rec.update({"ok": False, "count": 0, "polygons": []})
            out.append(rec)
            continue
        raw_polys: List[Dict[str, Any]] = []
        if isinstance(item, dict) and isinstance(item.get("polygons"), list):
            raw_polys = [_validate(p) for p in item["polygons"]]
        if auto:
            raw_polys.extend(_validate(p) for p in _auto_contours(img, min_area))
        kept: List[Dict[str, Any]] = []
        for p in raw_polys:
            pts = _simplify(p["points"], simplify)
            if len(pts) > max_v:
                pts = pts[:max_v]
            p["points"] = pts
            if polygon_area(pts) >= min_area and len(pts) >= 3:
                kept.append(p)
        rec.update({"ok": True, "count": len(kept), "polygons": kept})
        out.append(rec)
    return out