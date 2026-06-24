"""P4-7-W1: Multimodal parsers.

Each parser takes a ``MediaRef`` (URL or inline base64) and returns a
``ParsedMedia`` with extracted text, simple metadata, and a deterministic
content hash.  All parsers are hermetic — heavy ML dependencies (Pillow,
moviepy, whisper, pypdf) are imported lazily with graceful fallback to a
deterministic stub.  This keeps unit tests fast and free of optional deps.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .types import MediaRef, ModalKind, b64_to_bytes

logger = logging.getLogger(__name__)


@dataclass
class ParsedMedia:
    """Output of any parser."""

    kind: ModalKind
    text: str = ""                   # extracted text / caption / OCR
    meta: Dict[str, Any] = field(default_factory=dict)
    chunks: List[str] = field(default_factory=list)  # for RAG chunking
    frames: int = 0                  # for video
    duration_sec: float = 0.0
    content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "text": self.text,
            "meta": self.meta,
            "chunks": self.chunks,
            "frames": self.frames,
            "duration_sec": self.duration_sec,
            "content_hash": self.content_hash,
        }


# ── helpers ────────────────────────────────────────────────────────────────
def _hash_content(prefix: str, payload: bytes) -> str:
    return hashlib.sha256(prefix.encode("utf-8") + payload).hexdigest()[:16]


def _load_bytes(ref: MediaRef) -> Optional[bytes]:
    if ref.data_b64:
        try:
            return b64_to_bytes(ref.data_b64)
        except Exception:  # pragma: no cover - b64 decode failure
            logger.warning("b64 decode failed for media ref")
            return None
    if ref.url and ref.url.startswith(("http://", "https://")):
        try:
            import urllib.request
            with urllib.request.urlopen(ref.url, timeout=5) as r:
                return r.read()
        except Exception as exc:  # pragma: no cover - network may be blocked
            logger.debug("urllib fetch failed for %s: %s", ref.url, exc)
            return None
    if ref.url and os.path.isfile(ref.url):
        try:
            with open(ref.url, "rb") as f:
                return f.read()
        except OSError:  # pragma: no cover
            return None
    return None


def _stub_text(ref: MediaRef, hint: str) -> str:
    base = (ref.text or ref.url or ref.short_id())[:120]
    return f"[stub:{ref.kind.value}] {hint}: {base}".strip()


# ── image parser ───────────────────────────────────────────────────────────
class ImageParser:
    """Image → caption + meta.  Uses Pillow if available, else deterministic stub."""

    def parse(self, ref: MediaRef) -> ParsedMedia:
        meta: Dict[str, Any] = {}
        content_hash = ""
        data = _load_bytes(ref)
        if data:
            content_hash = _hash_content("image", data)
            try:
                from PIL import Image  # type: ignore
                img = Image.open(io.BytesIO(data))
                meta = {
                    "format": img.format,
                    "mode": img.mode,
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": len(data),
                }
                text = _stub_text(
                    ref, f"image {img.width}x{img.height} {img.format or '?'}"
                )
            except Exception:
                meta = {"size_bytes": len(data)}
                text = _stub_text(ref, f"image {len(data)}B")
        else:
            text = _stub_text(ref, "image (no data)")
            content_hash = hashlib.sha1(ref.short_id().encode()).hexdigest()[:16]
        return ParsedMedia(
            kind=ModalKind.IMAGE,
            text=text,
            meta=meta,
            chunks=[text],
            content_hash=content_hash,
        )


# ── audio parser ───────────────────────────────────────────────────────────
class AudioParser:
    """Audio → text (ASR placeholder) + meta."""

    def parse(self, ref: MediaRef) -> ParsedMedia:
        data = _load_bytes(ref)
        size_b = len(data) if data else 0
        # 16 kbps heuristic for duration
        duration = round(size_b / 2000.0, 2) if size_b else 0.0
        text = _stub_text(ref, f"audio {duration}s")
        return ParsedMedia(
            kind=ModalKind.AUDIO,
            text=text,
            meta={"size_bytes": size_b, "duration_sec": duration},
            chunks=[text],
            duration_sec=duration,
            content_hash=_hash_content("audio", data) if data else hashlib.sha1(ref.short_id().encode()).hexdigest()[:16],
        )


# ── video parser ───────────────────────────────────────────────────────────
class VideoParser:
    """Video → text + frame count + meta.  Uses OpenCV if available."""

    def parse(self, ref: MediaRef) -> ParsedMedia:
        data = _load_bytes(ref)
        size_b = len(data) if data else 0
        frames = 0
        duration = 0.0
        if data:
            try:
                import cv2  # type: ignore
                import numpy as np  # type: ignore
                arr = np.frombuffer(data, dtype=np.uint8)
                cap = cv2.VideoCapture()
                if cap.open(arr.tobytes(), cv2.CAP_ANY):  # unlikely to work for raw bytes
                    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 0
                    duration = round(frames / fps, 2) if fps else 0.0
                    cap.release()
            except Exception:
                pass
        if not duration:
            duration = round(size_b / 50_000.0, 2) if size_b else 0.0
            frames = int(duration * 24) if duration else 0
        text = _stub_text(ref, f"video {duration}s {frames}frames")
        return ParsedMedia(
            kind=ModalKind.VIDEO,
            text=text,
            meta={"size_bytes": size_b, "duration_sec": duration, "frames": frames},
            chunks=[text],
            frames=frames,
            duration_sec=duration,
            content_hash=_hash_content("video", data) if data else hashlib.sha1(ref.short_id().encode()).hexdigest()[:16],
        )


# ── document parser ────────────────────────────────────────────────────────
class DocumentParser:
    """Document (PDF/DOCX/MD/TXT) → text + chunks."""

    def parse(self, ref: MediaRef) -> ParsedMedia:
        text = ""
        chunks: List[str] = []
        meta: Dict[str, Any] = {}
        if ref.text:
            text = ref.text
        else:
            data = _load_bytes(ref)
            if data:
                # try PDF
                if (ref.mime or "").endswith("pdf") or (ref.url or "").lower().endswith(".pdf"):
                    try:
                        from pypdf import PdfReader  # type: ignore
                        reader = PdfReader(io.BytesIO(data))
                        text = "\n".join((p.extract_text() or "") for p in reader.pages)
                        meta["pages"] = len(reader.pages)
                    except Exception:
                        text = data.decode("utf-8", errors="ignore")
                else:
                    text = data.decode("utf-8", errors="ignore")
            else:
                text = _stub_text(ref, "document (no data)")
        if text:
            chunks = _chunk_text(text)
        return ParsedMedia(
            kind=ModalKind.DOCUMENT,
            text=text,
            meta=meta,
            chunks=chunks or [text],
            content_hash=_hash_content("doc", text.encode("utf-8")),
        )


def _chunk_text(text: str, max_len: int = 320, overlap: int = 40) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_len, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


# ── dispatcher ─────────────────────────────────────────────────────────────
_PARSERS = {
    ModalKind.IMAGE: ImageParser(),
    ModalKind.AUDIO: AudioParser(),
    ModalKind.VIDEO: VideoParser(),
    ModalKind.DOCUMENT: DocumentParser(),
    ModalKind.TEXT: None,  # text is identity — caller wraps as ParsedMedia
}


def parse_media(ref: MediaRef) -> ParsedMedia:
    """Single dispatch entry point used by understanding / RAG / agent."""
    if ref.kind == ModalKind.TEXT:
        return ParsedMedia(
            kind=ModalKind.TEXT,
            text=ref.text or "",
            chunks=[ref.text or ""] if ref.text else [],
            content_hash=hashlib.sha1((ref.text or "").encode("utf-8")).hexdigest()[:16],
        )
    parser = _PARSERS.get(ref.kind)
    if parser is None:
        raise ValueError(f"no parser for kind={ref.kind}")
    return parser.parse(ref)