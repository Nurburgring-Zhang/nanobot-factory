"""clean_text_normalize — Unicode/case/punctuation normalization.

Reproducible text cleaner: NFKC normalize, full-width → ASCII, unify
whitespace, optional lowercasing and punctuation stripping.

Skill function: ``clean_text_normalize(input) -> SkillOutput``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_text_normalize"


class TextNormalizeInput(BaseModel):
    text: str = Field("", description="Raw text to clean")
    lowercase: bool = Field(False)
    strip_punct: bool = Field(False)
    collapse_whitespace: bool = Field(True)
    to_ascii: bool = Field(True)


class TextNormalizeOutput(BaseModel):
    original: str = ""
    normalized: str = ""
    changes: List[str] = Field(default_factory=list)
    length_before: int = 0
    length_after: int = 0


_FULLWIDTH = {
    "！": "!", "（": "(", "）": ")", "，": ",", "。": ".",
    "：": ":", "；": ";", "？": "?", "—": "-", "–": "-",
    "～": "~", "／": "/", "　": " ",
}
_FW_MAP = str.maketrans(_FULLWIDTH)
_PUNCT_RE = re.compile(r"[\u2000-\u206F\u2E00-\u2E7F\.,!?;:\"'()\[\]{}/\\<>\-_=+@#$%^&*`~]+")
_WS_RE = re.compile(r"\s+")


def _to_ascii(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text)
    fw = nfkc.translate(_FW_MAP)
    return unicodedata.normalize("NFKC", fw)


async def clean_text_normalize(input: SkillInput) -> SkillOutput:
    payload = TextNormalizeInput(**(input.params or {}))
    original = payload.text
    text = original

    changes: List[str] = []
    if payload.to_ascii:
        text = _to_ascii(text)
        if text != original:
            changes.append("to_ascii")

    if payload.lowercase:
        new = text.lower()
        if new != text:
            changes.append("lowercase")
        text = new

    if payload.strip_punct:
        new = _PUNCT_RE.sub(" ", text)
        if new != text:
            changes.append("strip_punct")
        text = new

    if payload.collapse_whitespace:
        new = _WS_RE.sub(" ", text).strip()
        if new != text:
            changes.append("collapse_whitespace")
        text = new

    out = TextNormalizeOutput(
        original=original,
        normalized=text,
        changes=changes,
        length_before=len(original),
        length_after=len(text),
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_text_normalize"),
    )


__all__ = ["TextNormalizeInput", "TextNormalizeOutput", "clean_text_normalize"]
