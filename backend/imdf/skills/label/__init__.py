"""imdf.skills.label — 17 multimodal labeling skills.

Each ``label_<name>`` module exposes one async function with signature::

    async def label_<name>(input: SkillInput) -> SkillOutput

The skills fall back to a deterministic offline mock whenever the upstream
service is unreachable (no internet, API error, or ``LABEL_OFFLINE=1``).

Registry contents:

| skill_id                  | category | trigger                |
|---------------------------|----------|------------------------|
| label_clip_zero           | classify | zero-shot CLIP         |
| label_clip_multi          | classify | multi-label CLIP       |
| label_blip_caption        | caption  | BLIP image captioning  |
| label_blip2_vqa           | vqa      | BLIP-2 visual QA       |
| label_llava_chat          | chat     | LLaVA multimodal chat  |
| label_gpt4v_label         | label    | GPT-4V labeling        |
| label_qwen_vl             | label    | Qwen-VL labeling       |
| label_glm4v               | label    | GLM-4V labeling        |
| label_yolo_detect         | detect   | YOLO object detection  |
| label_sam_segment         | segment  | SAM segmentation       |
| label_depth_estimate      | depth    | monocular depth        |
| label_pose_detect         | pose     | human pose estimation  |
| label_ocr_text            | ocr      | OCR text recognition   |
| label_asr_transcribe      | asr      | ASR transcription      |
| label_sentiment           | nlp      | sentiment analysis     |
| label_entity_ner          | nlp      | named entity recog.    |
| label_keyword_extract     | nlp      | keyword extraction     |

Public API:
    from backend.imdf.skills.label import (
        LABEL_SKILLS, list_label_skills, get_label_skill, run_label_skill,
        # direct access to handlers:
        label_clip_zero, label_clip_multi, label_blip_caption, label_blip2_vqa,
        label_llava_chat, label_gpt4v_label, label_qwen_vl, label_glm4v,
        label_yolo_detect, label_sam_segment, label_depth_estimate,
        label_pose_detect, label_ocr_text, label_asr_transcribe,
        label_sentiment, label_entity_ner, label_keyword_extract,
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

from backend.skills import SkillInput, SkillOutput

from ._base import NETWORK_OK, LabelBaseOutput, build_output
from .label_asr_transcribe import AsrTranscribeInput, label_asr_transcribe
from .label_blip2_vqa import Blip2VqaInput, label_blip2_vqa
from .label_blip_caption import BlipCaptionInput, label_blip_caption
from .label_clip_multi import ClipMultiInput, label_clip_multi
from .label_clip_zero import ClipZeroInput, label_clip_zero
from .label_depth_estimate import DepthEstimateInput, label_depth_estimate
from .label_entity_ner import EntityNerInput, label_entity_ner
from .label_glm4v import Glm4VInput, label_glm4v
from .label_gpt4v_label import Gpt4VLabelInput, label_gpt4v_label
from .label_keyword_extract import KeywordExtractInput, label_keyword_extract
from .label_llava_chat import LlavaChatInput, TurnModel, label_llava_chat
from .label_ocr_text import OcrTextInput, label_ocr_text
from .label_pose_detect import PoseDetectInput, label_pose_detect
from .label_qwen_vl import QwenVlInput, label_qwen_vl
from .label_sam_segment import SamSegmentInput, label_sam_segment
from .label_sentiment import SentimentInput, label_sentiment
from .label_yolo_detect import YoloDetectInput, label_yolo_detect


# ---------------------------------------------------------------------------
# SkillSpec — typed metadata per skill
# ---------------------------------------------------------------------------
@dataclass
class LabelSkillSpec:
    skill_id: str
    name: str
    category: str
    handler: Callable[[SkillInput], Awaitable[SkillOutput]]
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    trigger_phrases: List[str] = field(default_factory=list)
    inputs_schema: Dict[str, Any] = field(default_factory=dict)
    outputs_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "trigger_phrases": list(self.trigger_phrases),
            "inputs_schema": dict(self.inputs_schema),
            "outputs_schema": dict(self.outputs_schema),
            "dependencies": list(self.dependencies),
        }


def _spec(
    skill_id: str,
    name: str,
    category: str,
    handler: Callable[[SkillInput], Awaitable[SkillOutput]],
    *,
    description: str = "",
    trigger: List[str] = None,
    inputs: Dict[str, Any] = None,
    outputs: Dict[str, Any] = None,
    deps: List[str] = None,
    version: str = "1.0.0",
) -> LabelSkillSpec:
    return LabelSkillSpec(
        skill_id=skill_id, name=name, category=category,
        handler=handler, description=description,
        version=version, enabled=True,
        trigger_phrases=list(trigger or []),
        inputs_schema=dict(inputs or {}),
        outputs_schema=dict(outputs or {}),
        dependencies=list(deps or []),
    )


# Common input/output schema fragments used by most skills
_IMG_INPUT = {"image": {"type": "string", "description": "Image URL or local path"}}
_ENVELOPE = {
    "timestamp": {"type": "string"},
    "source": {"type": "string", "enum": ["label", "live", "mock"]},
    "confidence": {"type": "number"},
    "elapsed_ms": {"type": "number"},
}


LABEL_SKILLS: List[LabelSkillSpec] = [
    _spec("label_clip_zero", "CLIP Zero-Shot", "classify",
          label_clip_zero,
          description="CLIP zero-shot image classification — pick the best candidate label.",
          trigger=["clip", "zero-shot", "image classify", "clip zero"],
          inputs={**_IMG_INPUT, "candidates": {"type": "array", "minItems": 2},
                  "top_k": {"type": "integer"}, "model": {"type": "string"}},
          outputs={"label": {"type": "string"}, "score": {"type": "number"},
                   "scores": {"type": "object"}, "top_k": {"type": "array"}},
          deps=["backend.imdf.skills.label.label_clip_zero"]),
    _spec("label_clip_multi", "CLIP Multi-Label", "classify",
          label_clip_multi,
          description="CLIP multi-label classification — independent sigmoid scores per label.",
          trigger=["clip multi", "multi-label", "clip 多标签"],
          inputs={**_IMG_INPUT, "candidates": {"type": "array", "minItems": 2},
                  "threshold": {"type": "number"}, "model": {"type": "string"}},
          outputs={"scores": {"type": "object"}, "selected": {"type": "array"},
                   "threshold": {"type": "number"}},
          deps=["backend.imdf.skills.label.label_clip_multi"]),
    _spec("label_blip_caption", "BLIP Caption", "caption",
          label_blip_caption,
          description="BLIP image captioning with style control.",
          trigger=["blip", "caption", "image caption"],
          inputs={**_IMG_INPUT, "max_length": {"type": "integer"},
                  "style": {"type": "string", "enum": ["factual", "romantic", "humorous", "poetic"]}},
          outputs={"caption": {"type": "string"}, "style": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_blip_caption"]),
    _spec("label_blip2_vqa", "BLIP-2 VQA", "vqa",
          label_blip2_vqa,
          description="BLIP-2 visual question answering.",
          trigger=["blip2", "vqa", "visual qa", "ask image"],
          inputs={**_IMG_INPUT, "question": {"type": "string"},
                  "max_new_tokens": {"type": "integer"}},
          outputs={"answer": {"type": "string"}, "question": {"type": "string"},
                   "confidence": {"type": "number"}},
          deps=["backend.imdf.skills.label.label_blip2_vqa"]),
    _spec("label_llava_chat", "LLaVA Chat", "chat",
          label_llava_chat,
          description="LLaVA multi-turn multimodal chat.",
          trigger=["llava", "multimodal chat", "llava 对话"],
          inputs={"turns": {"type": "array"}, "max_new_tokens": {"type": "integer"},
                  "temperature": {"type": "number"}},
          outputs={"reply": {"type": "string"}, "turns": {"type": "array"}},
          deps=["backend.imdf.skills.label.label_llava_chat"]),
    _spec("label_gpt4v_label", "GPT-4V Label", "label",
          label_gpt4v_label,
          description="OpenAI GPT-4V multimodal labeling (caption + tags + JSON schema).",
          trigger=["gpt-4v", "gpt4v", "openai vision", "gpt vision"],
          inputs={**_IMG_INPUT, "prompt": {"type": "string"},
                  "schema": {"type": "object"}, "max_tokens": {"type": "integer"}},
          outputs={"caption": {"type": "string"}, "tags": {"type": "array"},
                   "structured": {"type": "object"}},
          deps=["backend.imdf.skills.label.label_gpt4v_label", "openai"]),
    _spec("label_qwen_vl", "Qwen-VL Label", "label",
          label_qwen_vl,
          description="Alibaba Qwen-VL bilingual captioning + tagging.",
          trigger=["qwen", "qwen-vl", "通义千问"],
          inputs={**_IMG_INPUT, "prompt": {"type": "string"},
                  "lang": {"type": "string", "enum": ["en", "zh"]},
                  "max_tokens": {"type": "integer"}},
          outputs={"caption": {"type": "string"}, "tags": {"type": "array"},
                   "lang": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_qwen_vl"]),
    _spec("label_glm4v", "GLM-4V Label", "label",
          label_glm4v,
          description="Zhipu GLM-4V multimodal labeling (caption / classify / extract).",
          trigger=["glm", "glm-4v", "zhipu", "智谱"],
          inputs={**_IMG_INPUT, "task": {"type": "string", "enum": ["caption", "classify", "extract"]},
                  "prompt": {"type": "string"}, "options": {"type": "array"},
                  "lang": {"type": "string"}},
          outputs={"task": {"type": "string"}, "result": {}, "lang": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_glm4v"]),
    _spec("label_yolo_detect", "YOLO Detect", "detect",
          label_yolo_detect,
          description="YOLO object detection with bounding boxes.",
          trigger=["yolo", "object detect", "目标检测"],
          inputs={**_IMG_INPUT, "classes": {"type": "array"},
                  "conf_threshold": {"type": "number"}},
          outputs={"boxes": {"type": "array"}, "count": {"type": "integer"}},
          deps=["backend.imdf.skills.label.label_yolo_detect"]),
    _spec("label_sam_segment", "SAM Segment", "segment",
          label_sam_segment,
          description="SAM (Segment Anything) — box / point / auto segmentation masks.",
          trigger=["sam", "segment", "分割"],
          inputs={**_IMG_INPUT, "boxes": {"type": "array"},
                  "points": {"type": "array"},
                  "mode": {"type": "string", "enum": ["auto", "box", "point"]}},
          outputs={"masks": {"type": "array"}, "count": {"type": "integer"},
                   "mode": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_sam_segment"]),
    _spec("label_depth_estimate", "Depth Estimate", "depth",
          label_depth_estimate,
          description="Monocular depth estimation with summary statistics.",
          trigger=["depth", "midas", "深度估计"],
          inputs={**_IMG_INPUT, "max_depth": {"type": "number"},
                  "normalize": {"type": "boolean"}, "sample_size": {"type": "integer"}},
          outputs={"depth_map": {"type": "array"}, "stats": {"type": "object"},
                   "shape": {"type": "array"}},
          deps=["backend.imdf.skills.label.label_depth_estimate"]),
    _spec("label_pose_detect", "Pose Detect", "pose",
          label_pose_detect,
          description="Human pose estimation (COCO 17 / Body 18 / Body 25).",
          trigger=["pose", "openpose", "姿态估计", "骨架"],
          inputs={**_IMG_INPUT, "format": {"type": "string"},
                  "max_people": {"type": "integer"}},
          outputs={"poses": {"type": "array"}, "count": {"type": "integer"},
                   "format": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_pose_detect"]),
    _spec("label_ocr_text", "OCR Text", "ocr",
          label_ocr_text,
          description="OCR text recognition with per-region bounding boxes.",
          trigger=["ocr", "text recognition", "文字识别"],
          inputs={**_IMG_INPUT, "lang": {"type": "string"},
                  "detect_orientation": {"type": "boolean"}},
          outputs={"text": {"type": "string"}, "regions": {"type": "array"},
                   "lang": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_ocr_text"]),
    _spec("label_asr_transcribe", "ASR Transcribe", "asr",
          label_asr_transcribe,
          description="ASR speech-to-text transcription with optional timestamps.",
          trigger=["asr", "whisper", "speech to text", "语音转写"],
          inputs={"audio": {"type": "string"}, "lang": {"type": "string"},
                  "timestamps": {"type": "boolean"}},
          outputs={"text": {"type": "string"}, "segments": {"type": "array"},
                   "lang": {"type": "string"}},
          deps=["backend.imdf.skills.label.label_asr_transcribe"]),
    _spec("label_sentiment", "Sentiment", "nlp",
          label_sentiment,
          description="Sentiment analysis (positive/neutral/negative).",
          trigger=["sentiment", "情感分析", "polarity"],
          inputs={"text": {"type": "string"},
                  "granularity": {"type": "string", "enum": ["sentence", "paragraph", "document"]},
                  "lang": {"type": "string"}},
          outputs={"label": {"type": "string"}, "score": {"type": "number"},
                   "sentences": {"type": "array"}},
          deps=["backend.imdf.skills.label.label_sentiment"]),
    _spec("label_entity_ner", "Entity NER", "nlp",
          label_entity_ner,
          description="Named entity recognition with type filtering.",
          trigger=["ner", "entity", "命名实体"],
          inputs={"text": {"type": "string"}, "types": {"type": "array"},
                  "lang": {"type": "string"}},
          outputs={"entities": {"type": "array"}, "count": {"type": "integer"},
                   "types": {"type": "array"}},
          deps=["backend.imdf.skills.label.label_entity_ner"]),
    _spec("label_keyword_extract", "Keyword Extract", "nlp",
          label_keyword_extract,
          description="Keyword and keyphrase extraction.",
          trigger=["keyword", "extract keywords", "关键词提取"],
          inputs={"text": {"type": "string"}, "top_k": {"type": "integer"},
                  "min_length": {"type": "integer"}, "lang": {"type": "string"}},
          outputs={"keywords": {"type": "array"}, "keyphrases": {"type": "array"},
                   "count": {"type": "integer"}},
          deps=["backend.imdf.skills.label.label_keyword_extract"]),
]


_BY_ID: Dict[str, LabelSkillSpec] = {s.skill_id: s for s in LABEL_SKILLS}


def list_label_skills() -> List[LabelSkillSpec]:
    """Return all 17 label skills."""
    return list(LABEL_SKILLS)


def get_label_skill(skill_id: str) -> LabelSkillSpec:
    """Look up a skill by id; raises KeyError if missing."""
    if skill_id not in _BY_ID:
        raise KeyError(f"label skill not found: {skill_id}")
    return _BY_ID[skill_id]


async def run_label_skill(skill_id: str, input: SkillInput) -> SkillOutput:
    """Dispatch a call to the requested label skill and return its output."""
    if skill_id not in _BY_ID:
        return build_output(
            success=False, error=f"unknown label skill: {skill_id}", source="label",
        )
    return await _BY_ID[skill_id].handler(input)


__all__ = [
    # re-exports — base utilities
    "NETWORK_OK",
    "LabelBaseOutput",
    # re-exports — Pydantic input models
    "ClipZeroInput", "ClipMultiInput",
    "BlipCaptionInput", "Blip2VqaInput", "LlavaChatInput", "TurnModel",
    "Gpt4VLabelInput", "QwenVlInput", "Glm4VInput",
    "YoloDetectInput", "SamSegmentInput", "DepthEstimateInput", "PoseDetectInput",
    "OcrTextInput", "AsrTranscribeInput",
    "SentimentInput", "EntityNerInput", "KeywordExtractInput",
    # re-exports — handlers
    "label_clip_zero", "label_clip_multi",
    "label_blip_caption", "label_blip2_vqa", "label_llava_chat",
    "label_gpt4v_label", "label_qwen_vl", "label_glm4v",
    "label_yolo_detect", "label_sam_segment", "label_depth_estimate", "label_pose_detect",
    "label_ocr_text", "label_asr_transcribe",
    "label_sentiment", "label_entity_ner", "label_keyword_extract",
    # registry
    "LabelSkillSpec", "LABEL_SKILLS",
    "list_label_skills", "get_label_skill", "run_label_skill",
]