"""P19 v5.1: 3D PointCloud modality — GLB / glTF / OBJ / PLY.

GLB / glTF (binary JSON-wrapped geometry):

    header: 'glTF'  + version(uint32) + length(uint32)
    JSON chunk: { asset, scenes, meshes, accessors, bufferViews, buffers }
    BIN chunk : raw vertex / index / texture data

OBJ (Wavefront text format): vertices ``v x y z``, faces ``f i j k``.

PLY (Stanford polygon format): header text + ascii/binary vertex payload.

Schema (canonical — what the validator checks):

    {
        "format": "glb" | "gltf" | "obj" | "ply",
        "n_vertices": int,
        "n_faces":    int,
        "has_normals":   bool,
        "has_uvs":       bool,
        "has_materials": bool,
        "has_textures":  bool,
    }
"""
from __future__ import annotations

import json
import logging
import os
import struct
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


# ── Parsers (each returns a Dict[str, Any] matching the schema) ───────────
def _parse_glb(raw: bytes) -> Dict[str, Any]:
    """Minimal GLB parser: header + JSON chunk + (skip) BIN chunk.

    Returns: ``{"format": "glb", "n_vertices": int, "n_faces": int, ...}``.
    Falls back to empty schema on parse error (validator will flag it).
    """
    if len(raw) < 12 or raw[:4] != b"glTF":
        raise ValueError("not a GLB file (missing 'glTF' magic)")
    version, length = struct.unpack("<II", raw[4:12])
    if length > len(raw):
        raise ValueError(f"GLB length mismatch: header={length}, file={len(raw)}")
    # JSON chunk header: chunk_length(uint32) + chunk_type('JSON')
    if len(raw) < 20:
        raise ValueError("GLB JSON chunk header missing")
    json_len = struct.unpack("<I", raw[12:16])[0]
    json_type = raw[16:20]
    if json_type != b"JSON":
        raise ValueError(f"GLB first chunk is {json_type!r}, expected 'JSON'")
    json_bytes = raw[20:20 + json_len]
    try:
        doc = json.loads(json_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"GLB JSON chunk parse error: {exc}") from exc

    accessors = doc.get("accessors", []) or []
    meshes = doc.get("meshes", []) or []
    n_vertices = 0
    n_faces = 0
    has_normals = False
    has_uvs = False
    has_materials = bool(doc.get("materials"))
    has_textures = bool(doc.get("textures"))
    for acc in accessors:
        atype = acc.get("type", "").upper()
        count = int(acc.get("count", 0) or 0)
        if atype == "VEC3" and "POSITION" in (acc.get("name", "") or "").upper():
            n_vertices += count
        if atype == "SCALAR" and "indices" in (acc.get("name", "") or "").lower():
            n_faces += count // 3
    # Always scan mesh primitives — these are independent of the
    # POSITION-name detection above.  We only fall back to mesh-primitives
    # for n_vertices / n_faces when the accessor scan didn't catch them,
    # otherwise we'd double-count.
    for mesh in meshes:
        for prim in mesh.get("primitives", []) or []:
            attrs = prim.get("attributes", {}) or {}
            if "NORMAL" in attrs:
                has_normals = True
            if "TEXCOORD_0" in attrs:
                has_uvs = True
            # fall back: fill n_vertices if accessor-by-name didn't catch it
            if n_vertices == 0 and "POSITION" in attrs:
                acc_idx = attrs["POSITION"]
                if 0 <= acc_idx < len(accessors):
                    n_vertices += int(accessors[acc_idx].get("count", 0))
            # fall back: indices → face count (only if accessor-name detection missed it)
            if n_faces == 0:
                idx = prim.get("indices")
                if idx is not None and 0 <= idx < len(accessors):
                    n_faces += int(accessors[idx].get("count", 0)) // 3
    return {
        "format": "glb",
        "version": version,
        "n_vertices": n_vertices,
        "n_faces": n_faces,
        "has_normals": has_normals,
        "has_uvs": has_uvs,
        "has_materials": has_materials,
        "has_textures": has_textures,
        "asset_version": (doc.get("asset") or {}).get("version", ""),
    }


