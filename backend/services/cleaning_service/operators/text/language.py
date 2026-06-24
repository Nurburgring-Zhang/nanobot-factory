"""clean.text.language — language identification heuristic.

Uses Unicode-script ratio + ASCII proportion to label language as zh/en/mixed/other.
Not a production LID model; meant for cheap filtering.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


_CJK_RX = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_HAN_RX = re.compile(r"[\u4e00-\u9fff]")
_ASCII_RX = re.compile(r"[\x00-\x7f]")


def _classify(s: str) -> str:
    if not s:
        return "empty"
    cjk = len(_CJK_RX.findall(s))
    ascii_ = len(_ASCII_RX.findall(s))
    total = len(s)
    cjk_ratio = cjk / total
    ascii_ratio = ascii_ / total
    if cjk_ratio > 0.5:
        return "zh"
    if ascii_ratio > 0.85:
        return "en"
    if cjk_ratio > 0.2 and ascii_ratio > 0.2:
        return "mixed"
    return "other"


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return {item, language, passed} per item; filter to target_lang.

    params:
        target_lang: str = "any" (zh|en|mixed|other|any)
    """
    target = str(params.get("target_lang", "any"))
    out = []
    for x in items:
        s = x if isinstance(x, str) else repr(x)
        lang = _classify(s)
        rec = {"item": x, "language": lang, "char_count": len(s)}
        if target == "any":
            rec["passed"] = True
        else:
            rec["passed"] = lang == target
        out.append(rec)
    return [r for r in out if r.get("passed", True)]