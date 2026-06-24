"""P3-3-W2: search-service routes.

REST surface:
  GET    /healthz
  GET    /api/v1/search/text?q=&top_k=            BM25 / keyword
  GET    /api/v1/search/semantic?q=&top_k=        hybrid vector + BM25
  GET    /api/v1/search/vector?q=&top_k=          vector cosine
  POST   /api/v1/search/vector/query              vector query (post payload)
  POST   /api/v1/search/documents                 ingest a document
  GET    /api/v1/search/documents                 list corpus
  GET    /api/v1/search/documents/{doc_id}        get one
  DELETE /api/v1/search/documents/{doc_id}        drop one
  GET    /api/v1/search/stats                     corpus + index stats
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search-service"])


# =====================================================================
# Document model
# =====================================================================

class DocumentIn(BaseModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    title: str = Field(default="", max_length=256)
    content: str = Field(..., min_length=1, max_length=20000)
    tags: List[str] = Field(default_factory=list)
    modality: str = Field(default="text", max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("modality")
    @classmethod
    def _v_modality(cls, v: str) -> str:
        allowed = {"text", "image", "audio", "video", "multimodal"}
        if v not in allowed:
            raise ValueError(f"modality must be one of {sorted(allowed)}")
        return v


class Document(DocumentIn):
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        return d


# =====================================================================
# Search engine (lightweight, in-process)
# =====================================================================

_TOKEN_RE_LOCAL = __import__("re").compile(r"[\w]+", __import__("re").UNICODE)


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    text = text.lower()
    toks = _TOKEN_RE_LOCAL.findall(text)
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
        bigrams = ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]
        toks = toks + bigrams
    return toks


@dataclass
class _Vec:
    """Lightweight TF-IDF cosine similarity index."""
    dim: int = 256
    _docs: List[str] = field(default_factory=list)
    _vecs: List[List[float]] = field(default_factory=list)

    def fit(self, doc_text: str) -> List[float]:
        toks = _tokenize(doc_text)
        vec = [0.0] * self.dim
        for t in toks:
            h = abs(hash(t)) % self.dim
            vec[h] += 1.0
        # L2 norm
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def add(self, doc_id: str, text: str) -> None:
        self._docs.append(doc_id)
        self._vecs.append(self.fit(text))

    def query(self, text: str, top_k: int = 10) -> List[Tuple[str, float]]:
        qv = self.fit(text)
        scored: List[Tuple[str, float]] = []
        for did, dv in zip(self._docs, self._vecs):
            s = sum(a * b for a, b in zip(qv, dv))
            if s > 0:
                scored.append((did, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def clear(self) -> None:
        self._docs.clear()
        self._vecs.clear()


class _BM25:
    """Tiny BM25 with default k1=1.5, b=0.75."""
    k1 = 1.5
    b = 0.75

    def __init__(self) -> None:
        self._docs: List[str] = []
        self._toks: List[List[str]] = []
        self._df: Dict[str, int] = {}
        self._avgdl = 0.0
        self._N = 0

    def add(self, doc_id: str, text: str) -> None:
        toks = _tokenize(text)
        self._docs.append(doc_id)
        self._toks.append(toks)
        self._N += 1
        self._avgdl = (
            self._avgdl * (self._N - 1) + len(toks)) / self._N
        seen = set()
        for t in toks:
            if t not in seen:
                self._df[t] = self._df.get(t, 0) + 1
                seen.add(t)

    def query(self, text: str, top_k: int = 10) -> List[Tuple[str, float]]:
        q_toks = _tokenize(text)
        if not q_toks or self._N == 0:
            return []
        scores: Dict[str, float] = {}
        for qt in q_toks:
            df = self._df.get(qt, 0)
            if df == 0:
                continue
            idf = math.log(1 + (self._N - df + 0.5) / (df + 0.5))
            for did, toks in zip(self._docs, self._toks):
                tf = toks.count(qt)
                if tf == 0:
                    continue
                dl = len(toks)
                denom = tf + self.k1 * (
                    1 - self.b + self.b * dl / max(1e-9, self._avgdl))
                s = idf * (tf * (self.k1 + 1)) / denom
                scores[did] = scores.get(did, 0.0) + s
        out = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return out[:top_k]

    def clear(self) -> None:
        self._docs.clear()
        self._toks.clear()
        self._df.clear()
        self._avgdl = 0.0
        self._N = 0


@dataclass
class SearchEngine:
    """Aggregates text + vector + hybrid + pgvector-capable vector search."""
    _lock: threading.RLock = field(default_factory=threading.RLock)
    docs: Dict[str, Document] = field(default_factory=dict)
    vec: _Vec = field(default_factory=_Vec)
    bm25: _BM25 = field(default_factory=_BM25)
    _pgvector_ok: Optional[bool] = None

    # ----- corpus size & dim -----
    def corpus_size(self) -> int:
        with self._lock:
            return len(self.docs)

    def vector_dim(self) -> int:
        return self.vec.dim

    def has_pgvector(self) -> bool:
        if self._pgvector_ok is None:
            self._pgvector_ok = self._probe_pgvector()
        return self._pgvector_ok

    # ----- document CRUD -----
    def add_document(self, doc: Document) -> Document:
        with self._lock:
            if not doc.id:
                doc.id = f"doc-{uuid.uuid4().hex[:12]}"
            existing = self.docs.get(doc.id)
            if existing is not None:
                # remove from indexes first
                self._remove_from_indexes(doc.id)
            self.docs[doc.id] = doc
            blob = f"{doc.title}\n{doc.content}\n{' '.join(doc.tags)}"
            self.vec.add(doc.id, blob)
            self.bm25.add(doc.id, blob)
            if self.has_pgvector():
                self._upsert_pgvector(doc, blob)
            return doc

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self.docs:
                return False
            self.docs.pop(doc_id, None)
            self._remove_from_indexes(doc_id)
            if self.has_pgvector():
                self._delete_pgvector(doc_id)
            return True

    def _remove_from_indexes(self, doc_id: str) -> None:
        # Tiny in-memory indexes — rebuild on delete for simplicity
        items = list(self.docs.values())
        self.vec.clear()
        self.bm25.clear()
        for d in items:
            blob = f"{d.title}\n{d.content}\n{' '.join(d.tags)}"
            self.vec.add(d.id, blob)
            self.bm25.add(d.id, blob)

    # ----- search modes -----
    def text_search(self, q: str, top_k: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            hits = self.bm25.query(q, top_k=top_k)
            out: List[Dict[str, Any]] = []
            for did, score in hits:
                d = self.docs.get(did)
                if d is None:
                    continue
                out.append({
                    "id": d.id, "title": d.title,
                    "snippet": d.content[:200], "score": float(score),
                    "modality": d.modality, "tags": list(d.tags),
                })
            return out

    def semantic_search(self, q: str, top_k: int = 10,
                        alpha: float = 0.5) -> List[Dict[str, Any]]:
        """Hybrid: alpha * vector + (1-alpha) * BM25. alpha in [0, 1]."""
        alpha = max(0.0, min(1.0, alpha))
        with self._lock:
            vec_hits = dict(self.vec.query(q, top_k=top_k * 3))
            bm_hits = dict(self.bm25.query(q, top_k=top_k * 3))
            all_ids = set(vec_hits) | set(bm_hits)
            # normalise each side to [0, 1]
            def _norm(m: Dict[str, float]) -> Dict[str, float]:
                if not m:
                    return {}
                mx = max(m.values())
                if mx <= 0:
                    return {}
                return {k: v / mx for k, v in m.items()}
            v = _norm(vec_hits)
            b = _norm(bm_hits)
            scored: List[Tuple[str, float]] = []
            for did in all_ids:
                s = alpha * v.get(did, 0.0) + (1 - alpha) * b.get(did, 0.0)
                if s > 0:
                    scored.append((did, s))
            scored.sort(key=lambda x: x[1], reverse=True)
            out: List[Dict[str, Any]] = []
            for did, score in scored[:top_k]:
                d = self.docs.get(did)
                if d is None:
                    continue
                out.append({
                    "id": d.id, "title": d.title,
                    "snippet": d.content[:200], "score": float(score),
                    "modality": d.modality, "tags": list(d.tags),
                    "components": {
                        "vector": v.get(did, 0.0),
                        "bm25": b.get(did, 0.0),
                    },
                })
            return out

    def vector_search(self, q: str, top_k: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            hits = self.vec.query(q, top_k=top_k)
            out: List[Dict[str, Any]] = []
            for did, score in hits:
                d = self.docs.get(did)
                if d is None:
                    continue
                out.append({
                    "id": d.id, "title": d.title,
                    "snippet": d.content[:200], "score": float(score),
                    "modality": d.modality, "tags": list(d.tags),
                })
            return out

    # ----- pgvector (best-effort) -----
    def _probe_pgvector(self) -> bool:
        try:
            dsn = os.environ.get("PG_DSN") or os.environ.get(
                "PGVECTOR_DSN") or os.environ.get("DATABASE_URL")
            if not dsn:
                return False
            import psycopg2  # type: ignore
            conn = psycopg2.connect(dsn, connect_timeout=2)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM pg_extension WHERE extname='vector'")
                    ok = cur.fetchone() is not None
                return bool(ok)
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return False

    def _upsert_pgvector(self, doc: Document, blob: str) -> None:
        try:
            import psycopg2  # type: ignore
            dsn = os.environ.get("PG_DSN") or os.environ.get(
                "PGVECTOR_DSN") or os.environ.get("DATABASE_URL")
            if not dsn:
                return
            conn = psycopg2.connect(dsn, connect_timeout=2)
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS search_corpus (
                            id TEXT PRIMARY KEY,
                            title TEXT,
                            content TEXT,
                            tags TEXT,
                            embedding vector(256)
                        )
                    """)
                    emb = self.vec.fit(blob)
                    # Format as pgvector literal: '[v1,v2,...]'
                    vec_literal = "[" + ",".join(
                        f"{x:.6f}" for x in emb) + "]"
                    cur.execute(
                        "INSERT INTO search_corpus (id, title, content, tags, embedding) "
                        "VALUES (%s,%s,%s,%s,%s::vector) "
                        "ON CONFLICT (id) DO UPDATE SET "
                        "title=EXCLUDED.title, content=EXCLUDED.content, "
                        "tags=EXCLUDED.tags, embedding=EXCLUDED.embedding",
                        (doc.id, doc.title, doc.content,
                         ",".join(doc.tags), vec_literal))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("pgvector upsert skipped: %s", e)

    def _delete_pgvector(self, doc_id: str) -> None:
        try:
            import psycopg2  # type: ignore
            dsn = os.environ.get("PG_DSN") or os.environ.get(
                "PGVECTOR_DSN") or os.environ.get("DATABASE_URL")
            if not dsn:
                return
            conn = psycopg2.connect(dsn, connect_timeout=2)
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM search_corpus WHERE id=%s",
                                (doc_id,))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("pgvector delete skipped: %s", e)


