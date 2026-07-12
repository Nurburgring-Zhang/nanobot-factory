"""通用分页参数 — Pydantic v2 BaseModel, 兼容 Pydantic v1 风格签名
=============================================================

不引入新依赖 (G6)。 错误信息中文化 (G4)。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SortOrder = Literal["asc", "desc"]
MAX_LIMIT = 200


class PaginationParams(BaseModel):
    """通用分页参数 — 注入到 GET 列表端点。"""
    skip: int = Field(0, ge=0, le=10_000_000, description="跳过的记录数")
    limit: int = Field(20, ge=1, le=MAX_LIMIT, description="每页条数")
    sort_by: Optional[str] = Field(
        default=None,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$",
        description="排序字段 (字母+数字+下划线, ≤64 字符)",
    )
    order: SortOrder = Field(default="asc", description="排序方向")

    model_config = ConfigDict(extra="forbid")
