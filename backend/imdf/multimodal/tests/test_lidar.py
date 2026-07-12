"""P19 v5.1: Tests for the LiDAR modality (LAS / LAZ / E57).

Verifies:
1. Modality registration (id, name, file_extensions).
2. Header parsing for LAS 1.4 / E57.
3. Processor → ModalityAsset round-trip on real bytes.
4. Validator (ok / error / warning).
5. Embedder 1024-dim.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from multimodal.lidar import (
    LIDAR_MODALITY,
    _parse_las,
    _parse_laz,
    _parse_e57,
)
from multimodal.business_modalities import (
    ModalityAsset,
    ModalityValidation,
    embed_asset,
    get_modality,
)


# ── fixtures: minimal valid LAS 1.4 file ──────────────────────────────────
def _make_las(point_count: int = 0) -> bytes:
    """LAS 1.4 with point-data-format 1, 0 VLRs, 0 points."""
    hdr = bytearray(227)
    hdr[0:4] = b"LASF"                 # signature
    hdr[4:6] = b"\x00\x00"             # file source id (unused)
    hdr[6:8] = b"\x00\x00"             # global encoding
    hdr[8:24] = b"\x00" * 16           # project id (4) + reserved (12)
    # version: 1.4 at offset 24
    hdr[24] = 1; hdr[25] = 4
    # system identifier 32 bytes
    hdr[26:58] = b"unit-test" + b"\x00" * 23
    # generating software 32 bytes
    hdr[58:90] = b"pytest" + b"\x00" * 27
    # file creation day / year
    hdr[90:92] = struct.pack("<H", 1)
    hdr[92:94] = struct.pack("<H", 2024)
    # header size
    hdr[94:96] = struct.pack("<H", 227)
    # offset to point data (just after header — no VLRs)
    hdr[96:100] = struct.pack("<I", 227)
    # number of VLRs
    hdr[100:104] = struct.pack("<I", 0)
    # point-data-format id (1 = GPS time)
    hdr[104] = 1
    hdr[105:107] = struct.pack("<H", 28)  # point size for format 1
    # legacy number of point records
    hdr[107:111] = struct.pack("<I", point_count)
    # legacy number of points by return (5×uint32)
    for i in range(5):
        hdr[111 + i * 4:111 + (i + 1) * 4] = struct.pack("<I", 0)
    # x scale / y scale / z scale (double)
    hdr[131:147] = struct.pack("<ddd", 0.01, 0.01, 0.01)
    # x / y / z offset
    hdr[147:171] = struct.pack("<ddd", 0.0, 0.0, 0.0)
    # bounding box (LAS 1.4: MaxX/MinX/MaxY/MinY/MaxZ/MinZ, all double)
    hdr[179:187] = struct.pack("<d", 100.0)   # Max X
    hdr[187:195] = struct.pack("<d", 0.0)     # Min X
    hdr[195:203] = struct.pack("<d", 100.0)   # Max Y
    hdr[203:211] = struct.pack("<d", 0.0)     # Min Y
    hdr[211:219] = struct.pack("<d", 100.0)   # Max Z
    hdr[219:227] = struct.pack("<d", 0.0)     # Min Z
    return bytes(hdr)


def _make_e57() -> bytes:
    return (
        b'<?xml version="1.0"?>\n'
        b'<E57Root guid="abc-123">\n'
        b'  <coordinateMetadata>foo</coordinateMetadata>\n'
        b'  <color>red</color>\n'
        b'  <classification>ground</classification>\n'
        b'</E57Root>\n'
    )


# ── 1. registration ──────────────────────────────────────────────────────
def test_lidar_registered():
    m = get_modality("lidar")
    assert m is LIDAR_MODALITY
    assert "激光雷达" in m.name["zh"]
    assert "LiDAR" in m.name["en"]
    for ext in (".las", ".laz", ".e57"):
        assert ext in m.file_extensions


def test_lidar_schema():
    s = LIDAR_MODALITY.schema
    for k in ("format", "n_points", "point_format", "min_xyz", "max_xyz",
              "has_gps_time", "has_rgb"):
        assert k in s


# ── 2. parsing ────────────────────────────────────────────────────────────
def test_parse_las_minimal():
    raw = _make_las(point_count=100)
    info = _parse_las(raw)
    assert info["format"] == "las"
    assert info["version"] == "1.4"
    assert info["n_points"] == 100
    assert info["point_format"] == 1
    assert info["has_gps_time"] is True
    assert info["min_xyz"] == [0.0, 0.0, 0.0]
    assert info["max_xyz"] == [100.0, 100.0, 100.0]


def test_parse_las_bad_signature():
    with pytest.raises(ValueError):
        _parse_las(b"\x00" * 300)


def test_parse_laz_delegates():
    raw = b"LASZ" + _make_las()[4:]
    info = _parse_laz(raw)
    assert info["format"] == "laz"


def test_parse_e57():
    info = _parse_e57(_make_e57())
    assert info["format"] == "e57"
    assert info["has_rgb"] is True
    assert info["has_classification"] is True


# ── 3. processor ──────────────────────────────────────────────────────────
def _tmp(tmp_path: Path, name: str, raw: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(raw)
    return str(p)


def test_processor_las(tmp_path):
    raw = _make_las(point_count=42)
    p = _tmp(tmp_path, "scan.las", raw)
    asset = LIDAR_MODALITY.processor(path=p, raw=raw, filename="scan.las")
    assert asset.modality_id == "lidar"
    assert asset.metadata["n_points"] == 42
    assert "LiDAR" in asset.text


def test_processor_e57(tmp_path):
    raw = _make_e57()
    p = _tmp(tmp_path, "scan.e57", raw)
    asset = LIDAR_MODALITY.processor(path=p, raw=raw, filename="scan.e57")
    assert asset.metadata["format"] == "e57"
    assert asset.metadata["has_rgb"] is True


# ── 4. validator ──────────────────────────────────────────────────────────
def test_validator_ok(tmp_path):
    raw = _make_las(point_count=10)
    p = _tmp(tmp_path, "good.las", raw)
    asset = LIDAR_MODALITY.processor(path=p, raw=raw, filename="good.las")
    v = LIDAR_MODALITY.validator(asset)
    assert v.ok is True


def test_validator_unsupported_format():
    asset = ModalityAsset(
        asset_id="x", modality_id="lidar",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"format": "pcd"},
    )
    v = LIDAR_MODALITY.validator(asset)
    assert v.ok is False


def test_validator_zero_points_warns():
    raw = _make_las(point_count=0)
    asset = ModalityAsset(
        asset_id="x", modality_id="lidar",
        canonical_kind="document", path="", sha256="abc", size=len(raw),
        mime="application/octet-stream", text="",
        metadata={"format": "las", "n_points": 0, "min_xyz": [0, 0, 0],
                  "max_xyz": [0, 0, 0], "has_gps_time": False, "has_rgb": False},
    )
    v = LIDAR_MODALITY.validator(asset)
    assert v.ok is True
    assert any("zero points" in w for w in v.warnings)


# ── 5. preview ────────────────────────────────────────────────────────────
def test_preview_format():
    asset = ModalityAsset(
        asset_id="x", modality_id="lidar",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"format": "las", "n_points": 7, "point_format": 3},
    )
    assert "LAS" in LIDAR_MODALITY.preview(asset)
    assert "7" in LIDAR_MODALITY.preview(asset)


# ── 6. embedder 1024-dim ──────────────────────────────────────────────────
def test_embedder_returns_1024_dim(tmp_path):
    raw = _make_las(50)
    p = _tmp(tmp_path, "scan.las", raw)
    asset = LIDAR_MODALITY.processor(path=p, raw=raw, filename="scan.las")
    vec = LIDAR_MODALITY.embedder(asset)
    assert len(vec) == 1024
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    assert 0.99 <= norm <= 1.01


def test_embed_asset_dispatch(tmp_path):
    raw = _make_las(20)
    p = _tmp(tmp_path, "scan.las", raw)
    asset = LIDAR_MODALITY.processor(path=p, raw=raw, filename="scan.las")
    vec = embed_asset(asset)
    assert len(vec) == 1024