"""P19 v5.1: Business-modality registry — 4 specialised data domains.

This module provides a tiny, dependency-free registry of *business modalities*
that sit alongside the canonical ``ModalKind`` enum (image/video/audio/document/text)
and let the dataset factory ingest domain-specific 3D, geospatial, medical and
panoptic-segmentation artefacts into the unified 1024-dim embedding space.

Each modality exposes a stable ``Modality`` dataclass:

* ``id``         — canonical lowercase id, e.g. ``"three_d_pointcloud"``
* ``name``       — bilingual display name (``"zh"`` / ``"en"``)
* ``file_extensions`` — accepted file suffixes (lowercase, with leading dot)
* ``schema``     — schema sketch (dict describing the structural fields)
* ``processor``  — ``bytes / path → ParsedMedia`` adapter
* ``validator``  — ``ParsedMedia → (ok: bool, errors: list[str])`` schema check
* ``preview``    — best-effort short textual preview used by the UI
* ``embedder``   — ``bytes / path → 1024-dim L2-normalised list[float]``

Why a separate registry (rather than extending ``ModalKind``)?
``ModalKind`` is consumed by Pydantic v2 enums and HTTP routes; widening it
would require a cross-package migration.  The business modalities layer
sits on top, mapping each new id → one of the five canonical ModalKind
buckets for storage / RAG, while keeping the schema / validation logic
domain-specific.

Reference: reports/VDP-2026-V5-对比差距清单.md (Section 6 — 12 业务模态).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .embedding import UNIFIED_DIM

logger = logging.getLogger(__name__)


# ── Result types ───────────────────────────────────────────────────────────
@dataclass
class ModalityValidation:
    """Result of ``Modality.validator``."""

    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


@dataclass
class ModalityAsset:
    """Asset produced by ``Modality.processor``.

    Mirrors the shape returned by the legacy IMDF ``Asset`` table (path,
    hash, size, data_type, plus a metadata dict for domain-specific fields).
    """

    asset_id: str
    modality_id: str  # e.g. "three_d_pointcloud"
    canonical_kind: str  # image | video | audio | document | text
    path: str
    sha256: str
    size: int
    mime: str
    text: str = ""  # short textual preview (used for RAG chunking)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "modality_id": self.modality_id,
            "canonical_kind": self.canonical_kind,
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
            "mime": self.mime,
            "text": self.text[:400],
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


# ── Modality dataclass ─────────────────────────────────────────────────────
@dataclass
class Modality:
    """One business-modality descriptor.

    Each modality wires up a **processor**, **validator**, **preview** and
    **embedder**.  All four functions are intentionally tolerant of malformed
    input (they never raise) — callers receive ``ModalityAsset`` /
    ``ModalityValidation`` objects describing the outcome.
    """

    id: str
    name: Dict[str, str]  # {"zh": ..., "en": ...}
    file_extensions: List[str]  # [".glb", ".gltf", ...]
    canonical_kind: str  # image | video | audio | document | text
    schema: Dict[str, Any]
    processor: Callable[..., ModalityAsset]
    validator: Callable[[ModalityAsset], ModalityValidation]
    preview: Callable[[ModalityAsset], str]
    embedder: Callable[[ModalityAsset], List[float]]
    description: str = ""

    def matches_filename(self, filename: str) -> bool:
        ext = os.path.splitext(filename or "")[1].lower()
        return ext in self.file_extensions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "file_extensions": list(self.file_extensions),
            "canonical_kind": self.canonical_kind,
            "schema": self.schema,
            "description": self.description,
        }


# ── Common helpers ─────────────────────────────────────────────────────────
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _new_asset_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _safe_read(path: str) -> bytes:
    """Read a file as bytes; return b"" if missing."""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def _hash_fingerprint(data: bytes, dim: int = UNIFIED_DIM) -> np.ndarray:
    """Deterministic hash-based fingerprint → L2-normalised 1024-dim vector."""
    vec = np.zeros(dim, dtype=np.float32)
    if not data:
        return vec
    # chunk the file to spread entropy evenly across the dim
    chunk_size = max(64, len(data) // (dim // 4))
    i = 0
    while i < len(data):
        chunk = data[i:i + chunk_size]
        h = hashlib.sha256(chunk).digest()
        # 8 indices per chunk (32 bytes → 8 uint32s)
        for j in range(0, 32, 4):
            v = struct.unpack(">I", h[j:j + 4])[0]
            vec[(v ^ i) % dim] += 1.0
        i += chunk_size
    n = float(np.linalg.norm(vec)) or 1.0
    return (vec / n).astype(np.float32)


def _statistical_fingerprint(
    data: np.ndarray,
    dim: int = UNIFIED_DIM,
    bins_per_axis: int = 8,
) -> np.ndarray:
    """Project an ``np.ndarray`` (e.g. point coords, pixel grid) to ``dim``-d.

    The function flattens ``data`` to 2D (``N×C``), discretises each column
    into ``bins_per_axis`` quantile bins and emits a multi-index histogram.
    This is the canonical "feature-binning" trick that maps structured
    arrays of arbitrary shape to a stable fixed-dim fingerprint.
    """
    vec = np.zeros(dim, dtype=np.float32)
    if data is None or data.size == 0:
        return vec
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    # cap rows to keep cost predictable
    if arr.shape[0] > 8192:
        idx = np.linspace(0, arr.shape[0] - 1, 8192).astype(np.int64)
        arr = arr[idx]
    n_features = arr.shape[1]
    for col in range(n_features):
        x = arr[:, col]
        if np.allclose(x, x[0]):
            continue
        try:
            edges = np.quantile(x, np.linspace(0.0, 1.0, bins_per_axis + 1)[1:-1])
        except Exception:
            edges = np.array([x.mean()])
        if edges.size == 0:
            continue
        bin_ids = np.clip(np.digitize(x, edges), 0, bins_per_axis - 1)
        # cross-feature offset to spread bins across the 1024-dim space
        offset = (col * 131 + 17) % dim
        for b in bin_ids:
            vec[(offset + int(b) * (dim // bins_per_axis)) % dim] += 1.0
    n = float(np.linalg.norm(vec)) or 1.0
    return (vec / n).astype(np.float32)


# ── Modality registry ─────────────────────────────────────────────────────
_REGISTRY: Dict[str, Modality] = {}


def register_modality(modality: Modality) -> Modality:
    """Add a Modality to the global registry. Idempotent (overwrites)."""
    _REGISTRY[modality.id] = modality
    return modality


def get_modality(modality_id: str) -> Optional[Modality]:
    return _REGISTRY.get(modality_id)


def list_modalities() -> List[Modality]:
    return list(_REGISTRY.values())


def detect_business_modality(filename: str, mime: str = "") -> Optional[Modality]:
    """Find the first registered modality that accepts ``filename`` (or ``mime``).

    Returns ``None`` if no business modality matches — caller should fall back
    to the canonical ``ModalKind`` pipeline.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    for m in _REGISTRY.values():
        if ext and ext in m.file_extensions:
            return m
    return None


