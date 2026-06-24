"""P4-7-W1: 12 service 共享多模态适配器.

Each of the 12 services can mount :class:`MultimodalAdapter` and gain
uniform 6-input-modality / 3-output-kind semantics::

    Input modalities
        text | image | video | audio | document | multimodal_mix

    Output kinds
        text | structured_json | multimodal_response

The adapter:

* Resolves the right handler from ``service_id`` + ``modality`` (text /
  image → user_service, video → asset_service, audio → annotation_service,
  cross-modal → search_service, ...).
* Builds a :class:`MultimodalDocument` from the raw input.
* Embeds it via :class:`MultiModalEmbedder` (1024-dim).
* Stores the result in :class:`MultimodalStore` (in-process, with optional
  PG/vector persistence).
* Returns the canonical response envelope that the consumer can render
  as text / JSON / multimodal.
"""
from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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
    OUTPUT_JSON,
    OUTPUT_MULTIMODAL,
    OUTPUT_TEXT,
    ALL_MODALITIES,
    ALL_OUTPUT_KINDS,
    detect_modality,
)
from imdf.multimodal.embedding import (
    EmbeddingRecord,
    EmbeddingRequest,
    EmbeddingResponse,
    MultiModalEmbedder,
    UNIFIED_DIM,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing table — which service handles which modality by default
# ---------------------------------------------------------------------------
SERVICE_IDS: Tuple[str, ...] = (
    "user_service", "asset_service", "search_service",
    "annotation_service", "collection_service", "cleaning_service",
    "dataset_service", "evaluation_service", "notification_service",
    "scoring_service", "workflow_service", "agent_service",
)


# Default modality → service routing (P4-7-W1 spec)
MODALITY_ROUTING: Dict[str, str] = {
    MODALITY_IMAGE: "user_service",     # 人脸照片 → 人脸特征
    "image_classify": "asset_service",  # 图像 → 分类
    MODALITY_AUDIO: "annotation_service",
    MODALITY_VIDEO: "asset_service",
    MODALITY_DOCUMENT: "search_service",
    MODALITY_EMAIL: "notification_service",
    "cross_modal": "search_service",
    MODALITY_TEXT: "search_service",
    MODALITY_MULTIMIX: "search_service",
}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
@dataclass
class AdapterRecord:
    service_id: str
    modality: str
    doc_id: str
    output_kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    embedding_entity_id: str = ""
    timestamp: str = ""


class MultimodalStore:
    """In-process record store.  Thread-safe."""

    def __init__(self) -> None:
        self._records: Dict[str, AdapterRecord] = {}
        self._lock = threading.RLock()

    def add(self, rec: AdapterRecord) -> None:
        with self._lock:
            self._records[rec.doc_id] = rec

    def get(self, doc_id: str) -> Optional[AdapterRecord]:
        with self._lock:
            return self._records.get(doc_id)

    def list(self, service_id: Optional[str] = None,
             modality: Optional[str] = None,
             limit: int = 200) -> List[AdapterRecord]:
        with self._lock:
            items = list(self._records.values())
        if service_id:
            items = [r for r in items if r.service_id == service_id]
        if modality:
            items = [r for r in items if r.modality == modality]
        return items[:limit]

    def size(self) -> int:
        with self._lock:
            return len(self._records)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
@dataclass
class AdapterRequest:
    """Inbound request from any of the 12 services."""
    service_id: str
    modality: str
    text: Optional[str] = None
    base64: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    entity_type: str = "generic"
    entity_id: str = ""
    output_kind: str = OUTPUT_TEXT
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterResponse:
    service_id: str
    modality: str
    output_kind: str
    doc_id: str
    text: str = ""
    structured: Dict[str, Any] = field(default_factory=dict)
    multimodal: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    routed_to: str = ""
    warnings: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "modality": self.modality,
            "output_kind": self.output_kind,
            "doc_id": self.doc_id,
            "text": self.text,
            "structured": self.structured,
            "multimodal": self.multimodal,
            "embedding_dim": len(self.embedding) if self.embedding else 0,
            "routed_to": self.routed_to,
            "warnings": self.warnings,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


class MultimodalAdapter:
    """Single shared adapter — instantiated once per service or once globally."""

    def __init__(self, service_id: str = "search_service",
                 parser: Optional[MultiModalParser] = None,
                 embedder: Optional[MultiModalEmbedder] = None,
                 store: Optional[MultimodalStore] = None) -> None:
        if service_id not in SERVICE_IDS:
            logger.warning("unknown service_id=%s; using as-is", service_id)
        self.service_id = service_id
        self.parser = parser or MultiModalParser()
        self.embedder = embedder or MultiModalEmbedder()
        self.store = store or MultimodalStore()
        self._handlers: Dict[str, Callable[[AdapterRequest, MultimodalDocument],
                                           Dict[str, Any]]] = {
            MODALITY_TEXT: self._handle_text,
            MODALITY_IMAGE: self._handle_image,
            MODALITY_VIDEO: self._handle_video,
            MODALITY_AUDIO: self._handle_audio,
            MODALITY_DOCUMENT: self._handle_document,
            MODALITY_EMAIL: self._handle_email,
            MODALITY_MULTIMIX: self._handle_multimix,
        }

    # ----- routing -------------------------------------------------------
    def route(self, modality: str) -> str:
        return MODALITY_ROUTING.get(modality, "search_service")

    def accept(self, modality: str) -> bool:
        return modality in ALL_MODALITIES

    def output_kinds(self) -> Tuple[str, ...]:
        return ALL_OUTPUT_KINDS

    # ----- main entry point ---------------------------------------------
    def process(self, req: AdapterRequest) -> AdapterResponse:
        t0 = time.time()
        warnings: List[str] = []
        # 1) build document
        if req.modality == MODALITY_TEXT:
            doc = MultimodalDocument(
                doc_id=f"mm-{uuid.uuid4().hex[:12]}",
                modality=MODALITY_TEXT,
                text=req.text or "",
                metadata=dict(req.metadata),
            )
            if req.text:
                doc.segments.append(_seg_from_text(doc, req.text))
        elif req.base64:
            data = base64.b64decode(req.base64)
            try:
                doc = self.parser.parse(data, filename=req.filename,
                                        mime_type=req.mime_type,
                                        modality=req.modality)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"parser_failed:{e!s}")
                doc = MultimodalDocument(
                    doc_id=f"mm-{uuid.uuid4().hex[:12]}",
                    modality=req.modality,
                    metadata={"raw_bytes": len(data)},
                )
        elif req.text:
            doc = MultimodalDocument(
                doc_id=f"mm-{uuid.uuid4().hex[:12]}",
                modality=MODALITY_TEXT,
                text=req.text,
                metadata=dict(req.metadata),
            )
            doc.segments.append(_seg_from_text(doc, req.text))
        else:
            raise ValueError("AdapterRequest requires text or base64")

        warnings.extend(doc.warnings)

        # 2) handler dispatch (modality-specific)
        handler = self._handlers.get(req.modality, self._handle_text)
        try:
            handler_payload = handler(req, doc)
        except Exception as e:  # noqa: BLE001
            logger.warning("handler %s failed: %s", req.modality, e)
            warnings.append(f"handler_failed:{e!s}")
            handler_payload = {"fallback": True, "text": doc.text[:500]}

        # 3) embed (best-effort)
        embedding_vec: Optional[List[float]] = None
        embedding_entity_id = ""
        try:
            emb_req = EmbeddingRequest(
                entity_type=req.entity_type or self.service_id,
                entity_id=req.entity_id or doc.doc_id,
                modality=doc.modality,
                text=doc.text or None,
                base64=req.base64,
                document=doc,
                metadata={"service_id": self.service_id, **req.metadata},
            )
            rec = self.embedder.encode_one(emb_req)
            embedding_vec = rec.vector
            embedding_entity_id = rec.entity_id
        except Exception as e:  # noqa: BLE001
            warnings.append(f"embed_failed:{e!s}")

        # 4) compose response per output_kind
        resp = AdapterResponse(
            service_id=self.service_id,
            modality=req.modality,
            output_kind=req.output_kind,
            doc_id=doc.doc_id,
            embedding=embedding_vec,
            routed_to=self.route(req.modality),
            warnings=warnings,
            elapsed_ms=(time.time() - t0) * 1000,
        )
        if req.output_kind == OUTPUT_TEXT:
            resp.text = handler_payload.get("text") or doc.text
        elif req.output_kind == OUTPUT_JSON:
            resp.structured = {
                **handler_payload,
                "doc_id": doc.doc_id,
                "modality": doc.modality,
                "metadata": doc.metadata,
                "n_segments": len(doc.segments),
                "n_images": len(doc.images),
                "n_tables": len(doc.tables),
            }
        else:  # multimodal_response
            resp.multimodal = {
                "text": doc.text,
                "images": [i.to_dict() for i in doc.images[:8]],
                "tables": [t.to_dict() for t in doc.tables[:8]],
                "segments": [s.to_dict() for s in doc.segments[:8]],
                "metadata": doc.metadata,
                "handler": handler_payload,
            }
        # 5) persist record
        self.store.add(AdapterRecord(
            service_id=self.service_id,
            modality=req.modality,
            doc_id=doc.doc_id,
            output_kind=req.output_kind,
            payload={
                "text": resp.text,
                "structured": resp.structured,
                "multimodal": resp.multimodal,
            },
            embedding_entity_id=embedding_entity_id,
            timestamp=time.time(),
        ))
        return resp

    # ----- handlers ------------------------------------------------------
    def _handle_text(self, req: AdapterRequest,
                     doc: MultimodalDocument) -> Dict[str, Any]:
        return {"text": doc.text, "length": len(doc.text)}

    def _handle_image(self, req: AdapterRequest,
                      doc: MultimodalDocument) -> Dict[str, Any]:
        info: Dict[str, Any] = {"modality": "image"}
        if doc.images:
            img = doc.images[0]
            info["dimensions"] = [img.width, img.height]
            info["sha256"] = img.sha256
            info["ocr_text"] = img.ocr_text
            info["bytes"] = img.bytes_size
        if doc.text:
            info["extracted_text"] = doc.text[:500]
        return info

    def _handle_video(self, req: AdapterRequest,
                      doc: MultimodalDocument) -> Dict[str, Any]:
        return {
            "modality": "video",
            "frames": len(doc.images),
            "duration_s": doc.metadata.get("duration_s")
                or doc.metadata.get("duration_s_estimated", 0.0),
            "width": doc.metadata.get("width", 0),
            "height": doc.metadata.get("height", 0),
            "keyframe_timestamps": [
                img.timestamp for img in doc.images if img.timestamp is not None
            ],
        }

    def _handle_audio(self, req: AdapterRequest,
                      doc: MultimodalDocument) -> Dict[str, Any]:
        return {
            "modality": "audio",
            "transcript": doc.text,
            "duration_s": doc.metadata.get("duration_s")
                or doc.metadata.get("duration_s_estimated", 0.0),
            "n_segments": len(doc.segments),
        }

    def _handle_document(self, req: AdapterRequest,
                         doc: MultimodalDocument) -> Dict[str, Any]:
        return {
            "modality": "document",
            "n_segments": len(doc.segments),
            "n_tables": len(doc.tables),
            "n_images": len(doc.images),
            "pages": doc.metadata.get("pages") or doc.metadata.get("slides", 0),
            "text_length": len(doc.text),
        }

    def _handle_email(self, req: AdapterRequest,
                      doc: MultimodalDocument) -> Dict[str, Any]:
        return {
            "modality": "email",
            "subject": doc.metadata.get("subject", ""),
            "from": doc.metadata.get("from", ""),
            "to": doc.metadata.get("to", ""),
            "date": doc.metadata.get("date", ""),
            "attachments": len(doc.images),
            "body_preview": doc.text[:500],
        }

    def _handle_multimix(self, req: AdapterRequest,
                         doc: MultimodalDocument) -> Dict[str, Any]:
        return {
            "modality": "multimix",
            "components": doc.metadata.get("components", []),
            "text_length": len(doc.text),
            "n_images": len(doc.images),
        }


