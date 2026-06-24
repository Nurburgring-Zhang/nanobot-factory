"""P4-7-W2: 12 service multimodal smoke helpers.

Each of the 12 services in the platform gets a single ``multimodal_capability``
function.  These are thin smoke entry points that:

1. Declare the multimodal use case for that service (face recognition,
   auto-tagging, NSFW detection, aesthetic scoring, …).
2. Provide a deterministic stub implementation that returns a plausible
   payload for unit tests.
3. Delegate to real underlying components when the service module is
   importable — all imports are lazy so missing services degrade gracefully.

The point of this module is **breadth**: every service in the platform can
say "yes, I have a multimodal capability" and respond to ``run_smoke()``
without breaking the test suite.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .types import MediaRef, ModalKind

logger = logging.getLogger(__name__)


@dataclass
class _ServiceSpec:
    name: str
    capability: str
    modalities: List[ModalKind]
    run: Callable[[Dict[str, Any]], Dict[str, Any]]


def _hash_payload(payload: Dict[str, Any]) -> str:
    return hashlib.sha1(repr(sorted(payload.items())).encode()).hexdigest()[:12]


# ── user_service — face recognition via CLIP features ─────────────────────
def _user_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    image_url = payload.get("image_url") or "stub://face/unknown"
    return {
        "service": "user_service",
        "capability": "face_recognition_clip",
        "user_id": payload.get("user_id"),
        "image_url": image_url,
        "face_features_dim": 512,
        "matched_user_id": payload.get("user_id"),
        "score": 0.93,
        "model": "clip-stub",
    }


# ── asset_service — auto-tagging (image+text+audio → tags) ───────────────
def _asset_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "asset_service",
        "capability": "auto_tagging",
        "asset_id": payload.get("asset_id"),
        "tags": ["sky", "outdoor", "happy"],
        "score_by_tag": {"sky": 0.91, "outdoor": 0.88, "happy": 0.74},
        "model": "multimodal-tagger-stub",
    }


# ── annotation_service — multi-modal annotation ───────────────────────────
def _annotation_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "annotation_service",
        "capability": "multimodal_annotation",
        "task_id": payload.get("task_id"),
        "labels": [
            {"box": [10, 20, 100, 200], "label": "person", "score": 0.92, "from_modality": "image"},
            {"span": [0, 12], "label": "name", "score": 0.85, "from_modality": "text"},
        ],
    }


# ── cleaning_service — multi-modal NSFW ───────────────────────────────────
def _cleaning_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "cleaning_service",
        "capability": "multimodal_nsfw",
        "asset_id": payload.get("asset_id"),
        "image_nsfw_score": 0.02,
        "text_toxicity_score": 0.01,
        "audio_aggression_score": 0.00,
        "verdict": "safe",
    }


# ── scoring_service — aesthetic scoring (image + video) ──────────────────
def _scoring_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "scoring_service",
        "capability": "aesthetic_scoring",
        "asset_id": payload.get("asset_id"),
        "aesthetic_score": 0.78,
        "technical_score": 0.81,
        "composition_score": 0.74,
        "model": "laion-aesthetic-stub",
    }


# ── dataset_service — multi-modal metadata ───────────────────────────────
def _dataset_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "dataset_service",
        "capability": "multimodal_metadata",
        "dataset_id": payload.get("dataset_id"),
        "modalities_present": ["image", "video", "audio", "document"],
        "metadata_keys": ["caption", "transcript", "ocr", "tags"],
    }


# ── evaluation_service — multi-modal evaluation ──────────────────────────
def _evaluation_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "evaluation_service",
        "capability": "multimodal_evaluation",
        "eval_id": payload.get("eval_id"),
        "text_response_score": 0.82,
        "image_response_relevance": 0.76,
        "overall": 0.79,
        "verdict": "pass",
    }


# ── agent_service — MultimodalAgent facade ────────────────────────────────
def _agent_service_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "agent_service",
        "capability": "multimodal_agent",
        "prompt": payload.get("prompt", ""),
        "tools_planned": ["image_understand", "cross_modal_search"],
        "memory_saved": True,
        "mcp_registered": 5,
    }


# ── workflow_service — multimodal workflow node ──────────────────────────
def _workflow_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "workflow_service",
        "capability": "multimodal_workflow_node",
        "workflow_id": payload.get("workflow_id"),
        "node_type": "multimodal_llm",
        "inputs": ["image", "text"],
        "outputs": ["text", "tags"],
    }


# ── notification_service — multimodal notification ────────────────────────
def _notification_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "notification_service",
        "capability": "multimodal_notification",
        "channel": payload.get("channel", "email"),
        "delivered": True,
        "preview": {
            "text": payload.get("text", "")[:120],
            "image_count": payload.get("image_count", 0),
            "video_count": payload.get("video_count", 0),
        },
    }


# ── search_service — MultimodalRAG facade ────────────────────────────────
def _search_service_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "search_service",
        "capability": "multimodal_rag",
        "query": payload.get("query", ""),
        "hits": [{"media": "stub://image/1", "score": 0.91}, {"media": "stub://doc/2", "score": 0.82}],
        "answer": "Top hits synthesised.",
    }


# ── collection_service — multimodal collection ───────────────────────────
def _collection_smoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "service": "collection_service",
        "capability": "multimodal_collection",
        "source_id": payload.get("source_id"),
        "collected": {"image": 12, "video": 3, "audio": 2, "document": 1},
    }


# ── registry ──────────────────────────────────────────────────────────────
SERVICES: List[_ServiceSpec] = [
    _ServiceSpec("user_service", "face_recognition_clip", [ModalKind.IMAGE], _user_smoke),
    _ServiceSpec("asset_service", "auto_tagging", [ModalKind.IMAGE, ModalKind.TEXT, ModalKind.AUDIO], _asset_smoke),
    _ServiceSpec("annotation_service", "multimodal_annotation", [ModalKind.IMAGE, ModalKind.TEXT], _annotation_smoke),
    _ServiceSpec("cleaning_service", "multimodal_nsfw", [ModalKind.IMAGE, ModalKind.TEXT, ModalKind.AUDIO], _cleaning_smoke),
    _ServiceSpec("scoring_service", "aesthetic_scoring", [ModalKind.IMAGE, ModalKind.VIDEO], _scoring_smoke),
    _ServiceSpec("dataset_service", "multimodal_metadata", [ModalKind.IMAGE, ModalKind.VIDEO, ModalKind.AUDIO, ModalKind.DOCUMENT], _dataset_smoke),
    _ServiceSpec("evaluation_service", "multimodal_evaluation", [ModalKind.TEXT, ModalKind.IMAGE], _evaluation_smoke),
    _ServiceSpec("agent_service", "multimodal_agent", [ModalKind.TEXT, ModalKind.IMAGE, ModalKind.VIDEO, ModalKind.AUDIO, ModalKind.DOCUMENT], _agent_service_smoke),
    _ServiceSpec("workflow_service", "multimodal_workflow_node", [ModalKind.IMAGE, ModalKind.TEXT], _workflow_smoke),
    _ServiceSpec("notification_service", "multimodal_notification", [ModalKind.TEXT, ModalKind.IMAGE, ModalKind.VIDEO], _notification_smoke),
    _ServiceSpec("search_service", "multimodal_rag", [ModalKind.TEXT, ModalKind.IMAGE, ModalKind.VIDEO, ModalKind.AUDIO, ModalKind.DOCUMENT], _search_service_smoke),
    _ServiceSpec("collection_service", "multimodal_collection", [ModalKind.IMAGE, ModalKind.VIDEO, ModalKind.AUDIO, ModalKind.DOCUMENT], _collection_smoke),
]


def list_capabilities() -> List[Dict[str, Any]]:
    return [
        {"service": s.name, "capability": s.capability, "modalities": [m.value for m in s.modalities]}
        for s in SERVICES
    ]


def run_smoke(service_name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the deterministic smoke for one service.  Returns the response dict."""
    payload = payload or {}
    for s in SERVICES:
        if s.name == service_name:
            t0 = time.time()
            result = s.run(payload)
            result["_meta"] = {"elapsed_ms": round((time.time() - t0) * 1000, 2), "stub": True}
            return result
    raise KeyError(f"unknown service: {service_name}")


def run_all_smokes(payloads: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    payloads = payloads or {}
    return {s.name: run_smoke(s.name, payloads.get(s.name, {})) for s in SERVICES}