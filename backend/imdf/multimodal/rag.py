"""P4-7-W1: MultimodalRAG — cross-modal retrieval augmented generation.

The RAG stack is intentionally tiny:

* ``VectorStore``        — in-memory cosine index over heterogeneous embeddings
* ``MultimodalRAG``      — top-level façade used by API and Agent

Embeddings come from ``MultiModalEmbedder`` (P4-7 unified 1024-dim space) via
the ``get_embedding`` shim.  Documents come from ``parsers.parse_media``
(returns ``ParsedMedia`` with text + chunks).

The RAG API:

* ``index(refs)``  — add media to the index
* ``search(query, top_k=5)`` — return ranked ``RetrievedItem`` list
* ``answer(query, top_k=5)`` — return text + citations (LLM stub falls back to
  concatenation of top chunks when no model is available)

P10-B migration: 旧 ``MultimodalEmbedder.embed(ref)`` (512-d) 已替换为新
``MultiModalEmbedder.encode_one(...)`` (1024-d), 旧 ``Embedding`` 仍保留在
``embedders.py`` 中以做兼容, 但 RAG 现在走 ``embedding.get_embedding``。
"""
from __future__ import annotations

import heapq
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .embedders import Embedding, cosine  # 保留旧的 Embedding dataclass + cosine 工具
from .embedding import MultiModalEmbedder, get_embedding, UNIFIED_DIM
from .parsers import ParsedMedia, parse_media
from .types import MediaRef, ModalKind

# P19 v5.1: business-modality registry — 4 new domains route through
# 1024-dim unified embedding space (hash + structural feature blend).
try:
    from .business_modalities import (
        detect_business_modality,
        embed_asset as _biz_embed_asset,
        process_file as _biz_process_file,
        ModalityAsset,
    )