def _seg_from_text(doc: MultimodalDocument, text: str):
    from imdf.multimodal.parser import DocumentSegment
    return DocumentSegment(
        segment_id=f"seg-{uuid.uuid4().hex[:8]}",
        text=text, start=0, end=len(text), segment_type="text",
    )


# ---------------------------------------------------------------------------
# FastAPI mount helper — shared by all 12 services
# ---------------------------------------------------------------------------
from pydantic import BaseModel, Field as _Field  # noqa: E402


class MultimodalProcessRequest(BaseModel):
    """Pydantic request body for ``POST /api/v1/multimodal/process``.

    Defined at module level so FastAPI's dependency solver can resolve the
    forward reference (Pydantic v2 + FastAPI requirement).
    """
    modality: str = _Field(..., min_length=1)
    text: Optional[str] = None
    base64: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    entity_type: str = "generic"
    entity_id: str = ""
    output_kind: str = OUTPUT_TEXT
    metadata: Dict[str, Any] = _Field(default_factory=dict)


def build_multimodal_router(service_id: str,
                            adapter: Optional[MultimodalAdapter] = None):
    """Return a FastAPI APIRouter exposing:

        GET  /api/v1/multimodal/health
        GET  /api/v1/multimodal/modalities
        GET  /api/v1/multimodal/records
        POST /api/v1/multimodal/process
    """
    from fastapi import APIRouter, HTTPException, status, Body
    if adapter is None:
        adapter = MultimodalAdapter(service_id=service_id)

    router = APIRouter(prefix="/api/v1/multimodal", tags=["multimodal"])

    @router.get("/health")
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "service_id": service_id,
            "store_size": adapter.store.size(),
            "embedding_dim": adapter.embedder.dim,
            "pg_vector_enabled": adapter.embedder.has_pg(),
            "modalities": list(ALL_MODALITIES),
            "output_kinds": list(ALL_OUTPUT_KINDS),
        }

    @router.get("/modalities")
    async def modalities() -> Dict[str, Any]:
        return {
            "input_modalities": list(ALL_MODALITIES),
            "output_kinds": list(ALL_OUTPUT_KINDS),
            "routing": dict(MODALITY_ROUTING),
            "supported_formats": list(MultiModalParser.SUPPORTED_INPUT_FORMATS),
        }

    @router.get("/records")
    async def records(modality: Optional[str] = None,
                      limit: int = 50) -> Dict[str, Any]:
        return {
            "total": adapter.store.size(),
            "items": [
                {
                    "doc_id": r.doc_id, "modality": r.modality,
                    "output_kind": r.output_kind, "service_id": r.service_id,
                    "embedding_entity_id": r.embedding_entity_id,
                }
                for r in adapter.store.list(modality=modality, limit=limit)
            ],
        }

    @router.post("/process")
    async def process(req: MultimodalProcessRequest = Body(...)) -> Dict[str, Any]:
        if not adapter.accept(req.modality):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported_modality:{req.modality}",
            )
        if req.output_kind not in ALL_OUTPUT_KINDS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported_output_kind:{req.output_kind}",
            )
        if not req.text and not req.base64:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="payload_empty:provide_text_or_base64",
            )
        adapter_req = AdapterRequest(
            service_id=service_id,
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
        resp = adapter.process(adapter_req)
        return resp.to_dict()

    return router


__all__ = [
    "MultimodalAdapter",
    "MultimodalStore",
    "AdapterRequest",
    "AdapterResponse",
    "AdapterRecord",
    "SERVICE_IDS",
    "MODALITY_ROUTING",
    "build_multimodal_router",
]
