"""P4-6-W2: Operator marketplace — 200+ operators.

The marketplace aggregates operators from across the platform:

  * P3-4  cleaning / scoring / annotation / filter / export / evaluation
  * P3-6  pipeline / multimodal / feedback templates
  * P4-5  multi-modal generators (image / video / voice / storyboard / …)
  * P4-6  visual operators (inpaint / outpaint / upscale / pose / …)
  * agent / orchestration helpers

Each operator is registered as an :class:`OperatorDef` with versioned
:class:`OperatorVersion` records. A small in-memory inverted index
powers ``search_operators``. The full registry is exposed via
``OPERATOR_REGISTRY`` and the ``list_operators`` / ``market_summary``
helpers.

This module is intentionally self-contained: it does not import
``services.cleaining_service`` etc. because those services expose their
own public REST surface; the marketplace only needs a stable slug +
schema contract so the visual editor can render the right form.
"""
from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# =====================================================================
# Data models
# =====================================================================

@dataclass
class OperatorVersion:
    """One version of an operator. Versions are immutable."""

    version: str  # semver
    released_at: str = ""
    changelog: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    deprecated: bool = False
    replaces: Optional[str] = None  # previous version replaced by this one

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "released_at": self.released_at,
            "changelog": self.changelog,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "deprecated": self.deprecated,
            "replaces": self.replaces,
        }


@dataclass
class OperatorDef:
    """A marketplace entry."""

    id: str  # canonical slug
    name: str
    category: str  # cleaning / scoring / annotation / filter / export / evaluation / generator / editor / agent
    description: str = ""
    icon: str = ""
    color: str = ""
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    versions: List[OperatorVersion] = field(default_factory=list)
    latest: str = "1.0.0"
    owner: str = "system"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "tags": list(self.tags),
            "capabilities": list(self.capabilities),
            "latest": self.latest,
            "owner": self.owner,
            "version_count": len(self.versions),
            "versions": [v.to_dict() for v in self.versions],
        }

    def latest_version(self) -> OperatorVersion:
        for v in self.versions:
            if v.version == self.latest:
                return v
        return self.versions[0]


# =====================================================================
# Schema helpers
# =====================================================================

def _schema(props: Dict[str, str], required: Iterable[str] = ()) -> Dict[str, Any]:
    """Tiny JSON-schema builder used to keep registry entries terse."""
    out_props: Dict[str, Any] = {}
    for name, kind in props.items():
        out_props[name] = {"type": kind}
    return {
        "type": "object",
        "properties": out_props,
        "required": list(required),
    }


def _version(v: str, in_: Dict[str, str], out: Dict[str, str],
             changelog: str = "",
             replaces: Optional[str] = None,
             deprecated: bool = False) -> OperatorVersion:
    return OperatorVersion(
        version=v,
        released_at=datetime.utcnow().isoformat(),
        changelog=changelog,
        input_schema=_schema(in_),
        output_schema=_schema(out),
        replaces=replaces,
        deprecated=deprecated,
    )


# =====================================================================
# Registry builder
# =====================================================================

CATEGORIES: List[str] = [
    "cleaning", "scoring", "annotation", "filter",
    "export", "evaluation", "generator", "editor", "agent",
]


