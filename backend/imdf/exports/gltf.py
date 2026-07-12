"""P19 v5.1-D3: glTF 2.0 (JSON-only) exporter.

glTF 是一种 JSON 格式, 描述场景、mesh、accessor、bufferView、buffer;
外部二进制数据通过 ``buffer.uri`` 引用 (.bin 文件或 data URI)。

本 exporter 输出:
- 单个 .gltf JSON 文件 (内嵌 base64 buffer URI)
- 或者 .gltf + 旁边 .bin (无 base64, 体积更小)

简化设计: 我们直接复用 ``exports.glb`` 的 JSON chunk 构建逻辑, 把
BIN chunk 转为 base64 嵌进 buffer.uri, 输出单文件 .gltf.
"""
from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import glb as _glb


def _build_gltf_doc(positions: List[float], normals: List[float],
                    indices: List[int], embed_base64: bool = True) -> Tuple[Dict[str, Any], bytes]:
    """构造 glTF JSON + BIN bytes. (复用 glb 的 accessor / bufferView 逻辑)."""
    n_vert = len(positions) // 3
    n_idx = len(indices)
    has_normals = len(normals) == n_vert * 3
    has_indices = n_idx > 0

    bin_buf = bytearray()
    bin_buf.extend(struct.pack(f"<{n_vert * 3}f", *positions))
    pos_end = len(bin_buf)
    if has_normals:
        bin_buf.extend(struct.pack(f"<{n_vert * 3}f", *normals))
    norm_end = len(bin_buf)
    if has_indices:
        bin_buf.extend(struct.pack(f"<{n_idx}I", *indices))
    idx_end = len(bin_buf)
    while len(bin_buf) % 4 != 0:
        bin_buf.append(0)
    bin_len = len(bin_buf)

    buffer_views: List[Dict[str, Any]] = [
        {"buffer": 0, "byteOffset": 0, "byteLength": pos_end, "target": 34962},
    ]
    if has_normals:
        buffer_views.append({"buffer": 0, "byteOffset": pos_end, "byteLength": norm_end - pos_end, "target": 34962})
    if has_indices:
        buffer_views.append({"buffer": 0, "byteOffset": norm_end, "byteLength": idx_end - norm_end, "target": 34963})

    min_xyz = [0.0, 0.0, 0.0]
    max_xyz = [0.0, 0.0, 0.0]
    if n_vert > 0:
        xs = positions[0::3]
        ys = positions[1::3]
        zs = positions[2::3]
        if xs:
            min_xyz = [min(xs), min(ys), min(zs)]
            max_xyz = [max(xs), max(ys), max(zs)]
    accessors: List[Dict[str, Any]] = [
        {
            "bufferView": 0,
            "componentType": 5126,
            "count": n_vert,
            "type": "VEC3",
            "min": min_xyz,
            "max": max_xyz,
            "name": "POSITION",
        }
    ]
    bv_idx = 1
    if has_normals:
        accessors.append({"bufferView": bv_idx, "componentType": 5126, "count": n_vert, "type": "VEC3", "name": "NORMAL"})
        bv_idx += 1
    if has_indices:
        accessors.append({"bufferView": bv_idx, "componentType": 5125, "count": n_idx, "type": "SCALAR", "name": "indices"})

    mesh_prim_attrs: Dict[str, int] = {"POSITION": 0}
    if has_normals:
        mesh_prim_attrs["NORMAL"] = 1
    primitive: Dict[str, Any] = {"attributes": mesh_prim_attrs, "mode": 4}
    if has_indices:
        primitive["indices"] = 2 if has_normals else 1

    if embed_base64:
        uri = "data:application/octet-stream;base64," + base64.b64encode(bytes(bin_buf)).decode("ascii")
    else:
        uri = "dataset.bin"

    gltf_doc = {
        "asset": {"version": "2.0", "generator": "nanobot-factory exports.gltf"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [primitive]}],
        "buffers": [{"uri": uri, "byteLength": bin_len}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    return gltf_doc, bytes(bin_buf)


def export(dataset, output: str, **kwargs) -> str:
    """导出 dataset 内 3D 文件为 glTF JSON."""
    embed_base64 = bool(kwargs.get("embed_base64", True))
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
            if ext not in {".glb", ".gltf", ".obj", ".ply"}:
                continue
            p, n, idx = _glb._load_vertices_from_file(path)
            positions.extend(p)
            if n and not normals:
                normals.extend(n)
            for i in idx:
                indices.append(i + vertex_offset)
            vertex_offset += len(p) // 3
    doc, bin_buf = _build_gltf_doc(positions, normals, indices, embed_base64=embed_base64)
    out_path = output or "dataset.gltf"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    if not embed_base64 and bin_buf:
        bin_path = os.path.splitext(out_path)[0] + ".bin"
        with open(bin_path, "wb") as fh:
            fh.write(bin_buf)
    return out_path


def validate_gltf(raw: str) -> Dict[str, Any]:
    """验证 raw JSON 字符串是否为合法 glTF 2.0. 用于测试."""
    try:
        doc = json.loads(raw)
    except Exception as exc:
        return {"ok": False, "error": f"JSON parse error: {exc}"}
    if not isinstance(doc, dict):
        return {"ok": False, "error": "not an object"}
    asset = doc.get("asset", {})
    if asset.get("version", "") != "2.0":
        return {"ok": False, "error": f"asset.version != '2.0': {asset.get('version')!r}"}
    if not doc.get("scenes") or not doc.get("meshes"):
        return {"ok": False, "error": "missing scenes or meshes"}
    if not doc.get("buffers"):
        return {"ok": False, "error": "missing buffers"}
    return {
        "ok": True,
        "asset_version": asset.get("version"),
        "n_scenes": len(doc.get("scenes", [])),
        "n_meshes": len(doc.get("meshes", [])),
        "n_accessors": len(doc.get("accessors", [])),
        "n_buffers": len(doc.get("buffers", [])),
        "buffer_uri_kind": "base64" if (doc.get("buffers") or [{}])[0].get("uri", "").startswith("data:") else "external",
    }


__all__ = ["export", "validate_gltf"]