except Exception:  # pragma: no cover
    detect_business_modality = None  # type: ignore[assignment]
    _biz_embed_asset = None  # type: ignore[assignment]
    _biz_process_file = None  # type: ignore[assignment]
    ModalityAsset = None  # type: ignore[assignment]

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
    def __init__(self, embedder: Optional[MultiModalEmbedder] = None) -> None:
        # P10-B: 接受新 MultiModalEmbedder, 默认懒加载全局实例
        self.embedder = embedder  # type: ignore[assignment]
        self._items: List[Embedding] = []

    def add(self, emb: Embedding) -> None:
        self._items.append(emb)

    def add_media(self, ref: MediaRef) -> ParsedMedia:
        parsed = parse_media(ref) if ref.kind != ModalKind.TEXT else ParsedMedia(
            kind=ModalKind.TEXT, text=ref.text or "", chunks=[ref.text or ""]
        )
        # P10-B: 用新 get_embedding 适配器拿到 1024-d 向量
        vec = get_embedding(ref)
        emb = Embedding(vector=vec, kind=ref.kind, ref=ref, parsed_hash=parsed.content_hash)
        self.add(emb)
        return parsed

    # ── P19 v5.1: business-modality ingestion ───────────────────────────────
    def add_business_asset(self, asset: Any) -> Embedding:
        """Add a ``ModalityAsset`` (3D / LiDAR / DICOM / Panoptic) to the index.

        Uses the modality-specific embedder (1024-dim L2-normalised).  Falls
        back to ``get_embedding`` for the underlying ``MediaRef`` if the
        asset's embedder fails.
        """
        biz_meta = getattr(asset, "metadata", None) or {}
        modality_id = getattr(asset, "modality_id", "") or biz_meta.get("filename", "")
        # Build a synthetic MediaRef carrying the business modality tag so
        # the embedder shim can route to the right encoder.
        ref = MediaRef(
            kind=ModalKind.DOCUMENT,
            url=getattr(asset, "path", "") or "",
            text=getattr(asset, "text", "") or "",
            mime=getattr(asset, "mime", "") or "",
            meta={
                "modality_id": getattr(asset, "modality_id", ""),
                "asset_id": getattr(asset, "asset_id", ""),
                "sha256": getattr(asset, "sha256", ""),
                "size": getattr(asset, "size", 0),
            },
        )
        # 1) try the business-modality embedder first
        vec: Optional[List[float]] = None
        if _biz_embed_asset is not None:
            try:
                vec = _biz_embed_asset(asset)
            except Exception as exc:  # noqa: BLE001
                logger.debug("business embedder failed: %s", exc)
        # 2) fall back to the unified shim
        if not vec or len(vec) != UNIFIED_DIM:
            vec = get_embedding(ref)
        # 3) safety: re-L2-normalise + dim check
        import math
        n = math.sqrt(sum(x * x for x in vec)) or 1.0
        vec = [x / n for x in vec]
        if len(vec) != UNIFIED_DIM:
            vec = (vec + [0.0] * UNIFIED_DIM)[:UNIFIED_DIM]
        emb = Embedding(
            vector=vec,
            kind=ModalKind.DOCUMENT,
            ref=ref,
            parsed_hash=getattr(asset, "sha256", "") or "",
        )
        self.add(emb)
        return emb

    def add_business_file(self, path: str) -> Embedding:
        """One-shot: process a file via the business-modality registry and add to index."""
        if _biz_process_file is None:
            raise RuntimeError("business modality registry unavailable")
        asset = _biz_process_file(path)
        return self.add_business_asset(asset)

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

    # ── Depth-7 持久化支持 ────────────────────────────────────────────────
    def rehydrate_from_db(self, engine=None) -> int:
        """从 ``models.Embedding`` 表把已持久化向量拉回内存索引。

        Returns: rehydrate 数量 (0 = 表空 / DB 不可用 / 失败)。

        设计: ``Embedding`` 表是持久源, ``VectorStore`` 是 in-memory 缓存。
        启动时调一次, 把已有行拉回, 避免重启后 RAG 检索结果空。

        失败模式:
        - DB 不可用 → 返回 0, 不抛 (上层 RAG 还是可以 ``index()`` 重建)
        - Embedding 表空 → 返回 0, 不抛
        - 部分行 ``vector`` 字段格式坏 → 跳过该行, 继续
        """
        try:
            from sqlalchemy.orm import Session
            from models import Embedding as DBEmbedding
        except Exception as exc:  # pragma: no cover
            logger.debug(f"VectorStore.rehydrate: import 失败: {exc}")
            return 0

        if engine is None:
            try:
                from db import engine as default_engine
                engine = default_engine
            except Exception as exc:  # pragma: no cover
                logger.debug(f"VectorStore.rehydrate: 拿默认 engine 失败: {exc}")
                return 0
        if engine is None:
            return 0

        n = 0
        try:
            from .types import MediaRef, ModalKind
            kind_map = {
                "text": ModalKind.TEXT,
                "image": ModalKind.IMAGE,
                "video": ModalKind.VIDEO,
                "audio": ModalKind.AUDIO,
                "document": ModalKind.DOCUMENT,
                "3d": ModalKind.DOCUMENT,  # 没有 3D enum, 退化到 DOCUMENT
            }
            with Session(engine) as s:
                rows = s.query(DBEmbedding).limit(100000).all()
                for row in rows:
                    try:
                        vec_raw = row.vector
                        # vector 字段跨 DB 兼容: PG → pgvector 列表, SQLite → JSON list
                        if vec_raw is None:
                            continue
                        if isinstance(vec_raw, str):
                            try:
                                import json as _json
                                vec = _json.loads(vec_raw)
                            except Exception:
                                continue
                        elif isinstance(vec_raw, (list, tuple)):
                            vec = list(vec_raw)
                        else:
                            # pgvector 的 Vector 对象: str repr 是 '[0.1,0.2,...]'
                            try:
                                vec = [float(x) for x in str(vec_raw).strip("[]").split(",")]
                            except Exception:
                                continue
                        if not vec:
                            continue
                        # entity_type → ModalKind 映射 (asset → image/text 等, user_query → text)
                        ent = (getattr(row, "entity_type", "") or "text").lower()
                        kind = kind_map.get(ent, ModalKind.TEXT)
                        # ref 重建: MediaRef 字段 (kind/url/data_b64/text/mime/meta),
                        # entity_id 放到 meta.ref_id, text 用 chunk_text
                        ref = MediaRef(
                            kind=kind,
                            text=getattr(row, "chunk_text", "") or "",
                            meta={"ref_id": getattr(row, "entity_id", "") or ""},
                        )
                        emb = Embedding(vector=vec, kind=kind, ref=ref)
                        self._items.append(emb)
                        n += 1
                    except Exception as exc:  # pragma: no cover
                        logger.debug(f"VectorStore.rehydrate: 跳过一行 ({exc})")
                        continue
        except Exception as exc:  # pragma: no cover
            logger.warning(f"VectorStore.rehydrate 失败: {exc}")
            return 0
        if n:
            logger.info(f"VectorStore.rehydrate: {n} embeddings 从 DB 拉回")
        return n


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

    def index_business_files(self, paths: List[str]) -> List[Dict[str, Any]]:
        """P19 v5.1: ingest a list of file paths via the business-modality registry.

        Returns one record per file with the resulting embedding dim.
        """
        out: List[Dict[str, Any]] = []
        for p in paths:
            try:
                asset = _biz_process_file(p)
                emb = self.store.add_business_asset(asset)
                out.append(
                    {
                        "asset": asset.to_dict(),
                        "dim": len(emb.vector),
                        "modality_id": asset.modality_id,
                        "sha256": asset.sha256,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("index_business_files: %s failed: %s", p, exc)
                out.append({"path": p, "error": str(exc)})
        return out

    # ── read side ───────────────────────────────────────────────────────
    def search(
        self,
        query: MediaRef,
        top_k: int = 5,
    ) -> List[RetrievedItem]:
        # P10-B: 用 get_embedding 适配器
        vec = get_embedding(query)
        return self.store.query(vec, top_k=top_k)

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