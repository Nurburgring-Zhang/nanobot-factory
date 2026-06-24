"""annot.video.video_caption — video captioning operator.

Inputs:
    items: list of dicts {video_id, captions: [str], metadata?: {...}}
    params:
        min_words: int = 1
        max_words: int = 500
        language: str = "auto"
        multi_caption: bool = False       — accept multiple captions and rank
        templates: list = []

Returns per-item: {item_index, ok, captions, top_caption, word_count, language}.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_HTML_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s).strip()


def _lang_detect(s: str) -> str:
    if not s:
        return "unknown"
    cjk = len(_CJK_RE.findall(s))
    ratio = cjk / max(1, len(s))
    if ratio > 0.3:
        return "zh"
    if re.search(r"[a-zA-Z]", s):
        return "en"
    return "other"


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_w = int(params.get("min_words", 1))
    max_w = int(params.get("max_words", 500))
    lang_target = str(params.get("language", "auto"))
    multi = bool(params.get("multi_caption", False))
    templates = list(params.get("templates") or [])

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"item_index": i}
        if not isinstance(item, dict):
            rec.update({"ok": False, "captions": [],
                        "error": "input_must_be_dict"})
            out.append(rec)
            continue
        caps_raw = item.get("captions") or []
        if isinstance(caps_raw, str):
            caps_raw = [caps_raw]
        cleaned: List[str] = []
        for c in caps_raw:
            c = _strip_html(str(c))
            for t in templates:
                if isinstance(t, str) and "{caption}" in t:
                    c = t.format(caption=c).strip()
                    break
            cleaned.append(c)
        cleaned = [c for c in cleaned if min_w <= len(c.split()) <= max_w]
        cleaned = [
            c for c in cleaned
            if lang_target == "auto" or _lang_detect(c) == lang_target
        ]
        top = cleaned[0] if cleaned else ""
        rec.update({
            "ok": bool(cleaned),
            "video_id": item.get("video_id"),
            "captions": cleaned if multi else ([top] if top else []),
            "top_caption": top,
            "word_count": len(top.split()) if top else 0,
            "language": _lang_detect(top) if top else "unknown",
        })
        out.append(rec)
    return out