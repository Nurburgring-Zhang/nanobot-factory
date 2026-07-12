"""P19 v5.1: Tests for the DICOM medical-imaging modality.

Verifies:
1. Modality registration (.dcm / .dicom).
2. Minimal DICOM parser extracts modality, rows, columns, bits.
3. Processor + validator round-trip.
4. 1024-dim embedder.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from multimodal.medical import (
    MEDICAL_MODALITY,
    _parse_dicom,
    DICOM_MAGIC,
    _read_dcm_element,
)
from multimodal.business_modalities import (
    ModalityAsset,
    ModalityValidation,
    embed_asset,
    get_modality,
)


# ── helpers: build a tiny DICOM file ──────────────────────────────────────
def _explicit_vr_element(group: int, element: int, vr: bytes, value: bytes) -> bytes:
    """Build one DICOM explicit-VR element."""
    if vr in {b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"}:
        return (
            struct.pack("<HH", group, element)
            + vr
            + b"\x00\x00"               # reserved
            + struct.pack("<I", len(value))
            + value
        )
    return (
        struct.pack("<HH", group, element)
        + vr
        + struct.pack("<H", len(value))
        + value
    )


def _make_dicom(
    modality: str = "CT",
    rows: int = 512,
    columns: int = 512,
    bits: int = 16,
    patient_id: str = "P-001",
    study_uid: str = "1.2.3.4",
    series_uid: str = "1.2.3.5",
) -> bytes:
    preamble = b"\x00" * 128
    magic = b"DICM"
    # meta header group (0002,xxxx)
    transfer_syntax = b"1.2.840.10008.1.2.1\x00"  # explicit VR LE
    sop_class = b"1.2.840.10008.5.1.4.1.1.2\x00"  # CT Image
    meta = (
        _explicit_vr_element(0x0002, 0x0001, b"OB", b"\x00\x01")  # File Meta Information Version
        + _explicit_vr_element(0x0002, 0x0002, b"UI", sop_class)
        + _explicit_vr_element(0x0002, 0x0003, b"UI", b"1.2.3.6\x00")
        + _explicit_vr_element(0x0002, 0x0010, b"UI", transfer_syntax)
        # identifying info (group 0008)
        + _explicit_vr_element(0x0008, 0x0016, b"UI", sop_class)
        + _explicit_vr_element(0x0008, 0x0060, b"CS", modality.encode() + b" ")
        + _explicit_vr_element(0x0010, 0x0020, b"LO", patient_id.encode())
        + _explicit_vr_element(0x0020, 0x000D, b"UI", study_uid.encode() + b"\x00")
        + _explicit_vr_element(0x0020, 0x000E, b"UI", series_uid.encode() + b"\x00")
        # image dims (group 0028)
        + _explicit_vr_element(0x0028, 0x0010, b"US", struct.pack("<H", rows))
        + _explicit_vr_element(0x0028, 0x0011, b"US", struct.pack("<H", columns))
        + _explicit_vr_element(0x0028, 0x0100, b"US", struct.pack("<H", bits))
        + _explicit_vr_element(0x0028, 0x0101, b"US", struct.pack("<H", bits))
    )
    return preamble + magic + meta


# ── 1. registration ──────────────────────────────────────────────────────
def test_medical_registered():
    m = get_modality("medical_dicom")
    assert m is MEDICAL_MODALITY
    assert "医学影像" in m.name["zh"]
    assert "DICOM" in m.name["en"]
    assert ".dcm" in m.file_extensions
    assert ".dicom" in m.file_extensions


def test_medical_schema():
    s = MEDICAL_MODALITY.schema
    for k in ("format", "modality", "rows", "columns", "bits_allocated", "n_frames"):
        assert k in s


# ── 2. parsing ────────────────────────────────────────────────────────────
def test_parse_dicom_minimal():
    raw = _make_dicom(modality="CT", rows=256, columns=320, bits=12)
    info = _parse_dicom(raw)
    assert info["format"] == "dicom"
    assert info["modality"] == "CT"
    assert info["rows"] == 256
    assert info["columns"] == 320
    assert info["bits_allocated"] == 12
    assert info["bits_stored"] == 12
    assert info["patient_id"] == "P-001"
    assert info["transfer_syntax_uid"].startswith("1.2.840.10008")


def test_parse_dicom_mr():
    raw = _make_dicom(modality="MR", rows=128, columns=128, bits=16)
    info = _parse_dicom(raw)
    assert info["modality"] == "MR"
    assert info["rows"] == 128


def test_parse_dicom_no_magic():
    with pytest.raises(ValueError):
        _parse_dicom(b"\x00" * 200)


def test_parse_dicom_short():
    with pytest.raises(ValueError):
        _parse_dicom(b"DICM")


def test_read_element_long_vr():
    raw = _make_dicom()
    elt = _read_dcm_element(raw, 128 + 4)
    assert elt is not None
    grp, ele, vr, length, value = elt
    assert isinstance(grp, int)
    assert isinstance(ele, int)


# ── 3. processor ──────────────────────────────────────────────────────────
def _tmp(tmp_path: Path, name: str, raw: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(raw)
    return str(p)


def test_processor_dcm(tmp_path):
    raw = _make_dicom(modality="CT", rows=512, columns=512)
    p = _tmp(tmp_path, "scan.dcm", raw)
    asset = MEDICAL_MODALITY.processor(path=p, raw=raw, filename="scan.dcm")
    assert asset.modality_id == "medical_dicom"
    assert asset.metadata["modality"] == "CT"
    assert asset.metadata["rows"] == 512
    assert "DICOM" in asset.text


def test_processor_dicom_ext(tmp_path):
    raw = _make_dicom(modality="MR")
    p = _tmp(tmp_path, "scan.dicom", raw)
    asset = MEDICAL_MODALITY.processor(path=p, raw=raw, filename="scan.dicom")
    assert asset.metadata["modality"] == "MR"


# ── 4. validator ──────────────────────────────────────────────────────────
def test_validator_ok(tmp_path):
    raw = _make_dicom()
    p = _tmp(tmp_path, "good.dcm", raw)
    asset = MEDICAL_MODALITY.processor(path=p, raw=raw, filename="good.dcm")
    v = MEDICAL_MODALITY.validator(asset)
    assert v.ok is True, v.errors


def test_validator_no_modality():
    asset = ModalityAsset(
        asset_id="x", modality_id="medical_dicom",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"format": "dicom", "modality": "",
                                     "rows": 0, "columns": 0},
    )
    v = MEDICAL_MODALITY.validator(asset)
    assert v.ok is True
    assert any("Modality" in w for w in v.warnings)


# ── 5. preview ────────────────────────────────────────────────────────────
def test_preview_format():
    asset = ModalityAsset(
        asset_id="x", modality_id="medical_dicom",
        canonical_kind="document", path="", sha256="", size=0,
        mime="", text="", metadata={"modality": "US", "rows": 256,
                                     "columns": 256, "n_frames": 1},
    )
    p = MEDICAL_MODALITY.preview(asset)
    assert "US" in p
    assert "256" in p


# ── 6. embedder 1024-dim ──────────────────────────────────────────────────
def test_embedder_returns_1024_dim(tmp_path):
    raw = _make_dicom(rows=128, columns=128)
    p = _tmp(tmp_path, "scan.dcm", raw)
    asset = MEDICAL_MODALITY.processor(path=p, raw=raw, filename="scan.dcm")
    vec = MEDICAL_MODALITY.embedder(asset)
    assert len(vec) == 1024
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    assert 0.99 <= norm <= 1.01


def test_embed_asset_dispatch(tmp_path):
    raw = _make_dicom()
    p = _tmp(tmp_path, "scan.dcm", raw)
    asset = MEDICAL_MODALITY.processor(path=p, raw=raw, filename="scan.dcm")
    vec = embed_asset(asset)
    assert len(vec) == 1024