"""VDP-2026 R4 — Multimodal coordinator public API."""
from .engine import (
    MultimodalPipeline,
    ModalitySpec,
    ExportSpec,
    Modality,
    ModalityRegistry,
    MODALITIES,
    EXPORTS,
    get_pipeline,
    reset_pipeline_for_test,
    configure_db,
)
from .routes import router

__all__ = [
    "MultimodalPipeline",
    "ModalitySpec",
    "ExportSpec",
    "Modality",
    "ModalityRegistry",
    "MODALITIES",
    "EXPORTS",
    "get_pipeline",
    "reset_pipeline_for_test",
    "configure_db",
    "router",
]
