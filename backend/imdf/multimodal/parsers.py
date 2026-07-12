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
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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
def _parse_video_with_cv2(path: str) -> Optional[Dict[str, Any]]:
    """Try to read video metadata with OpenCV (container-level only — no frame decoding).

    Returns a dict with fps/frame_count/width/height/duration_sec/codec, or
    ``None`` if cv2 is not available or fails to open the file. The CAP_PROP_*
    accessors read container-level metadata (essentially free — no frame
    decoding happens).
    """
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - cv2 missing
        logger.debug("cv2 not available: %s", exc)
        return None
    cap = cv2.VideoCapture()
    try:
        if not cap.open(path):
            return None
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        # 4-char codec from FOURCC, e.g. "avc1" / "mp4v"
        try:
            fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
            codec = "".join(
                chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)
            ).strip("\x00") or None
        except Exception:
            codec = None
        if frames <= 0 and fps > 0:
            # Some containers don't report FRAME_COUNT until read; if we got
            # a real fps + width, treat it as a valid parse.
            duration = 0.0
        else:
            duration = round(frames / fps, 3) if fps > 0 else 0.0
        return {
            "fps": round(fps, 3),
            "frame_count": frames,
            "width": width,
            "height": height,
            "duration_sec": duration,
            "codec": codec,
        }
    except Exception as exc:
        logger.debug("cv2 VideoCapture failed for %s: %s", path, exc)
        return None
    finally:
        try:
            cap.release()
        except Exception:  # pragma: no cover
            pass


