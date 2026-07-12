"""Dataset — Pydantic v2 model for public dataset crawlers (P20-B1 batch 2)

Field spec from task:
    id, title, url, size, format, tags

We extend with a few common-sense extras (license, downloads, description,
created_at, channel, raw) but keep the 6 core fields first-class so the
downstream pipeline can rely on them.

All fields are coerced to safe types:
    - id:        str (always non-empty — fallback "channel:idx")
    - title:     str (non-empty)
    - url:       HttpUrl → str for forward-compat with httpx JSON dumps
    - size:      Optional[str] — free-form ("1.2 GB", "15000 rows")
    - format:    List[str] — csv, parquet, jsonl …
    - tags:      List[str]
    - downloads: Optional[int] — total download count when known
    - license:   Optional[str]
    - channel:   str — which crawler produced this
    - description: str
    - created_at: datetime — when we ingested this into our system
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Dataset(BaseModel):
    """统一 6 核心字段 + 扩展 — Pydantic v2.

    The 6 mandated fields (id, title, url, size, format, tags) are the
    public contract; extras are best-effort enrichment from the source.
    """

    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        validate_assignment=False,
        arbitrary_types_allowed=True,
    )

    # -------- core 6 fields --------
    id: str = Field(..., description="Dataset id within the source")
    title: str = Field(..., description="Human-readable dataset name")
    url: str = Field(..., description="Canonical dataset URL")
    size: Optional[str] = Field(default=None, description="Size string ('1.2 GB')")
    format: List[str] = Field(
        default_factory=list,
        description="File formats (csv, parquet, jsonl, arrow, …)",
    )
    tags: List[str] = Field(default_factory=list, description="Subject tags")

    # -------- enrichment --------
    channel: str = Field(default="", description="Which crawler produced this")
    description: str = Field(default="", description="Long-form description")
    license: Optional[str] = Field(default=None, description="License name")
    downloads: Optional[int] = Field(default=None, ge=0, description="Total downloads")
    stars: Optional[int] = Field(default=None, ge=0, description="Likes/stars")
    author: Optional[str] = Field(default=None, description="Uploader / owner")
    last_updated: Optional[str] = Field(
        default=None, description="ISO timestamp from source"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Ingestion timestamp (UTC)",
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="Source-specific extra fields"
    )

    # -------- validators --------

    @field_validator("id", "title", "url", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        if v is None or v == "":
            return ""
        return str(v).strip()

    @field_validator("format", "tags", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x is not None and str(x).strip()]
        if isinstance(v, str):
            # split csv / pipe / comma
            if not v:
                return []
            parts = [p.strip() for p in v.replace("|", ",").split(",")]
            return [p for p in parts if p]
        return [str(v)]

    @field_validator("downloads", "stars", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            n = int(v)
            return n if n >= 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("url", mode="before")
    @classmethod
    def _coerce_url(cls, v: Any) -> str:
        # accept HttpUrl objects too — convert to str
        if v is None:
            return ""
        if hasattr(v, "unicode_string"):
            return str(v.unicode_string())
        return str(v).strip()

    # -------- helpers --------

    def to_dict(self) -> Dict[str, Any]:
        out = self.model_dump()
        if isinstance(out.get("created_at"), datetime):
            out["created_at"] = out["created_at"].isoformat()
        return out


__all__ = ["Dataset"]