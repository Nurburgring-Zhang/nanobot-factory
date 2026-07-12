"""P5-R1-T5: labels ontology endpoint (Task 5 quick wins).

Exposes:
  GET  /api/v1/labels/ontology                      — list industry ontologies
  GET  /api/v1/labels/ontology/{industry}           — single industry ontology
  GET  /api/v1/labels/ontology/{industry}/labels    — flat label list

The data is sourced from ``engines.annotation_quality.INDUSTRY_SCHEMAS`` plus
a built-in default taxonomy. Frontend ``Annotation.vue`` calls these to
populate its "任务标签 ontology" dropdown.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

try:
    from engines.annotation_quality import INDUSTRY_SCHEMAS
except ImportError:  # pragma: no cover — engine import is optional in tests
    INDUSTRY_SCHEMAS = {}

router = APIRouter(prefix="/api/v1/labels", tags=["labels-ontology"])

# Built-in label categories & default taxonomy (used when INDUSTRY_SCHEMAS
# is empty). Keeps the endpoint useful even when the engine module is not
# importable (e.g. minimal test env).
_DEFAULT_ONTOLOGY: Dict[str, Any] = {
    "general": {
        "name": "通用标注",
        "standard": "通用 / General",
        "schema": {
            "label": "string",
            "confidence": "0..1",
            "bbox": [0, 0, 0, 0],
            "polygon": [[0, 0]],
            "category": "object|text|action",
        },
        "labels": ["object", "text", "action", "scene", "attribute"],
    },
    "image_classification": {
        "name": "图像分类",
        "standard": "ImageNet / CIFAR",
        "schema": {"label": "string", "top_k": [0.0]},
        "labels": ["animal", "vehicle", "food", "scene", "object", "person", "plant", "building"],
    },
    "object_detection": {
        "name": "目标检测",
        "standard": "COCO",
        "schema": {
            "bbox": [0, 0, 0, 0],
            "category": "string",
            "score": 0.0,
        },
        "labels": ["person", "vehicle", "animal", "furniture", "food", "electronics", "tool", "sport"],
    },
    "image_segmentation": {
        "name": "图像分割",
        "standard": "COCO-Stuff / ADE20K",
        "schema": {"mask": "rle_or_polygon", "category": "string"},
        "labels": ["sky", "building", "road", "vegetation", "person", "car", "animal", "object"],
    },
    "text_ner": {
        "name": "命名实体识别",
        "standard": "CoNLL-2003 / OntoNotes",
        "schema": {"text": "string", "entities": [{"start": 0, "end": 0, "type": "PER|ORG|LOC|MISC"}]},
        "labels": ["PER", "ORG", "LOC", "MISC", "DATE", "TIME", "MONEY", "PERCENT"],
    },
    "text_classification": {
        "name": "文本分类",
        "standard": "GLUE / SuperGLUE",
        "schema": {"text": "string", "label": "string", "score": 0.0},
        "labels": ["positive", "negative", "neutral", "spam", "ham", "toxic", "safe"],
    },
    "ocr": {
        "name": "OCR 转写",
        "standard": "ICDAR / TextVQA",
        "schema": {"text": "string", "bbox": [0, 0, 0, 0], "language": "zh|en|ja"},
        "labels": ["text", "handwriting", "number", "symbol", "table_cell"],
    },
}


def _build_ontology() -> Dict[str, Any]:
    """Merge INDUSTRY_SCHEMAS + default taxonomy into a single {industry: def} map."""
    out: Dict[str, Any] = {}
    for ind, meta in (INDUSTRY_SCHEMAS or {}).items():
        out[ind] = {
            "name": meta.get("name", ind),
            "standard": meta.get("standard", ""),
            "schema": meta.get("schema", {}),
            "labels": _extract_labels(meta.get("schema", {})),
        }
    for ind, meta in _DEFAULT_ONTOLOGY.items():
        if ind not in out:
            out[ind] = meta
    return out


def _extract_labels(schema: Any) -> List[str]:
    """Walk the schema tree and pull out enum-like string values as labels."""
    labels: List[str] = []
    seen = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        elif isinstance(node, str):
            # Heuristic: pick strings that look like enum values: "a|b|c" or
            # value-name patterns (no spaces, no parentheses).
            if "|" in node:
                for part in node.split("|"):
                    part = part.strip()
                    if part and len(part) < 40 and " " not in part and part not in seen:
                        labels.append(part)
                        seen.add(part)
            elif node.startswith("$") or node.endswith("_"):
                return
            elif (
                len(node) < 40
                and " " not in node
                and any(ch.isalpha() for ch in node)
                and not node[0].isdigit()
                and node not in seen
            ):
                labels.append(node)
                seen.add(node)

    _walk(schema)
    return labels


_ONTO = _build_ontology()


@router.get("/ontology")
async def list_ontology(
    q: str | None = Query(None, max_length=200, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List all label ontologies (industries + general taxonomy)."""
    items: List[Dict[str, Any]] = []
    for ind, meta in _ONTO.items():
        items.append({
            "industry": ind,
            "name": meta.get("name", ind),
            "standard": meta.get("standard", ""),
            "label_count": len(meta.get("labels", [])),
        })
    if q:
        ql = q.lower()
        items = [it for it in items if ql in it["industry"].lower() or ql in (it.get("name") or "").lower()]
    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "count": total,
        "industries": page,
        "limit": limit,
        "offset": offset,
    }


@router.get("/ontology/{industry}")
async def get_ontology(industry: str) -> Dict[str, Any]:
    if industry not in _ONTO:
        raise HTTPException(status_code=404, detail=f"ontology_not_found: {industry}")
    meta = _ONTO[industry]
    return {
        "success": True,
        "industry": industry,
        "name": meta.get("name", industry),
        "standard": meta.get("standard", ""),
        "schema": meta.get("schema", {}),
        "labels": meta.get("labels", []),
    }


@router.get("/ontology/{industry}/labels")
async def get_ontology_labels(industry: str) -> Dict[str, Any]:
    if industry not in _ONTO:
        raise HTTPException(status_code=404, detail=f"ontology_not_found: {industry}")
    labels = _ONTO[industry].get("labels", [])
    return {
        "success": True,
        "industry": industry,
        "count": len(labels),
        "labels": labels,
    }