"""clean_html_strip — Strip HTML tags and decode entities.

Removes HTML tags (preserving selected ones via ``keep_tags``), decodes
common HTML entities, and collapses leftover whitespace.

Skill function: ``clean_html_strip(input) -> SkillOutput``.
"""

import html
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_html_strip"


class HtmlStripInput(BaseModel):
    html: str = Field("", description="Raw HTML or fragment")
    keep_tags: List[str] = Field(default_factory=lambda: ["br", "p", "li"],
                                description="Tag names whose inner text should be preserved")
    decode_entities: bool = Field(True)


class HtmlStripOutput(BaseModel):
    text: str = ""
    line_count: int = 0
    char_count: int = 0
    stripped_tags: int = 0


_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", re.MULTILINE)
_WS_RE = re.compile(r"[ \t\f\v]+")
_NL_RE = re.compile(r"\n{2,}")


async def clean_html_strip(input: SkillInput) -> SkillOutput:
    payload = HtmlStripInput(**(input.params or {}))
    raw = payload.html

    tags_kept = {t.lower() for t in payload.keep_tags}

    # Replace <br>/<p>/<li> with newlines before stripping; keep others' inner text
    placeholder_map = {"br": "\n", "hr": "\n", "li": "\n", "p": "\n", "div": "\n",
                       "tr": "\n", "h1": "\n", "h2": "\n", "h3": "\n", "h4": "\n", "h5": "\n", "h6": "\n"}
    preserved = raw
    for tag, repl in placeholder_map.items():
        preserved = re.sub(rf"<\s*/?\s*{tag}\b[^>]*>", repl, preserved, flags=re.IGNORECASE)

    stripped_tags = len(_TAG_RE.findall(preserved))
    text = _TAG_RE.sub("", preserved)

    if payload.decode_entities:
        text = html.unescape(text)

    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n", text).strip()
    lines = [ln for ln in text.split("\n") if ln.strip()]

    out = HtmlStripOutput(
        text=text,
        line_count=len(lines),
        char_count=len(text),
        stripped_tags=stripped_tags,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_html_strip"),
    )


__all__ = ["HtmlStripInput", "HtmlStripOutput", "clean_html_strip"]