def _parse_gltf(raw: bytes) -> Dict[str, Any]:
    """glTF (JSON-only) — same schema as GLB minus binary chunks."""
    doc = json.loads(raw.decode("utf-8"))
    return _parse_glb(b"glTF" + b"\x02\x00\x00\x00" + struct.pack("<I", len(raw) + 12) + struct.pack("<I", len(raw)) + b"JSON" + raw + b"BIN\x00\x00\x00\x00")


def _parse_obj(raw: bytes) -> Dict[str, Any]:
    """OBJ text parser — counts vertices and faces, looks for ``vn``/``vt``."""
    text = raw.decode("utf-8", errors="ignore")
    n_v = n_vt = n_vn = n_f = 0
    has_materials = False
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        head, _, rest = s.partition(" ")
        if head == "v":
            n_v += 1
        elif head == "vt":
            n_vt += 1
        elif head == "vn":
            n_vn += 1
        elif head == "f":
            n_f += 1
        elif head in ("mtllib", "usemtl"):
            has_materials = True
    return {
        "format": "obj",
        "n_vertices": n_v,
        "n_faces": n_f,
        "has_normals": n_vn > 0,
        "has_uvs": n_vt > 0,
        "has_materials": has_materials,
        "has_textures": has_materials,
    }


def _parse_ply(raw: bytes) -> Dict[str, Any]:
    """PLY parser — handles ascii and binary_little_endian formats."""
    if not raw.startswith(b"ply"):
        raise ValueError("not a PLY file (missing 'ply' magic)")
    header_end = raw.find(b"end_header\n")
    if header_end < 0:
        header_end = raw.find(b"end_header\r\n")
    if header_end < 0:
        raise ValueError("PLY header end marker not found")
    header = raw[:header_end].decode("ascii", errors="ignore")
    is_binary = "binary_little_endian" in header or "binary_big_endian" in header
    n_vertices = 0
    for line in header.splitlines():
        if line.startswith("element vertex"):
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "vertex":
                try:
                    n_vertices = int(parts[2])
                except ValueError:
                    n_vertices = 0
    if not is_binary:
        # ascii body — count "f " or vertex rows
        body = raw[header_end:].decode("ascii", errors="ignore")
        rows = [ln for ln in body.splitlines() if ln.strip() and not ln.startswith("comment")]
        return {
            "format": "ply",
            "n_vertices": n_vertices or len(rows),
            "n_faces": 0,
            "has_normals": "property float nx" in header,
            "has_uvs": False,
            "has_materials": False,
            "has_textures": False,
        }
    return {
        "format": "ply",
        "n_vertices": n_vertices,
        "n_faces": 0,
        "has_normals": "property float nx" in header,
        "has_uvs": False,
        "has_materials": False,
        "has_textures": False,
    }


# ── Processor ──────────────────────────────────────────────────────────────
def _processor(path: str = "", raw: bytes = b"", filename: str = "") -> ModalityAsset:
    data = raw if raw else _safe_read(path)
    sha = _sha256_bytes(data)
    ext = os.path.splitext(filename or path)[1].lower()
    fmt = ext.lstrip(".")
    metadata: Dict[str, Any] = {"filename": filename or os.path.basename(path)}
    text_preview = ""
    try:
        if fmt == "glb":
            metadata.update(_parse_glb(data))
        elif fmt == "gltf":
            metadata.update(_parse_gltf(data))
        elif fmt == "obj":
            metadata.update(_parse_obj(data))
        elif fmt == "ply":
            metadata.update(_parse_ply(data))
        else:
            metadata["error"] = f"unknown 3D format: {fmt}"
    except Exception as exc:  # noqa: BLE001
        metadata["error"] = str(exc)

    n_v = int(metadata.get("n_vertices", 0) or 0)
    n_f = int(metadata.get("n_faces", 0) or 0)
    text_preview = (
        f"3D pointcloud/mesh [{fmt}]: {n_v} vertices, {n_f} faces, "
        f"normals={metadata.get('has_normals', False)}, "
        f"uvs={metadata.get('has_uvs', False)}, "
        f"materials={metadata.get('has_materials', False)}"
    )
    return ModalityAsset(
        asset_id=_new_asset_id("three_d"),
        modality_id="three_d_pointcloud",
        canonical_kind="document",  # 3D meshes map to document for legacy storage
        path=path,
        sha256=sha,
        size=len(data),
        mime={
            "glb": "model/gltf-binary",
            "gltf": "model/gltf+json",
            "obj": "model/obj",
            "ply": "application/octet-stream",
        }.get(fmt, "application/octet-stream"),
        text=text_preview,
        metadata=metadata,
    )


