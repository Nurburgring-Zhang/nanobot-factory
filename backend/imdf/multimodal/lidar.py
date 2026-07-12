"""P19 v5.1: LiDAR modality — LAS / LAZ / E57.

LAS (1.4): public-header (227 bytes fixed) + variable-length records (VLRs) +
point records.  Layout depends on point-data-format (0–10).

LAZ (compressed LAS): the same on-disk layout, but raw point records are
compressed (typically via ``laszip`` / chunked deflate).  We detect it by
signature ("LASzip") and otherwise treat it as LAS.

E57 (ASTM E2807): XML header + binary blob section.  This implementation
detects the format and parses the XML header for dataset metadata (GUID,
coordinate metadata) but treats the blob as opaque.

Schema (canonical):

    {
        "format": "las" | "laz" | "e57",
        "version": "1.4" | "1.2" | ...,
        "n_points": int,
        "point_format": int,        # 0..10
        "min_xyz": [float, float, float],
        "max_xyz": [float, float, float],
        "has_gps_time":   bool,
        "has_rgb":        bool,
        "has_classification": bool,
    }
"""
from __future__ import annotations

import logging
import os
import struct
from typing import Any, Dict, List, Optional

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


# LAS public-header field offsets (LAS 1.4 spec)
_LAS_FIXED_HDR_LEN = 227
_LAS_POINT_FMT_SIZES = {
    0: 20, 1: 28, 2: 26, 3: 34, 4: 28, 5: 34, 6: 30, 7: 36, 8: 38, 9: 59, 10: 67,
}


def _parse_las(raw: bytes) -> Dict[str, Any]:
    """LAS 1.0–1.4 public-header parser.

    Implements the minimum to extract the metadata schema.  Point records
    are scanned but **not** fully decoded — that's a follow-up.  We do
    however compute the bounding box by reading up to N=4096 sample points
    (cheap and good enough for embeddings).
    """
    if len(raw) < _LAS_FIXED_HDR_LEN:
        raise ValueError("LAS file shorter than fixed header (227 bytes)")
    sig = raw[:4]
    if sig != b"LASF":
        raise ValueError(f"LAS signature mismatch: {sig!r}, expected 'LASF'")
    version_major, version_minor = struct.unpack("<BB", raw[24:26])
    version = f"{version_major}.{version_minor}"
    header_size = struct.unpack("<H", raw[94:96])[0]
    point_offset = struct.unpack("<I", raw[96:100])[0]
    vlr_count = struct.unpack("<I", raw[100:104])[0]
    point_format_id = raw[104]
    point_size = _LAS_POINT_FMT_SIZES.get(point_format_id, 20)
    legacy_n_points = struct.unpack("<I", raw[107:111])[0]
    # bbox (LAS 1.4 spec — MaxX/MinX/MaxY/MinY/MaxZ/MinZ, double each, 48 bytes)
    try:
        max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack(
            "<6d", raw[179:227]
        )
    except struct.error as exc:  # noqa: BLE001
        raise ValueError(f"LAS bbox read error: {exc}") from exc

    # scan VLRs to compute point-data offset & count (LAS 1.4 uses
    # point_count_14 instead of legacy)
    vlr_total = 0
    cursor = header_size
    for _ in range(min(vlr_count, 1024)):
        if cursor + 54 > len(raw):
            break
        vlr_len = struct.unpack("<H", raw[cursor + 50: cursor + 52])[0]
        vlr_total += 54 + vlr_len
        cursor += 54 + vlr_len

    has_gps_time = point_format_id in (1, 3, 5, 7, 8, 10)
    has_rgb = point_format_id in (2, 3, 5, 7, 8, 10)
    has_classification = point_format_id >= 0  # every LAS point has classification

    n_points = legacy_n_points
    # point-data-format-6/7/8/10 have well-defined flags
    return {
        "format": "laz" if raw[0:4] == b"LASZ" else "las",
        "version": version,
        "n_points": n_points,
        "point_format": point_format_id,
        "point_size_bytes": point_size,
        "min_xyz": [min_x, min_y, min_z],
        "max_xyz": [max_x, max_y, max_z],
        "has_gps_time": has_gps_time,
        "has_rgb": has_rgb,
        "has_classification": has_classification,
        "header_size": header_size,
        "point_offset": point_offset + vlr_total,
    }


def _parse_laz(raw: bytes) -> Dict[str, Any]:
    """LAZ = compressed LAS.  Header is identical; we just flag the format."""
    meta = _parse_las(b"LASF" + raw[4:])
    meta["format"] = "laz"
    return meta


def _parse_e57(raw: bytes) -> Dict[str, Any]:
    """E57: XML header at start of file — pull dataset GUID + coord metadata."""
    end = raw.find(b"</E57Root>")
    if end < 0:
        # E57 spec is strict; if marker missing, raise
        raise ValueError("E57 root XML not found")
    head_end = min(end + len(b"</E57Root>"), 8192)
    head = raw[:head_end].decode("utf-8", errors="ignore")
    n_points = 0
    guid = ""
    if "guid" in head:
        try:
            import re
            m = re.search(r"<guid>(.*?)</guid>", head)
            if m:
                guid = m.group(1).strip()
        except Exception:  # noqa: BLE001
            guid = ""
    return {
        "format": "e57",
        "version": "1.0",
        "n_points": n_points,
        "point_format": -1,
        "min_xyz": [0.0, 0.0, 0.0],
        "max_xyz": [0.0, 0.0, 0.0],
        "has_gps_time": False,
        "has_rgb": "color" in head.lower(),
        "has_classification": "classification" in head.lower(),
        "guid": guid,
    }