def _parse_video_metadata(
    source_path: Optional[Union[str, Path]] = None,
    *,
    data: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Lightweight file-level video metadata (P21 P2 P4 simplified contract).

    Contract (per R1-F3 fix spec):
      - ``size_bytes`` (always)
      - ``path``       (always — the real file path or the tempfile path used
                        for parsing; the tempfile is cleaned up on return)
      - ``source``:    "cv2" if cv2 produced real metadata
                       "file" if cv2 was unavailable or returned no real data
      - If cv2 worked: also ``fps``, ``frame_count``, ``width``, ``height``,
                       ``duration_sec``, ``codec``

    Does NOT do full video frame decoding. Does NOT require ffprobe.
    """
    # 1. Resolve to a real path (write bytes to tempfile if needed)
    tmp_path: Optional[str] = None
    cleanup_tmp = False
    if source_path is not None and os.path.isfile(str(source_path)):
        path_for_cv2 = str(source_path)
        try:
            size_b = os.path.getsize(path_for_cv2)
        except OSError:
            size_b = 0
    elif data is not None:
        # Preserve a real extension when the source is known — helps cv2
        # container detection.
        suffix = ".mp4"
        if source_path is not None:
            _, ext = os.path.splitext(str(source_path))
            if ext:
                suffix = ext
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        except Exception:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
        cleanup_tmp = True
        path_for_cv2 = tmp_path
        size_b = len(data)
    else:
        path_for_cv2 = None
        size_b = 0

    # 2. Try cv2 for container-level metadata (no frame decoding)
    cv2_meta: Optional[Dict[str, Any]] = None
    if path_for_cv2 is not None:
        cv2_meta = _parse_video_with_cv2(path_for_cv2)
    cv2_ok = (
        cv2_meta is not None
        and (
            int(cv2_meta.get("frame_count", 0) or 0) > 0
            or int(cv2_meta.get("width", 0) or 0) > 0
        )
    )

    # 3. Build the result dict
    if cv2_ok:
        out: Dict[str, Any] = {
            "size_bytes": size_b,
            "path": path_for_cv2 or "",
            "source": "cv2",
        }
        for k in ("fps", "frame_count", "width", "height", "duration_sec", "codec"):
            if k in cv2_meta:  # type: ignore[operator]
                out[k] = cv2_meta[k]  # type: ignore[index]
    else:
        out = {
            "size_bytes": size_b,
            "path": path_for_cv2 or "",
            "source": "file",
        }

    # 4. Cleanup the tempfile we created (if any)
    if cleanup_tmp and tmp_path and os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return out


# Backward-compat alias — the previous (failed-attempt) implementation
# exported a ``_parse_video_real`` helper. Older callers that import it
# keep working; the new function returns the same lightweight contract.
_parse_video_real = _parse_video_metadata


class VideoParser:
    """Video → text + frame count + meta.

    Lightweight parser (P21 P2 P4): returns file-level metadata (size, path)
    and, when cv2 is available, optional container-level metadata
    (fps/width/height/frames/duration/codec).

    Does NOT do full video frame decoding. Does NOT require ffprobe.

    Backward-compatible:
      - ``parse(MediaRef)``  — original API
      - ``parse(str/Path)``  — direct file path
      - ``parse(bytes)``     — in-memory bytes (written to a tempfile, decoded,
                              tempfile cleaned up on return)
    """

    def parse(self, ref: Union[MediaRef, str, Path, bytes, bytearray]) -> ParsedMedia:
        # ── Normalize input to (data, source_path, ref_label) ───────────
        data: Optional[bytes] = None
        source_path: Optional[Union[str, Path]] = None
        ref_label: str = ""
        is_invalid = False

        if isinstance(ref, MediaRef):
            ref_label = ref.short_id()
            # Prefer a local file URL — avoids tempfile round-trip.
            if ref.url and os.path.isfile(ref.url):
                source_path = ref.url
                try:
                    with open(ref.url, "rb") as f:
                        data = f.read()
                except OSError:
                    data = None
            if data is None:
                data = _load_bytes(ref) or None
        elif isinstance(ref, (str, Path)):
            ref_label = str(ref)
            sp = str(ref)
            if os.path.isfile(sp):
                source_path = sp
                try:
                    with open(sp, "rb") as f:
                        data = f.read()
                except OSError as exc:
                    raise FileNotFoundError(
                        f"VideoParser: cannot read file {sp!r}: {exc}"
                    ) from exc
            else:
                # Path provided but file doesn't exist — raise, don't silently stub.
                raise FileNotFoundError(
                    f"VideoParser: file not found: {sp!r}"
                )
        elif isinstance(ref, (bytes, bytearray)):
            data = bytes(ref)
            ref_label = f"<bytes:{len(data)}>"
        else:
            raise TypeError(
                f"VideoParser.parse: unsupported input type "
                f"{type(ref).__name__!r}; expected MediaRef, str/Path, or bytes"
            )

        if data is None and source_path is None:
            # Nothing to parse — caller did not provide usable bytes or a
            # readable file. Surface as explicit invalid input (no silent stub).
            is_invalid = True
            meta_out: Dict[str, Any] = {
                "size_bytes": 0,
                "path": "",
                "source": "none",
            }
        else:
            meta_out = _parse_video_metadata(source_path=source_path, data=data)

        # Surface the parsed values onto the ParsedMedia wrapper.
        width = int(meta_out.get("width", 0) or 0)
        height = int(meta_out.get("height", 0) or 0)
        fps = float(meta_out.get("fps", 0.0) or 0.0)
        frames = int(meta_out.get("frame_count", 0) or 0)
        duration = float(meta_out.get("duration_sec", 0.0) or 0.0)
        source = meta_out.get("source") or "none"

        # Compose a human-readable text summary.
        if is_invalid:
            text = _stub_text(
                MediaRef(kind=ModalKind.VIDEO, url=ref_label or None),
                "video (no data)",
            )
            content_hash = hashlib.sha1(ref_label.encode("utf-8")).hexdigest()[:16]
        else:
            if source == "cv2":
                text = (
                    f"video {width}x{height} {fps}fps {duration}s "
                    f"{frames}frames codec={meta_out.get('codec') or '?'} src=cv2"
                )
            else:
                # File-level fallback — no decoded metadata
                text = (
                    f"video file {meta_out.get('size_bytes', 0)}B "
                    f"src=file path={meta_out.get('path', '')}"
                )
            content_hash = _hash_content("video", data) if data else hashlib.sha1(
                ref_label.encode("utf-8")
            ).hexdigest()[:16]

        return ParsedMedia(
            kind=ModalKind.VIDEO,
            text=text,
            meta=meta_out,
            chunks=[text],
            frames=frames,
            duration_sec=duration,
            content_hash=content_hash,
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