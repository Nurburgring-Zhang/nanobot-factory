"""annotation_service.operators — 20 annotation operators registry (P3-5-W1).

Layout:
  operators/
    _image_utils.py     (shared helpers — load_image_any, bbox_iou_xyxy, etc.)
    image/{bbox, polygon, keypoint, semantic_seg, instance_seg,
           classification, caption, ocr_box}.py
    video/{tracking, action_recognition, temporal_seg,
           shot_detection, video_caption}.py
    text/{ner, sentiment, text_classification, qa_pair}.py
    3d/{lidar_box, 3d_mesh, depth_map}.py

Exports:
  OPERATORS: dict[str, callable]   — 20 entries, id → run(items, params)
  OPERATOR_META: dict[str, dict]   — id → metadata
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import image, text, three_d, video
from .three_d import depth_map, lidar_box, three_d_mesh  # noqa: F401  (ensure importable)

# ── Operator → metadata table ─────────────────────────────────────────────────
# Each entry: {id, name, category, modality, description, params, run}
_META_TABLE: List[Dict[str, Any]] = [
    # ── Image (8) ────────────────────────────────────────────────────────────
    {"id": "annot.image.bbox", "name": "Image Bounding Box",
     "category": "geometry", "modality": "image",
     "description": "Validate, NMS, and normalize rectangular bounding boxes.",
     "params": [
         {"name": "min_area", "type": "int", "default": 16, "required": False},
         {"name": "iou_threshold", "type": "float", "default": 0.0, "required": False},
         {"name": "min_confidence", "type": "float", "default": 0.0, "required": False},
         {"name": "max_boxes", "type": "int", "default": 1000, "required": False},
         {"name": "auto_estimate", "type": "bool", "default": False, "required": False},
     ], "run": image.bbox.run},
    {"id": "annot.image.polygon", "name": "Image Polygon",
     "category": "geometry", "modality": "image",
     "description": "Validate polygons; simplify (DP); auto-extract contours.",
     "params": [
         {"name": "min_area", "type": "float", "default": 4.0, "required": False},
         {"name": "simplify", "type": "float", "default": 0.0, "required": False},
         {"name": "max_vertices", "type": "int", "default": 1000, "required": False},
         {"name": "auto_contour", "type": "bool", "default": False, "required": False},
     ], "run": image.polygon.run},
    {"id": "annot.image.keypoint", "name": "Image Keypoint",
     "category": "geometry", "modality": "image",
     "description": "COCO 17-keypoint skeleton; auto-detect via Harris corners.",
     "params": [
         {"name": "num_keypoints", "type": "int", "default": 17, "required": False},
         {"name": "min_visible", "type": "float", "default": 0.0, "required": False},
         {"name": "coco_skeleton", "type": "bool", "default": True, "required": False},
         {"name": "auto_harris", "type": "bool", "default": False, "required": False},
         {"name": "max_auto", "type": "int", "default": 50, "required": False},
     ], "run": image.keypoint.run},
    {"id": "annot.image.semantic_seg", "name": "Semantic Segmentation",
     "category": "geometry", "modality": "image",
     "description": "Validate mask shape, per-class histogram, ratios.",
     "params": [
         {"name": "num_classes", "type": "int", "default": 21, "required": False},
         {"name": "include_background", "type": "bool", "default": True, "required": False},
         {"name": "compute_histogram", "type": "bool", "default": True, "required": False},
         {"name": "min_class_ratio", "type": "float", "default": 0.0, "required": False},
         {"name": "method", "type": "str", "default": "pascal_voc", "required": False},
     ], "run": image.semantic_seg.run},
    {"id": "annot.image.instance_seg", "name": "Instance Segmentation",
     "category": "geometry", "modality": "image",
     "description": "Validate per-instance mask+bbox; area stats; NMS.",
     "params": [
         {"name": "max_instances", "type": "int", "default": 100, "required": False},
         {"name": "iou_threshold", "type": "float", "default": 0.5, "required": False},
         {"name": "min_area", "type": "int", "default": 16, "required": False},
         {"name": "mask_format", "type": "str", "default": "polygon", "required": False},
     ], "run": image.instance_seg.run},
    {"id": "annot.image.classification", "name": "Image Classification",
     "category": "categorical", "modality": "image",
     "description": "Top-K classification with label whitelist and confidence gate.",
     "params": [
         {"name": "top_k", "type": "int", "default": 5, "required": False},
         {"name": "min_confidence", "type": "float", "default": 0.0, "required": False},
         {"name": "label_set", "type": "list", "default": [], "required": False},
         {"name": "multi_label", "type": "bool", "default": False, "required": False},
     ], "run": image.classification.run},
    {"id": "annot.image.caption", "name": "Image Caption",
     "category": "text", "modality": "image",
     "description": "Validate caption length, strip HTML, language detect.",
     "params": [
         {"name": "min_words", "type": "int", "default": 1, "required": False},
         {"name": "max_words", "type": "int", "default": 200, "required": False},
         {"name": "min_chars", "type": "int", "default": 1, "required": False},
         {"name": "language", "type": "str", "default": "auto", "required": False},
         {"name": "strip_html", "type": "bool", "default": True, "required": False},
         {"name": "templates", "type": "list", "default": [], "required": False},
     ], "run": image.caption.run},
    {"id": "annot.image.ocr_box", "name": "OCR Text Boxes",
     "category": "text", "modality": "image",
     "description": "Validate OCR words/lines; charset and score gates.",
     "params": [
         {"name": "min_score", "type": "float", "default": 0.3, "required": False},
         {"name": "min_box_area", "type": "int", "default": 16, "required": False},
         {"name": "iou_threshold", "type": "float", "default": 0.0, "required": False},
         {"name": "min_text_length", "type": "int", "default": 1, "required": False},
         {"name": "allowed_chars", "type": "str", "default": "", "required": False},
     ], "run": image.ocr_box.run},

    # ── Video (5) ────────────────────────────────────────────────────────────
    {"id": "annot.video.tracking", "name": "Multi-Object Tracking",
     "category": "temporal", "modality": "video",
     "description": "IoU-based tracker; builds tracks across frames.",
     "params": [
         {"name": "max_age", "type": "int", "default": 30, "required": False},
         {"name": "min_hits", "type": "int", "default": 3, "required": False},
         {"name": "iou_threshold", "type": "float", "default": 0.3, "required": False},
     ], "run": video.tracking.run},
    {"id": "annot.video.action_recognition", "name": "Action Recognition",
     "category": "temporal", "modality": "video",
     "description": "Per-clip top-K action labels with category whitelist.",
     "params": [
         {"name": "top_k", "type": "int", "default": 5, "required": False},
         {"name": "min_confidence", "type": "float", "default": 0.0, "required": False},
         {"name": "label_set", "type": "list", "default": [], "required": False},
         {"name": "min_clip_length", "type": "int", "default": 1, "required": False},
         {"name": "max_clip_length", "type": "int", "default": 100000, "required": False},
         {"name": "action_categories", "type": "list", "default": [], "required": False},
     ], "run": video.action_recognition.run},
    {"id": "annot.video.temporal_seg", "name": "Temporal Segmentation",
     "category": "temporal", "modality": "video",
     "description": "Time-stamped segments; merge, drop overlaps, duration filter.",
     "params": [
         {"name": "min_duration", "type": "float", "default": 0.1, "required": False},
         {"name": "max_duration", "type": "float", "default": 600.0, "required": False},
         {"name": "merge_same_label", "type": "bool", "default": False, "required": False},
         {"name": "min_gap", "type": "float", "default": 0.0, "required": False},
         {"name": "allow_overlap", "type": "bool", "default": False, "required": False},
         {"name": "label_set", "type": "list", "default": [], "required": False},
     ], "run": video.temporal_seg.run},
    {"id": "annot.video.shot_detection", "name": "Shot Detection",
     "category": "temporal", "modality": "video",
     "description": "Detect shot boundaries from per-frame features.",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.30, "required": False},
         {"name": "min_shot_length", "type": "int", "default": 1, "required": False},
         {"name": "method", "type": "str", "default": "brightness", "required": False},
         {"name": "hysteresis", "type": "float", "default": 0.05, "required": False},
     ], "run": video.shot_detection.run},
    {"id": "annot.video.video_caption", "name": "Video Caption",
     "category": "text", "modality": "video",
     "description": "Validate video captions (length, language, multi-caption).",
     "params": [
         {"name": "min_words", "type": "int", "default": 1, "required": False},
         {"name": "max_words", "type": "int", "default": 500, "required": False},
         {"name": "language", "type": "str", "default": "auto", "required": False},
         {"name": "multi_caption", "type": "bool", "default": False, "required": False},
         {"name": "templates", "type": "list", "default": [], "required": False},
     ], "run": video.video_caption.run},

    # ── Text (4) ──────────────────────────────────────────────────────────────
    {"id": "annot.text.ner", "name": "Named Entity Recognition",
     "category": "text", "modality": "text",
     "description": "Validate spans, drop overlaps, filter entity types.",
     "params": [
         {"name": "entity_types", "type": "list", "default": [], "required": False},
         {"name": "min_length", "type": "int", "default": 1, "required": False},
         {"name": "allow_overlap", "type": "bool", "default": False, "required": False},
         {"name": "merge_strategy", "type": "str", "default": "longest", "required": False},
     ], "run": text.ner.run},
    {"id": "annot.text.sentiment", "name": "Sentiment Analysis",
     "category": "categorical", "modality": "text",
     "description": "Lexicon-based zh+en sentiment scoring.",
     "params": [
         {"name": "label_set", "type": "list",
          "default": ["positive", "negative", "neutral"], "required": False},
         {"name": "top_k", "type": "int", "default": 1, "required": False},
         {"name": "min_score", "type": "float", "default": 0.0, "required": False},
         {"name": "intensity_threshold", "type": "float", "default": 0.0, "required": False},
         {"name": "method", "type": "str", "default": "lexicon", "required": False},
     ], "run": text.sentiment.run},
    {"id": "annot.text.text_classification", "name": "Text Classification",
     "category": "categorical", "modality": "text",
     "description": "Top-K text labels with whitelist and length gates.",
     "params": [
         {"name": "top_k", "type": "int", "default": 1, "required": False},
         {"name": "min_score", "type": "float", "default": 0.0, "required": False},
         {"name": "label_set", "type": "list", "default": [], "required": False},
         {"name": "multi_label", "type": "bool", "default": False, "required": False},
         {"name": "strip_html", "type": "bool", "default": True, "required": False},
         {"name": "min_text_length", "type": "int", "default": 1, "required": False},
         {"name": "max_text_length", "type": "int", "default": 100000, "required": False},
     ], "run": text.text_classification.run},
    {"id": "annot.text.qa_pair", "name": "Question/Answer Pair",
     "category": "text", "modality": "text",
     "description": "Validate QA pairs; offset-context check; deduplicate.",
     "params": [
         {"name": "max_answers", "type": "int", "default": 5, "required": False},
         {"name": "min_answer_length", "type": "int", "default": 1, "required": False},
         {"name": "max_answer_length", "type": "int", "default": 10000, "required": False},
         {"name": "require_context", "type": "bool", "default": False, "required": False},
         {"name": "validate_offsets", "type": "bool", "default": True, "required": False},
         {"name": "deduplicate", "type": "bool", "default": True, "required": False},
     ], "run": text.qa_pair.run},

    # ── 3D (3) ────────────────────────────────────────────────────────────────
    {"id": "annot.3d.lidar_box", "name": "LiDAR 3D Bounding Box",
     "category": "geometry", "modality": "3d",
     "description": "Validate 3D boxes (center/size/yaw); volume filter; 3D NMS.",
     "params": [
         {"name": "min_volume", "type": "float", "default": 0.01, "required": False},
         {"name": "max_volume", "type": "float", "default": 200.0, "required": False},
         {"name": "min_score", "type": "float", "default": 0.0, "required": False},
         {"name": "iou_3d_threshold", "type": "float", "default": 0.0, "required": False},
         {"name": "yaw_range", "type": "list", "default": [-3.1416, 3.1416], "required": False},
         {"name": "allowed_labels", "type": "list", "default": [], "required": False},
     ], "run": lidar_box.run},
    {"id": "annot.3d.3d_mesh", "name": "3D Mesh",
     "category": "geometry", "modality": "3d",
     "description": "Validate mesh (verts/faces); bbox, centroid, surface area.",
     "params": [
         {"name": "min_faces", "type": "int", "default": 1, "required": False},
         {"name": "max_faces", "type": "int", "default": 1000000, "required": False},
         {"name": "compute_bbox", "type": "bool", "default": True, "required": False},
         {"name": "compute_centroid", "type": "bool", "default": True, "required": False},
         {"name": "compute_surface_area", "type": "bool", "default": True, "required": False},
         {"name": "label_strategy", "type": "str", "default": "face", "required": False},
     ], "run": three_d_mesh.run},
    {"id": "annot.3d.depth_map", "name": "Depth Map",
     "category": "geometry", "modality": "3d",
     "description": "Validate depth; min/max/mean/std; histogram; intrinsics.",
     "params": [
         {"name": "min_depth", "type": "float", "default": 0.0, "required": False},
         {"name": "max_depth", "type": "float", "default": 1000.0, "required": False},
         {"name": "unit", "type": "str", "default": "m", "required": False},
         {"name": "compute_stats", "type": "bool", "default": True, "required": False},
         {"name": "compute_histogram", "type": "bool", "default": True, "required": False},
         {"name": "histogram_bins", "type": "int", "default": 64, "required": False},
         {"name": "require_intrinsics", "type": "bool", "default": False, "required": False},
     ], "run": depth_map.run},
]


OPERATORS: Dict[str, Callable] = {entry["id"]: entry["run"] for entry in _META_TABLE}


def _meta_without_callable(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "run"}


OPERATOR_META: Dict[str, Dict[str, Any]] = {
    entry["id"]: _meta_without_callable(entry) for entry in _META_TABLE
}


def list_operators(modality: str = None, category: str = None) -> List[Dict[str, Any]]:
    """Return operator metadata list; filter by modality/category."""
    out = [_meta_without_callable(e) for e in _META_TABLE]
    if modality:
        out = [e for e in out if e.get("modality") == modality]
    if category:
        out = [e for e in out if e.get("category") == category]
    return out


def get_operator(op_id: str) -> Callable:
    """Return the run() callable for an operator id; None if missing."""
    return OPERATORS.get(op_id)


def get_meta(op_id: str) -> Dict[str, Any]:
    """Return metadata for an operator id; None if missing."""
    return OPERATOR_META.get(op_id)


__all__ = [
    "OPERATORS",
    "OPERATOR_META",
    "list_operators",
    "get_operator",
    "get_meta",
]