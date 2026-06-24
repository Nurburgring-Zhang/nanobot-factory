"""annot.3d.3d_mesh — 3D mesh annotation operator.

Inputs:
    items: list of dicts {
        mesh_id?,
        vertices: [(x,y,z), ...]  (or N×3 array),
        faces: [[v0, v1, v2], ...],
        labels?: [{face_index|label, value}]
    }
    params:
        min_faces: int = 1
        max_faces: int = 1000000
        compute_bbox: bool = True
        compute_centroid: bool = True
        compute_surface_area: bool = True
        label_strategy: str = "face"   — face | vertex | none

Returns per-item: {item_index, ok, vertex_count, face_count, bbox, centroid, surface_area, labels}.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _as_vertices(verts: Any) -> List[List[float]]:
    out: List[List[float]] = []
    for v in verts or []:
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            out.append([float(v[0]), float(v[1]), float(v[2])])
        elif hasattr(v, "__len__") and len(v) >= 3:
            out.append([float(v[0]), float(v[1]), float(v[2])])
    return out


def _as_faces(faces: Any) -> List[List[int]]:
    out: List[List[int]] = []
    for f in faces or []:
        if isinstance(f, (list, tuple)) and len(f) >= 3:
            out.append([int(f[0]), int(f[1]), int(f[2])])
    return out


def _bbox(verts: List[List[float]]) -> Dict[str, List[float]]:
    if not verts:
        return {"min": [0, 0, 0], "max": [0, 0, 0]}
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}


def _centroid(verts: List[List[float]]) -> List[float]:
    if not verts:
        return [0.0, 0.0, 0.0]
    n = len(verts)
    sx = sum(v[0] for v in verts) / n
    sy = sum(v[1] for v in verts) / n
    sz = sum(v[2] for v in verts) / n
    return [round(sx, 4), round(sy, 4), round(sz, 4)]


def _triangle_area(a, b, c) -> float:
    ax, ay, az = a
    bx, by, bz = b
    cx, cy, cz = c
    abx, aby, abz = bx - ax, by - ay, bz - az
    acx, acy, acz = cx - ax, cy - ay, cz - az
    # cross product
    cx_, cy_, cz_ = (aby * acz - abz * acy,
                     abz * acx - abx * acz,
                     abx * acy - aby * acx)
    return 0.5 * (cx_ * cx_ + cy_ * cy_ + cz_ * cz_) ** 0.5


def _surface_area(verts: List[List[float]], faces: List[List[int]]) -> float:
    if not verts or not faces:
        return 0.0
    total = 0.0
    for f in faces:
        try:
            total += _triangle_area(verts[f[0]], verts[f[1]], verts[f[2]])
        except Exception:  # noqa: BLE001
            continue
    return total


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_f = int(params.get("min_faces", 1))
    max_f = int(params.get("max_faces", 1_000_000))
    do_bbox = bool(params.get("compute_bbox", True))
    do_centroid = bool(params.get("compute_centroid", True))
    do_area = bool(params.get("compute_surface_area", True))
    label_strategy = str(params.get("label_strategy", "face"))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict):
            rec.update({"ok": False, "error": "input_must_be_dict"})
            out.append(rec)
            continue
        verts = _as_vertices(item.get("vertices"))
        faces = _as_faces(item.get("faces"))
        ok = (min_f <= len(faces) <= max_f) and len(verts) >= 3
        rec.update({
            "ok": ok,
            "mesh_id": item.get("mesh_id"),
            "vertex_count": len(verts),
            "face_count": len(faces),
            "bbox": _bbox(verts) if do_bbox else None,
            "centroid": _centroid(verts) if do_centroid else None,
            "surface_area": round(_surface_area(verts, faces), 4) if do_area else None,
            "labels": item.get("labels") or [],
            "label_strategy": label_strategy,
        })
        out.append(rec)
    return out