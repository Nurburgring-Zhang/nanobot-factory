"""P4-7-W1: multimodal API routes for the search service.

Endpoints
---------

* ``GET  /api/v1/multimodal/health``
* ``GET  /api/v1/multimodal/modalities``
* ``GET  /api/v1/multimodal/records``
* ``POST /api/v1/multimodal/process``         (6 模态输入 / 3 种输出)
* ``POST /api/v1/multimodal/parse``           (alias for process; spec name)
* ``POST /api/v1/multimodal/parse/batch``     (batch)
* ``POST /api/v1/multimodal/embed``           (single)
* ``POST /api/v1/multimodal/embed/batch``     (batch)
* ``POST /api/v1/search/multimodal``          (cross-modal retrieval)
* ``POST /api/v1/search/multimodal/rag``      (RAG with citations)
* ``GET  /api/v1/search/multimodal/indexed``  (list indexed entities)

Mounted in ``services/search_service/main.py``.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from imdf.multimodal.parser import (
    MultiModalParser,
    MultimodalDocument,
    MODALITY_AUDIO,
    MODALITY_DOCUMENT,
    MODALITY_EMAIL,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    MODALITY_VIDEO,
    MODALITY_MULTIMIX,
    ALL_MODALITIES,
    ALL_OUTPUT_KINDS,
    OUTPUT_TEXT,
)
from imdf.multimodal.embedding import (
    EmbeddingRequest,
    MultiModalEmbedder,
    UNIFIED_DIM,
)
from common.multimodal_adapter import (
    AdapterRequest,
    MultimodalAdapter,
    MultimodalProcessRequest,
    MultimodalStore,
    build_multimodal_router,
)
from services.search_service.multimodal_rag import (
    MultimodalQuery,
    MultimodalRAG,
    index_document,
)

logger = logging.getLogger(__name__)

# Two routers so the spec paths land on /api/v1/multimodal/* and
# /api/v1/search/multimodal/* consistently.
multimodal_router = APIRouter(tags=["multimodal"])
search_multimodal_router = APIRouter(tags=["multimodal-search"])


# ---------------------------------------------------------------------------
# Singletons (kept module-level for TestClient)
# ---------------------------------------------------------------------------
_PARSER: Optional[MultiModalParser] = None
_EMBEDDER: Optional[MultiModalEmbedder] = None
_ADAPTER: Optional[MultimodalAdapter] = None
_RAG: Optional[MultimodalRAG] = None
_STORE: Optional[MultimodalStore] = None


def get_parser() -> MultiModalParser:
    global _PARSER
    if _PARSER is None:
        _PARSER = MultiModalParser()
    return _PARSER


def get_embedder() -> MultiModalEmbedder:
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = MultiModalEmbedder()
    return _EMBEDDER


def get_adapter() -> MultimodalAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = MultimodalAdapter(
            service_id="search_service",
            parser=get_parser(),
            embedder=get_embedder(),
            store=get_store(),
        )
    return _ADAPTER


def get_store() -> MultimodalStore:
    global _STORE
    if _STORE is None:
        _STORE = MultimodalStore()
    return _STORE


def get_rag() -> MultimodalRAG:
    global _RAG
    if _RAG is None:
        _RAG = MultimodalRAG(embedder=get_embedder(), parser=get_parser())
    return _RAG


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ParseRequest(BaseModel):
    source: Optional[str] = None
    base64: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    modality: Optional[str] = None


class EmbedRequest(BaseModel):
    entity_type: str = "generic"
    entity_id: str = ""
    modality: str = MODALITY_TEXT
    text: Optional[str] = None
    base64: Optional[str] = None
    document: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    text: str = ""
    base64: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    modality_hint: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)


class IndexRequest(BaseModel):
    source: Optional[str] = None
    base64: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    modality: Optional[str] = None
    entity_type: str = "asset"
    entity_id: str = ""


# ---------------------------------------------------------------------------
# /api/v1/multimodal/*  (generic)
# ---------------------------------------------------------------------------
@multimodal_router.get("/api/v1/multimodal/health")
async def mm_health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "search_service",
        "service_id": "search_service",
        "embedding_dim": get_embedder().dim,
        "store_size": get_store().size(),
        "pg_vector_enabled": get_embedder().has_pg(),
        "modalities": list(ALL_MODALITIES),
        "output_kinds": list(ALL_OUTPUT_KINDS),
    }


@multimodal_router.get("/api/v1/multimodal/modalities")
async def mm_modalities() -> Dict[str, Any]:
    return {
        "input_modalities": list(ALL_MODALITIES),
        "output_kinds": list(ALL_OUTPUT_KINDS),
        "supported_formats": list(MultiModalParser.SUPPORTED_INPUT_FORMATS),
    }


@multimodal_router.post("/api/v1/multimodal/parse")
async def mm_parse(req: ParseRequest) -> Dict[str, Any]:
    if not req.source and not req.base64:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="payload_empty")
    parser = get_parser()
    t0 = time.time()
    if req.source:
        doc = parser.parse(req.source, filename=req.filename,
                           mime_type=req.mime_type, modality=req.modality)
    else:
        data = base64.b64decode(req.base64)
        doc = parser.parse(data, filename=req.filename,
                           mime_type=req.mime_type, modality=req.modality)
    return {
        "elapsed_ms": round((time.time() - t0) * 1000, 3),
        "document": doc.to_dict(),
    }


@multimodal_router.post("/api/v1/multimodal/parse/batch")
async def mm_parse_batch(items: List[ParseRequest]) -> Dict[str, Any]:
    if not items:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="items_empty")
    parser = get_parser()
    t0 = time.time()
    out: List[Dict[str, Any]] = []
    for it in items:
        if not it.source and not it.base64:
            continue
        if it.source:
            doc = parser.parse(it.source, filename=it.filename,
                               mime_type=it.mime_type, modality=it.modality)
        else:
            data = base64.b64decode(it.base64 or b"")
            doc = parser.parse(data, filename=it.filename,
                               mime_type=it.mime_type, modality=it.modality)
        out.append(doc.to_dict())
    return {
        "elapsed_ms": round((time.time() - t0) * 1000, 3),
        "total": len(out),
        "documents": out,
    }


@multimodal_router.post("/api/v1/multimodal/embed")
async def mm_embed(req: EmbedRequest) -> Dict[str, Any]:
    doc = None
    if req.document:
        try:
            doc = MultimodalDocument(**req.document)
        except Exception:  # noqa: BLE001
            doc = None
    er = EmbeddingRequest(
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        modality=req.modality,
        text=req.text,
        base64=req.base64,
        document=doc,
        metadata=dict(req.metadata),
    )
    rec = get_embedder().encode_one(er)
    return rec.to_dict()


@multimodal_router.post("/api/v1/multimodal/embed/batch")
async def mm_embed_batch(items: List[EmbedRequest]) -> Dict[str, Any]:
    if not items:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="items_empty")
    reqs: List[EmbeddingRequest] = []
    for it in items:
        doc = None
        if it.document:
            try:
                doc = MultimodalDocument(**it.document)
            except Exception:  # noqa: BLE001
                doc = None
        reqs.append(EmbeddingRequest(
            entity_type=it.entity_type,
            entity_id=it.entity_id,
            modality=it.modality,
            text=it.text,
            base64=it.base64,
            document=doc,
            metadata=dict(it.metadata),
        ))
    resp = get_embedder().encode_batch(reqs)
    return resp.to_dict()


@multimodal_router.post("/api/v1/multimodal/process")
async def mm_process(req: MultimodalProcessRequest) -> Dict[str, Any]:
    adapter_req = AdapterRequest(
        service_id="search_service",
        modality=req.modality,
        text=req.text,
        base64=req.base64,
        filename=req.filename,
        mime_type=req.mime_type,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        output_kind=req.output_kind,
        metadata=dict(req.metadata),
    )
    return get_adapter().process(adapter_req).to_dict()


# Mount the canonical multimodal router that every service exposes
generic_mm = build_multimodal_router(
    service_id="search_service",
    adapter=get_adapter(),
)


# ---------------------------------------------------------------------------
# /api/v1/search/multimodal/*  (RAG-flavoured)
# ---------------------------------------------------------------------------
@search_multimodal_router.post("/api/v1/search/multimodal")
async def search_multimodal(req: SearchRequest) -> Dict[str, Any]:
    if not req.text and not req.base64:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="payload_empty")
    q = MultimodalQuery(
        text=req.text, base64=req.base64,
        filename=req.filename, mime_type=req.mime_type,
        modality_hint=req.modality_hint, top_k=req.top_k,
    )
    t0 = time.time()
    cands = get_rag().search(q)
    return {
        "elapsed_ms": round((time.time() - t0) * 1000, 3),
        "query": req.text,
        "expected_modality": get_rag().reranker.expected_modality(q),
        "total": len(cands),
        "items": [c.to_dict() for c in cands],
    }


@search_multimodal_router.post("/api/v1/search/multimodal/rag")
async def search_multimodal_rag(req: SearchRequest) -> Dict[str, Any]:
    if not req.text and not req.base64:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="payload_empty")
    q = MultimodalQuery(
        text=req.text, base64=req.base64,
        filename=req.filename, mime_type=req.mime_type,
        modality_hint=req.modality_hint, top_k=req.top_k,
    )
    ans = get_rag().answer(q)
    return ans.to_dict()


@search_multimodal_router.post("/api/v1/search/multimodal/index")
async def search_multimodal_index(req: IndexRequest) -> Dict[str, Any]:
    if not req.source and not req.base64:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="payload_empty")
    if req.source:
        doc = get_parser().parse(req.source, filename=req.filename,
                                 mime_type=req.mime_type, modality=req.modality)
    else:
        data = base64.b64decode(req.base64 or b"")
        doc = get_parser().parse(data, filename=req.filename,
                                 mime_type=req.mime_type, modality=req.modality)
    rec = index_document(get_embedder(), doc, {
        "entity_type": req.entity_type,
        "entity_id": req.entity_id or doc.doc_id,
    })
    return {"document": doc.to_dict(), "embedding": rec.to_dict()}


@search_multimodal_router.get("/api/v1/search/multimodal/indexed")
async def search_multimodal_indexed(
    entity_type: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    items = get_embedder().list_entities(entity_type=entity_type)[:limit]
    return {
        "total": len(items),
        "items": [
            {
                "entity_id": r.entity_id,
                "entity_type": r.entity_type,
                "modality": r.modality,
                "dim": r.dim,
                "metadata": r.metadata,
            }
            for r in items
        ],
    }


# include the generic router as well so the spec paths work both ways
def all_routers() -> List[APIRouter]:
    return [multimodal_router, search_multimodal_router, generic_mm]


__all__ = [
    "multimodal_router",
    "search_multimodal_router",
    "all_routers",
    "get_parser",
    "get_embedder",
    "get_adapter",
    "get_rag",
    "get_store",
]