# =====================================================================
# Singleton + seed
# =====================================================================

_ENGINE: Optional[SearchEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_search_engine() -> SearchEngine:
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = SearchEngine()
                _seed_demo_corpus(_ENGINE)
    return _ENGINE


def _seed_demo_corpus(eng: SearchEngine) -> None:
    samples: List[Tuple[str, str, str, List[str]]] = [
        ("doc-001", "Image Generation Overview",
         "Stable Diffusion is a latent text-to-image diffusion model capable "
         "of generating photo-realistic images given any text input.",
         ["image", "diffusion", "t2i"]),
        ("doc-002", "Workflow DAG Design",
         "A DAG (Directed Acyclic Graph) defines node dependencies for "
         "workflow execution. Topological sort yields execution waves.",
         ["workflow", "dag", "topology"]),
        ("doc-003", "Notification Channels",
         "Push notifications can be delivered via WebSocket, email, "
         "or webhook fan-out. Each channel has its own delivery contract.",
         ["notification", "websocket", "email"]),
        ("doc-004", "Vector Retrieval Basics",
         "Vector retrieval uses cosine similarity between embedding vectors. "
         "pgvector stores 1024-dim vectors and supports fast ANN search.",
         ["vector", "pgvector", "embedding"]),
        ("doc-005", "Image Cleaning Pipeline",
         "Image cleaning removes duplicates, NSFW, blurry, and "
         "low-quality samples using perceptual hashes and CLIP scoring.",
         ["cleaning", "phash", "quality"]),
        ("doc-006", "Annotation Review Workflow",
         "A multi-reviewer consensus workflow runs three annotators in "
         "parallel and resolves disagreements via the agreement engine.",
         ["annotation", "consensus", "review"]),
        ("doc-007", "Video Generation",
         "Modern video generation models produce 5-second clips from text, "
         "with optional image conditioning for image-to-video workflows.",
         ["video", "t2v", "i2v"]),
        ("doc-008", "Aesthetic Scoring",
         "Aesthetic scoring ranks images by visual appeal using a learned "
         "regressor; clip score measures text-image alignment.",
         ["aesthetic", "clip", "scoring"]),
        ("doc-009", "Dataset Versioning",
         "Each dataset version is immutable and references its parent. "
         "Samples can be filtered by quality, modality, and tags.",
         ["dataset", "version", "immutable"]),
        ("doc-010", "Search Service Architecture",
         "The search service exposes text, semantic, and vector search. "
         "It seeds a tiny corpus on boot so smoke tests return results.",
         ["search", "semantic", "vector"]),
    ]
    for did, title, content, tags in samples:
        d = Document(id=did, title=title, content=content, tags=tags)
        eng.add_document(d)


# =====================================================================
# Pydantic request models
# =====================================================================

class VectorQueryRequest(BaseModel):
    vector: List[float] = Field(..., min_length=1, max_length=2048)
    top_k: int = Field(default=10, ge=1, le=100)


class SemanticQuery(BaseModel):
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)