def embed_asset(asset: ModalityAsset) -> List[float]:
    """Dispatch ``asset.modality_id`` to the registered embedder; default hash."""
    m = _REGISTRY.get(asset.modality_id)
    if m is None:
        return _hash_fingerprint(b"", UNIFIED_DIM).tolist()
    try:
        vec = m.embedder(asset)
    except Exception as exc:  # noqa: BLE001
        logger.debug("embedder %s failed: %s — falling back to hash", m.id, exc)
        vec = _hash_fingerprint(_safe_read(asset.path), UNIFIED_DIM)
    if not isinstance(vec, list):
        vec = list(vec)
    if len(vec) != UNIFIED_DIM:
        arr = np.asarray(vec, dtype=np.float32)
        if arr.size < UNIFIED_DIM:
            arr = np.pad(arr, (0, UNIFIED_DIM - arr.size))
        else:
            arr = arr[:UNIFIED_DIM]
        n = float(np.linalg.norm(arr)) or 1.0
        arr = arr / n
        vec = arr.tolist()
    return vec


def process_file(path: str, filename: Optional[str] = None) -> ModalityAsset:
    """Best-effort ingestion of a single file via its matched modality.

    Returns a stub asset with ``canonical_kind="document"`` if no business
    modality matches; the stub is still valid for storage / hash purposes.
    """
    fn = filename or os.path.basename(path)
    raw = _safe_read(path)
    sha = _sha256_bytes(raw) if raw else ""
    modality = detect_business_modality(fn)
    if modality is None:
        # Fallback stub — caller can re-classify via the canonical parser.
        return ModalityAsset(
            asset_id=_new_asset_id("asset"),
            modality_id="generic",
            canonical_kind="document",
            path=path,
            sha256=sha,
            size=len(raw),
            mime="application/octet-stream",
            text=f"[stub] {fn} ({len(raw)} bytes)",
            metadata={"filename": fn},
        )
    try:
        return modality.processor(path=path, raw=raw, filename=fn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("processor %s failed for %s: %s", modality.id, path, exc)
        return ModalityAsset(
            asset_id=_new_asset_id("asset"),
            modality_id=modality.id,
            canonical_kind=modality.canonical_kind,
            path=path,
            sha256=sha,
            size=len(raw),
            mime="application/octet-stream",
            text=f"[error] {fn}: {exc}",
            metadata={"filename": fn, "error": str(exc)},
        )


__all__ = [
    "Modality",
    "ModalityAsset",
    "ModalityValidation",
    "register_modality",
    "get_modality",
    "list_modalities",
    "detect_business_modality",
    "embed_asset",
    "process_file",
    "UNIFIED_DIM",
]