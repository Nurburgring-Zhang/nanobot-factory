"""Paper — Pydantic v2 model for academic crawler channels (P20-D).

Common schema used by all 5 academic channels:
    arxiv, pubmed, ieee, semanticscholar, googlescholar

Core fields are the most-stable identifiers extracted from public APIs:
    id            unique paper id within the source (str)
    title         paper title (str)
    url           canonical URL (str)
    authors       list of author names
    abstract      paper abstract/snippet
    year          publication year (int | None)
    venue         journal / conference / repository name (str | None)
    doi           digital object identifier (str | None)
    keywords      list[str] of subject tags / categories
    citation_count optional int — citations when the source provides it
    pdf_url       optional str — direct PDF URL when discoverable
    channel       which crawler produced this
    extra         source-specific extras (Dict[str, Any])
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Paper(BaseModel):
    """Unified academic paper model — Pydantic v2."""

    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        validate_assignment=False,
        arbitrary_types_allowed=True,
    )

    # -------- core fields --------
    id: str = Field(..., min_length=1, max_length=300)
    title: str = Field(..., min_length=1, max_length=1000)
    url: str = Field(..., min_length=1, max_length=2000)
    authors: List[str] = Field(default_factory=list)
    abstract: str = Field(default="", max_length=8000)
    year: Optional[int] = Field(default=None, ge=1700, le=2100)
    venue: Optional[str] = Field(default=None, max_length=500)
    doi: Optional[str] = Field(default=None, max_length=300)
    keywords: List[str] = Field(default_factory=list)

    # -------- enrichment --------
    citation_count: Optional[int] = Field(default=None, ge=0)
    pdf_url: Optional[str] = Field(default=None, max_length=2000)
    channel: str = Field(default="", max_length=50)
    extra: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # -------- validators --------

    @field_validator("id", "title", "url", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("authors", "keywords", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x is not None and str(x).strip()]
        if isinstance(v, str):
            if not v:
                return []
            # split on common delimiters
            parts: List[str] = []
            for sep in (";|", "||", " | ", "; ", ","):
                if sep in v:
                    parts = [p.strip() for p in v.split(sep)]
                    break
            if not parts:
                parts = [v.strip()]
            return [p for p in parts if p]
        return [str(v)]

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            # try to extract year from a date string
            s = str(v)
            import re
            m = re.search(r"(19|20)\d{2}", s)
            if m:
                try:
                    return int(m.group(0))
                except ValueError:
                    return None
            return None
        if 1700 <= n <= 2100:
            return n
        return None

    @field_validator("citation_count", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            n = int(v)
            return n if n >= 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("url", "pdf_url", mode="before")
    @classmethod
    def _coerce_url(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        if s.startswith("http://") or s.startswith("https://"):
            return s
        # sometimes DOI-only URL is given
        if s.startswith("doi:") or s.startswith("DOI:"):
            return "https://doi.org/" + s.split(":", 1)[1].strip()
        return s

    # -------- helpers --------

    def to_dict(self) -> Dict[str, Any]:
        out = self.model_dump()
        if isinstance(out.get("created_at"), datetime):
            out["created_at"] = out["created_at"].isoformat()
        return out


__all__ = ["Paper"]
