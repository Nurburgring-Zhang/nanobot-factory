"""annot.image.caption — image captioning / description operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'caption'?: str, 'captions'?: [str]}
    params:
        min_words: int = 1
        max_words: int = 200
        min_chars: int = 1
        language: str = "auto"        — zh | en | auto
        strip_html: bool = True
        templates: list = []          — caption templates

Returns per-image: {image_index, ok, caption, word_count, char_count, language}.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .._image_utils import load_image_any

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


def _normalize(s: str, templates: list) -> str:
    for t in templates:
        if isinstance(t, str) and "{caption}" in t:
            return t.format(caption=s).strip()
    return s


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_w = int(params.get("min_words", 1))
    max_w = int(params.get("max_words", 200))
    min_c = int(params.get("min_chars", 1))
    lang_target = str(params.get("language", "auto"))
    strip = bool(params.get("strip_html", True))
    templates = list(params.get("templates") or [])

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        rec: Dict[str, Any] = {"image_index": i}
        img_input = item.get("image") if isinstance(item, dict) and "image" in item else (
            {k: v for k, v in item.items()
             if k not in ("caption", "captions")}
            if isinstance(item, dict) else item
        )
        img, meta = load_image_any(img_input)
        rec["image_meta"] = meta
        caption = ""
        if isinstance(item, dict):
            if isinstance(item.get("caption"), str):
                caption = item["caption"]
            elif isinstance(item.get("captions"), list) and item["captions"]:
                caption = item["captions"][0]
        if strip:
            caption = _strip_html(caption)
        caption = _normalize(caption, templates)
        words = [w for w in caption.split() if w.strip()]
        wc = len(words)
        cc = len(caption)
        lang = _lang_detect(caption) if lang_target == "auto" else lang_target
        valid = wc >= min_w and wc <= max_w and cc >= min_c and (lang_target == "auto" or lang == lang_target)
        rec.update({
            "ok": valid and img is not None,
            "caption": caption,
            "word_count": wc,
            "char_count": cc,
            "language": lang,
        })
        out.append(rec)
    return out