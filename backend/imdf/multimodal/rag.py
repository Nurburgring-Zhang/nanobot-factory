"""P4-7-W1: MultimodalRAG — cross-modal retrieval augmented generation.

The RAG stack is intentionally tiny:

* ``VectorStore``        — in-memory cosine index over heterogeneous embeddings
* ``MultimodalRAG``      — top-level façade used by API and Agent

Embeddings come from ``MultimodalEmbedder``.  Documents come from
``parsers.parse_media`` (returns ``ParsedMedia`` with text + chunks).

The RAG API:

* ``index(refs)``  — add media to the index
* ``search(query, top_k=5)`` — return ranked ``RetrievedItem`` list
* ``answer(query, top_k=5)`` — return text + citations (LLM stub falls back to
  concatenation of top chunks when no model is available)
"""
from __future__ import annotations

import heapq
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .embedders import Embedding, MultimodalEmbedder, cosine
from .parsers import ParsedMedia, parse_media
from .types import MediaRef, ModalKind

logger = logging.getLogger(__name__)


@dataclass
class RetrievedItem:
    media: MediaRef
    score: float
    chunk: str
    parsed_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "media": self.media.to_dict(),
            "score": round(self.score, 6),
            "chunk": self.chunk[:400],
            "parsed_hash": self.parsed_hash,
        }


# ── in-memory cosine index ────────────────────────────────────────────────
class VectorStore:
    def __init__(self, embedder: Optional[MultimodalEmbedder] = None) -> None:
        self.embedder = embedder or MultimodalEmbedder()
        self._items: List[Embedding] = []

    def add(self, emb: Embedding) -> None:
        self._items.append(emb)

    def add_media(self, ref: MediaRef) -> ParsedMedia:
        parsed = parse_media(ref) if ref.kind != ModalKind.TEXT else ParsedMedia(
            kind=ModalKind.TEXT, text=ref.text or "", chunks=[ref.text or ""]
        )
        emb = self.embedder.embed(ref)
        self.add(emb)
        return parsed

    def query(self, vec: List[float], top_k: int = 5) -> List[RetrievedItem]:
        scored = []
        for emb in self._items:
            s = cosine(vec, emb.vector)
            scored.append((s, emb))
        scored.sort(key=lambda x: x[0], reverse=True)
        out: List[RetrievedItem] = []
        for s, emb in scored[:top_k]:
            chunk = (emb.ref.text or "")[:400]
            if not chunk:
                parsed = parse_media(emb.ref)
                chunk = parsed.text
            out.append(
                RetrievedItem(
                    media=emb.ref,
                    score=s,
                    chunk=chunk,
                    parsed_hash=emb.parsed_hash,
                )
            )
        return out

    def __len__(self) -> int:
        return len(self._items)


# ── high-level façade ─────────────────────────────────────────────────────
class MultimodalRAG:
    """Public RAG façade."""

    def __init__(self, store: Optional[VectorStore] = None) -> None:
        self.store = store or VectorStore()

    # ── write side ──────────────────────────────────────────────────────
    def index(self, refs: List[MediaRef]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in refs:
            parsed = self.store.add_media(r)
            out.append(parsed.to_dict())
        return out

    # ── read side ───────────────────────────────────────────────────────
    def search(
        self,
        query: MediaRef,
        top_k: int = 5,
    ) -> List[RetrievedItem]:
        emb = self.store.embedder.embed(query)
        return self.store.query(emb.vector, top_k=top_k)

    def answer(
        self,
        query: MediaRef,
        top_k: int = 5,
        llm_call: Optional[Any] = None,
    ) -> Dict[str, Any]:
        t0 = time.time()
        items = self.search(query, top_k=top_k)
        citations = [it.to_dict() for it in items]
        if llm_call is not None and items:
            ctx = "\n\n".join(f"[{i + 1}] {it.chunk}" for i, it in enumerate(items))
            prompt = (
                "Answer the user query using ONLY the following cross-modal context.\n"
                f"Context:\n{ctx}\n\nQuery:\n{query.text or query.url or ''}"
            )
            try:
                text = str(llm_call(prompt))
            except Exception as exc:  # pragma: no cover
                logger.debug("LLM call failed: %s", exc)
                text = "\n".join(it.chunk for it in items[:3])
        else:
            text = "\n".join(it.chunk for it in items[:3]) if items else ""
        return {
            "request_id": f"rag-{uuid.uuid4().hex[:10]}",
            "text": text,
            "citations": citations,
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
        }