# =====================================================================
# REST
# =====================================================================

@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    eng = get_search_engine()
    return {
        "status": "ok",
        "service": "search-service",
        "version": "0.1.0",
        "corpus_size": eng.corpus_size(),
        "vector_dim": eng.vector_dim(),
        "pgvector_enabled": eng.has_pgvector(),
    }


@router.get("/api/v1/search/text")
async def search_text(q: str = "", top_k: int = 10) -> Dict[str, Any]:
    if not q or not q.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="query_empty")
    top_k = max(1, min(top_k, 100))
    eng = get_search_engine()
    t0 = time.time()
    items = eng.text_search(q, top_k=top_k)
    return {
        "query": q, "mode": "text", "top_k": top_k,
        "elapsed_ms": round((time.time() - t0) * 1000, 3),
        "total": len(items), "items": items,
    }


@router.get("/api/v1/search/semantic")
async def search_semantic(q: str = "", top_k: int = 10,
                          alpha: float = 0.5) -> Dict[str, Any]:
    if not q or not q.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="query_empty")
    top_k = max(1, min(top_k, 100))
    eng = get_search_engine()
    t0 = time.time()
    items = eng.semantic_search(q, top_k=top_k, alpha=alpha)
    return {
        "query": q, "mode": "semantic", "alpha": alpha, "top_k": top_k,
        "elapsed_ms": round((time.time() - t0) * 1000, 3),
        "total": len(items), "items": items,
    }


