"""P19 v5.1: Integration tests — RAG + MultimodalRAG + business modalities.

Verifies that the four business modalities (3D / LiDAR / DICOM / Panoptic)
ingest cleanly through ``MultimodalRAG.index_business_files`` and produce
1024-dim unified embeddings retrievable via cosine similarity.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from multimodal.rag import MultimodalRAG, VectorStore
from multimodal.business_modalities import (
    detect_business_modality,
    embed_asset,
    list_modalities,
    process_file,
)


# ── helpers (same minimal-bytes fixtures as the per-modality tests) ────────
def _make_glb() -> bytes:
    g = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"name": "m0"}],
        "accessors": [
            {"count": 4, "type": "VEC3", "name": "POSITION"},
            {"count": 6, "type": "SCALAR", "name": "indices"},
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0}],
        "buffers": [{"byteLength": 0}],
    }
    j = json.dumps(g).encode("utf-8")
    pad = (-len(j)) % 4
    j = j + b" " * pad
    binchunk = b"\x00\x00\x00\x00"
    binpad = (-len(binchunk)) % 4
    binchunk = binchunk + b"\x00" * binpad
    j_len = len(j)
    b_len = len(binchunk)
    header = b"glTF" + struct.pack("<II", 2, 12 + 8 + j_len + 8 + b_len)
    json_chunk = struct.pack("<I", j_len) + b"JSON" + j
    bin_chunk = struct.pack("<I", b_len) + b"BIN\x00" + binchunk
    return header + json_chunk + bin_chunk


def _make_las() -> bytes:
    hdr = bytearray(227)
    hdr[0:4] = b"LASF"
    hdr[24] = 1; hdr[25] = 4
    hdr[94:96] = struct.pack("<H", 227)
    hdr[96:100] = struct.pack("<I", 227)
    hdr[100:104] = struct.pack("<I", 0)
    hdr[104] = 1
    hdr[107:111] = struct.pack("<I", 100)
    hdr[171:179] = struct.pack("<d", 100.0)
    hdr[179:187] = struct.pack("<d", 100.0)
    hdr[187:195] = struct.pack("<d", 100.0)
    return bytes(hdr)


def _make_dcm() -> bytes:
    def el(group, element, vr, value):
        if vr in {b"OB", b"OW", b"OF"}:
            return struct.pack("<HH", group, element) + vr + b"\x00\x00" + struct.pack("<I", len(value)) + value
        return struct.pack("<HH", group, element) + vr + struct.pack("<H", len(value)) + value
    preamble = b"\x00" * 128
    body = (
        el(0x0008, 0x0060, b"CS", b"CT ")
        + el(0x0010, 0x0020, b"LO", b"P-001")
        + el(0x0028, 0x0010, b"US", struct.pack("<H", 256))
        + el(0x0028, 0x0011, b"US", struct.pack("<H", 256))
    )
    return preamble + b"DICM" + body


def _make_panoptic() -> bytes:
    return json.dumps({
        "images": [{"id": 1, "file_name": "a.jpg", "height": 480, "width": 640}],
        "annotations": [{"image_id": 1, "file_name": "a.png",
                         "segments_info": [{"id": 1, "category_id": 1, "iscrowd": 0}]}],
        "categories": [{"id": 1, "name": "person", "isthing": 1}],
    }).encode("utf-8")


# ── 1. list_modalities exposes all 4 ─────────────────────────────────────
def test_list_modalities_has_all_four():
    mods = list_modalities()
    ids = sorted(m.id for m in mods)
    assert ids == sorted([
        "three_d_pointcloud", "lidar",
        "medical_dicom", "panoptic_segmentation",
    ])


def test_detect_business_modality_per_format():
    assert detect_business_modality("scene.glb").id == "three_d_pointcloud"
    assert detect_business_modality("scan.las").id == "lidar"
    assert detect_business_modality("scan.dcm").id == "medical_dicom"
    assert detect_business_modality("annotations.panoptic.json").id == "panoptic_segmentation"


def test_detect_no_match():
    assert detect_business_modality("photo.jpg") is None


# ── 2. process_file dispatches correctly ─────────────────────────────────
def test_process_file_dispatch(tmp_path):
    files = [
        ("scene.glb", _make_glb()),
        ("scan.las", _make_las()),
        ("patient.dcm", _make_dcm()),
        ("ann.panoptic.json", _make_panoptic()),
    ]
    for name, raw in files:
        p = tmp_path / name
        p.write_bytes(raw)
        asset = process_file(str(p))
        assert asset.modality_id in {
            "three_d_pointcloud", "lidar", "medical_dicom", "panoptic_segmentation"
        }
        assert asset.size == len(raw)


# ── 3. RAG integration: 1024-dim index + cosine retrieval ───────────────
def test_rag_index_business_files_returns_1024_dim(tmp_path):
    files = [
        ("scene.glb", _make_glb()),
        ("scan.las", _make_las()),
        ("patient.dcm", _make_dcm()),
        ("ann.panoptic.json", _make_panoptic()),
    ]
    paths = []
    for name, raw in files:
        p = tmp_path / name
        p.write_bytes(raw)
        paths.append(str(p))

    rag = MultimodalRAG()
    out = rag.index_business_files(paths)
    assert len(out) == 4
    for rec in out:
        assert rec["dim"] == 1024
        assert rec["modality_id"] in {
            "three_d_pointcloud", "lidar", "medical_dicom", "panoptic_segmentation"
        }


def test_rag_index_business_file_via_vector_store(tmp_path):
    raw = _make_glb()
    p = tmp_path / "scene.glb"
    p.write_bytes(raw)
    store = VectorStore()
    emb = store.add_business_file(str(p))
    assert len(emb.vector) == 1024
    assert len(store) == 1


def test_rag_search_after_business_index(tmp_path):
    files = [
        ("scene.glb", _make_glb()),
        ("scan.las", _make_las()),
        ("patient.dcm", _make_dcm()),
        ("ann.panoptic.json", _make_panoptic()),
    ]
    paths = []
    for name, raw in files:
        p = tmp_path / name
        p.write_bytes(raw)
        paths.append(str(p))

    rag = MultimodalRAG()
    rag.index_business_files(paths)

    # search by a text query — uses unified 1024-dim space
    from multimodal.types import MediaRef, ModalKind
    hits = rag.search(MediaRef(kind=ModalKind.TEXT, text="3D mesh"), top_k=2)
    assert len(hits) >= 1
    assert all(isinstance(h.score, float) for h in hits)


def test_business_modalities_l2_normalised(tmp_path):
    raw = _make_glb()
    p = tmp_path / "scene.glb"
    p.write_bytes(raw)
    asset = process_file(str(p))
    vec = embed_asset(asset)
    n = math.sqrt(sum(x * x for x in vec))
    assert 0.99 <= n <= 1.01


def test_business_modality_different_assets_have_different_embeddings(tmp_path):
    raw_a = _make_glb()
    raw_b = _make_panoptic()
    p_a = tmp_path / "a.glb"
    p_a.write_bytes(raw_a)
    p_b = tmp_path / "b.panoptic.json"
    p_b.write_bytes(raw_b)
    a1 = process_file(str(p_a))
    a2 = process_file(str(p_b))
    v1 = embed_asset(a1)
    v2 = embed_asset(a2)
    # cosine ≈ 0 (or at least ≠ 1) — different modalities should not collide
    dot = sum(x * y for x, y in zip(v1, v2))
    assert dot < 0.99, "different modalities should not produce identical vectors"