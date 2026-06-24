"""cleaning_service.operators — 32 cleaning operators registry (P3-4-W1).

Layout:
  operators/
    _image_utils.py / _video_utils.py / _audio_utils.py   (shared deps)
    image/{resolution, aspect_ratio, blur, nsfw,
           deduplicate_md5, deduplicate_phash, deduplicate_semantic,
           noise, color_balance, face_blur, watermark, compress_artifact}.py
    video/{resolution, duration, fps, black_border, static,
           nsfw, deduplicate, compress_artifact}.py
    text/{empty, length, deduplicate, language, sensitive,
          toxicity, html, pii}.py
    audio/{snr, silence, duration, sample_rate}.py

Exports:
  OPERATORS: dict[str, callable]        — 32 entries, id → run(items, params)
  OPERATOR_META: dict[str, dict]        — id → {category, name, params, ...}
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import audio, image, text, video

# ── Operator → metadata table ─────────────────────────────────────────────────
# Each entry: {id, name, category, modality, description, params, run}
_META_TABLE: List[Dict[str, Any]] = [
    # ── Image (12) ────────────────────────────────────────────────────────────
    {"id": "clean.image.resolution", "name": "Image Resolution Filter",
     "category": "filter", "modality": "image",
     "description": "Keep images with width/height within [min_w,max_w]×[min_h,max_h]",
     "params": [
         {"name": "min_w", "type": "int", "default": 256, "required": False},
         {"name": "max_w", "type": "int", "default": 8192, "required": False},
         {"name": "min_h", "type": "int", "default": 256, "required": False},
         {"name": "max_h", "type": "int", "default": 8192, "required": False},
         {"name": "drop_missing", "type": "bool", "default": False, "required": False},
     ], "run": image.resolution.run},
    {"id": "clean.image.aspect_ratio", "name": "Image Aspect Ratio Filter",
     "category": "filter", "modality": "image",
     "description": "Keep images with W/H aspect ratio within [min_ratio, max_ratio]",
     "params": [
         {"name": "min_ratio", "type": "float", "default": 0.5, "required": False},
         {"name": "max_ratio", "type": "float", "default": 2.0, "required": False},
     ], "run": image.aspect_ratio.run},
    {"id": "clean.image.blur", "name": "Image Blur Detector",
     "category": "quality", "modality": "image",
     "description": "Laplacian-variance blur score; filter low-variance items",
     "params": [
         {"name": "min_variance", "type": "float", "default": 80.0, "required": False},
         {"name": "mode", "type": "str", "default": "filter", "required": False},
     ], "run": image.blur.run},
    {"id": "clean.image.nsfw", "name": "Image NSFW Detector",
     "category": "compliance", "modality": "image",
     "description": "YCbCr skin-tone heuristic; flag skin ratio above threshold",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.35, "required": False},
     ], "run": image.nsfw.run},
    {"id": "clean.image.deduplicate.md5", "name": "Image MD5 Dedup",
     "category": "dedup", "modality": "image",
     "description": "Exact MD5-hash deduplication",
     "params": [], "run": image.deduplicate_md5.run},
    {"id": "clean.image.deduplicate.phash", "name": "Image Perceptual-Hash Dedup",
     "category": "dedup", "modality": "image",
     "description": "64-bit pHash near-duplicate detection",
     "params": [
         {"name": "hamming_threshold", "type": "int", "default": 10, "required": False},
     ], "run": image.deduplicate_phash.run},
    {"id": "clean.image.deduplicate.semantic", "name": "Image Semantic Dedup",
     "category": "dedup", "modality": "image",
     "description": "RGB-histogram cosine-similarity near-duplicate detection",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.92, "required": False},
     ], "run": image.deduplicate_semantic.run},
    {"id": "clean.image.noise", "name": "Image Noise Estimator",
     "category": "quality", "modality": "image",
     "description": "Robust Laplacian-MAD noise sigma estimate",
     "params": [
         {"name": "max_sigma", "type": "float", "default": 25.0, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": image.noise.run},
    {"id": "clean.image.color_balance", "name": "Image Color Balance",
     "category": "quality", "modality": "image",
     "description": "Gray-world color-cast deviation detector",
     "params": [
         {"name": "deviation_threshold", "type": "float", "default": 0.15, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": image.color_balance.run},
    {"id": "clean.image.face_blur", "name": "Image Face Blur",
     "category": "privacy", "modality": "image",
     "description": "Detect faces via Haar cascade and Gaussian-blur them",
     "params": [
         {"name": "blur_strength", "type": "int", "default": 25, "required": False},
         {"name": "min_face_size", "type": "int", "default": 30, "required": False},
     ], "run": image.face_blur.run},
    {"id": "clean.image.watermark", "name": "Image Watermark Embedder",
     "category": "branding", "modality": "image",
     "description": "Embed text watermark via imdf.watermark_engine",
     "params": [
         {"name": "text", "type": "str", "default": "nanobot-factory", "required": False},
         {"name": "position", "type": "str", "default": "bottom_right", "required": False},
         {"name": "opacity", "type": "float", "default": 0.5, "required": False},
     ], "run": image.watermark.run},
    {"id": "clean.image.compress_artifact", "name": "Image Compression Artifact",
     "category": "quality", "modality": "image",
     "description": "8x8 DCT-blockiness JPEG-artifact heuristic",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.45, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": image.compress_artifact.run},

    # ── Video (8) ─────────────────────────────────────────────────────────────
    {"id": "clean.video.resolution", "name": "Video Resolution Filter",
     "category": "filter", "modality": "video",
     "description": "Keep videos with width/height within bounds",
     "params": [
         {"name": "min_w", "type": "int", "default": 320, "required": False},
         {"name": "max_w", "type": "int", "default": 7680, "required": False},
         {"name": "min_h", "type": "int", "default": 240, "required": False},
         {"name": "max_h", "type": "int", "default": 4320, "required": False},
     ], "run": video.resolution.run},
    {"id": "clean.video.duration", "name": "Video Duration Filter",
     "category": "filter", "modality": "video",
     "description": "Keep videos within [min_seconds, max_seconds]",
     "params": [
         {"name": "min_seconds", "type": "float", "default": 1.0, "required": False},
         {"name": "max_seconds", "type": "float", "default": 600.0, "required": False},
     ], "run": video.duration.run},
    {"id": "clean.video.fps", "name": "Video FPS Filter",
     "category": "filter", "modality": "video",
     "description": "Keep videos with FPS in [min_fps, max_fps]",
     "params": [
         {"name": "min_fps", "type": "float", "default": 15.0, "required": False},
         {"name": "max_fps", "type": "float", "default": 120.0, "required": False},
     ], "run": video.fps.run},
    {"id": "clean.video.black_border", "name": "Video Black-Border Detector",
     "category": "quality", "modality": "video",
     "description": "Detect letterbox/pillarbox black borders",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.85, "required": False},
         {"name": "max_frames", "type": "int", "default": 8, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": video.black_border.run},
    {"id": "clean.video.static", "name": "Video Static Frame Detector",
     "category": "quality", "modality": "video",
     "description": "Detect videos with mostly static frames",
     "params": [
         {"name": "motion_threshold", "type": "float", "default": 0.02, "required": False},
         {"name": "max_frames", "type": "int", "default": 12, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": video.static.run},
    {"id": "clean.video.nsfw", "name": "Video NSFW Detector",
     "category": "compliance", "modality": "video",
     "description": "Sample frames; aggregate skin-tone ratio",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.35, "required": False},
         {"name": "max_frames", "type": "int", "default": 10, "required": False},
     ], "run": video.nsfw.run},
    {"id": "clean.video.deduplicate", "name": "Video Near-Duplicate Dedup",
     "category": "dedup", "modality": "video",
     "description": "Perceptual-hash sampled frames to detect near-dup videos",
     "params": [
         {"name": "hamming_threshold", "type": "int", "default": 12, "required": False},
         {"name": "frames_per_video", "type": "int", "default": 4, "required": False},
     ], "run": video.deduplicate.run},
    {"id": "clean.video.compress_artifact", "name": "Video Compression Artifact",
     "category": "quality", "modality": "video",
     "description": "Blockiness score averaged over sampled frames",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.4, "required": False},
         {"name": "max_frames", "type": "int", "default": 8, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": video.compress_artifact.run},

    # ── Text (8) ──────────────────────────────────────────────────────────────
    {"id": "clean.text.empty", "name": "Empty Filter",
     "category": "filter", "modality": "text",
     "description": "Drop empty/None/whitespace-only items",
     "params": [
         {"name": "keep_none", "type": "bool", "default": False, "required": False},
     ], "run": text.empty.run},
    {"id": "clean.text.length", "name": "Length Filter",
     "category": "filter", "modality": "text",
     "description": "Keep items whose length is within [min_chars, max_chars]",
     "params": [
         {"name": "min_chars", "type": "int", "default": 1, "required": False},
         {"name": "max_chars", "type": "int", "default": 100000, "required": False},
     ], "run": text.length.run},
    {"id": "clean.text.deduplicate", "name": "Text Dedup",
     "category": "dedup", "modality": "text",
     "description": "Exact MD5 + SimHash near-duplicate dedup",
     "params": [
         {"name": "hamming_threshold", "type": "int", "default": 3, "required": False},
         {"name": "enable_exact", "type": "bool", "default": True, "required": False},
     ], "run": text.deduplicate.run},
    {"id": "clean.text.language", "name": "Language Filter",
     "category": "filter", "modality": "text",
     "description": "Classify language (zh|en|mixed|other); filter by target",
     "params": [
         {"name": "target_lang", "type": "str", "default": "any", "required": False},
     ], "run": text.language.run},
    {"id": "clean.text.sensitive", "name": "Sensitive Word Filter",
     "category": "compliance", "modality": "text",
     "description": "Filter or mask sensitive words",
     "params": [
         {"name": "mode", "type": "str", "default": "drop", "required": False},
         {"name": "wordlist", "type": "list", "default": [], "required": False},
         {"name": "case_sensitive", "type": "bool", "default": False, "required": False},
     ], "run": text.sensitive.run},
    {"id": "clean.text.toxicity", "name": "Toxicity Detector",
     "category": "compliance", "modality": "text",
     "description": "Heuristic toxicity scoring (profanity + CAPS + punctuation)",
     "params": [
         {"name": "threshold", "type": "float", "default": 0.5, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
         {"name": "wordlist", "type": "list", "default": [], "required": False},
     ], "run": text.toxicity.run},
    {"id": "clean.text.html", "name": "HTML Stripper",
     "category": "format", "modality": "text",
     "description": "Remove HTML tags, unescape entities, collapse whitespace",
     "params": [
         {"name": "collapse_whitespace", "type": "bool", "default": True, "required": False},
     ], "run": text.html.run},
    {"id": "clean.text.pii", "name": "PII Detector/Redactor",
     "category": "privacy", "modality": "text",
     "description": "Detect/redact PII using imdf.pii_engine",
     "params": [
         {"name": "strategy", "type": "str", "default": "mask", "required": False},
     ], "run": text.pii.run},

    # ── Audio (4) ─────────────────────────────────────────────────────────────
    {"id": "clean.audio.snr", "name": "Audio SNR",
     "category": "quality", "modality": "audio",
     "description": "Per-frame energy-based SNR (dB) estimate",
     "params": [
         {"name": "min_snr_db", "type": "float", "default": 10.0, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": audio.snr.run},
    {"id": "clean.audio.silence", "name": "Audio Silence Detector",
     "category": "quality", "modality": "audio",
     "description": "Detect overly silent audio",
     "params": [
         {"name": "max_silence_ratio", "type": "float", "default": 0.6, "required": False},
         {"name": "silence_db", "type": "float", "default": -40.0, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": audio.silence.run},
    {"id": "clean.audio.duration", "name": "Audio Duration Filter",
     "category": "filter", "modality": "audio",
     "description": "Keep audio within [min_seconds, max_seconds]",
     "params": [
         {"name": "min_seconds", "type": "float", "default": 0.5, "required": False},
         {"name": "max_seconds", "type": "float", "default": 3600.0, "required": False},
     ], "run": audio.duration.run},
    {"id": "clean.audio.sample_rate", "name": "Audio Sample-Rate Check",
     "category": "quality", "modality": "audio",
     "description": "Verify sample rate vs target",
     "params": [
         {"name": "target_sr", "type": "int", "default": 16000, "required": False},
         {"name": "tolerance_pct", "type": "float", "default": 0.05, "required": False},
         {"name": "mode", "type": "str", "default": "score", "required": False},
     ], "run": audio.sample_rate.run},
]


OPERATORS: Dict[str, Callable] = {entry["id"]: entry["run"] for entry in _META_TABLE}


def _meta_without_callable(entry: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in entry.items() if k != "run"}
    return out


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