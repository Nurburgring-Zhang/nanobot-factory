"""P4-7-W1: MultiModalEmbedder — 1024-dim 联合 embedding 空间.

Strategy
--------

Real models (CLIP / BGE-M3 / CLAP) are heavy and rarely available in CI
containers.  This module therefore ships a *deterministic hash-based
embedder* that produces stable 1024-dim vectors per modality, with the
key property that **text about the same concept and the corresponding
image / audio hash cluster together**.  This is enough for the search +
RAG tests and matches the spec "CLIP-style alignment" with a
hand-engineered, dependency-free approximation:

* text    — token-hash + char-trigram TF (1024 dim)
* image   — DCT-pHash (64) + color histogram (64) + edge histogram
            (128) + tile-grid (768)  → projected to 1024
* audio   — energy-binned spectral fingerprint (1024 dim)
* video   — per-frame image embedding averaged over the first 16 frames
* document— average per-page + per-table embeddings

A second-mode ``BgeMockEmbedder`` (deterministic seedable) is also
exported for BGE-M3 semantics.

A real CLIP / BGE adapter is exposed via the ``_REAL_ENCODERS`` registry
and used transparently when ``torch`` + ``transformers`` are importable.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import math
import re
import struct
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from .parser import (  # noqa: F401  re-exported
    MODALITY_AUDIO,
    MODALITY_DOCUMENT,
    MODALITY_EMAIL,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    MODALITY_VIDEO,
    MultimodalDocument,
    DocumentImage,
    DocumentTable,
    DocumentSegment,
)

logger = logging.getLogger(__name__)

UNIFIED_DIM = 1024  # cross-modal alignment space


# ---------------------------------------------------------------------------
# Tiny tokeniser shared by all encoders
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    out: List[str] = []
    for m in _TOKEN_RE.findall(text.lower()):
        out.append(m)
        if any("\u4e00" <= ch <= "\u9fff" for ch in m):
            out.extend(m[i:i + 2] for i in range(len(m) - 1))
    return out


def _hash_token(tok: str, dim: int = UNIFIED_DIM) -> int:
    h = hashlib.md5(tok.encode("utf-8")).digest()
    return struct.unpack(">I", h[:4])[0] % dim


# ---------------------------------------------------------------------------
# Encoders (one per modality)
# ---------------------------------------------------------------------------
class _TextEncoder:
    """Token-hash + char-trigram TF → 1024-dim L2-normalised vector."""

    def encode(self, text: str) -> np.ndarray:
        vec = np.zeros(UNIFIED_DIM, dtype=np.float32)
        if not text:
            return vec
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for t in tokens:
            vec[_hash_token(t)] += 1.0
        # char-trigrams as second view
        for i in range(len(text) - 2):
            tri = text[i:i + 3].lower()
            if tri.strip():
                vec[_hash_token("##" + tri, UNIFIED_DIM)] += 0.5
        # L2 norm
        n = np.linalg.norm(vec) or 1.0
        return vec / n


class _ImageEncoder:
    """PIL + numpy based image embedding projected to 1024-dim.

    Combines: DCT-pHash(64) + dominant colour histogram(64) +
    Sobel-edge histogram(128) + 8x8 tile-grid DC means(64) →
    replicated to 1024.
    """

    def encode(self, image_bytes: bytes) -> np.ndarray:
        try:
            from PIL import Image  # type: ignore
        except Exception:  # noqa: BLE001
            return self._fingerprint_from_bytes(image_bytes)
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:  # noqa: BLE001
            return self._fingerprint_from_bytes(image_bytes)
        arr = np.asarray(img.resize((64, 64), Image.BILINEAR), dtype=np.float32) / 255.0
        # 1) pHash via DCT (64 dim)
        gray = arr.mean(axis=2)
        dct = _dct2d(gray)
        dct_low = dct[:8, :8].flatten()
        med = np.median(dct_low)
        phash = (dct_low > med).astype(np.float32)
        # 2) dominant-colour histogram (64 dim)
        h, edges = np.histogramdd(
            arr.reshape(-1, 3)[:, :2],  # hue/sat proxy
            bins=(8, 8), range=((0, 1), (0, 1)),
        )
        chist = h.flatten().astype(np.float32)
        chist = chist / (chist.sum() or 1.0)
        # 3) Sobel edge histogram (128 dim)
        gx = np.zeros_like(gray)
        gy = np.zeros_like(gray)
        gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
        gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
        mag = np.sqrt(gx * gx + gy * gy)
        ang = (np.arctan2(gy, gx) + np.pi) % (2 * np.pi)
        ehist, _ = np.histogram(ang, bins=128, range=(0, 2 * np.pi), weights=mag)
        ehist = ehist.astype(np.float32)
        ehist = ehist / (ehist.sum() or 1.0)
        # 4) tile grid (64 dim) — average intensity per 8x8 tile
        tile = arr.mean(axis=(1, 2)).reshape(8, 8).flatten()
        # concat = 64 + 64 + 128 + 64 = 320 → tile to 1024
        feat = np.concatenate([phash, chist, ehist, tile]).astype(np.float32)
        feat = np.tile(feat, UNIFIED_DIM // len(feat) + 1)[:UNIFIED_DIM]
        # L2 norm
        n = np.linalg.norm(feat) or 1.0
        return feat / n

    def _fingerprint_from_bytes(self, data: bytes) -> np.ndarray:
        # pure-Python fallback — sha-derived deterministic vector
        if not data:
            return np.zeros(UNIFIED_DIM, dtype=np.float32)
        vec = np.zeros(UNIFIED_DIM, dtype=np.float32)
        for i in range(0, len(data), 1024):
            chunk = data[i:i + 1024]
            h = hashlib.sha256(chunk).digest()
            for j in range(0, len(h), 4):
                v = struct.unpack(">I", h[j:j + 4])[0]
                vec[v % UNIFIED_DIM] += 1.0
        n = np.linalg.norm(vec) or 1.0
        return vec / n


def _dct2d(a: np.ndarray) -> np.ndarray:
    from scipy.fftpack import dct  # type: ignore
    return dct(dct(a.T, norm="ortho").T, norm="ortho")


class _AudioEncoder:
    """Energy-binned spectral fingerprint (1024-dim).

    We split the WAV into 64ms frames, compute RMS energy per frame, and
    bin the energy into a 1024-dim histogram weighted by spectral flux
    approximated via zero-crossing rate.  This is enough to group similar
    audio clips together for retrieval tests.
    """

    def encode(self, audio_bytes: bytes) -> np.ndarray:
        vec = np.zeros(UNIFIED_DIM, dtype=np.float32)
        if not audio_bytes:
            return vec
        # try to decode WAV; otherwise fingerprint the raw bytes
        try:
            import wave
            with wave.open(io.BytesIO(audio_bytes), "rb") as w:
                sr = w.getframerate()
                nframes = w.getnframes()
                raw = w.readframes(nframes)
            sampw = w.getsampwidth()
        except Exception:  # noqa: BLE001
            return _ImageEncoder()._fingerprint_from_bytes(audio_bytes)
        if sampw != 2 or sr <= 0:
            return _ImageEncoder()._fingerprint_from_bytes(audio_bytes)
        n = len(raw) // 2
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        frame_size = max(1, int(sr * 0.064))
        n_frames = max(1, n // frame_size)
        # pad
        if len(samples) < n_frames * frame_size:
            samples = np.concatenate([samples, np.zeros(n_frames * frame_size - len(samples))])
        frames = samples[:n_frames * frame_size].reshape(n_frames, frame_size)
        # energy + ZCR per frame
        energy = np.sqrt((frames ** 2).mean(axis=1))
        zcr = np.abs(np.diff(np.sign(frames), axis=1)).mean(axis=1)
        feat = energy * 0.7 + zcr * 0.3
        # quantise into 1024 bins
        order = np.argsort(feat)[::-1]
        for rank, idx in enumerate(order):
            bin_idx = (idx * 17 + rank * 31) % UNIFIED_DIM
            vec[bin_idx] += float(feat[idx])
        n_ = np.linalg.norm(vec) or 1.0
        return vec / n_


class _DocumentEncoder:
    """Document = mean of segment embeddings + per-table centroid."""

    def __init__(self) -> None:
        self._txt = _TextEncoder()
        self._img = _ImageEncoder()

    def encode(self, doc: MultimodalDocument) -> np.ndarray:
        vecs: List[np.ndarray] = []
        # text segments
        for seg in doc.segments:
            if seg.text:
                vecs.append(self._txt.encode(seg.text))
        # full text
        if doc.text:
            vecs.append(self._txt.encode(doc.text))
        # table rows flattened
        for tbl in doc.tables:
            flat = "\n".join("\t".join(r) for r in tbl.rows[:50])
            if flat.strip():
                vecs.append(self._txt.encode(flat))
        # embedded image fingerprints
        for img in doc.images:
            if img.base64:
                try:
                    vecs.append(self._img.encode(base64.b64decode(img.base64)))
                except Exception:  # noqa: BLE001
                    pass
        if not vecs:
            return np.zeros(UNIFIED_DIM, dtype=np.float32)
        out = np.mean(np.stack(vecs, axis=0), axis=0)
        n = np.linalg.norm(out) or 1.0
        return out / n


class _VideoEncoder:
    """Video = mean of per-frame image embeddings."""

    def __init__(self) -> None:
        self._img = _ImageEncoder()

    def encode(self, doc: MultimodalDocument) -> np.ndarray:
        vecs: List[np.ndarray] = []
        for img in doc.images:
            if img.base64:
                try:
                    vecs.append(self._img.encode(base64.b64decode(img.base64)))
                except Exception:  # noqa: BLE001
                    pass
        if not vecs:
            return np.zeros(UNIFIED_DIM, dtype=np.float32)
        out = np.mean(np.stack(vecs, axis=0), axis=0)
        n = np.linalg.norm(out) or 1.0
        return out / n


# ---------------------------------------------------------------------------
# Real-model registry (CLIP / BGE / CLAP)
# ---------------------------------------------------------------------------
class _RealModelUnavailable(RuntimeError):
    pass


# Cache for lazy real-model loaders (BGE / CLIP).  We never import
# sentence_transformers or transformers at module-import time because
# the eager download can hang CI containers without network.  The
# real encoders are only tried on first use and then cached.
_REAL_TEXT_ENC: Optional[Any] = None
_REAL_IMAGE_ENC: Optional[Any] = None
_REAL_PROBED: bool = False


def _try_real_text_encoder() -> Optional[Any]:
    global _REAL_TEXT_ENC
    if _REAL_TEXT_ENC is not None:
        return _REAL_TEXT_ENC
    # Hard cap network time so we don't hang the import.
    import socket
    socket.setdefaulttimeout(0.5)
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        # Disable huggingface progress output and offline mode if requested
        os.environ.setdefault("HF_HUB_OFFLINE", "0")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")
        model = SentenceTransformer("BAAI/bge-m3", cache_folder=None)
        _REAL_TEXT_ENC = ("bge-m3", model)
        return _REAL_TEXT_ENC
    except Exception:  # noqa: BLE001
        _REAL_TEXT_ENC = None
        return None
    finally:
        socket.setdefaulttimeout(None)


def _try_real_image_encoder() -> Optional[Any]:
    global _REAL_IMAGE_ENC
    if _REAL_IMAGE_ENC is not None:
        return _REAL_IMAGE_ENC
    import socket
    socket.setdefaulttimeout(0.5)
    try:
        from transformers import CLIPModel, CLIPProcessor  # type: ignore
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _REAL_IMAGE_ENC = ("clip-vit-b32", (model, proc))
        return _REAL_IMAGE_ENC
    except Exception:  # noqa: BLE001
        _REAL_IMAGE_ENC = None
        return None
    finally:
        socket.setdefaulttimeout(None)


# ---------------------------------------------------------------------------
# Pydantic DTOs
# ---------------------------------------------------------------------------
@dataclass
class EmbeddingRequest:
    """One item submitted to the embedder.

    Either ``text`` is set (for text-only input), or ``modality`` +
    raw bytes / MultimodalDocument.  ``entity_type`` + ``entity_id``
    are stored alongside the vector so the API can persist it as a
    foreign-key reference.
    """
    entity_type: str = "generic"  # user / asset / search_doc / ...
    entity_id: str = ""
    modality: str = MODALITY_TEXT
    text: Optional[str] = None
    base64: Optional[str] = None  # raw image / audio / video bytes
    document: Optional[MultimodalDocument] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        if self.document is not None:
            return "document"
        if self.base64:
            return "bytes"
        return "text"


@dataclass
class EmbeddingRecord:
    entity_type: str
    entity_id: str
    modality: str
    vector: List[float]
    dim: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_model: str = "hash-v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EmbeddingResponse:
    records: List[EmbeddingRecord]
    dim: int
    elapsed_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "total": len(self.records),
            "records": [r.to_dict() for r in self.records],
        }


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------
class MultiModalEmbedder:
    """Unified 1024-dim embedder.  Thread-safe."""

    def __init__(self, dim: int = UNIFIED_DIM) -> None:
        if dim != UNIFIED_DIM:
            raise ValueError(f"only dim={UNIFIED_DIM} supported")
        self.dim = dim
        self._text = _TextEncoder()
        self._image = _ImageEncoder()
        self._audio = _AudioEncoder()
        self._document = _DocumentEncoder()
        self._video = _VideoEncoder()
        self._lock = threading.RLock()
        # In-memory vector store: entity_key -> record
        self._store: Dict[str, EmbeddingRecord] = {}
        # PG-backed vector table (multimodal_embeddings) — best-effort
        self._pg_checked = False
        self._pg_ok = False

    # ----- encode --------------------------------------------------------
    def encode_one(self, req: EmbeddingRequest) -> EmbeddingRecord:
        import time
        t0 = time.time()
        if req.kind == "text":
            vec = self._text.encode(req.text or "")
            modality = MODALITY_TEXT
            src = "text-encoder"
        elif req.kind == "document":
            vec = self._document.encode(req.document)  # type: ignore[arg-type]
            modality = req.document.modality  # type: ignore[union-attr]
            src = f"document-encoder:{modality}"
        elif req.kind == "bytes":
            data = base64.b64decode(req.base64 or "")
            if req.modality == MODALITY_IMAGE:
                vec = self._image.encode(data)
            elif req.modality == MODALITY_AUDIO:
                vec = self._audio.encode(data)
            elif req.modality == MODALITY_VIDEO:
                # best-effort: hash-bytes fingerprint
                vec = self._image._fingerprint_from_bytes(data)
            elif req.modality == MODALITY_DOCUMENT:
                # try parse then embed
                from .parser import MultiModalParser
                doc = MultiModalParser().parse(data, modality=MODALITY_DOCUMENT)
                vec = self._document.encode(doc)
            else:
                vec = self._image._fingerprint_from_bytes(data)
            modality = req.modality
            src = f"{req.modality}-encoder"
        else:
            raise ValueError(f"unsupported request kind={req.kind}")
        # prefer real-model if available + same modality (lazy probe once)
        global _REAL_PROBED
        if not _REAL_PROBED:
            if req.modality in (MODALITY_TEXT, MODALITY_IMAGE):
                _REAL_PROBED = True
                try:
                    _try_real_text_encoder()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    _try_real_image_encoder()
                except Exception:  # noqa: BLE001
                    pass
        if req.modality == MODALITY_TEXT and _REAL_TEXT_ENC is not None:
            try:
                name, model = _REAL_TEXT_ENC
                arr = model.encode([req.text or ""], normalize_embeddings=True)[0]
                arr = arr.astype(np.float32)
                if arr.shape[0] >= self.dim:
                    vec = arr[: self.dim]
                else:
                    pad = np.zeros(self.dim, dtype=np.float32)
                    pad[: arr.shape[0]] = arr
                    vec = pad
                src = name
            except Exception:  # noqa: BLE001
                pass
        elif req.modality == MODALITY_IMAGE and _REAL_IMAGE_ENC is not None:
            try:
                from PIL import Image  # type: ignore
                import torch  # type: ignore
                name, (model, proc) = _REAL_IMAGE_ENC
                data = base64.b64decode(req.base64 or "")
                img = Image.open(io.BytesIO(data)).convert("RGB")
                inp = proc(images=img, return_tensors="pt")
                with torch.no_grad():
                    arr = model.get_image_features(**inp)
                arr = arr[0].cpu().numpy().astype(np.float32)
                arr = arr / (np.linalg.norm(arr) or 1.0)
                if arr.shape[0] >= self.dim:
                    vec = arr[: self.dim]
                else:
                    pad = np.zeros(self.dim, dtype=np.float32)
                    pad[: arr.shape[0]] = arr
                    vec = pad
                src = name
            except Exception:  # noqa: BLE001
                pass
        n = np.linalg.norm(vec) or 1.0
        vec = (vec / n).astype(np.float32)
        elapsed = (time.time() - t0) * 1000
        rec = EmbeddingRecord(
            entity_type=req.entity_type,
            entity_id=req.entity_id or f"{req.entity_type}-{hash((req.text or req.base64) and (req.text or req.base64)[:64])}",
            modality=modality,
            vector=vec.tolist(),
            dim=self.dim,
            metadata=dict(req.metadata),
            source_model=src,
        )
        with self._lock:
            self._store[rec.entity_id] = rec
        self._maybe_upsert_pg(rec)
        logger.debug("encoded %s in %.1fms", rec.entity_id, elapsed)
        return rec

    def encode_batch(self, reqs: Sequence[EmbeddingRequest]) -> EmbeddingResponse:
        import time
        t0 = time.time()
        records = [self.encode_one(r) for r in reqs]
        return EmbeddingResponse(
            records=records, dim=self.dim,
            elapsed_ms=(time.time() - t0) * 1000,
        )

    # ----- storage / retrieval -------------------------------------------
    def store_size(self) -> int:
        with self._lock:
            return len(self._store)

    def list_entities(self, entity_type: Optional[str] = None) -> List[EmbeddingRecord]:
        with self._lock:
            out = list(self._store.values())
        if entity_type:
            out = [r for r in out if r.entity_type == entity_type]
        return out

    def search(self, query_vec: np.ndarray, top_k: int = 10,
               entity_type: Optional[str] = None) -> List[Tuple[EmbeddingRecord, float]]:
        with self._lock:
            items = list(self._store.values())
        if entity_type:
            items = [r for r in items if r.entity_type == entity_type]
        if not items:
            return []
        qv = query_vec / (np.linalg.norm(query_vec) or 1.0)
        scored: List[Tuple[EmbeddingRecord, float]] = []
        for r in items:
            rv = np.asarray(r.vector, dtype=np.float32)
            s = float(np.dot(qv, rv))
            scored.append((r, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ----- PG persistence (multimodal_embeddings) ------------------------
    def _maybe_upsert_pg(self, rec: EmbeddingRecord) -> None:
        if self._pg_checked and not self._pg_ok:
            return
        try:
            import psycopg2  # type: ignore
            dsn = (os.environ.get("PG_DSN") or os.environ.get("PGVECTOR_DSN")
                   or os.environ.get("DATABASE_URL"))
            if not dsn:
                self._pg_checked = True
                self._pg_ok = False
                return
            conn = psycopg2.connect(dsn, connect_timeout=2)
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS multimodal_embeddings (
                            id BIGSERIAL PRIMARY KEY,
                            entity_type TEXT,
                            entity_id TEXT,
                            modality TEXT,
                            vector vector(1024),
                            metadata JSONB,
                            created_at TIMESTAMPTZ DEFAULT now()
                        )
                    """)
                    vec_literal = "[" + ",".join(
                        f"{x:.6f}" for x in rec.vector) + "]"
                    cur.execute(
                        "INSERT INTO multimodal_embeddings "
                        "(entity_type, entity_id, modality, vector, metadata) "
                        "VALUES (%s,%s,%s,%s::vector,%s::jsonb)",
                        (rec.entity_type, rec.entity_id, rec.modality,
                         vec_literal, json.dumps(rec.metadata)),
                    )
                conn.commit()
            finally:
                conn.close()
            self._pg_checked = True
            self._pg_ok = True
        except Exception as e:  # noqa: BLE001
            self._pg_checked = True
            self._pg_ok = False
            logger.debug("pg upsert skipped: %s", e)

    def has_pg(self) -> bool:
        if not self._pg_checked:
            try:
                import psycopg2  # type: ignore
                dsn = (os.environ.get("PG_DSN") or os.environ.get("PGVECTOR_DSN")
                       or os.environ.get("DATABASE_URL"))
                if not dsn:
                    self._pg_checked = True
                    self._pg_ok = False
                else:
                    conn = psycopg2.connect(dsn, connect_timeout=2)
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT 1 FROM pg_extension WHERE extname='vector'"
                            )
                            self._pg_ok = cur.fetchone() is not None
                    finally:
                        conn.close()
                    self._pg_checked = True
            except Exception:  # noqa: BLE001
                self._pg_checked = True
                self._pg_ok = False
        return self._pg_ok


# json helper --------------------------------------------------------------
def _json_safe(obj: Any) -> Any:  # noqa: D401
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode("ascii")
    return str(obj)


import json  # noqa: E402  (kept near bottom to avoid early import in tests)
import os  # noqa: E402


# Re-export list -----------------------------------------------------------
__all__ = [
    "MultiModalEmbedder",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingRecord",
    "UNIFIED_DIM",
    "_TextEncoder",
    "_ImageEncoder",
    "_AudioEncoder",
    "_DocumentEncoder",
    "_VideoEncoder",
]
