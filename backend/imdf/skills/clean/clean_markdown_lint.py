"""clean_markdown_lint — Markdown syntax checker.

Lightweight, regex-driven Markdown linter that flags common issues
without external dependencies.  Reports line-numbered diagnostics.

Skill function: ``clean_markdown_lint(input) -> SkillOutput``.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_markdown_lint"


class MarkdownLintInput(BaseModel):
    markdown: str = Field("", description="Markdown source")
    max_line_length: int = Field(120, ge=20)


class LintIssue(BaseModel):
    line: int
    column: int = 0
    rule: str
    message: str
    severity: str = "warning"


class MarkdownLintOutput(BaseModel):
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    line_count: int = 0


_HR_RE = re.compile(r"^([-*_])\1{2,}\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CODE_FENCE_RE = re.compile(r"^(```|~~~)")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+")


def _check_line(line: str, lineno: int, max_len: int, in_code: List[bool]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if in_code[0]:
        if _CODE_FENCE_RE.match(line):
            in_code[0] = False
        return issues
    if _CODE_FENCE_RE.match(line):
        in_code[0] = True
        return issues
    if len(line) > max_len:
        issues.append({
            "line": lineno, "column": 0, "rule": "line-length",
            "message": f"line {len(line)} chars exceeds limit {max_len}",
            "severity": "warning",
        })
    if _HR_RE.match(line):
        return issues
    m = _HEADING_RE.match(line)
    if m and not line.endswith("  "):
        # Heading without trailing space — fine, just convention warning if missing
        pass
    if line.endswith("  "):
        issues.append({
            "line": lineno, "column": len(line.rstrip()), "rule": "trailing-spaces",
            "message": "trailing whitespace", "severity": "warning",
        })
    if "\t" in line:
        issues.append({
            "line": lineno, "column": line.index("\t"), "rule": "tab-character",
            "message": "tab character", "severity": "warning",
        })
    if _LIST_RE.match(line):
        # Mark with info that a list item starts here — useful for downstream
        pass
    return issues


async def clean_markdown_lint(input: SkillInput) -> SkillOutput:
    payload = MarkdownLintInput(**(input.params or {}))
    in_code = [False]
    issues: List[Dict[str, Any]] = []
    lines = payload.markdown.splitlines()
    for idx, line in enumerate(lines, start=1):
        issues.extend(_check_line(line, idx, payload.max_line_length, in_code))

    if in_code[0]:
        issues.append({
            "line": len(lines), "column": 0, "rule": "unclosed-code-fence",
            "message": "code fence opened but never closed", "severity": "error",
        })

    error_count = sum(1 for i in issues if i["severity"] == "error")
    out = MarkdownLintOutput(
        issues=issues,
        error_count=error_count,
        warning_count=len(issues) - error_count,
        line_count=len(lines),
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_markdown_lint"),
    )


__all__ = ["MarkdownLintInput", "MarkdownLintOutput", "clean_markdown_lint"]
