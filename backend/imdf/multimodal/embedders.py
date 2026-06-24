"""P4-7-W1: Multimodal embedders.

Two implementations live here:

* ``CLIPEmbedder``     — image ↔ text shared 512-d embedding (preferred)
* ``MultimodalEmbedder`` — image / video / audio / text → vector

Heavy model dependencies (``open_clip``, ``transformers``) are imported lazily
with a deterministic hash-based fallback.  In tests the fallback path is
exercised — vectors are stable for a given input so RAG results remain
reproducible.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .types import MediaRef, ModalKind
from .parsers import ParsedMedia, parse_media

logger = logging.getLogger(__name__)


DIM = 512  # shared vector dim


def _stable_vector(seed: str, dim: int = DIM) -> List[float]:
    """Deterministic unit vector derived from a string seed.

    Used as a hermetic fallback when no real model is installed.  The vector is
    L2-normalised so cosine similarity reduces to a dot product.
    """
    out: List[float] = []
    for i in range(dim):
        h = hashlib.sha256(f"{seed}::{i}".encode("utf-8")).digest()
        # take 4 bytes → float32 → map to [-1, 1]
        val = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
        out.append(val * 2 - 1)
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def _cos(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


@dataclass
class Embedding:
    vector: List[float]
    kind: ModalKind
    ref: MediaRef
    parsed_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dim": len(self.vector),
            "kind": self.kind.value,
            "ref": self.ref.short_id(),
            "parsed_hash": self.parsed_hash,
        }


# ── CLIP-style image↔text embedder ────────────────────────────────────────
class CLIPEmbedder:
    """Image-text joint embedder.  Falls back to deterministic hash vectors."""

    name = "clip-stub"

    def __init__(self) -> None:
        self._real = None
        if os.environ.get("MULTIMODAL_LLM_DISABLED") == "1" or os.environ.get("MULTIMODAL_GENERATION_DISABLE_PROVIDERS") == "1":
            return
        try:  # pragma: no cover - optional
            import open_clip  # type: ignore
            self._real = open_clip
        except Exception:
            self._real = None

    def embed_image(self, ref: MediaRef, parsed: Optional[ParsedMedia] = None) -> Embedding:
        parsed = parsed or parse_media(ref)
        if self._real is not None and ref.data_b64:  # pragma: no cover
            try:
                import torch  # type: ignore
                model, _, preprocess = self._real.create_model_and_transforms(
                    "ViT-B-32", pretrained="laion2b_s34b_b79k"
                )
                from PIL import Image  # type: ignore
                import base64
                import io as _io
                img = Image.open(_io.BytesIO(base64.b64decode(ref.data_b64.split(",", 1)[-1])))
                tensor = preprocess(img).unsqueeze(0)
                with torch.no_grad():
                    feat = model.encode_image(tensor)
                v = feat[0].tolist()
                return Embedding(vector=v, kind=ModalKind.IMAGE, ref=ref, parsed_hash=parsed.content_hash)
            except Exception as exc:
                logger.debug("open_clip image embed failed: %s", exc)
        v = _stable_vector(f"img::{parsed.content_hash or ref.short_id()}")
        return Embedding(vector=v, kind=ModalKind.IMAGE, ref=ref, parsed_hash=parsed.content_hash)

    def embed_text(self, text: str) -> Embedding:
        if self._real is not None:  # pragma: no cover
            try:
                import torch  # type: ignore
                model, _, _ = self._real.create_model_and_transforms(
                    "ViT-B-32", pretrained="laion2b_s34b_b79k"
                )
                tokenizer = self._real.get_tokenizer("ViT-B-32")
                tokens = tokenizer([text])
                with torch.no_grad():
                    feat = model.encode_text(tokens)
                v = feat[0].tolist()
                ref = MediaRef(kind=ModalKind.TEXT, text=text)
                return Embedding(vector=v, kind=ModalKind.TEXT, ref=ref)
            except Exception as exc:
                logger.debug("open_clip text embed failed: %s", exc)
        v = _stable_vector(f"txt::{text[:200]}")
        ref = MediaRef(kind=ModalKind.TEXT, text=text)
        return Embedding(vector=v, kind=ModalKind.TEXT, ref=ref)


# ── multimodal dispatcher (image/video/audio/text → vector) ───────────────
class MultimodalEmbedder:
    """Wrap CLIPEmbedder + per-modal dispatch."""

    def __init__(self, clip: Optional[CLIPEmbedder] = None) -> None:
        self.clip = clip or CLIPEmbedder()

    def embed(self, ref: MediaRef) -> Embedding:
        if ref.kind == ModalKind.TEXT:
            return self.clip.embed_text(ref.text or "")
        if ref.kind == ModalKind.IMAGE:
            return self.clip.embed_image(ref)
        parsed = parse_media(ref)
        # collapse non-image to text → vector (good enough for stub; deterministic)
        return self.clip.embed_text(parsed.text or ref.short_id())


def cosine(a: List[float], b: List[float]) -> float:
    return _cos(a, b)