def _build_cleaning() -> List[OperatorDef]:
    """P3-4 cleaning operators (~32)."""
    items = [
        ("dedup_hash", "Hash dedup (pHash)", ["image", "dedup"]),
        ("dedup_semantic", "Semantic dedup (CLIP)", ["image", "dedup", "clip"]),
        ("nsfw_classifier", "NSFW classifier", ["nsfw", "safety"]),
        ("blur_detector", "Blur detector", ["quality", "blur"]),
        ("aesthetic_low", "Aesthetic low-pass filter", ["aesthetic"]),
        ("watermark_detector", "Watermark detector", ["watermark"]),
        ("c2pa_check", "C2PA provenance check", ["provenance"]),
        ("face_count", "Face count", ["face"]),
        ("face_blur", "Face anonymiser (blur)", ["face", "anonymise"]),
        ("ocr_text", "OCR (Tesseract / PaddleOCR)", ["ocr"]),
        ("pii_redact_email", "PII redact — email", ["pii"]),
        ("pii_redact_phone", "PII redact — phone", ["pii"]),
        ("pii_redact_idcard", "PII redact — ID card", ["pii"]),
        ("language_id", "Language ID (fasttext)", ["nlp"]),
        ("toxicity", "Toxicity classifier", ["safety", "nlp"]),
        ("size_normalise", "Size normalise", ["preprocess"]),
        ("color_balance", "Color balance (white balance)", ["preprocess"]),
        ("jpeg_artifact", "JPEG artifact remover", ["preprocess"]),
        ("video_dedup", "Video dedup (frame hash)", ["video", "dedup"]),
        ("video_keyframe", "Video keyframe extraction", ["video", "preprocess"]),
        ("video_scene", "Video scene detection", ["video"]),
        ("audio_dedup", "Audio dedup (chromaprint)", ["audio", "dedup"]),
        ("audio_vad", "Voice activity detection", ["audio", "vad"]),
        ("audio_silence_trim", "Silence trim", ["audio"]),
        ("audio_normalise_loudness", "Loudness normalise (LUFS)", ["audio"]),
        ("audio_language_id", "Spoken language ID", ["audio", "nlp"]),
        ("text_dedup_minhash", "Text dedup (MinHash)", ["text", "dedup"]),
        ("text_pii_regex", "Text PII regex scrubber", ["text", "pii"]),
        ("text_lang_detect", "Text language detect", ["text", "nlp"]),
        ("text_grammar", "Text grammar pass", ["text"]),
        ("image_caption_blip", "Image caption (BLIP-2)", ["caption"]),
        ("image_dense_caption", "Dense caption (Kosmos-2)", ["caption"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.cleaning.{slug}",
            name=label,
            category="cleaning",
            description=f"{label} — data cleaning operator.",
            icon="🧹", color="#10b981",
            tags=tags + ["cleaning"],
            capabilities=["preprocess", "filter"],
            versions=[
                _version("1.0.0", {"input": "any"}, {"output": "any"}),
                _version("1.1.0", {"input": "any", "threshold": "number"},
                         {"output": "any", "score": "number"},
                         changelog="add threshold param"),
            ],
            latest="1.1.0",
        ))
    return out


def _build_cleaning_extra() -> List[OperatorDef]:
    """Extra cleaning / preprocessing operators (12) — rounds to 44."""
    items = [
        ("image_resize", "Image resize (bicubic)", ["image", "preprocess"]),
        ("image_pad", "Image pad to square", ["image", "preprocess"]),
        ("image_format_convert", "Image format convert (webp/jpg/png)", ["image"]),
        ("video_resize", "Video resize", ["video", "preprocess"]),
        ("video_fps_normalise", "FPS normalise", ["video", "preprocess"]),
        ("video_audio_mux", "Mux audio into video", ["video", "audio"]),
        ("audio_resample", "Audio resample", ["audio", "preprocess"]),
        ("audio_mono", "Force mono audio", ["audio", "preprocess"]),
        ("text_normalise_unicode", "Unicode normalise (NFC/NFKC)", ["text"]),
        ("text_lower", "Text lowercase", ["text"]),
        ("json_schema_validate", "Validate against JSON schema", ["schema"]),
        ("dedup_simhash", "SimHash near-dedup", ["dedup", "text"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.cleaning.{slug}",
            name=label, category="cleaning",
            description=f"{label} — extra cleaning operator.",
            icon="🧹", color="#10b981",
            tags=tags + ["cleaning"],
            capabilities=["preprocess", "filter"],
            versions=[_version("1.0.0", {"input": "any"},
                               {"output": "any"})],
            latest="1.0.0",
        ))
    return out


def _build_scoring() -> List[OperatorDef]:
    """P3-4 scoring operators (~15)."""
    items = [
        ("aesthetic_laion", "Aesthetic scorer (LAION)", ["aesthetic"]),
        ("aesthetic_musiq", "Aesthetic scorer (MUSIQ)", ["aesthetic"]),
        ("quality_brisque", "BRISQUE quality", ["quality"]),
        ("quality_maniqa", "MANIQA quality", ["quality"]),
        ("quality_clip_score", "CLIP alignment score", ["alignment", "clip"]),
        ("face_quality", "Face quality (CR-FIQA)", ["face", "quality"]),
        ("text_quality", "Text perplexity / quality", ["text", "quality"]),
        ("audio_mos", "Audio MOS predictor", ["audio", "quality"]),
        ("video_aesthetic", "Video aesthetic predictor", ["video", "aesthetic"]),
        ("motion_score", "Motion magnitude", ["video", "motion"]),
        ("camera_motion", "Camera motion classifier", ["video", "motion"]),
        ("speech_intelligibility", "Speech intelligibility (STOI)", ["audio"]),
        ("composite_score", "Composite rank aggregator", ["rank"]),
        ("relevance_clip", "CLIP text-image relevance", ["alignment"]),
        ("rank_topk", "Top-K ranker", ["rank"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.scoring.{slug}",
            name=label, category="scoring",
            description=f"{label} — quality / ranking operator.",
            icon="⭐", color="#f59e0b",
            tags=tags + ["scoring"],
            capabilities=["score", "rank"],
            versions=[_version("1.0.0", {"input": "any"},
                               {"score": "number"})],
            latest="1.0.0",
        ))
    return out


def _build_annotation() -> List[OperatorDef]:
    """P3-4 annotation operators (~20)."""
    items = [
        ("bbox_detection", "BBox detection (YOLOv8)", ["bbox", "det"]),
        ("obb_detection", "Oriented BBox detection", ["obb"]),
        ("instance_seg", "Instance segmentation (Mask R-CNN)", ["segmentation"]),
        ("semantic_seg", "Semantic segmentation", ["segmentation"]),
        ("panoptic_seg", "Panoptic segmentation", ["segmentation"]),
        ("keypoint", "Keypoint detection (pose)", ["keypoint", "pose"]),
        ("depth_estimation", "Depth estimation (MiDaS)", ["depth"]),
        ("normal_estimation", "Surface normal", ["normal"]),
        ("obj3d_detection", "3D object detection", ["3d", "det"]),
        ("tracking_sort", "SORT tracker", ["tracking"]),
        ("tracking_bytetrack", "ByteTrack tracker", ["tracking"]),
        ("action_recognition", "Action recognition", ["video", "action"]),
        ("ocr_words", "OCR with word boxes", ["ocr", "bbox"]),
        ("ner_english", "English NER", ["nlp", "ner"]),
        ("ner_chinese", "Chinese NER", ["nlp", "ner", "zh"]),
        ("qa_extract", "Extractive QA", ["nlp", "qa"]),
        ("summarisation", "Text summarisation", ["nlp"]),
        ("classify_image", "Image classification (CLIP zero-shot)", ["classify"]),
        ("classify_text", "Text classification", ["nlp", "classify"]),
        ("video_caption", "Video caption (VideoLLaMA)", ["video", "caption"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.annotation.{slug}",
            name=label, category="annotation",
            description=f"{label} — annotation / detection operator.",
            icon="🏷️", color="#8b5cf6",
            tags=tags + ["annotation"],
            capabilities=["det", "classify", "segment", "nlp"],
            versions=[_version("1.0.0", {"input": "any"},
                               {"annotations": "array"})],
            latest="1.0.0",
        ))
    return out


def _build_filter() -> List[OperatorDef]:
    """P3-4 filter / rule operators (~12)."""
    items = [
        ("threshold_score", "Score threshold", ["threshold"]),
        ("tag_match", "Tag match (all / any / none)", ["rule"]),
        ("length_range", "Length range filter", ["rule"]),
        ("duration_range", "Duration range filter (video/audio)", ["rule"]),
        ("aspect_ratio", "Aspect-ratio filter", ["image"]),
        ("language_allow", "Language allow-list", ["text"]),
        ("nsfw_block", "NSFW block (zero tolerance)", ["safety"]),
        ("dedup_block", "Dedup block (drop duplicates)", ["dedup"]),
        ("ratio_pos_neg", "Positive / negative ratio filter", ["rule"]),
        ("time_window", "Time-window filter", ["rule"]),
        ("random_sample", "Random sampling", ["sample"]),
        ("stratified_sample", "Stratified sampling", ["sample"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.filter.{slug}",
            name=label, category="filter",
            description=f"{label} — filtering / rule operator.",
            icon="🔍", color="#0ea5e9",
            tags=tags + ["filter"],
            capabilities=["rule", "threshold", "sample"],
            versions=[_version("1.0.0", {"items": "array"},
                               {"items": "array"})],
            latest="1.0.0",
        ))
    return out


def _build_export() -> List[OperatorDef]:
    """P3-4 export / dataset materialisation operators (~10)."""
    items = [
        ("jsonl", "Export to JSONL", ["jsonl"]),
        ("parquet", "Export to Parquet", ["parquet"]),
        ("coco", "Export to COCO", ["coco", "bbox"]),
        ("yolo", "Export to YOLO txt", ["yolo", "bbox"]),
        ("voc", "Export to Pascal VOC", ["voc", "bbox"]),
        ("lvis", "Export to LVIS", ["lvis"]),
        ("webdataset", "Export to WebDataset", ["wds", "tar"]),
        ("huggingface", "Push to HuggingFace hub", ["hf"]),
        ("aliyun_oss", "Upload to Aliyun OSS", ["oss", "aliyun"]),
        ("local_copy", "Local copy", ["local"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.export.{slug}",
            name=label, category="export",
            description=f"{label} — export / materialise operator.",
            icon="📦", color="#ec4899",
            tags=tags + ["export"],
            capabilities=["export", "materialise"],
            versions=[_version("1.0.0", {"items": "array"},
                               {"uri": "string"})],
            latest="1.0.0",
        ))
    return out


def _build_evaluation() -> List[OperatorDef]:
    """P3-4 evaluation operators (~10)."""
    items = [
        ("gen_eval", "GenEval suite", ["geneval"]),
        ("hpsv2", "HPSv2 human-preference", ["hps"]),
        ("clip_score_eval", "CLIP score eval", ["clip"]),
        ("fid", "FID score", ["fid"]),
        ("is_inception", "Inception Score", ["is"]),
        ("lpips", "LPIPS diversity", ["lpips"]),
        ("bleu", "BLEU", ["nlp", "bleu"]),
        ("rouge", "ROUGE", ["nlp", "rouge"]),
        ("cider", "CIDEr", ["nlp", "cider"]),
        ("wer", "WER (speech)", ["audio", "wer"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.evaluation.{slug}",
            name=label, category="evaluation",
            description=f"{label} — model evaluation operator.",
            icon="📊", color="#6366f1",
            tags=tags + ["eval"],
            capabilities=["eval", "metric"],
            versions=[_version("1.0.0", {"items": "array"},
                               {"metric": "number"})],
            latest="1.0.0",
        ))
    return out


def _build_evaluation_extra() -> List[OperatorDef]:
    """Extra evaluation operators (12) — rounds to 22 in evaluation."""
    items = [
        ("mmmu", "MMMU multi-modal understanding", ["mmmu"]),
        ("mmlu", "MMLU text benchmark", ["mmlu"]),
        ("arc", "ARC reasoning benchmark", ["arc"]),
        ("hellaswag", "HellaSwag commonsense", ["hellaswag"]),
        ("truthfulqa", "TruthfulQA", ["truthfulqa"]),
        ("aesthetic_benchmark", "Aesthetic benchmark suite", ["aesthetic"]),
        ("ocr_accuracy", "OCR accuracy benchmark", ["ocr", "benchmark"]),
        ("diversity_score", "Output diversity score", ["diversity"]),
        ("bias_score", "Bias detection score", ["bias", "safety"]),
        ("robustness_score", "Robustness perturbation", ["robustness"]),
        ("safety_judge", "LLM safety judge", ["safety", "judge"]),
        ("human_pref_alignment", "Human preference alignment", ["alignment"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.evaluation.{slug}",
            name=label, category="evaluation",
            description=f"{label} — extra evaluation operator.",
            icon="📊", color="#6366f1",
            tags=tags + ["eval"],
            capabilities=["eval", "metric"],
            versions=[_version("1.0.0", {"items": "array"},
                               {"metric": "number"})],
            latest="1.0.0",
        ))
    return out


def _build_generator() -> List[OperatorDef]:
    """P4-5 multi-modal generators (18)."""
    items = [
        ("sdxl_txt2img", "SDXL text-to-image", ["sdxl", "txt2img"]),
        ("sd3_txt2img", "SD3 text-to-image", ["sd3", "txt2img"]),
        ("flux_txt2img", "Flux text-to-image", ["flux", "txt2img"]),
        ("kandinsky_txt2img", "Kandinsky text-to-image", ["kandinsky"]),
        ("dalle3", "DALL-E 3 (remote)", ["dalle"]),
        ("midjourney_remote", "Midjourney (remote)", ["midjourney"]),
        ("qwen_image", "Qwen-Image", ["qwen"]),
        ("kolors", "Kolors (Kwai)", ["kolors"]),
        ("animatediff", "AnimateDiff", ["video", "anim"]),
        ("cogvideox", "CogVideoX", ["video", "cog"]),
        ("wan_video", "Wan 2.1 video", ["video", "wan"]),
        ("kling_video", "Kling video (remote)", ["video", "kling"]),
        ("hunyuan_video", "Hunyuan video", ["video", "hunyuan"]),
        ("cosyvoice_tts", "CosyVoice TTS", ["tts", "zh"]),
        ("bark_tts", "Bark TTS", ["tts", "en"]),
        ("musicgen", "MusicGen background music", ["music"]),
        ("diffrythm", "DiffRythm music", ["music", "rhythm"]),
        ("lora_load", "LoRA load + apply", ["lora"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.generator.{slug}",
            name=label, category="generator",
            description=f"{label} — multi-modal generation operator.",
            icon="🎨", color="#a855f7",
            tags=tags + ["generator"],
            capabilities=["generate"],
            versions=[_version("1.0.0", {"prompt": "string"},
                               {"uri": "string"})],
            latest="1.0.0",
        ))
    return out


def _build_editor() -> List[OperatorDef]:
    """P4-6 visual operators (~39)."""
    items = [
        ("inpaint", "Inpaint (mask-driven)", ["inpaint"]),
        ("outpaint", "Outpaint (extend canvas)", ["outpaint"]),
        ("upscale_4x", "Upscale 4x (Real-ESRGAN)", ["upscale"]),
        ("upscale_2x", "Upscale 2x", ["upscale"]),
        ("face_restore", "Face restore (CodeFormer)", ["face"]),
        ("color_grade", "Color grading (LUT)", ["color"]),
        ("relight", "Relight (IC-Light)", ["relight"]),
        ("bg_remove", "Background removal (rembg)", ["bg"]),
        ("bg_replace", "Background replace", ["bg", "inpaint"]),
        ("crop_resize", "Crop + resize", ["preprocess"]),
        ("rotate_flip", "Rotate / flip", ["preprocess"]),
        ("denoise", "Denoise (DnCNN)", ["preprocess"]),
        ("deblur", "Deblur", ["preprocess"]),
        ("dejpeg", "De-JPEG artefact", ["preprocess"]),
        ("style_transfer", "Style transfer", ["style"]),
        ("cartoonify", "Cartoonify", ["style"]),
        ("sketch_to_image", "Sketch → image", ["sketch", "controlnet"]),
        ("pose_to_image", "Pose → image (ControlNet)", ["pose", "controlnet"]),
        ("depth_to_image", "Depth → image (ControlNet)", ["depth", "controlnet"]),
        ("canny_to_image", "Canny → image (ControlNet)", ["canny", "controlnet"]),
        ("ip_adapter", "IP-Adapter style ref", ["ip_adapter"]),
        ("img2img", "Image-to-image", ["img2img"]),
        ("tiled_diffusion", "Tiled diffusion", ["tile"]),
        ("img2vid", "Image → video (Stable Video)", ["i2v"]),
        ("vid2vid", "Video → video", ["v2v"]),
        ("frame_interp", "Frame interpolation (RIFE)", ["interp"]),
        ("super_res_video", "Video super-res", ["upscale", "video"]),
        ("subtitle_burn", "Burn subtitles (ASS / SRT)", ["subtitle"]),
        ("video_cut", "Cut / trim video", ["video", "cut"]),
        ("video_concat", "Concatenate clips", ["video", "concat"]),
        ("video_speed", "Speed change (slow / fast)", ["video", "speed"]),
        ("audio_mix", "Audio mix (multi-track)", ["audio", "mix"]),
        ("audio_fade", "Audio fade in / out", ["audio"]),
        ("audio_eq", "Audio equaliser", ["audio"]),
        ("audio_denoise", "Audio denoise", ["audio"]),
        ("video_transition", "Apply video transition", ["video", "transition"]),
        ("watermark_add", "Add watermark", ["watermark"]),
        ("watermark_remove", "Remove watermark (inpaint)", ["watermark"]),
        ("export_mp4", "Export final MP4", ["export", "mp4"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.editor.{slug}",
            name=label, category="editor",
            description=f"{label} — visual / video editor operator.",
            icon="🖌️", color="#06b6d4",
            tags=tags + ["editor"],
            capabilities=["edit", "transform", "render"],
            versions=[_version("1.0.0", {"input": "any"},
                               {"output": "any"})],
            latest="1.0.0",
        ))
    return out


def _build_agent() -> List[OperatorDef]:
    """P3-4 agent / orchestration helpers (~10)."""
    items = [
        ("llm_chat", "LLM chat (gpt-4o / claude / qwen)", ["llm"]),
        ("llm_embed", "LLM embedding", ["llm", "embed"]),
        ("agent_dispatch", "Agent dispatch (15 types)", ["agent"]),
        ("memory_recall", "Memory recall (vector)", ["memory"]),
        ("memory_store", "Memory store (long-term)", ["memory"]),
        ("rag_query", "RAG query (vector+BM25)", ["rag"]),
        ("tool_call", "Tool call (function-call)", ["tool"]),
        ("plan_agent", "Planning agent (ReAct)", ["agent", "plan"]),
        ("critic_agent", "Critic agent (review)", ["agent", "review"]),
        ("router_agent", "Router agent (intent)", ["agent", "router"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.agent.{slug}",
            name=label, category="agent",
            description=f"{label} — agent / orchestration operator.",
            icon="🤖", color="#7c3aed",
            tags=tags + ["agent"],
            capabilities=["llm", "agent"],
            versions=[_version("1.0.0", {"input": "any"},
                               {"output": "any"})],
            latest="1.0.0",
        ))
    return out


def _build_template_ops() -> List[OperatorDef]:
    """P3-6 / P3-6.5 / P4-3 / P4-4 / P4-6 templates surfaced as operators (10)."""
    items = [
        ("tpl_export", "Workflow export template (P3-6)", ["template", "export"]),
        ("tpl_pipeline", "Workflow pipeline template (P3-6)", ["template", "pipeline"]),
        ("tpl_multimodal", "Multi-modal template (P3-6)", ["template", "multimodal"]),
        ("tpl_feedback", "Feedback loop template (P3-6)", ["template", "feedback"]),
        ("tpl_memory_palace", "MemoryPalace read/write (P4-3)", ["template", "memory"]),
        ("tpl_lineage", "Lineage tracker (P4-4)", ["template", "lineage"]),
        ("tpl_director_story", "Director story template (P4-6)", ["template", "director"]),
        ("tpl_director_visual", "Director visual template (P4-6)", ["template", "director"]),
        ("tpl_director_assembly", "Director assembly template (P4-6)", ["template", "director"]),
        ("tpl_eval_suite", "Evaluation suite template (P3-6)", ["template", "eval"]),
    ]
    out: List[OperatorDef] = []
    for slug, label, tags in items:
        out.append(OperatorDef(
            id=f"op.template.{slug}",
            name=label, category="agent",
            description=f"{label} — workflow template wrapped as operator.",
            icon="📋", color="#7c3aed",
            tags=tags + ["template"],
            capabilities=["template", "orchestrate"],
            versions=[_version("1.0.0", {"input": "any"},
                               {"output": "any"})],
            latest="1.0.0",
        ))
    return out


# =====================================================================
# Registry singleton
# =====================================================================

class _Registry:
    """Thread-safe operator registry + search index."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[str, OperatorDef] = {}
        self._index: Dict[str, Set[str]] = defaultdict(set)  # term → op_id
        self._bootstrap()

    def _add(self, op: OperatorDef) -> None:
        self._items[op.id] = op
        tokens = self._tokenize(op)
        for t in tokens:
            self._index[t].add(op.id)

    def _tokenize(self, op: OperatorDef) -> Set[str]:
        blob = " ".join([
            op.id, op.name, op.description, op.category,
            " ".join(op.tags), " ".join(op.capabilities),
        ]).lower()
        return {t for t in re.split(r"[^a-z0-9]+", blob) if t}

    def _bootstrap(self) -> None:
        builders = [
            _build_cleaning,
            _build_cleaning_extra,
            _build_scoring,
            _build_annotation,
            _build_filter,
            _build_export,
            _build_evaluation,
            _build_evaluation_extra,
            _build_generator,
            _build_editor,
            _build_agent,
            _build_template_ops,
        ]
        for b in builders:
            for op in b():
                self._add(op)

    # ----- public -----
    def get(self, op_id: str) -> Optional[OperatorDef]:
        with self._lock:
            return self._items.get(op_id)

    def list(self, category: Optional[str] = None) -> List[OperatorDef]:
        with self._lock:
            items = list(self._items.values())
        if category:
            items = [o for o in items if o.category == category]
        return items

    def search(self, q: str, category: Optional[str] = None) -> List[OperatorDef]:
        with self._lock:
            ids: Set[str] = set()
            if not q:
                ids = set(self._items.keys())
            else:
                for tok in re.split(r"[^a-z0-9]+", q.lower()):
                    if tok:
                        ids |= self._index.get(tok, set())
            if category:
                items = [self._items[i] for i in ids
                         if self._items[i].category == category
                         and i in self._items]
            else:
                items = [self._items[i] for i in ids if i in self._items]
        items.sort(key=lambda o: (o.category, o.name))
        return items

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            per_cat: Dict[str, int] = {}
            for o in self._items.values():
                per_cat[o.category] = per_cat.get(o.category, 0) + 1
            return {
                "total": len(self._items),
                "per_category": per_cat,
                "categories": sorted(per_cat.keys()),
            }

    def schema(self, op_id: str) -> Optional[Dict[str, Any]]:
        op = self.get(op_id)
        if op is None:
            return None
        v = op.latest_version()
        return {
            "id": op.id,
            "name": op.name,
            "category": op.category,
            "version": v.version,
            "input_schema": v.input_schema,
            "output_schema": v.output_schema,
        }


_REGISTRY = _Registry()

# Public re-exports ------------------------------------------------------------
OPERATOR_REGISTRY: Dict[str, OperatorDef] = _REGISTRY._items  # for introspection


def get_operator(op_id: str) -> Optional[OperatorDef]:
    return _REGISTRY.get(op_id)


def list_operators(category: Optional[str] = None) -> List[OperatorDef]:
    return _REGISTRY.list(category=category)


def search_operators(q: str, category: Optional[str] = None) -> List[OperatorDef]:
    return _REGISTRY.search(q, category=category)


def market_summary() -> Dict[str, Any]:
    return _REGISTRY.summary()


def operator_schema(op_id: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.schema(op_id)


# Convenience alias for tests
SearchIndex = _Registry


__all__ = [
    "CATEGORIES",
    "OPERATOR_REGISTRY",
    "OperatorDef",
    "OperatorVersion",
    "SearchIndex",
    "get_operator",
    "list_operators",
    "search_operators",
    "market_summary",
    "operator_schema",
]
