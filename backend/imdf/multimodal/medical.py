"""P19 v5.1: Medical imaging (DICOM) modality — ``.dcm`` / ``.dicom``.

DICOM (Digital Imaging and Communications in Medicine) uses a 128-byte
preamble followed by the 4-byte ``DICM`` magic and a sequence of explicit
VR Little-Endian data elements.  Each element has:

    tag (group, element — uint16 each)
    VR (2 ASCII chars for explicit VR)
    length (uint16 or uint32 depending on VR)
    value (the actual data)

This implementation does **not** attempt to fully decode the pixel data;
we extract the file-level metadata (PatientID, Modality, StudyDate,
Rows/Columns, BitsAllocated, etc.) so the modality registry can route the
file into the medical dataset bucket without depending on ``pydicom``.

Schema:

    {
        "format": "dicom",
        "transfer_syntax_uid": "1.2.840.10008.1.2.1",
        "sop_class_uid":      "1.2.840.10008.5.1.4.1.1.7",
        "modality":           "CT" | "MR" | "US" | "...",
        "patient_id":         str,
        "study_uid":          str,
        "series_uid":         str,
        "rows":               int,
        "columns":            int,
        "bits_allocated":     int,
        "bits_stored":        int,
        "is_multiframe":      bool,
        "n_frames":           int (1 if not multiframe),
    }
"""
from __future__ import annotations

import logging
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

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

# DICOM magic — 128-byte preamble + 'DICM'
DICOM_MAGIC_OFFSET = 128
DICOM_MAGIC = b"DICM"
DICOM_PREAMBLE_LEN = 128

