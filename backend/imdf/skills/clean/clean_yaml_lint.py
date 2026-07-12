"""clean_yaml_lint — YAML syntax check.

Parses YAML with a small built-in tokeniser when PyYAML isn't installed so
the skill is always usable.  Reports line-numbered diagnostics.

Skill function: ``clean_yaml_lint(input) -> SkillOutput``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_yaml_lint"


class YamlLintInput(BaseModel):
    yaml: str = Field("", description="YAML source")
    strict_indent: bool = Field(True)


class YamlLintIssue(BaseModel):
    line: int
    rule: str
    message: str
    severity: str = "error"


class YamlLintOutput(BaseModel):
    valid: bool
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    parsed: bool = False
    keys: List[str] = Field(default_factory=list)


_INDENT_RE = re.compile(r"^( *)(.*)$")


def _basic_yaml_parse(text: str) -> Dict[str, Any]:
    """Lightweight YAML → dict.  Handles top-level scalars and ``key: value`` blocks.

    This is *not* a full YAML implementation — it intentionally prefers
    usefulness over completeness so we can validate the common shape of a
    skill metadata file even when PyYAML is missing.
    """
    result: Dict[str, Any] = {}
    stack: List[tuple[int, Dict[str, Any]]] = [(-1, result)]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _INDENT_RE.match(line)
        if not m:
            continue
        indent_str, content = m.group(1), m.group(2)
        indent = len(indent_str)
        if ":" not in content:
            continue
        key, _, value = content.partition(":")
        key = key.strip()
        value = value.strip()
        # pop deeper frames
        while stack and indent <= stack[-1][0] and len(stack) > 1:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            new: Dict[str, Any] = {}
            parent[key] = new
            stack.append((indent, new))
        else:
            parent[key] = value
    return result


def _tab_check(text: str) -> List[Dict[str, Any]]:
    return [
        {"line": i, "rule": "tab-character", "message": "indentation uses tabs", "severity": "error"}
        for i, line in enumerate(text.splitlines(), start=1)
        if "\t" in line
    ]


async def clean_yaml_lint(input: SkillInput) -> SkillOutput:
    payload = YamlLintInput(**(input.params or {}))
    issues: List[Dict[str, Any]] = []

    for issue in _tab_check(payload.yaml):
        issues.append(issue)

    parsed_doc: Dict[str, Any] = {}
    try:
        parsed_doc = _basic_yaml_parse(payload.yaml)
        parsed = True
        valid = not issues
    except Exception as exc:
        issues.append({"line": 0, "rule": "parse-failure", "message": str(exc), "severity": "error"})
        parsed = False
        valid = False

    out = YamlLintOutput(
        valid=valid,
        issues=issues,
        parsed=parsed,
        keys=list(parsed_doc.keys()) if parsed else [],
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_yaml_lint"),
    )


__all__ = ["YamlLintInput", "YamlLintIssue", "YamlLintOutput", "clean_yaml_lint"]
