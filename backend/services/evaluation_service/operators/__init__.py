"""evaluation_service.operators — 10 evaluation operators registry (P3-5-W2).

Exports:
  OPERATORS: dict[str, callable]   — 10 entries, id → run(items, params)
  OPERATOR_META: dict[str, dict]   — id → {category, modality, params, ...}
  list_operators(...) / get_operator(id) / get_meta(id)
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from services._none_safety import safe_dict_run  # P6-Fix-P0-1: NoneType guard

from . import (
    fid,
    clip_score,
    bleu,
    rouge,
    bert_score,
    aesthetic_predict,
    hpsv2,
    video_quality,
    audio_quality,
    bad_case_detect,
)


_META_TABLE: List[Dict[str, Any]] = [
    {"id": "eval.image.fid", "name": "FID (Frechet Inception Distance)",
     "category": "image", "modality": "image",
     "description": "Frechet distance between generated and reference image distributions (lower = better)",
     "params": [
         {"name": "ref_items", "type": "list", "default": [], "required": False,
          "description": "Reference image paths/bytes for distribution"},
         {"name": "score_threshold", "type": "float", "default": 100.0, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": fid.run},

    {"id": "eval.image.clip_score", "name": "CLIP Score (image-text alignment)",
     "category": "image", "modality": "image",
     "description": "Image-text alignment via token-overlap + quality heuristic (0-1)",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.25, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": clip_score.run},

    {"id": "eval.text.bleu", "name": "BLEU (text generation)",
     "category": "text", "modality": "text",
     "description": "Bilingual Evaluation Understudy n-gram precision (0-1)",
     "params": [
         {"name": "refs", "type": "list", "default": [], "required": False},
         {"name": "max_n", "type": "int", "default": 4, "required": False},
         {"name": "threshold", "type": "float", "default": 0.1, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": bleu.run},

    {"id": "eval.text.rouge", "name": "ROUGE (text summarization)",
     "category": "text", "modality": "text",
     "description": "ROUGE-1/2/L F-measures (0-1)",
     "params": [
         {"name": "refs", "type": "list", "default": [], "required": False},
         {"name": "threshold", "type": "float", "default": 0.2, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": rouge.run},

    {"id": "eval.text.bert_score", "name": "BERTScore (text semantic similarity)",
     "category": "text", "modality": "text",
     "description": "IDF-weighted character-n-gram cosine (proxy for BERTScore, no model load)",
     "params": [
         {"name": "refs", "type": "list", "default": [], "required": False},
         {"name": "threshold", "type": "float", "default": 0.5, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": bert_score.run},

    {"id": "eval.image.aesthetic", "name": "Aesthetic Predictor",
     "category": "image", "modality": "image",
     "description": "Aesthetic quality 1-10 (LAION-style heuristic: brightness, contrast, saturation, symmetry)",
     "params": [
         {"name": "threshold", "type": "float", "default": 5.0, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": aesthetic_predict.run},

    {"id": "eval.image.hpsv2", "name": "HPSv2 (Human Preference Score v2)",
     "category": "image", "modality": "image",
     "description": "Human preference heuristic combining alignment + sharpness + cleanness (0-1)",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.4, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": hpsv2.run},

    {"id": "eval.video.quality", "name": "Video Quality Assessment",
     "category": "video", "modality": "video",
     "description": "Resolution / fps / stability / sharpness / black-frame composite (0-1)",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.5, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": video_quality.run},

    {"id": "eval.audio.quality", "name": "Audio Quality Assessment",
     "category": "audio", "modality": "audio",
     "description": "Sample-rate / SNR / clipping / silence / dynamic-range composite (0-1)",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.5, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": audio_quality.run},

    {"id": "eval.bad_case.detect", "name": "Bad Case Auto-Detector",
     "category": "meta", "modality": "any",
     "description": "Multi-metric threshold-based bad-case flagging",
     "params": [
         {"name": "rules", "type": "dict", "default": {}, "required": False,
          "description": "Per-metric thresholds (overrides defaults)"},
         {"name": "min_violations", "type": "int", "default": 1, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": bad_case_detect.run},
]


OPERATORS: Dict[str, Callable] = {
    entry["id"]: safe_dict_run(entry["run"]) for entry in _META_TABLE
}


def _meta_without_callable(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "run"}


OPERATOR_META: Dict[str, Dict[str, Any]] = {
    entry["id"]: _meta_without_callable(entry) for entry in _META_TABLE
}


def list_operators(modality: str = None, category: str = None) -> List[Dict[str, Any]]:
    out = [_meta_without_callable(e) for e in _META_TABLE]
    if modality:
        out = [e for e in out if e.get("modality") == modality]
    if category:
        out = [e for e in out if e.get("category") == category]
    return out


def get_operator(op_id: str) -> Callable:
    return OPERATORS.get(op_id)


def get_meta(op_id: str) -> Dict[str, Any]:
    return OPERATOR_META.get(op_id)


__all__ = [
    "OPERATORS",
    "OPERATOR_META",
    "list_operators",
    "get_operator",
    "get_meta",
]
