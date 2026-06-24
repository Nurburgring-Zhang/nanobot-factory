"""聚合粒度枚举 — 统计 / 报表 / 仪表盘类端点专用
========================================

Pydantic v2 Literal, 单文件 < 50 行。错误信息中文化 (G4)。

覆盖场景:
  - 折线 / 柱状图的桶大小
  - 跨端点统一枚举, 避免下游分支处理 "5min" / "5m" / "5M" 等不一致写法
  - 粒度与时间范围强相关: 跨度过大却用 minute 会爆; 反之 month + 1d 跨度无意义
    校验放在 DateRangeParams.granularity_compatible() 调用方
"""
from __future__ import annotations

from typing import Literal

# 主粒度枚举 (与下游 dashboard / 报表库对齐)
Granularity = Literal["hour", "day", "week", "month", "quarter", "year"]

# 粒度白名单 (用于 Pydantic v2 不支持的场景 / 字符串白名单)
ALLOWED_GRANULARITIES = frozenset({"hour", "day", "week", "month", "quarter", "year"})

# 粒度 → 建议最小跨度 (天) — 用以提示 (非强制, 调用方决定)
MIN_SPAN_DAYS = {
    "hour": 1,
    "day": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "year": 365,
}


def is_valid_granularity(value: str) -> bool:
    """校验粒度是否在白名单内 — 给非 Pydantic 路径用 (e.g. 业务函数内部)。

    返回 True / False, 不抛异常。
    """
    return value in ALLOWED_GRANULARITIES
