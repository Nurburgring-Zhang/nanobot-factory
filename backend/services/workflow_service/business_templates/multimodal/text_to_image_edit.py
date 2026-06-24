"""P3-6.5-W2: Hybrid Multimodal — Text-guided Image Edit.

Source image + edit instruction -> optional mask -> instruction-based
edit -> quality score -> side-by-side manifest export.

Category: multimodal
Improvements over ``tpl-biz-mm-002``:
  * Edit-type routing (replace/insert/remove/style/global)
  * Per-region confidence (only modify masked area)
  * Side-by-side comparison report
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._helpers import _n, _meta


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-biz-mm-h02",
    "category": "multimodal",
    "name": "Text-guided Image Edit Pipeline (Hybrid)",
    "tags": ["edit", "instruction-edit", "imagen-editor", "edit-routing"],
    "description": (
        "Source image + edit instruction -> edit-type routing "
        "(replace/insert/remove/style/global) -> per-region mask -> "
        "instruction edit -> per-region quality score -> "
        "side-by-side manifest + comparison report."
    ),
    "version": "1.1.0",
    **_meta(
        inputs={
            "image_source": {"type": "object", "required": True,
                              "description": "URI or dataset ref"},
            "instructions": {"type": "array<object>", "required": True,
                              "description": "[{text, region, type, "
                                             "strength}]"},
            "editor_model": {"type": "string",
                              "default": "instructpix2pix"},
            "default_strength": {"type": "float", "default": 0.7,
                                   "min": 0.0, "max": 1.0},
            "min_edit_quality": {"type": "float", "default": 0.5,
                                  "min": 0.0, "max": 1.0},
            "oss_bucket": {"type": "string", "default": "edit-out"},
        },
        outputs=["edited/*.jpg", "manifest.jsonl",
                 "side_by_side/*.jpg", "stats.json"],
        steps=[
            {"id": "ld", "name": "Load Source Images",
             "operator": "collection.load_images",
             "config": {"source": "$inputs.image_source"}},
            {"id": "rt", "name": "Edit-Type Routing",
             "operator": "annotation.edit_route",
             "config": {"types": ["replace", "insert", "remove",
                                   "style", "global"]}},
            {"id": "mk", "name": "Per-Region Mask",
             "operator": "preprocessing.region_mask"},
            {"id": "ed", "name": "Instruction Edit",
             "operator": "generation.instruction_edit",
             "config": {"model": "$inputs.editor_model",
                        "default_strength":
                            "$inputs.default_strength"}},
            {"id": "sc", "name": "Per-Region Quality Score",
             "operator": "scoring.edit_quality",
             "config": {"min": "$inputs.min_edit_quality"}},
            {"id": "sx", "name": "Side-by-side Render",
             "operator": "postprocessing.side_by_side"},
            {"id": "wr", "name": "Manifest Export",
             "operator": "export.write_edit_manifest"},
            {"id": "up", "name": "OSS Upload",
             "operator": "oss.upload",
             "config": {"bucket": "$inputs.oss_bucket"},
             "depends_on": ["sc", "sx"]},
        ],
        metrics=["inputs", "edited", "by_edit_type",
                 "avg_quality", "duration_seconds"],
    ),
    "nodes": [_n("ld", "load_images", "collection"),
              _n("rt", "edit_route", "annotation", "ld"),
              _n("mk", "region_mask", "preprocessing", "rt"),
              _n("ed", "instruction_edit", "generation", "mk"),
              _n("sc", "edit_quality", "scoring", "ed"),
              _n("sx", "side_by_side", "postprocessing", "ed"),
              _n("wr", "manifest_export", "export", "sc", "sx"),
              _n("up", "oss_upload", "export", "wr")],
}