"""P19 v5.1: Tests for the 3D PointCloud modality (GLB / glTF / OBJ / PLY).

Verifies:
1. The modality is registered (id, name, file_extensions).
2. The processor produces a ``ModalityAsset`` for each supported format.
3. The validator returns ok=True for a valid file and ok=False for garbage.
4. The embedder returns a 1024-dim L2-normalised vector.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from multimodal.three_d import (
    THREE_D_MODALITY,
    _parse_glb,
    _parse_gltf,
    _parse_obj,
    _parse_ply,
)
from multimodal.business_modalities import (
    ModalityAsset,
    ModalityValidation,
    embed_asset,
    get_modality,
)


# ── fixtures: tiny valid files for each format ────────────────────────────
def _make_glb() -> bytes:
    """Minimal GLB v2: 1 mesh, 1 primitive, 4 vertices, 2 faces (indices)."""
    # Build a minimal glTF JSON
    g = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [{"name": "m0"}],
        "accessors": [
            {"count": 4, "type": "VEC3", "name": "POSITION"},
            {"count": 4, "type": "VEC3", "name": "NORMAL"},
            {"count": 6, "type": "SCALAR", "name": "indices"},
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0}],
        "buffers": [{"byteLength": 0}],
    }
    j = json.dumps(g).encode("utf-8")
    pad = (-len(j)) % 4
    j = j + b" " * pad
    binchunk = b""
    binpad = (-len(binchunk)) % 4
    binchunk = binchunk + b"\x00" * binpad
    j_len = len(j)
    b_len = len(binchunk)
    header = b"glTF" + struct.pack("<II", 2, 12 + 8 + j_len + 8 + b_len)
    json_chunk = struct.pack("<I", j_len) + b"JSON" + j
    bin_chunk = struct.pack("<I", b_len) + b"BIN\x00" + binchunk
    return header + json_chunk + bin_chunk


def _make_gltf() -> bytes:
    return json.dumps({
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"count": 8, "type": "VEC3", "name": "POSITION"}],
    }).encode("utf-8")


def _make_obj() -> bytes:
    return (
        b"# Wavefront OBJ\n"
        b"v 0.0 0.0 0.0\n"
        b"v 1.0 0.0 0.0\n"
        b"v 0.0 1.0 0.0\n"
        b"vn 0.0 0.0 1.0\n"
        b"vt 0.0 0.0\n"
        b"f 1 2 3\n"
        b"f 1 2 3\n"
        b"usemtl default\n"
    )


def _make_ply() -> bytes:
    return (
        b"ply\n"
        b"format ascii 1.0\n"
        b"comment test\n"
        b"element vertex 3\n"
        b"property float x\n"
        b"property float y\n"
        b"property float z\n"
        b"property float nx\n"
        b"property float ny\n"
        b"property float nz\n"
        b"end_header\n"
        b"0 0 0 0 0 1\n"
        b"1 0 0 0 0 1\n"
        b"0 1 0 0 0 1\n"
    )


# ── 1. registration ──────────────────────────────────────────────────────
def test_three_d_registered():
    m = get_modality("three_d_pointcloud")
    assert m is THREE_D_MODALITY
    assert m.id == "three_d_pointcloud"
    assert "三维点云" in m.name["zh"]
    assert "3D" in m.name["en"]
    for ext in (".glb", ".gltf", ".obj", ".ply"):
        assert ext in m.file_extensions, f"missing extension: {ext}"


def test_three_d_schema_fields():
    s = THREE_D_MODALITY.schema
    for k in ("format", "n_vertices", "n_faces", "has_normals", "has_uvs"):
        assert k in s


# ── 2. parsing ────────────────────────────────────────────────────────────
def test_parse_glb_minimal():
    raw = _make_glb()
    info = _parse_glb(raw)
    assert info["format"] == "glb"
    assert info["n_vertices"] == 4
    assert info["n_faces"] == 2
    assert info["has_materials"] is True
    assert info["has_normals"] is True


def test_parse_gltf_minimal():
    info = _parse_gltf(_make_gltf())
    assert info["format"] == "glb"  # _parse_gltf wraps _parse_glb
    assert info["n_vertices"] == 8


def test_parse_obj():
    info = _parse_obj(_make_obj())
    assert info["format"] == "obj"
    assert info["n_vertices"] == 3
    assert info["n_faces"] == 2
    assert info["has_normals"] is True
    assert info["has_uvs"] is True
    assert info["has_materials"] is True


def test_parse_ply_ascii():
    info = _parse_ply(_make_ply())
    assert info["format"] == "ply"
    assert info["n_vertices"] == 3
    assert info["has_normals"] is True


def test_parse_glb_garbage():
    with pytest.raises(ValueError):
        _parse_glb(b"NOT A GLB FILE")


# ── 3. processor (mock file → ModalityAsset) ───────────────────────────────
def _tmp_file(tmp_path: Path, name: str, raw: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(raw)
    return str(p)


def test_processor_glb(tmp_path):
    p = _tmp_file(tmp_path, "scene.glb", _make_glb())
    asset = THREE_D_MODALITY.processor(path=p, raw=_make_glb(), filename="scene.glb")
    assert isinstance(asset, ModalityAsset)
    assert asset.modality_id == "three_d_pointcloud"
    assert asset.canonical_kind == "document"
    assert asset.mime == "model/gltf-binary"
    assert asset.metadata["n_vertices"] == 4
    assert "3D pointcloud" in asset.text


def test_processor_obj(tmp_path):
    p = _tmp_file(tmp_path, "scene.obj", _make_obj())
    asset = THREE_D_MODALITY.processor(path=p, raw=_make_obj(), filename="scene.obj")
    assert asset.metadata["n_vertices"] == 3
    assert asset.metadata["format"] == "obj"
    assert asset.mime == "model/obj"


def test_processor_ply(tmp_path):
    p = _tmp_file(tmp_path, "scan.ply", _make_ply())
    asset = THREE_D_MODALITY.processor(path=p, raw=_make_ply(), filename="scan.ply")
    assert asset.metadata["n_vertices"] == 3
    assert asset.metadata["has_normals"] is True


# ── 4. validator ──────────────────────────────────────────────────────────
def test_validator_ok(tmp_path):
    p = _tmp_file(tmp_path, "good.glb", _make_glb())
    asset = THREE_D_MODALITY.processor(path=p, raw=_make_glb(), filename="good.glb")
    v = THREE_D_MODALITY.validator(asset)
    assert isinstance(v, ModalityValidation)
    assert v.ok is True, v.errors
    assert v.errors == []


def test_validator_bad_3d():
    asset = ModalityAsset(
        asset_id="x", modality_id="three_d_pointcloud",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"format": "stl"},
    )
    v = THREE_D_MODALITY.validator(asset)
    assert v.ok is False
    assert any("stl" in e for e in v.errors)


# ── 5. preview ────────────────────────────────────────────────────────────
def test_preview_format():
    asset = ModalityAsset(
        asset_id="x", modality_id="three_d_pointcloud",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"format": "obj", "n_vertices": 12, "n_faces": 6,
                                     "has_normals": True, "has_uvs": False},
    )
    p = THREE_D_MODALITY.preview(asset)
    assert "OBJ" in p
    assert "12" in p
    assert "6" in p


# ── 6. embedder (1024-dim unified) ────────────────────────────────────────
def test_embedder_returns_1024_dim(tmp_path):
    raw = _make_glb()
    p = _tmp_file(tmp_path, "scene.glb", raw)
    asset = THREE_D_MODALITY.processor(path=p, raw=raw, filename="scene.glb")
    vec = THREE_D_MODALITY.embedder(asset)
    assert isinstance(vec, list)
    assert len(vec) == 1024
    # L2-normalised
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    assert 0.99 <= norm <= 1.01


def test_embed_asset_dispatch(tmp_path):
    raw = _make_glb()
    p = _tmp_file(tmp_path, "scene.glb", raw)
    asset = THREE_D_MODALITY.processor(path=p, raw=raw, filename="scene.glb")
    vec = embed_asset(asset)
    assert len(vec) == 1024


def test_determinism(tmp_path):
    raw = _make_obj()
    p = _tmp_file(tmp_path, "a.obj", raw)
    a = THREE_D_MODALITY.processor(path=p, raw=raw, filename="a.obj")
    v1 = THREE_D_MODALITY.embedder(a)
    v2 = THREE_D_MODALITY.embedder(a)
    assert v1 == v2