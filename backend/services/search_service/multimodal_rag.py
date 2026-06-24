"""P4-7-W1: multimodal RAG (检索增强生成).

Cross-modal pipeline:

    query (text + optional 任意模态 payload)
        │
        ▼
    MultiModalParser  →  MultimodalDocument
        │
        ▼
    MultiModalEmbedder  →  1024-dim query vector
        │
        ▼
    EmbeddingStore.search  →  top-k candidates
        │
        ▼
    CrossModalReranker  →  CLIP-style score (modal match bonus)
        │
        ▼
    LLMAnswerSynthesizer  →  text answer with citations
        │
        ▼
    /api/v1/search/multimodal/rag  response

The LLM synthesizer is intentionally dependency-free: it composes the
candidates into a templated answer that mirrors the
"text + image ref + video timestamp" output spec from the task.  An
external LLM provider can be plugged in via ``llm_callback``.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from imdf.multimodal.parser import (
    MODALITY_AUDIO,
    MODALITY_DOCUMENT,
    MODALITY_EMAIL,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    MODALITY_VIDEO,
    MODALITY_MULTIMIX,
    MultimodalDocument,
    MultiModalParser,
    detect_modality,
)
from imdf.multimodal.embedding import (
    EmbeddingRecord,
    EmbeddingRequest,
    EmbeddingResponse,
    MultiModalEmbedder,
    UNIFIED_DIM,
)
from common.multimodal_adapter import (
    AdapterRequest,
    AdapterResponse,
    MultimodalAdapter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class MultimodalQuery:
    """User query that may carry text + any other modality."""
    text: str
    base64: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    modality_hint: Optional[str] = None
    top_k: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RagCandidate:
    """One retrieved candidate with cross-modal score."""
    entity_id: str
    entity_type: str
    modality: str
    score: float
    vector_score: float
    modal_bonus: float
    snippet: str = ""
    image_refs: List[Dict[str, Any]] = field(default_factory=list)
    video_timestamps: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "modality": self.modality,
            "score": round(self.score, 4),
            "vector_score": round(self.vector_score, 4),
            "modal_bonus": round(self.modal_bonus, 4),
            "snippet": self.snippet,
            "image_refs": self.image_refs,
            "video_timestamps": self.video_timestamps,
            "metadata": self.metadata,
        }


@dataclass
class RagAnswer:
    text: str
    citations: List[Dict[str, Any]]
    candidates: List[RagCandidate]
    query_doc_id: str
    elapsed_ms: float
    llm_source: str = "template-v1"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "citations": self.citations,
            "candidates": [c.to_dict() for c in self.candidates],
            "query_doc_id": self.query_doc_id,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "llm_source": self.llm_source,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Cross-modal reranker
# ---------------------------------------------------------------------------
class CrossModalReranker:
    """Apply a small bonus when the candidate's modality matches the
    expected modality derived from the query text.

    The bonus is a deterministic function of token co-occurrence:

    * "图像/image/photo/图"  → image
    * "视频/video/clip"     → video
    * "音频/audio/语音"     → audio
    * "文档/pdf/doc"        → document
    * "邮件/email"          → email

    When the query also carries a non-text payload, the expected
    modality is forced to the payload's modality.
    """

    KEYWORDS: Dict[str, Tuple[str, ...]] = {
        # Order matters: more specific keywords first so the most precise
        # match wins (e.g. "audio clip" → audio, not video).
        MODALITY_EMAIL: ("email", "mail", "邮件", "信件"),
        MODALITY_DOCUMENT: ("document", "doc", "pdf", "file", "文档", "文件", "报告"),
        MODALITY_AUDIO: ("audio", "sound", "voice", "speech", "asr", "音频", "语音", "声音"),
        MODALITY_VIDEO: ("video", "movie", "视频", "短片", "影片", "movie clip"),
        MODALITY_IMAGE: ("image", "photo", "picture", "图", "图像", "照片", "插图"),
    }

    def expected_modality(self, query: MultimodalQuery) -> str:
        if query.modality_hint:
            return query.modality_hint
        if query.base64:
            try:
                return detect_modality(query.base64, filename=query.filename,
                                       mime_type=query.mime_type)
            except Exception:  # noqa: BLE001
                pass
        text = (query.text or "").lower()
        for mod, kws in self.KEYWORDS.items():
            for kw in kws:
                if kw.lower() in text:
                    return mod
        return MODALITY_TEXT

    def rerank(self, query: MultimodalQuery,
               candidates: Sequence[Tuple[EmbeddingRecord, float]]) -> List[RagCandidate]:
        expected = self.expected_modality(query)
        out: List[RagCandidate] = []
        for rec, score in candidates:
            bonus = 0.0
            if rec.modality == expected:
                bonus = 0.35
            elif rec.modality == MODALITY_TEXT and expected != MODALITY_TEXT:
                bonus = -0.20
            elif rec.modality != expected and expected != MODALITY_TEXT:
                bonus = -0.10
            snippet = (rec.metadata.get("snippet") or rec.metadata.get("text") or "")[:300]
            out.append(RagCandidate(
                entity_id=rec.entity_id,
                entity_type=rec.entity_type,
                modality=rec.modality,
                score=float(score + bonus),
                vector_score=float(score),
                modal_bonus=float(bonus),
                snippet=snippet,
                image_refs=rec.metadata.get("image_refs") or [],
                video_timestamps=rec.metadata.get("video_timestamps") or [],
                metadata=rec.metadata,
            ))
        out.sort(key=lambda c: c.score, reverse=True)
        return out


# ---------------------------------------------------------------------------
# LLM answer synthesizer (template)
# ---------------------------------------------------------------------------
class LlmAnswerSynthesizer:
    """Compose a citation-rich answer from RAG candidates.

    For production, override with a real LLM client.  This default
    implementation produces a stable, well-formed answer that
    downstream UIs can render directly.
    """

    def __init__(self, llm_callback: Optional[Callable[[str, List[Dict[str, Any]]],
                                                       str]] = None) -> None:
        self.llm_callback = llm_callback

    def synthesize(self, query: MultimodalQuery,
                   candidates: Sequence[RagCandidate]) -> Tuple[str, List[Dict[str, Any]], str]:
        warnings: List[str] = []
        citations: List[Dict[str, Any]] = []
        if not candidates:
            text = (f"未找到与 \"{query.text}\" 直接相关的内容。"
                    "已尝试 6 种模态的联合 embedding 检索。")
            return text, citations, "template-empty"

        # Build context block
        ctx_lines: List[str] = []
        for i, c in enumerate(candidates, 1):
            citations.append({
                "rank": i,
                "entity_id": c.entity_id,
                "entity_type": c.entity_type,
                "modality": c.modality,
                "score": round(c.score, 4),
                "snippet": c.snippet,
                "image_refs": c.image_refs,
                "video_timestamps": c.video_timestamps,
            })
            ctx_lines.append(
                f"[{i}] (modality={c.modality}, score={c.score:.3f}) {c.snippet}"
            )
        context = "\n".join(ctx_lines)

        if self.llm_callback is not None:
            try:
                ans = self.llm_callback(query.text, citations)
                return ans, citations, "callback"
            except Exception as e:  # noqa: BLE001
                warnings.append(f"llm_callback_failed:{e!s}")

        # Template answer
        top = candidates[0]
        ans = (
            f"基于 {len(candidates)} 条跨模态证据，针对 \"{query.text}\" 的回答如下：\n\n"
            f"主要引用 [1] 来自 {top.entity_type}/{top.modality} (score={top.score:.3f})，"
            f"摘要：{top.snippet[:200]}\n\n"
            f"相关引用列表：\n{context}\n\n"
            f"提示：可点击引用跳转至原文 / 图像 / 视频时间戳。"
        )
        return ans, citations, "template-v1"


# ---------------------------------------------------------------------------
# RAG orchestrator
# ---------------------------------------------------------------------------
class MultimodalRAG:
    """Cross-modal RAG service used by search_service."""

    def __init__(self,
                 embedder: Optional[MultiModalEmbedder] = None,
                 parser: Optional[MultiModalParser] = None,
                 reranker: Optional[CrossModalReranker] = None,
                 synthesizer: Optional[LlmAnswerSynthesizer] = None) -> None:
        self.embedder = embedder or MultiModalEmbedder()
        self.parser = parser or MultiModalParser()
        self.reranker = reranker or CrossModalReranker()
        self.synthesizer = synthesizer or LlmAnswerSynthesizer()

    def search(self, query: MultimodalQuery) -> List[RagCandidate]:
        # 1) parse / embed query
        if query.base64:
            data = base64.b64decode(query.base64)
            doc = self.parser.parse(data, filename=query.filename,
                                    mime_type=query.mime_type)
        else:
            doc = MultimodalDocument(
                doc_id=f"q-{uuid.uuid4().hex[:12]}",
                modality=MODALITY_TEXT,
                text=query.text,
            )
        er = EmbeddingRequest(
            entity_type="query",
            entity_id=doc.doc_id,
            modality=doc.modality,
            text=doc.text or query.text,
            base64=query.base64,
            document=doc,
            metadata={"role": "query"},
        )
        qrec = self.embedder.encode_one(er)
        qv = np.asarray(qrec.vector, dtype=np.float32)
        # 2) top-k retrieval — exclude the query record itself
        raw_all = self.embedder.search(qv, top_k=max(1, query.top_k * 3))
        raw = [r for r in raw_all if r[0].entity_id != qrec.entity_id]
        # 3) rerank
        candidates = self.reranker.rerank(query, raw)
        return candidates[: query.top_k]

    def answer(self, query: MultimodalQuery) -> RagAnswer:
        import time
        t0 = time.time()
        warnings: List[str] = []
        # determine query doc id
        if query.base64:
            data = base64.b64decode(query.base64)
            doc = self.parser.parse(data, filename=query.filename,
                                    mime_type=query.mime_type)
            qdoc_id = doc.doc_id
        else:
            qdoc_id = f"q-{uuid.uuid4().hex[:12]}"
        candidates = self.search(query)
        text, citations, src = self.synthesizer.synthesize(query, candidates)
        return RagAnswer(
            text=text,
            citations=citations,
            candidates=candidates,
            query_doc_id=qdoc_id,
            elapsed_ms=(time.time() - t0) * 1000,
            llm_source=src,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Helper — feed a document into the embedder so RAG has something to search
# ---------------------------------------------------------------------------
def index_document(embedder: MultiModalEmbedder,
                   doc: MultimodalDocument,
                   extra_metadata: Optional[Dict[str, Any]] = None) -> EmbeddingRecord:
    """Index a parsed multimodal document so the RAG can find it."""
    meta = {
        "snippet": doc.text[:500],
        "image_refs": [
            {
                "image_id": img.image_id,
                "mime_type": img.mime_type,
                "page": img.page,
                "timestamp": img.timestamp,
                "sha256": img.sha256,
            }
            for img in doc.images[:8]
        ],
        "video_timestamps": [
            img.timestamp for img in doc.images if img.timestamp is not None
        ],
    }
    if extra_metadata:
        meta.update(extra_metadata)
    rec = embedder.encode_one(EmbeddingRequest(
        entity_type=extra_metadata.get("entity_type", "asset") if extra_metadata else "asset",
        entity_id=extra_metadata.get("entity_id", doc.doc_id) if extra_metadata else doc.doc_id,
        modality=doc.modality,
        text=doc.text or None,
        base64=None,
        document=doc,
        metadata=meta,
    ))
    return rec


__all__ = [
    "MultimodalQuery",
    "RagCandidate",
    "RagAnswer",
    "CrossModalReranker",
    "LlmAnswerSynthesizer",
    "MultimodalRAG",
    "index_document",
]
