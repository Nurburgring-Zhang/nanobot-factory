"""P19 v5.1-D3: Wavefront OBJ text exporter.

OBJ 是 ASCII 文本格式, 每行::

    v   x y z           (顶点)
    vn  nx ny nz        (顶点法线)
    vt  u v [w]         (顶点 UV)
    f   v1 v2 v3 ...    (face, 1-based index, 支持 v/vt/vn 形式)
    mtllib filename     (材质库引用)
    usemtl name         (使用材质)
    # comment

本 exporter 把 dataset 内 3D 文件 (obj/gltf/glb/ply) 拼接为一个 OBJ 文件;
若没有 3D 文件, 输出一个空 OBJ (只有 mtllib 注释 + 单位立方体 fallback).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import glb as _glb


def _gather_vertices(dataset) -> Tuple[List[float], List[float], List[int]]:
    """收集所有 3D 文件的顶点 / 法线 / indices."""
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


def _fallback_cube() -> Tuple[List[float], List[float], List[int]]:
    """空 dataset 时 fallback: 1x1 立方体的 8 顶点 + 12 三角面."""
    positions = [
        -0.5, -0.5, -0.5,
         0.5, -0.5, -0.5,
         0.5,  0.5, -0.5,
        -0.5,  0.5, -0.5,
        -0.5, -0.5,  0.5,
         0.5, -0.5,  0.5,
         0.5,  0.5,  0.5,
        -0.5,  0.5,  0.5,
    ]
    normals = [
        -0.577, -0.577, -0.577,
         0.577, -0.577, -0.577,
         0.577,  0.577, -0.577,
        -0.577,  0.577, -0.577,
        -0.577, -0.577,  0.577,
         0.577, -0.577,  0.577,
         0.577,  0.577,  0.577,
        -0.577,  0.577,  0.577,
    ]
    indices = [
        # -Z face
        1, 2, 3, 1, 3, 4,
        # +Z face
        5, 7, 6, 5, 8, 7,
        # -Y face
        1, 5, 6, 1, 6, 2,
        # +Y face
        3, 7, 8, 3, 8, 4,
        # -X face
        1, 4, 8, 1, 8, 5,
        # +X face
        2, 6, 7, 2, 7, 3,
    ]
    return positions, normals, indices


def export(dataset, output: str, **kwargs) -> str:
    """导出 dataset 内 3D 文件为 Wavefront OBJ 文本."""
    positions, normals, indices = _gather_vertices(dataset)
    if not positions:
        positions, normals, indices = _fallback_cube()

    n_vert = len(positions) // 3
    has_normals = len(normals) == n_vert * 3
    has_indices = len(indices) > 0

    out_path = output or "dataset.obj"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# Exported by nanobot-factory exports.obj")
    lines.append("# https://en.wikipedia.org/wiki/Wavefront_.obj_file")
    lines.append(f"# vertices={n_vert} faces={len(indices) // 3 if has_indices else 0}")
    lines.append("mtllib dataset.mtl")
    lines.append("usemtl default")

    # write positions (1-based: indices in OBJ)
    for i in range(n_vert):
        x = positions[3 * i]
        y = positions[3 * i + 1]
        z = positions[3 * i + 2]
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")

    if has_normals:
        for i in range(n_vert):
            nx = normals[3 * i]
            ny = normals[3 * i + 1]
            nz = normals[3 * i + 2]
            lines.append(f"vn {nx:.6f} {ny:.6f} {nz:.6f}")

    if has_indices:
        for i in range(0, len(indices), 3):
            # OBJ 索引 1-based, 支持 f v1 v2 v3
            try:
                a, b, c = indices[i], indices[i + 1], indices[i + 2]
                if has_normals:
                    # f v//vn
                    lines.append(f"f {a + 1}//{a + 1} {b + 1}//{b + 1} {c + 1}//{c + 1}")
                else:
                    lines.append(f"f {a + 1} {b + 1} {c + 1}")
            except Exception:
                pass
    else:
        # 没 indices 时, 简单写 "f" 引用 1,2,3... (三角形 fan), 仅当 n_vert >= 3
        if n_vert >= 3:
            if has_normals:
                lines.append(f"f 1//1 2//2 3//3")
            else:
                lines.append(f"f 1 2 3")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # 同时输出 .mtl 材质定义 (简单 Phong)
    mtl_path = os.path.splitext(out_path)[0] + ".mtl"
    with open(mtl_path, "w", encoding="utf-8") as fh:
        fh.write("# Exported by nanobot-factory\n")
        fh.write("newmtl default\n")
        fh.write("Ka 0.1 0.1 0.1\n")
        fh.write("Kd 0.8 0.8 0.8\n")
        fh.write("Ks 0.5 0.5 0.5\n")
        fh.write("Ns 32\n")
        fh.write("d 1.0\n")
        fh.write("illum 2\n")
    return out_path


def validate_obj(raw: str) -> Dict[str, Any]:
    """验证 raw 文本是否为合法 OBJ. 用于测试."""
    n_v = n_vt = n_vn = n_f = 0
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        head, _, _ = s.partition(" ")
        if head == "v":
            n_v += 1
        elif head == "vt":
            n_vt += 1
        elif head == "vn":
            n_vn += 1
        elif head == "f":
            n_f += 1
    if n_v == 0:
        return {"ok": False, "error": "no vertices"}
    return {
        "ok": True,
        "n_vertices": n_v,
        "n_normals": n_vn,
        "n_uvs": n_vt,
        "n_faces": n_f,
    }


__all__ = ["export", "validate_obj"]