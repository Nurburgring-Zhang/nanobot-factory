"""P4-7: Multimodal package (Gemini Omni style cross-modal understanding + generation + agent).

Modules
-------
- ``types``            : shared enums / dataclasses (ModalKind, UnderstandingTask, etc.)
- ``parsers``          : image / video / audio / document parsing (P4-7-W1)
- ``embedders``        : CLIP / AudioCLIP / multimodal embedders (P4-7-W1)
- ``rag``              : MultimodalRAG (P4-7-W1) — over different modalities
- ``understanding``    : CrossModalUnderstanding — 8 tasks (P4-7-W2)
- ``generation``       : CrossModalGeneration — text→image/video/audio (P4-7-W2)
- ``multimodal_agent`` : MultimodalAgent — tool-using multimodal agent (P4-7-W2)
- ``service_integration``: 12 service smoke helpers (P4-7-W2)
- ``routes``           : FastAPI router — /api/v1/multimodal/* + /api/v1/agent/multimodal
- ``parser``           : MultiModalParser — full document/email/video/audio parser (P4-7-W1 12 service)
- ``embedding``        : MultiModalEmbedder — 1024-dim unified cross-modal space (P4-7-W1)
- ``business_modalities``: P19 v5.1 — Modality dataclass + registry for specialised
  business domains (3D PointCloud, LiDAR, DICOM Medical, Panoptic Segmentation)

The package is fully self-contained; only Pydantic v2 + FastAPI + stdlib are
required at runtime.  Heavy model dependencies (CLIP, BLIP-2, etc.) are imported
lazily and fall back to deterministic mock implementations when not installed,
so unit tests run hermetically.
"""
from __future__ import annotations

from .types import (
    ModalKind,
    UnderstandingTask,
    GenerationTarget,
    AgentToolName,
    MediaRef,
    UnderstandingRequest,
    UnderstandingResponse,
    GenerationRequest,
    GenerationResponse,
    AgentRequest,
    AgentResponse,
)

# P4-7-W1: full parser + 1024-dim unified embedder (12 service adapter)
from .parser import (  # noqa: E402
    MultiModalParser,
    MultimodalDocument,
    DocumentImage,
    DocumentTable,
    DocumentSegment,
    detect_modality,
    MODALITY_TEXT,
    MODALITY_IMAGE,
    MODALITY_VIDEO,
    MODALITY_AUDIO,
    MODALITY_DOCUMENT,
    MODALITY_EMAIL,
    MODALITY_MULTIMIX,
    ALL_MODALITIES,
    OUTPUT_TEXT,
    OUTPUT_JSON,
    OUTPUT_MULTIMODAL,
    ALL_OUTPUT_KINDS,
)
from .embedding import (  # noqa: E402
    MultiModalEmbedder,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingRecord,
    UNIFIED_DIM,
)

# P19 v5.1: business modality registry (3D, LiDAR, DICOM, Panoptic)
from .business_modalities import (  # noqa: E402
    Modality,
    ModalityAsset,
    ModalityValidation,
    register_modality,
    get_modality,
    list_modalities,
    detect_business_modality,
    embed_asset,
    process_file,
)
from . import three_d as _three_d  # noqa: E402
from . import lidar as _lidar  # noqa: E402
from . import medical as _medical  # noqa: E402
from . import panoptic as _panoptic  # noqa: E402

# Side-effect import: register all 4 business modalities on package load
_THREE_D = _three_d.install()
_LIDAR = _lidar.install()
_MEDICAL = _medical.install()
_PANOPTIC = _panoptic.install()

__all__ = [
    "ModalKind",
    "UnderstandingTask",
    "GenerationTarget",
    "AgentToolName",
    "MediaRef",
    "UnderstandingRequest",
    "UnderstandingResponse",
    "GenerationRequest",
    "GenerationResponse",
    "AgentRequest",
    "AgentResponse",
    # P4-7-W1 12 service 统一多模态接口
    "MultiModalParser",
    "MultimodalDocument",
    "DocumentImage",
    "DocumentTable",
    "DocumentSegment",
    "detect_modality",
    "MultiModalEmbedder",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingRecord",
    "MODALITY_TEXT", "MODALITY_IMAGE", "MODALITY_VIDEO",
    "MODALITY_AUDIO", "MODALITY_DOCUMENT", "MODALITY_EMAIL",
    "MODALITY_MULTIMIX", "ALL_MODALITIES",
    "OUTPUT_TEXT", "OUTPUT_JSON", "OUTPUT_MULTIMODAL", "ALL_OUTPUT_KINDS",
    "UNIFIED_DIM",
    # P19 v5.1 business-modality registry
    "Modality",
    "ModalityAsset",
    "ModalityValidation",
    "register_modality",
    "get_modality",
    "list_modalities",
    "detect_business_modality",
    "embed_asset",
    "process_file",
    "THREE_D_MODALITY_ID",
    "LIDAR_MODALITY_ID",
    "MEDICAL_MODALITY_ID",
    "PANOPTIC_MODALITY_ID",
]

THREE_D_MODALITY_ID = _THREE_D.id
LIDAR_MODALITY_ID = _LIDAR.id
MEDICAL_MODALITY_ID = _MEDICAL.id
PANOPTIC_MODALITY_ID = _PANOPTIC.id
