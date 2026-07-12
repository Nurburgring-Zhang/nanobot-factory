"""clean_csv_normalize — CSV field normalization (delimiter / quote / headers).

Normalizes CSV text: detects delimiter, normalises quoting, trims header
names, lowercases them if requested, removes blank rows.

Skill function: ``clean_csv_normalize(input) -> SkillOutput``.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_csv_normalize"


class CsvNormalizeInput(BaseModel):
    csv: str = Field("", description="Raw CSV text")
    delimiter: str = Field(",", description="Override delimiter (auto-detect if empty)")
    lowercase_headers: bool = Field(False)
    trim_cells: bool = Field(True)
    drop_blank_rows: bool = Field(True)


class CsvNormalizeOutput(BaseModel):
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    detected_delimiter: str = ","
    removed_blank_rows: int = 0
    column_count: int = 0


_DELIMS = [",", "\t", ";", "|"]


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    counts = {d: sample.count(d) for d in _DELIMS}
    return max(counts.items(), key=lambda kv: kv[1])[0]


async def clean_csv_normalize(input: SkillInput) -> SkillOutput:
    payload = CsvNormalizeInput(**(input.params or {}))
    text = payload.csv
    if not text.strip():
        return SkillOutput(
            success=True,
            result=CsvNormalizeOutput().model_dump(),
            metadata=make_metadata(SKILL_ID, "clean_csv_normalize"),
        )

    delim = payload.delimiter or _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    if not rows:
        return SkillOutput(
            success=True,
            result=CsvNormalizeOutput(detected_delimiter=delim).model_dump(),
            metadata=make_metadata(SKILL_ID, "clean_csv_normalize"),
        )

    headers = [h.strip() for h in rows[0]] if rows else []
    if payload.lowercase_headers:
        headers = [h.lower() for h in headers]

    body = rows[1:] if len(rows) > 1 else []
    removed = 0
    cleaned: List[List[str]] = []
    for row in body:
        if payload.trim_cells:
            row = [c.strip() for c in row]
        if payload.drop_blank_rows and not any(row):
            removed += 1
            continue
        # Pad / truncate to header length
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        elif len(row) > len(headers):
            row = row[: len(headers)]
        cleaned.append(row)

    out = CsvNormalizeOutput(
        headers=headers,
        rows=cleaned,
        detected_delimiter=delim,
        removed_blank_rows=removed,
        column_count=len(headers),
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_csv_normalize"),
    )


__all__ = ["CsvNormalizeInput", "CsvNormalizeOutput", "clean_csv_normalize"]
