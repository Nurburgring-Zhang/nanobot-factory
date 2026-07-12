"""P19 v5.1-D3: PLY (Stanford Polygon) exporter — text ascii flavor.

PLY 是 3D mesh / point cloud 通用格式::

    ply
    format ascii 1.0
    comment ...
    element vertex N
    property float x
    property float y
    property float z
    [property float nx ny nz]
    element face M
    property list uchar int vertex_indices
    end_header
    <x> <y> <z> [nx ny nz]
    ...
    <n1> <v1> <v2> <v3>
    ...

本 exporter 输出 ASCII PLY (无 numpy 依赖), 读取 dataset 内 3D 文件 → PLY.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import glb as _glb


def _gather(dataset) -> Tuple[List[float], List[float], List[int]]:
    positions: List[float] = []
    normals: List[float] = []
    indices: List[int] = []
    vertex_offset = 0
    if dataset is not None:
        for f in getattr(dataset, "files", []) or []:
            path = getattr(f, "path", "")
            if not path:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in {".obj", ".gltf", ".glb", ".ply"}:
                continue
            p, n, idx = _glb._load_vertices_from_file(path)
            positions.extend(p)
            if n and not normals:
                normals.extend(n)
            for i in idx:
                indices.append(i + vertex_offset)
            vertex_offset += len(p) // 3
    return positions, normals, indices


def export(dataset, output: str, **kwargs) -> str:
    positions, normals, indices = _gather(dataset)
    n_vert = len(positions) // 3
    has_normals = len(normals) == n_vert * 3
    n_faces = len(indices) // 3
    if n_vert == 0:
        # fallback: 单点 (0,0,0)
        positions = [0.0, 0.0, 0.0]
        normals = []
        indices = []
        n_vert = 1
        n_faces = 0

    out_path = output or "dataset.ply"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("ply")
    lines.append("format ascii 1.0")
    lines.append("comment Exported by nanobot-factory exports.ply")
    lines.append(f"element vertex {n_vert}")
    lines.append("property float x")
    lines.append("property float y")
    lines.append("property float z")
    if has_normals:
        lines.append("property float nx")
        lines.append("property float ny")
        lines.append("property float nz")
    if n_faces > 0:
        lines.append(f"element face {n_faces}")
        lines.append("property list uchar int vertex_indices")
    lines.append("end_header")

    for i in range(n_vert):
        x = positions[3 * i]
        y = positions[3 * i + 1]
        z = positions[3 * i + 2]
        if has_normals:
            nx = normals[3 * i]
            ny = normals[3 * i + 1]
            nz = normals[3 * i + 2]
            lines.append(f"{x:.6f} {y:.6f} {z:.6f} {nx:.6f} {ny:.6f} {nz:.6f}")
        else:
            lines.append(f"{x:.6f} {y:.6f} {z:.6f}")

    if n_faces > 0:
        for i in range(0, len(indices), 3):
            try:
                a, b, c = indices[i], indices[i + 1], indices[i + 2]
                lines.append(f"3 {a} {b} {c}")
            except Exception:
                pass

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out_path


def validate_ply(raw: str) -> Dict[str, Any]:
    """验证 raw 文本是否为合法 ASCII PLY."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "ply":
        return {"ok": False, "error": "missing 'ply' magic"}
    if "format ascii" not in raw:
        return {"ok": False, "error": "not ascii format"}
    if "end_header" not in raw:
        return {"ok": False, "error": "missing end_header"}
    n_vert = 0
    n_face = 0
    has_normal = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("element vertex"):
            try:
                n_vert = int(s.split()[2])
            except Exception:
                n_vert = 0
        elif s.startswith("element face"):
            try:
                n_face = int(s.split()[2])
            except Exception:
                n_face = 0
        elif s.startswith("property float nx"):
            has_normal = True
    return {"ok": True, "n_vertices": n_vert, "n_faces": n_face, "has_normals": has_normal}


__all__ = ["export", "validate_ply"]