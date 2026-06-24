"""P4-7 shared multimodal types.

These dataclasses are the lingua franca across parsers, embedders, RAG, the
CrossModalUnderstanding engine, the CrossModalGeneration engine and the
MultimodalAgent.  Keeping them in one file avoids circular imports between
those modules.
"""
from __future__ import annotations

import base64
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ModalKind(str, Enum):
    """Five first-class modalities handled by the cross-modal stack."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    TEXT = "text"


class UnderstandingTask(str, Enum):
    """8 cross-modal understanding tasks supported by CrossModalUnderstanding."""

    CAPTION = "caption"          # 图/视频/音频 → 自然语言描述
    VQA = "vqa"                  # 视觉问答
    CLASSIFICATION = "classification"  # 跨模态分类
    RELATION = "relation"        # 跨模态关系抽取 (实体链接)
    SENTIMENT = "sentiment"      # 多模态情感分析
    OCR = "ocr"                  # 图/视频/文档 → 文本
    ASR = "asr"                  # 音频/视频 → 文本
    REASONING = "reasoning"      # 跨模态推理


class GenerationTarget(str, Enum):
    """4 generation targets supported by CrossModalGeneration."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"  # text-to-text fallback (rarely used but symmetric)


class AgentToolName(str, Enum):
    """Built-in tools exposed by MultimodalAgent."""

    IMAGE_UNDERSTAND = "image_understand"
    VIDEO_SUMMARIZE = "video_summarize"
    DOCUMENT_PARSE = "document_parse"
    VOICE_TRANSCRIBE = "voice_transcribe"
    CROSS_MODAL_SEARCH = "cross_modal_search"


@dataclass
class MediaRef:
    """A reference to a piece of media, by URL or inline base64."""

    kind: ModalKind
    url: Optional[str] = None
    data_b64: Optional[str] = None
    text: Optional[str] = None  # for TEXT modality
    mime: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def short_id(self) -> str:
        """Stable 12-char id used in cache keys / agent tool messages."""
        seed = (self.url or self.text or "") + (self.data_b64 or "")[:64]
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "url": self.url,
            "text": self.text,
            "mime": self.mime,
            "meta": self.meta,
            "short_id": self.short_id(),
        }


# ── request / response payloads ────────────────────────────────────────────
@dataclass
class UnderstandingRequest:
    """Input for CrossModalUnderstanding.understand()."""

    task: UnderstandingTask
    media: List[MediaRef] = field(default_factory=list)
    query: Optional[str] = None  # required for vqa / reasoning; ignored for caption
    params: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: f"und-{uuid.uuid4().hex[:10]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task": self.task.value,
            "media": [m.to_dict() for m in self.media],
            "query": self.query,
            "params": self.params,
        }


@dataclass
class UnderstandingResponse:
    """Output for CrossModalUnderstanding.understand()."""

    request_id: str
    task: UnderstandingTask
    text: str = ""
    label: Optional[str] = None  # for classification / sentiment
    score: Optional[float] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    model: str = "stub"
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task": self.task.value,
            "text": self.text,
            "label": self.label,
            "score": self.score,
            "citations": self.citations,
            "raw": self.raw,
            "elapsed_ms": self.elapsed_ms,
            "model": self.model,
            "timestamp": self.timestamp,
        }


@dataclass
class GenerationRequest:
    """Input for CrossModalGeneration.generate()."""

    text: str
    target: GenerationTarget
    ref_images: List[MediaRef] = field(default_factory=list)
    provider: Optional[str] = None  # openai_compatible / volcengine / comfyui / jimeng_cli
    params: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: f"gen-{uuid.uuid4().hex[:10]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "target": self.target.value,
            "ref_images": [m.to_dict() for m in self.ref_images],
            "provider": self.provider,
            "params": self.params,
        }


@dataclass
class GenerationCandidate:
    modality: GenerationTarget
    url: str
    mime: str
    seed: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_sec: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modality": self.modality.value,
            "url": self.url,
            "mime": self.mime,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "duration_sec": self.duration_sec,
            "meta": self.meta,
        }


@dataclass
class GenerationResponse:
    """Output for CrossModalGeneration.generate()."""

    request_id: str
    target: GenerationTarget
    candidates: List[GenerationCandidate] = field(default_factory=list)
    provider: str = "stub"
    elapsed_ms: float = 0.0
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "target": self.target.value,
            "candidates": [c.to_dict() for c in self.candidates],
            "provider": self.provider,
            "elapsed_ms": self.elapsed_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentRequest:
    """Input for MultimodalAgent.invoke()."""

    prompt: str
    media: List[MediaRef] = field(default_factory=list)
    session_id: Optional[str] = None
    save_to_memory: bool = True
    request_id: str = field(default_factory=lambda: f"agt-{uuid.uuid4().hex[:10]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "prompt": self.prompt,
            "media": [m.to_dict() for m in self.media],
            "session_id": self.session_id,
            "save_to_memory": self.save_to_memory,
        }


@dataclass
class AgentToolCall:
    """One tool invocation inside an AgentResponse."""

    tool: AgentToolName
    args: Dict[str, Any]
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool.value,
            "args": self.args,
            "result": self.result,
        }


@dataclass
class AgentResponse:
    """Output for MultimodalAgent.invoke()."""

    request_id: str
    text: str
    tool_calls: List[AgentToolCall] = field(default_factory=list)
    output_media: List[MediaRef] = field(default_factory=list)
    memory_ids: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "output_media": [m.to_dict() for m in self.output_media],
            "memory_ids": self.memory_ids,
            "elapsed_ms": self.elapsed_ms,
            "timestamp": self.timestamp,
        }


# ── helper: parse Pydantic / JSON payload into MediaRef ────────────────────
def parse_media_item(item: Union[Dict[str, Any], MediaRef, str]) -> MediaRef:
    """Coerce a single media entry (URL str / MediaRef / dict) into MediaRef."""
    if isinstance(item, MediaRef):
        return item
    if isinstance(item, str):
        if item.startswith(("http://", "https://", "/")):
            kind = ModalKind.IMAGE  # best-effort default
            low = item.lower()
            for k, exts in (
                (ModalKind.VIDEO, (".mp4", ".mov", ".webm", ".m4v")),
                (ModalKind.AUDIO, (".mp3", ".wav", ".flac", ".m4a", ".ogg")),
                (ModalKind.DOCUMENT, (".pdf", ".docx", ".md", ".txt")),
            ):
                if any(low.endswith(e) for e in exts):
                    kind = k
                    break
            return MediaRef(kind=kind, url=item)
        return MediaRef(kind=ModalKind.TEXT, text=item)
    if not isinstance(item, dict):
        raise TypeError(f"Unsupported media item type: {type(item).__name__}")
    kind_raw = item.get("kind") or item.get("modality") or "image"
    try:
        kind = ModalKind(kind_raw)
    except ValueError:
        kind = ModalKind.IMAGE
    return MediaRef(
        kind=kind,
        url=item.get("url"),
        data_b64=item.get("data_b64") or item.get("data"),
        text=item.get("text"),
        mime=item.get("mime"),
        meta=dict(item.get("meta") or {}),
    )


def b64_to_bytes(data_b64: str) -> bytes:
    if "," in data_b64 and data_b64.lstrip().startswith("data:"):
        data_b64 = data_b64.split(",", 1)[1]
    return base64.b64decode(data_b64)