# Explicit VR types whose length is uint32 (the rest use uint16)
_LONG_VRS = {b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"}


def _read_dcm_element(data: bytes, offset: int) -> Optional[Tuple[int, int, str, int, bytes]]:
    """Parse one explicit-VR Little-Endian DICOM element.

    Returns ``(group, element, vr, value_length, value_bytes)`` or ``None``
    if the offset is past EOF.  ``value_bytes`` is a slice of the original
    buffer (we don't decode strings here — caller asks for ``str()``).
    """
    if offset + 4 > len(data):
        return None
    group, element = struct.unpack("<HH", data[offset:offset + 4])
    if offset + 8 > len(data):
        return None
    vr = data[offset + 4:offset + 6]
    # skip reserved bytes if VR is OB/OW/etc.
    if vr in _LONG_VRS:
        if offset + 12 > len(data):
            return None
        # 2 reserved + 4 length
        length = struct.unpack("<I", data[offset + 8:offset + 12])[0]
        value_start = offset + 12
    else:
        if offset + 8 > len(data):
            return None
        length = struct.unpack("<H", data[offset + 6:offset + 8])[0]
        value_start = offset + 8
    if length > len(data) - value_start:
        # malformed; cap and continue
        length = len(data) - value_start
    return (group, element, vr.decode("ascii", errors="replace"), length, data[value_start:value_start + length])


def _parse_dicom(raw: bytes) -> Dict[str, Any]:
    """Best-effort DICOM parser — extract metadata tags only."""
    if len(raw) < DICOM_PREAMBLE_LEN + 4:
        raise ValueError("file too short to be DICOM (< 132 bytes)")
    magic_offset = DICOM_PREAMBLE_LEN
    if raw[magic_offset:magic_offset + 4] != DICOM_MAGIC:
        raise ValueError("DICM magic not found at offset 128 — not a DICOM file")
    out: Dict[str, Any] = {
        "format": "dicom",
        "transfer_syntax_uid": "",
        "sop_class_uid": "",
        "modality": "",
        "patient_id": "",
        "study_uid": "",
        "series_uid": "",
        "rows": 0,
        "columns": 0,
        "bits_allocated": 0,
        "bits_stored": 0,
        "is_multiframe": False,
        "n_frames": 1,
    }
    cursor = DICOM_PREAMBLE_LEN + 4
    elements_seen = 0
    while cursor < len(raw) and elements_seen < 1024:
        elt = _read_dcm_element(raw, cursor)
        if elt is None:
            break
        group, element, vr, length, value = elt
        elements_seen += 1
        # group 0x0002 = meta-information (always explicit VR LE)
        # group 0x0008 = identifying info
        # group 0x0028 = image presentation
        tag = (group << 16) | element
        if tag == 0x00020010:  # Transfer Syntax UID
            out["transfer_syntax_uid"] = value.decode("ascii", errors="ignore").strip("\x00 ")
        elif tag == 0x00080016:  # SOP Class UID
            out["sop_class_uid"] = value.decode("ascii", errors="ignore").strip("\x00 ")
        elif tag == 0x00080060:  # Modality
            out["modality"] = value.decode("ascii", errors="ignore").strip("\x00 ")
        elif tag == 0x00100020:  # Patient ID
            out["patient_id"] = value.decode("ascii", errors="ignore").strip("\x00 ")
        elif tag == 0x0020000D:  # Study Instance UID
            out["study_uid"] = value.decode("ascii", errors="ignore").strip("\x00 ")
        elif tag == 0x0020000E:  # Series Instance UID
            out["series_uid"] = value.decode("ascii", errors="ignore").strip("\x00 ")
        elif tag == 0x00280010:  # Rows
            if length >= 2:
                out["rows"] = struct.unpack("<H", value[:2])[0]
        elif tag == 0x00280011:  # Columns
            if length >= 2:
                out["columns"] = struct.unpack("<H", value[:2])[0]
        elif tag == 0x00280100:  # Bits Allocated
            if length >= 2:
                out["bits_allocated"] = struct.unpack("<H", value[:2])[0]
        elif tag == 0x00280101:  # Bits Stored
            if length >= 2:
                out["bits_stored"] = struct.unpack("<H", value[:2])[0]
        elif tag == 0x00280008:  # Number of Frames
            if length >= 2:
                out["is_multiframe"] = True
                out["n_frames"] = struct.unpack("<H", value[:2])[0]
        # Cursor advancement:
        # - long VR (OB/OW/OF/SQ/UT/UN): tag(4) + VR(2) + reserved(2) + length(4) + value = 12 + length
        # - short VR:                  tag(4) + VR(2) + length(2) + value          = 8 + length
        is_long = vr.encode("ascii") in _LONG_VRS
        cursor += (12 + length) if is_long else (8 + length)
    return out


# ── Processor ──────────────────────────────────────────────────────────────
def _processor(path: str = "", raw: bytes = b"", filename: str = "") -> ModalityAsset:
    data = raw if raw else _safe_read(path)
    sha = _sha256_bytes(data)
    metadata: Dict[str, Any] = {"filename": filename or os.path.basename(path)}
    try:
        metadata.update(_parse_dicom(data))
    except Exception as exc:  # noqa: BLE001
        metadata["error"] = str(exc)

    modality = metadata.get("modality", "?")
    rows = metadata.get("rows", 0)
    cols = metadata.get("columns", 0)
    n_frames = metadata.get("n_frames", 1)
    text_preview = (
        f"DICOM [{modality}]: {rows}×{cols}×{n_frames}, "
        f"bits={metadata.get('bits_allocated', 0)}, "
        f"pid={metadata.get('patient_id', 'anon')}, "
        f"study={metadata.get('study_uid', 'n/a')[:24]}"
    )
    return ModalityAsset(
        asset_id=_new_asset_id("medical"),
        modality_id="medical_dicom",
        canonical_kind="document",
        path=path,
        sha256=sha,
        size=len(data),
        mime="application/dicom",
        text=text_preview,
        metadata=metadata,
    )


# ── Validator ──────────────────────────────────────────────────────────────
def _validator(asset: ModalityAsset) -> ModalityValidation:
    errs: List[str] = []
    warns: List[str] = []
    md = asset.metadata or {}
    if md.get("format") != "dicom":
        errs.append("not a DICOM asset")
    if md.get("error"):
        errs.append(f"parse error: {md['error']}")
    if not md.get("modality"):
        warns.append("DICOM Modality tag missing")
    if md.get("rows", 0) <= 0 or md.get("columns", 0) <= 0:
        warns.append("DICOM Rows/Columns not set — non-image SOP class?")
    return ModalityValidation(ok=not errs, errors=errs, warnings=warns)


# ── Preview + embedder ────────────────────────────────────────────────────
def _preview(asset: ModalityAsset) -> str:
    md = asset.metadata or {}
    return (
        f"DICOM {md.get('modality', '?')} "
        f"{md.get('rows', 0)}×{md.get('columns', 0)}×{md.get('n_frames', 1)}"
    )


def _embedder(asset: ModalityAsset) -> List[float]:
    """Image-shape + tag fingerprint combined with byte fingerprint."""
    md = asset.metadata or {}
    feats = np.array(
        [
            float(md.get("rows", 0) or 0),
            float(md.get("columns", 0) or 0),
            float(md.get("n_frames", 1) or 1),
            float(md.get("bits_allocated", 0) or 0),
            float(md.get("bits_stored", 0) or 0),
            float(int(md.get("modality", "Z")[:1] or "Z", 36)) if md.get("modality") else 0.0,
            float(asset.size),
        ],
        dtype=np.float32,
    )
    feats[:3] = np.log1p(np.abs(feats[:3]))
    struct = _statistical_fingerprint(feats.reshape(1, -1))
    byts = _hash_fingerprint(_safe_read(asset.path))
    out = 0.5 * struct + 0.5 * byts
    n = float(np.linalg.norm(out)) or 1.0
    return (out / n).tolist()


# ── Registration ───────────────────────────────────────────────────────────
MEDICAL_SCHEMA: Dict[str, Any] = {
    "format": "dicom",
    "transfer_syntax_uid": "str (UID)",
    "sop_class_uid": "str (UID)",
    "modality": "CT | MR | US | XA | MG | ...",
    "patient_id": "str",
    "study_uid": "str (UID)",
    "series_uid": "str (UID)",
    "rows": "int",
    "columns": "int",
    "bits_allocated": "int",
    "bits_stored": "int",
    "is_multiframe": "bool",
    "n_frames": "int",
}

MEDICAL_MODALITY = Modality(
    id="medical_dicom",
    name={"zh": "医学影像 (DICOM)", "en": "Medical Imaging (DICOM)"},
    file_extensions=[".dcm", ".dicom"],
    canonical_kind="document",
    schema=MEDICAL_SCHEMA,
    processor=_processor,
    validator=_validator,
    preview=_preview,
    embedder=_embedder,
    description=(
        "DICOM (.dcm) medical imaging files — CT, MR, ultrasound, XA, etc. "
        "Used for clinical AI training (segmentation, classification, detection)."
    ),
)


def install() -> Modality:
    return register_modality(MEDICAL_MODALITY)


__all__ = [
    "MEDICAL_MODALITY",
    "MEDICAL_SCHEMA",
    "install",
    "_parse_dicom",
    "_read_dcm_element",
    "DICOM_MAGIC",
]