"""P3-6-W2: 5 multimodal special-flow templates.

These templates compose multiple generation models into cross-modal
pipelines that don't fit the standard "collect -> annotate -> export"
shape:

  * Image-to-Video (text -> image -> animate)
  * Text-guided image edit
  * Character consistency multi-image training
  * Style transfer dataset
  * Picture book generation
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._helpers import _n, _meta


_MULTIMODAL_TEMPLATES: List[Dict[str, Any]] = [

    # ---- 1. Image-to-Video -----------------------------------------
    {"id": "tpl-biz-mm-001", "category": "multimodal",
     "name": "Image-to-Video Pipeline",
     "tags": ["i2v", "text2img", "animate"],
     "description": ("Text prompt -> text-to-image -> image-to-video "
                     "animation, with optional caption overlay and "
                     "OSS export."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "prompts": {"type": "array<string>", "required": True,
                          "description": "List of text prompts"},
             "t2i_model": {"type": "string",
                            "default": "sdxl-1.0"},
             "i2v_model": {"type": "string",
                            "default": "stable-video-diffusion"},
             "fps": {"type": "int", "default": 8},
             "duration_sec": {"type": "float", "default": 4.0},
             "oss_bucket": {"type": "string", "default": "i2v-out"},
         },
         outputs=["videos/*.mp4", "frames/*.jpg", "manifest.json"],
         steps=[
             {"id": "t2i", "name": "Text-to-Image",
              "operator": "generation.text_to_image",
              "config": {"model": "$inputs.t2i_model",
                         "prompts": "$inputs.prompts"}},
             {"id": "q1", "name": "Quality Filter",
              "operator": "cleaning.aesthetic_filter",
              "config": {"min": 5.0}},
             {"id": "i2v", "name": "Image-to-Video",
              "operator": "video_generation.image_to_video",
              "config": {"model": "$inputs.i2v_model",
                         "fps": "$inputs.fps",
                         "duration_sec": "$inputs.duration_sec"}},
             {"id": "cap", "name": "Caption Overlay",
              "operator": "postprocessing.caption_overlay"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["prompts", "images", "videos",
                  "avg_duration", "duration_seconds"],
     ),
     "nodes": [_n("t2i", "text_to_image", "generation"),
               _n("q1", "quality_filter", "cleaning", "t2i"),
               _n("i2v", "image_to_video", "video_generation", "q1"),
               _n("cap", "caption_overlay", "postprocessing", "i2v"),
               _n("up", "oss_upload", "export", "cap")]},

    # ---- 2. Text-guided image edit ---------------------------------
    {"id": "tpl-biz-mm-002", "category": "multimodal",
     "name": "Text-guided Image Edit Pipeline",
     "tags": ["edit", "instruction-edit", "imagen-editor"],
     "description": ("Source image + edit instruction -> mask + "
                     "instruction edit -> quality score -> side-by-side "
                     "manifest export."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "image_source": {"type": "object", "required": True,
                               "description": "URI or dataset ref"},
             "instructions": {"type": "array<string>", "required": True},
             "editor_model": {"type": "string",
                               "default": "instructpix2pix"},
             "strength": {"type": "float", "default": 0.7,
                           "min": 0.0, "max": 1.0},
             "oss_bucket": {"type": "string", "default": "edit-out"},
         },
         outputs=["edited/*.jpg", "manifest.jsonl", "stats.json"],
         steps=[
             {"id": "ld", "name": "Load Source Images",
              "operator": "collection.load_images",
              "config": {"source": "$inputs.image_source"}},
             {"id": "mk", "name": "Auto Mask (optional)",
              "operator": "preprocessing.auto_mask"},
             {"id": "ed", "name": "Instruction Edit",
              "operator": "generation.instruction_edit",
              "config": {"model": "$inputs.editor_model",
                         "instructions": "$inputs.instructions",
                         "strength": "$inputs.strength"}},
             {"id": "sc", "name": "Edit Quality Score",
              "operator": "scoring.edit_quality"},
             {"id": "wr", "name": "Side-by-side Manifest",
              "operator": "export.write_edit_manifest"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["inputs", "edited", "avg_quality",
                  "duration_seconds"],
     ),
     "nodes": [_n("ld", "load_images", "collection"),
               _n("mk", "auto_mask", "preprocessing", "ld"),
               _n("ed", "instruction_edit", "generation", "mk"),
               _n("sc", "edit_quality", "scoring", "ed"),
               _n("wr", "manifest_export", "export", "sc"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 3. Character consistency multi-image ----------------------
    {"id": "tpl-biz-mm-003", "category": "multimodal",
     "name": "Character Consistency Training Pipeline",
     "tags": ["character", "consistency", "ip-adapter",
              "dreambooth"],
     "description": ("Multi-image character dataset: collect character "
                     "shots -> face/pose detect -> dedup -> caption "
                     "per shot -> LoRA/DreamBooth export."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "character_name": {"type": "string", "required": True},
             "image_sources": {"type": "array<object>", "required": True},
             "trigger_token": {"type": "string", "default": "sks"},
             "min_shots": {"type": "int", "default": 20},
             "oss_bucket": {"type": "string", "default": "char-data"},
         },
         outputs=["lora_train_data/", "captions.txt",
                  "trigger_token.txt", "stats.json"],
         steps=[
             {"id": "col", "name": "Character Shots Collect",
              "operator": "collection.character_source",
              "config": {"name": "$inputs.character_name",
                         "sources": "$inputs.image_sources"}},
             {"id": "fd", "name": "Face + Pose Detect",
              "operator": "preprocessing.character_detect"},
             {"id": "dd", "name": "Dedup (CLIP embedding)",
              "operator": "cleaning.clip_dedup"},
             {"id": "cg", "name": "Caption Per Shot",
              "operator": "annotation.vlm_caption"},
             {"id": "tk", "name": "Top-K Selection",
              "operator": "dataset.topk",
              "config": {"k": "$inputs.min_shots"}},
             {"id": "wr", "name": "LoRA Export",
              "operator": "export.write_lora_dataset",
              "config": {"trigger_token": "$inputs.trigger_token"}},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["shots", "after_dedup", "after_quality",
                  "lora_rows", "duration_seconds"],
     ),
     "nodes": [_n("col", "character_collect", "collection"),
               _n("fd", "face_pose_detect", "preprocessing", "col"),
               _n("dd", "clip_dedup", "cleaning", "fd"),
               _n("cg", "vlm_caption", "annotation", "dd"),
               _n("tk", "topk_select", "dataset", "cg"),
               _n("wr", "lora_export", "export", "tk"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 4. Style transfer dataset ---------------------------------
    {"id": "tpl-biz-mm-004", "category": "multimodal",
     "name": "Style Transfer Dataset Pipeline",
     "tags": ["style", "transfer", "aesthetic"],
     "description": ("Collect style + content images -> style embedding "
                     "-> paired train data (content|content+style) -> "
                     "Alpaca-style instruction export."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "content_sources": {"type": "array<object>", "required": True},
             "style_sources": {"type": "array<object>", "required": True},
             "style_model": {"type": "string",
                              "default": "vit-style-encoder"},
             "min_style_score": {"type": "float", "default": 0.6},
             "oss_bucket": {"type": "string", "default": "style-data"},
         },
         outputs=["alpaca.jsonl", "pairs.jsonl", "stats.json"],
         steps=[
             {"id": "ic", "name": "Content Collect",
              "operator": "collection.image_source",
              "config": {"sources": "$inputs.content_sources"}},
             {"id": "sc", "name": "Style Collect",
              "operator": "collection.image_source",
              "config": {"sources": "$inputs.style_sources"}},
             {"id": "emb", "name": "Style Embedding",
              "operator": "scoring.style_embed",
              "config": {"model": "$inputs.style_model"}},
             {"id": "pr", "name": "Pair (content, style)",
              "operator": "dataset.style_pair",
              "config": {"min_style_score": "$inputs.min_style_score"}},
             {"id": "wr", "name": "Instruction Export",
              "operator": "format.alpaca_style_export"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["content", "styles", "pairs",
                  "alpaca_rows", "duration_seconds"],
     ),
     "nodes": [_n("ic", "content_collect", "collection"),
               _n("sc", "style_collect", "collection"),
               _n("em", "style_embed", "scoring", "sc"),
               _n("pr", "style_pair", "dataset", "ic", "em"),
               _n("wr", "instruction_export", "export", "pr"),
               _n("up", "oss_upload", "export", "wr")]},

    # ---- 5. Picture book generation --------------------------------
    {"id": "tpl-biz-mm-005", "category": "multimodal",
     "name": "Picture Book Generation Pipeline",
     "tags": ["picture-book", "story", "illustration", "tts"],
     "description": ("Story text -> page split -> per-page illustration "
                     "(T2I) -> per-page TTS -> book PDF export."),
     "version": "1.0.0",
     **_meta(
         inputs={
             "story_id": {"type": "string", "required": True},
             "illustration_model": {"type": "string",
                                      "default": "sdxl-1.0"},
             "tts_model": {"type": "string", "default": "cosyvoice"},
             "style": {"type": "string", "default": "watercolor"},
             "oss_bucket": {"type": "string", "default": "picturebook"},
         },
         outputs=["book.pdf", "pages/*.jpg", "audio/*.wav",
                  "manifest.json"],
         steps=[
             {"id": "st", "name": "Story Split to Pages",
              "operator": "scripting.page_split",
              "config": {"story_id": "$inputs.story_id"}},
             {"id": "t2i", "name": "Per-Page Illustration",
              "operator": "generation.text_to_image",
              "config": {"model": "$inputs.illustration_model",
                         "style": "$inputs.style"}},
             {"id": "tts", "name": "Per-Page TTS",
              "operator": "audio.tts",
              "config": {"model": "$inputs.tts_model"}},
             {"id": "qa", "name": "Page Quality Review",
              "operator": "annotation.review"},
             {"id": "pdf", "name": "Book PDF Compose",
              "operator": "export.compose_picturebook"},
             {"id": "up", "name": "OSS Upload",
              "operator": "oss.upload",
              "config": {"bucket": "$inputs.oss_bucket"}},
         ],
         metrics=["pages", "illustrations", "audio",
                  "approved", "duration_seconds"],
     ),
     "nodes": [_n("st", "story_split", "scripting"),
               _n("t2i", "page_illustration", "generation", "st"),
               _n("tts", "page_tts", "audio", "st"),
               _n("qa", "page_review", "review", "t2i", "tts"),
               _n("pdf", "compose_pdf", "export", "qa"),
               _n("up", "oss_upload", "export", "pdf")]},
]


__all__ = ["_MULTIMODAL_TEMPLATES"]