# ── Validator ──────────────────────────────────────────────────────────────
def _validator(asset: ModalityAsset) -> ModalityValidation:
    errs: List[str] = []
    warns: List[str] = []
    md = asset.metadata or {}
    fmt = md.get("format") or ""
    if fmt not in {"glb", "gltf", "obj", "ply"}:
        errs.append(f"unsupported 3D format: {fmt!r}")
    if not md.get("error"):
        if md.get("n_vertices", 0) <= 0:
            warns.append("zero vertices — empty mesh?")
    else:
        errs.append(f"parse error: {md['error']}")
    return ModalityValidation(ok=not errs, errors=errs, warnings=warns)


# ── Preview + embedder ────────────────────────────────────────────────────
def _preview(asset: ModalityAsset) -> str:
    md = asset.metadata or {}
    return (
        f"3D {md.get('format', '?').upper()} "
        f"v={md.get('n_vertices', 0)} f={md.get('n_faces', 0)} "
        f"normals={md.get('has_normals', False)} uvs={md.get('has_uvs', False)}"
    )


def _embedder(asset: ModalityAsset) -> List[float]:
    """Combine structural metadata fingerprint with byte fingerprint."""
    data = _safe_read(asset.path)
    # structural component: encode (n_vertices, n_faces, flags) as a feature vector
    md = asset.metadata or {}
    feats = np.array(
        [
            float(md.get("n_vertices", 0) or 0),
            float(md.get("n_faces", 0) or 0),
            float(md.get("has_normals", False)),
            float(md.get("has_uvs", False)),
            float(md.get("has_materials", False)),
            float(md.get("has_textures", False)),
            float(asset.size),
        ],
        dtype=np.float32,
    )
    # log-scale the count fields so big meshes don't blow out the fingerprint
    feats[:2] = np.log1p(feats[:2])
    struct = _statistical_fingerprint(feats.reshape(1, -1))
    byts = _hash_fingerprint(data)
    # weighted blend
    out = 0.4 * struct + 0.6 * byts
    n = float(np.linalg.norm(out)) or 1.0
    return (out / n).tolist()


# ── Modality registration ─────────────────────────────────────────────────
THREE_D_SCHEMA: Dict[str, Any] = {
    "format": "glb | gltf | obj | ply",
    "n_vertices": "int",
    "n_faces": "int",
    "has_normals": "bool",
    "has_uvs": "bool",
    "has_materials": "bool",
    "has_textures": "bool",
}

THREE_D_MODALITY = Modality(
    id="three_d_pointcloud",
    name={"zh": "三维点云 / 网格", "en": "3D PointCloud / Mesh"},
    file_extensions=[".glb", ".gltf", ".obj", ".ply"],
    canonical_kind="document",
    schema=THREE_D_SCHEMA,
    processor=_processor,
    validator=_validator,
    preview=_preview,
    embedder=_embedder,
    description=(
        "3D point cloud / mesh formats (GLB, glTF, OBJ, PLY). Used for "
        "spatial-scene datasets, robotics and digital-twin training."
    ),
)


def install() -> Modality:
    return register_modality(THREE_D_MODALITY)


__all__ = [
    "THREE_D_MODALITY",
    "THREE_D_SCHEMA",
    "install",
    "_parse_glb",
    "_parse_gltf",
    "_parse_obj",
    "_parse_ply",
]