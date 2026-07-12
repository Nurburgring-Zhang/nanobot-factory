"""clean_pii_remove — PII redaction.

Removes or masks email addresses, phone numbers, ID numbers, IPv4 and
basic credit-card numbers.  Configurable replacement token.

Skill function: ``clean_pii_remove(input) -> SkillOutput``.
"""

import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_pii_remove"


class PiiRemoveInput(BaseModel):
    text: str = Field("", description="Free text to scrub")
    replacement: str = Field("[REDACTED]")
    detect: List[str] = Field(default_factory=lambda: ["email", "phone", "ipv4", "id_card", "credit_card"])


class PiiRemoveOutput(BaseModel):
    redacted: str = ""
    matches: List[Dict[str, Any]] = Field(default_factory=list)
    redaction_count: int = 0


_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s\-]?)?\(?\d{3,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{4}\b"),
    "ipv4": re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    "id_card": re.compile(r"\b\d{17}[\dXx]\b"),
    "credit_card": re.compile(r"\b(?:\d[ \-]?){13,16}\d\b"),
}


async def clean_pii_remove(input: SkillInput) -> SkillOutput:
    payload = PiiRemoveInput(**(input.params or {}))
    text = payload.text
    matches: List[Dict[str, Any]] = []

    for kind in payload.detect:
        pattern = _PATTERNS.get(kind)
        if pattern is None:
            continue
        for m in pattern.finditer(text):
            matches.append({
                "kind": kind,
                "start": m.start(),
                "end": m.end(),
                "value": m.group(0),
            })

    # Replace right-to-left so spans stay valid
    matches.sort(key=lambda r: r["start"], reverse=True)
    redacted = text
    for m in matches:
        redacted = redacted[: m["start"]] + payload.replacement + redacted[m["end"]:]

    out = PiiRemoveOutput(
        redacted=redacted,
        matches=sorted(matches, key=lambda r: r["start"]),
        redaction_count=len(matches),
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_pii_remove"),
    )


__all__ = ["PiiRemoveInput", "PiiRemoveOutput", "clean_pii_remove"]
