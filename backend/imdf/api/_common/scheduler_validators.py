"""调度器专用校验器 — 分页 / 时间范围 / trigger 块
========================================

复用 cron_validator.validate_trigger_config。

错误信息中文化 + 含字段名 (G4)。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

# 复用通用分页约束
from .pagination_compat import PaginationParams  # noqa: F401  (re-export)


# ─── 调度历史过滤参数 ───────────────────────────────────────────────

class SchedulerHistoryParams(PaginationParams):
    """调度历史查询参数 — 分页 + job_id 过滤 + 时间范围。"""
    job_id: Optional[str] = Field(
        default=None,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-]{1,128}$",
        description="按任务 ID 过滤 (含 preset_ 前缀)",
    )
    start: Optional[date] = Field(default=None, description="起始日期 (含)")
    end: Optional[date] = Field(default=None, description="结束日期 (含)")
    status: Optional[Literal["success", "failed", "running", "pending"]] = None

    @model_validator(mode="after")
    def _check_range(self):
        # Pydantic v2 + FastAPI Depends 的兼容: 直接 raise HTTPException 以保证 4xx
        # (ValueError 在 Depends 链中会被转为 500, 不是 422)
        if self.start and self.end and self.start > self.end:
            raise HTTPException(
                status_code=400,
                detail=f"start ({self.start}) 必须 ≤ end ({self.end})",
            )
        if self.start and self.end and (self.end - self.start).days > 365:
            raise HTTPException(status_code=400, detail="日期跨度不能超过 365 天")
        return self
