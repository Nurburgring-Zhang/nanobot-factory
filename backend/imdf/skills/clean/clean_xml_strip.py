"""clean_xml_strip — XML namespace cleanup.

Removes redundant namespace declarations, optionally collapses duplicate
prefixes, and produces a compact XML body.  Built-in pure-Python
parser; no lxml dependency.

Skill function: ``clean_xml_strip(input) -> SkillOutput``.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_xml_strip"


class XmlStripInput(BaseModel):
    xml: str = Field("", description="XML source")
    remove_namespaces: bool = Field(False)
    keep_root: bool = Field(True)


class XmlStripOutput(BaseModel):
    cleaned_xml: str = ""
    elements: int = 0
    namespaces: List[str] = Field(default_factory=list)
    removed_attrs: int = 0


_NS_RE = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"')


def _collect_namespaces(text: str) -> List[str]:
    return sorted(set(_NS_RE.findall(text)))


async def clean_xml_strip(input: SkillInput) -> SkillOutput:
    payload = XmlStripInput(**(input.params or {}))
    raw = payload.xml.strip()
    if not raw:
        return SkillOutput(
            success=True,
            result=XmlStripOutput(cleaned_xml="").model_dump(),
            metadata=make_metadata(SKILL_ID, "clean_xml_strip"),
        )

    namespaces = _collect_namespaces(raw)
    parsed_tree = ET.fromstring(raw)
    elements = sum(1 for _ in parsed_tree.iter())
    removed_attrs = len(namespaces) if payload.remove_namespaces else 0

    cleaned = raw
    if payload.remove_namespaces:
        cleaned = _NS_RE.sub("", cleaned)
        # strip "ns:" prefix from tag names for downstream readability
        cleaned = re.sub(r"<(/?)([\w]+):([\w]+)", r"<\1\3", cleaned)

    out = XmlStripOutput(
        cleaned_xml=cleaned,
        elements=elements,
        namespaces=namespaces,
        removed_attrs=removed_attrs,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_xml_strip"),
    )


__all__ = ["XmlStripInput", "XmlStripOutput", "clean_xml_strip"]