@router.get("/api/v1/search/vector")
async def search_vector(q: str = "", top_k: int = 10) -> Dict[str, Any]:
    if not q or not q.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="query_empty")
    top_k = max(1, min(top_k, 100))
    eng = get_search_engine()
    t0 = time.time()
    items = eng.vector_search(q, top_k=top_k)
    return {
        "query": q, "mode": "vector", "top_k": top_k,
        "elapsed_ms": round((time.time() - t0) * 1000, 3),
        "total": len(items), "items": items,
    }


@router.post("/api/v1/search/vector/query")
async def search_vector_post(req: VectorQueryRequest) -> Dict[str, Any]:
    eng = get_search_engine()
    qv = req.vector
    qnorm = math.sqrt(sum(x * x for x in qv)) or 1.0
    qv = [x / qnorm for x in qv]
    # brute-force cosine over all docs
    out: List[Dict[str, Any]] = []
    for did in list(eng.docs.keys()):
        # Re-fit doc on demand (cheap; corpus is small)
        d = eng.docs[did]
        blob = f"{d.title}\n{d.content}\n{' '.join(d.tags)}"
        dv = eng.vec.fit(blob)
        if len(dv) != len(qv):
            continue
        s = sum(a * b for a, b in zip(qv, dv))
        if s > 0:
            out.append({"id": did, "title": d.title,
                        "snippet": d.content[:200], "score": float(s)})
    out.sort(key=lambda x: x["score"], reverse=True)
    out = out[:req.top_k]
    return {"mode": "vector_post", "top_k": req.top_k, "total": len(out),
            "items": out}


@router.post("/api/v1/search/documents", status_code=status.HTTP_201_CREATED)
async def add_document(doc: DocumentIn) -> Dict[str, Any]:
    eng = get_search_engine()
    full = Document(**doc.model_dump())
    saved = eng.add_document(full)
    return saved.to_dict()


@router.get("/api/v1/search/documents")
async def list_documents(
    tag: Optional[str] = None,
    modality: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    limit = max(1, min(limit, 500))
    eng = get_search_engine()
    items = list(eng.docs.values())
    if tag:
        items = [d for d in items if tag in d.tags]
    if modality:
        items = [d for d in items if d.modality == modality]
    items = items[:limit]
    return {
        "total": len(items),
        "items": [d.to_dict() for d in items],
    }


@router.get("/api/v1/search/documents/{doc_id}")
async def get_document(doc_id: str) -> Dict[str, Any]:
    eng = get_search_engine()
    d = eng.docs.get(doc_id)
    if d is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"document_not_found: {doc_id}")
    return d.to_dict()


@router.delete("/api/v1/search/documents/{doc_id}")
async def delete_document(doc_id: str) -> Dict[str, Any]:
    eng = get_search_engine()
    ok = eng.delete_document(doc_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"document_not_found: {doc_id}")
    return {"success": True, "document_id": doc_id}


@router.get("/api/v1/search/stats")
async def stats() -> Dict[str, Any]:
    eng = get_search_engine()
    by_modality: Dict[str, int] = {}
    by_tag: Dict[str, int] = {}
    for d in eng.docs.values():
        by_modality[d.modality] = by_modality.get(d.modality, 0) + 1
        for t in d.tags:
            by_tag[t] = by_tag.get(t, 0) + 1
    return {
        "corpus_size": eng.corpus_size(),
        "vector_dim": eng.vector_dim(),
        "pgvector_enabled": eng.has_pgvector(),
        "by_modality": by_modality,
        "by_tag_top": sorted(
            by_tag.items(), key=lambda x: x[1], reverse=True)[:20],
    }


__all__ = ["router", "SearchEngine", "get_search_engine"]
