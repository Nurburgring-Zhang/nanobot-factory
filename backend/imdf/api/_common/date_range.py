"""日期范围参数 — 统计 / 报表 / 仪表盘类端点专用
========================================

Pydantic v2 BaseModel, 单文件 < 50 行。错误信息中文化 (G4)。

覆盖场景:
  - 报表 / 仪表盘接口的 start / end 时间范围
  - 跨度上限 365 天, 防止拉全表
  - start 必须 ≤ end, 反序日期拒绝
  - 不接受未来日期 (避免空查询)
  - preset 模式 (1d/7d/30d/90d/1y) 与自定义模式 (custom) 二选一
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

DatePreset = Literal["1d", "7d", "30d", "90d", "1y", "custom"]
MAX_SPAN_DAYS = 365

_PRESET_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}


class DateRangeParams(BaseModel):
    """日期范围, 注入到统计 / 报表类端点。

    字段:
      preset: 时间范围预设 (1d/7d/30d/90d/1y/custom), 选 custom 时必须提供 start/end
      start:  开始日期 (ISO 8601, 包含)
      end:    结束日期 (ISO 8601, 包含)

    失败 → 400 (FastAPI Depends 兼容模式: 直接 raise HTTPException,
    否则 ValueError 在 Depends 链中被转为 500, 不是 422)
    """
    preset: DatePreset = Field(default="7d", description="时间范围预设")
    start: Optional[date] = Field(default=None, description="开始日期")
    end: Optional[date] = Field(default=None, description="结束日期")

    @model_validator(mode="after")
    def _check_range(self):
        today = date.today()
        if self.preset != "custom":
            days = _PRESET_DAYS[self.preset]
            self.end = today
            self.start = self.end - timedelta(days=days - 1)
            return self
        # preset=custom 时, 业务校验必须 raise HTTPException (而非 ValueError),
        # 保证 FastAPI Depends 注入时返回 4xx 而不是 500
        if not (self.start and self.end):
            raise HTTPException(
                status_code=400,
                detail="preset=custom 时必须提供 start 和 end",
            )
        if self.start > self.end:
            raise HTTPException(
                status_code=400,
                detail=f"start ({self.start}) 必须 ≤ end ({self.end})",
            )
        if self.end > today:
            raise HTTPException(
                status_code=400,
                detail=f"end ({self.end}) 不能晚于今天 ({today})",
            )
        if (self.end - self.start).days > MAX_SPAN_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"日期跨度不能超过 {MAX_SPAN_DAYS} 天",
            )
        if self.start < today - timedelta(days=MAX_SPAN_DAYS * 4):
            raise HTTPException(
                status_code=400,
                detail=f"start ({self.start}) 超出历史窗口 {MAX_SPAN_DAYS * 4} 天",
            )
        return self
