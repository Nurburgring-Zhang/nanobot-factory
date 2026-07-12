"""label_entity_ner — Named Entity Recognition.

Extracts named entities from text and returns per-entity spans with type,
text, start/end char offsets, and confidence.

Inputs:
    text:       str
    types:      list[str]  — entity types to extract (PERSON, ORG, LOC, ...)
    lang:       str  — "auto"|"en"|"zh"

Outputs:
    entities:   list — {text, type, start, end, confidence}
    count:      int
    types:      list[str]
"""

import re
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    clamp,
    now_iso,
    post_json,
    require_non_empty,
    stable_seed,
)


_VALID_TYPES = {"PERSON", "ORG", "LOC", "MISC", "DATE", "TIME", "MONEY", "PERCENT", "GPE", "FAC"}


class EntityNerInput(BaseModel):
    text: str = Field(..., min_length=1)
    types: List[str] = Field(default_factory=lambda: ["PERSON", "ORG", "LOC"])
    lang: str = Field(default="auto")

    @field_validator("types")
    @classmethod
    def _t(cls, v: List[str]) -> List[str]:
        if not v:
            return ["PERSON", "ORG", "LOC"]
        out = []
        for t in v:
            tu = (t or "").upper().strip()
            if tu in _VALID_TYPES:
                out.append(tu)
        return out or ["PERSON", "ORG", "LOC"]


_PERSON_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")
_ORG_RE = re.compile(r"\b([A-Z][a-zA-Z]*\s+)?(Inc|Corp|Ltd|Co|LLC|GmbH|Group|Foundation|Studio|Lab)\b")
_DATE_RE = re.compile(r"\b\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b")
_MONEY_RE = re.compile(r"[\$€¥£]\s?\d+(?:[.,]\d+)?(?:\s?(?:USD|EUR|CNY|GBP|JPY))?")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")


async def label_entity_ner(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = EntityNerInput.model_validate(input.params or {})
        require_non_empty(payload.text, "text")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    detected_lang = payload.lang
    if detected_lang == "auto":
        detected_lang = "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in payload.text) else "en"

    live = None
    if NETWORK_OK:
        live = await post_json(
            "https://api.ner.example/extract",
            payload.model_dump(), timeout=5.0,
        )

    if live and isinstance(live, dict) and live.get("entities"):
        entities = [
            {
                "text": str(e.get("text", "")),
                "type": str(e.get("type", "MISC")),
                "start": int(e.get("start", 0)),
                "end": int(e.get("end", 0)),
                "confidence": clamp(float(e.get("confidence", 0.0))),
            }
            for e in live["entities"]
            if str(e.get("type", "")).upper() in payload.types
        ]
        return build_output(
            success=True,
            result={"entities": entities, "count": len(entities),
                    "types": payload.types, "lang": detected_lang,
                    "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — regex + lexicon.
    entities = _extract_entities(payload.text, payload.types, detected_lang, stable_seed(payload.text))
    return build_output(
        success=True,
        result={"entities": entities, "count": len(entities),
                "types": payload.types, "lang": detected_lang,
                "timestamp": now_iso()},
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _extract_entities(text: str, types: List[str], lang: str, seed: int) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    if "DATE" in types:
        for m in _DATE_RE.finditer(text):
            found.append({"text": m.group(), "type": "DATE", "start": m.start(),
                          "end": m.end(), "confidence": 0.92})
    if "MONEY" in types:
        for m in _MONEY_RE.finditer(text):
            found.append({"text": m.group(), "type": "MONEY", "start": m.start(),
                          "end": m.end(), "confidence": 0.9})
    if "PERCENT" in types:
        for m in _PERCENT_RE.finditer(text):
            found.append({"text": m.group(), "type": "PERCENT", "start": m.start(),
                          "end": m.end(), "confidence": 0.9})
    if "PERSON" in types:
        for m in _PERSON_RE.finditer(text):
            found.append({"text": m.group(), "type": "PERSON", "start": m.start(),
                          "end": m.end(), "confidence": 0.65})
    if "ORG" in types:
        for m in _ORG_RE.finditer(text):
            found.append({"text": m.group(), "type": "ORG", "start": m.start(),
                          "end": m.end(), "confidence": 0.6})

    # Deduplicate by (start, end)
    seen = set()
    unique: List[Dict[str, Any]] = []
    for ent in found:
        key = (ent["start"], ent["end"], ent["type"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(ent)

    # Stable sort by start
    unique.sort(key=lambda e: (e["start"], e["type"]))
    # Trim to 50 max for sanity
    return unique[:50]


__all__ = ["label_entity_ner", "EntityNerInput"]