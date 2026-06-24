"""annot.image.ocr_box — OCR text-detection (boxes + transcriptions) operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image,
                         'words'?: [{bbox, text, score}, ...],
                         'lines'?: [{bbox, words: [...]}, ...]}
    params:
        min_score: float = 0.3          — drop OCR words below this confidence
        min_box_area: int = 16          — drop boxes smaller than this
        iou_threshold: float = 0.0      — NMS within a line
        language: str = "auto"          — expected language hint
        min_text_length: int = 1        — drop empty/short transcriptions
        allowed_chars: str = ""         — empty=allow all; otherwise charset regex

Each word: {bbox:{x1,y1,x2,y2}, text:str, score?:float, polygon?:[[x,y],...]}.

Returns per-image: {image_index, ok, words_count, lines_count, words, lines}.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List

from .._image_utils import bbox_iou_xyxy


def _validate_word(w: Dict[str, Any]) -> Dict[str, Any]:
    bbox = w.get("bbox") or {}
    return {
        "id": w.get("id") or f"w_{uuid.uuid4().hex[:8]}",
        "bbox": {
            "x1": float(bbox.get("x1", 0)),
            "y1": float(bbox.get("y1", 0)),
            "x2": float(bbox.get("x2", 0)),
            "y2": float(bbox.get("y2", 0)),
        },
        "polygon": w.get("polygon"),
        "text": str(w.get("text", "")),
        "score": float(w.get("score", 1.0)),
    }


def _normalize_lines(lines: List[Dict[str, Any]], words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in lines:
        bbox = ln.get("bbox") or {}
        line = {
            "id": ln.get("id") or f"ln_{uuid.uuid4().hex[:8]}",
            "bbox": {
                "x1": float(bbox.get("x1", 0)),
                "y1": float(bbox.get("y1", 0)),
                "x2": float(bbox.get("x2", 0)),
                "y2": float(bbox.get("y2", 0)),
            },
            "text": str(ln.get("text", "")),
            "score": float(ln.get("score", 1.0)),
            "words": [_validate_word(w) for w in ln.get("words", []) or []],
        }
        out.append(line)
    return out


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_score = float(params.get("min_score", 0.3))
    min_area = int(params.get("min_box_area", 16))
    iou_thr = float(params.get("iou_threshold", 0.0))
    min_text = int(params.get("min_text_length", 1))
    allowed = str(params.get("allowed_chars", "")) or None

    charset_re = re.compile(f"[{re.escape(allowed)}]") if allowed else None

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"image_index": i}
        if not isinstance(item, dict):
            rec.update({"ok": False, "words": [], "lines": [],
                        "error": "input_must_be_dict"})
            out.append(rec)
            continue
        raw_words = [_validate_word(w) for w in item.get("words", []) or []]
        raw_lines = _normalize_lines(item.get("lines", []) or [], raw_words)

        # filter words
        def keep_word(w: Dict[str, Any]) -> bool:
            b = w["bbox"]
            area = max(0, b["x2"] - b["x1"]) * max(0, b["y2"] - b["y1"])
            if area < min_area:
                return False
            if w["score"] < min_score:
                return False
            if len(w["text"]) < min_text:
                return False
            if charset_re and w["text"] and not charset_re.search(w["text"]):
                return False
            return True

        words = [w for w in raw_words if keep_word(w)]
        # simple NMS within words
        if iou_thr > 0 and words:
            sorted_words = sorted(words, key=lambda w: w["score"], reverse=True)
            kept: List[Dict[str, Any]] = []
            while sorted_words:
                best = sorted_words.pop(0)
                kept.append(best)
                sorted_words = [
                    w for w in sorted_words
                    if bbox_iou_xyxy(best["bbox"], w["bbox"]) < iou_thr
                ]
            words = kept

        # filter lines
        lines: List[Dict[str, Any]] = []
        for ln in raw_lines:
            b = ln["bbox"]
            area = max(0, b["x2"] - b["x1"]) * max(0, b["y2"] - b["y1"])
            if area < min_area:
                continue
            if ln["score"] < min_score:
                continue
            ln["words"] = [w for w in ln["words"] if keep_word(w)]
            if len(ln["text"]) < min_text and not ln["words"]:
                continue
            lines.append(ln)

        rec.update({
            "ok": True,
            "words_count": len(words),
            "lines_count": len(lines),
            "words": words,
            "lines": lines,
        })
        out.append(rec)
    return out