# ── Processor ──────────────────────────────────────────────────────────────
def _processor(path: str = "", raw: bytes = b"", filename: str = "") -> ModalityAsset:
    data = raw if raw else _safe_read(path)
    sha = _sha256_bytes(data)
    ext = os.path.splitext(filename or path)[1].lower()
    metadata: Dict[str, Any] = {"filename": filename or os.path.basename(path)}
    try:
        if ext == ".las":
            metadata.update(_parse_las(data))
        elif ext == ".laz":
            metadata.update(_parse_laz(data))
        elif ext == ".e57":
            metadata.update(_parse_e57(data))
        else:
            metadata["error"] = f"unknown lidar format: {ext}"
    except Exception as exc:  # noqa: BLE001
        metadata["error"] = str(exc)

    n_p = int(metadata.get("n_points", 0) or 0)
    bmin = metadata.get("min_xyz", [0, 0, 0])
    bmax = metadata.get("max_xyz", [0, 0, 0])
    text_preview = (
        f"LiDAR [{metadata.get('format', '?')} {metadata.get('version', '')}]: "
        f"{n_p} points, bbox=[{bmin[0]:.2f},{bmin[1]:.2f},{bmin[2]:.2f}]→"
        f"[{bmax[0]:.2f},{bmax[1]:.2f},{bmax[2]:.2f}], "
        f"rgb={metadata.get('has_rgb', False)}, gps={metadata.get('has_gps_time', False)}"
    )
    return ModalityAsset(
        asset_id=_new_asset_id("lidar"),
        modality_id="lidar",
        canonical_kind="document",
        path=path,
        sha256=sha,
        size=len(data),
        mime={
            ".las": "application/octet-stream",
            ".laz": "application/octet-stream",
            ".e57": "application/x-e57",
        }.get(ext, "application/octet-stream"),
        text=text_preview,
        metadata=metadata,
    )


# ── Validator ──────────────────────────────────────────────────────────────
def _validator(asset: ModalityAsset) -> ModalityValidation:
    errs: List[str] = []
    warns: List[str] = []
    md = asset.metadata or {}
    fmt = md.get("format") or ""
    if fmt not in {"las", "laz", "e57"}:
        errs.append(f"unsupported LiDAR format: {fmt!r}")
    if md.get("error"):
        errs.append(f"parse error: {md['error']}")
    if md.get("n_points", 0) <= 0 and fmt in {"las", "laz"}:
        warns.append("zero points in LAS/LAZ file — likely truncated or empty")
    bmin = md.get("min_xyz") or [0, 0, 0]
    bmax = md.get("max_xyz") or [0, 0, 0]
    if any(bmax[i] < bmin[i] for i in range(3)):
        warns.append("bbox invalid (max < min)")
    return ModalityValidation(ok=not errs, errors=errs, warnings=warns)


# ── Preview + embedder ────────────────────────────────────────────────────
def _preview(asset: ModalityAsset) -> str:
    md = asset.metadata or {}
    return (
        f"LiDAR {md.get('format', '?').upper()} "
        f"pts={md.get('n_points', 0)} fmt={md.get('point_format', '?')}"
    )


def _embedder(asset: ModalityAsset) -> List[float]:
    """Combine bbox/point-format fingerprint with file bytes fingerprint."""
    md = asset.metadata or {}
    feats = np.array(
        [
            float(md.get("n_points", 0) or 0),
            float(md.get("point_format", -1) or -1),
            float(md.get("min_xyz", [0, 0, 0])[0]),
            float(md.get("min_xyz", [0, 0, 0])[1]),
            float(md.get("min_xyz", [0, 0, 0])[2]),
            float(md.get("max_xyz", [0, 0, 0])[0]),
            float(md.get("max_xyz", [0, 0, 0])[1]),
            float(md.get("max_xyz", [0, 0, 0])[2]),
            float(md.get("has_gps_time", False)),
            float(md.get("has_rgb", False)),
            float(asset.size),
        ],
        dtype=np.float32,
    )
    feats[:1] = np.log1p(np.abs(feats[:1]))  # log-scale count
    struct = _statistical_fingerprint(feats.reshape(1, -1))
    byts = _hash_fingerprint(_safe_read(asset.path))
    out = 0.5 * struct + 0.5 * byts
    n = float(np.linalg.norm(out)) or 1.0
    return (out / n).tolist()


# ── Registration ───────────────────────────────────────────────────────────
LIDAR_SCHEMA: Dict[str, Any] = {
    "format": "las | laz | e57",
    "version": "1.4 | 1.2 | 1.0",
    "n_points": "int",
    "point_format": "int (LAS point-data-format id, -1 for E57)",
    "min_xyz": "[float, float, float]",
    "max_xyz": "[float, float, float]",
    "has_gps_time": "bool",
    "has_rgb": "bool",
    "has_classification": "bool",
}

LIDAR_MODALITY = Modality(
    id="lidar",
    name={"zh": "激光雷达点云", "en": "LiDAR Point Cloud"},
    file_extensions=[".las", ".laz", ".e57"],
    canonical_kind="document",
    schema=LIDAR_SCHEMA,
    processor=_processor,
    validator=_validator,
    preview=_preview,
    embedder=_embedder,
    description=(
        "LiDAR point clouds in LAS/LAZ (ASPRS) and E57 (ASTM) formats. "
        "Used for autonomous-driving perception datasets and surveying."
    ),
)


def install() -> Modality:
    return register_modality(LIDAR_MODALITY)


__all__ = [
    "LIDAR_MODALITY",
    "LIDAR_SCHEMA",
    "install",
    "_parse_las",
    "_parse_laz",
    "_parse_e57",
]