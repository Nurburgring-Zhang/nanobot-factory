"""维度白名单校验器 — 统计 / 报表 / 仪表盘类端点专用
========================================

Pydantic v2 Literal, 单文件 < 50 行。错误信息中文化 (G4)。

覆盖场景:
  - GROUP BY 维度的安全白名单
  - 防止用户传入 "user.password" / "users.email" 等敏感字段
  - 防止 SQL 注入 (用户输入不会进入 SQL 字符串)

每端点的可选维度集合在 ALLOWED_DIMENSIONS 字典中按 endpoint 分类,
不在白名单内 → 422 (Pydantic 自动) 或 400 (函数式校验)。
"""
from __future__ import annotations

from typing import FrozenSet

# 通用维度白名单 — 大部分统计 / 报表端点共用的字段
COMMON_DIMENSIONS: FrozenSet[str] = frozenset({
    "user", "team", "category", "status", "action",
    "date", "hour", "weekday", "month",
})

# 端点专属白名单 (endpoint module → 允许的维度集合)
ALLOWED_DIMENSIONS: dict[str, FrozenSet[str]] = {
    # 运营看板 / 监控
    "ops": COMMON_DIMENSIONS | {"metric", "source"},
    "monitor": COMMON_DIMENSIONS | {"job", "queue", "status"},
    # 审计
    "audit": frozenset({"user", "method", "path", "status", "date", "hour"}),
    # 模板
    "templates": frozenset({"category", "author", "status", "tag", "rating", "date"}),
    # 众包
    "crowd": frozenset({"worker", "team", "task", "action", "status", "quality", "date"}),
    # 统计 / 仪表盘
    "stats": COMMON_DIMENSIONS | {"metric", "source"},
    # 报表
    "reports": COMMON_DIMENSIONS | {"metric", "report_type", "source"},
    # 调度
    "scheduler": frozenset({"job", "status", "trigger", "date", "hour"}),
    # PE / DAM
    "pe": frozenset({"modality", "stage", "subtype", "date"}),
    "dam": frozenset({"category", "format", "folder", "date", "size"}),
    # 质量
    "quality": frozenset({"category", "industry", "format", "score", "stage", "date"}),
    # webhook
    "webhook": frozenset({"webhook", "event", "status", "date"}),
    # 通用 (兜底)
    "default": COMMON_DIMENSIONS,
}


def is_valid_dimension(value: str, scope: str = "default") -> bool:
    """校验维度是否在指定 scope 的白名单内 — 给非 Pydantic 路径用。

    参数:
        value:  维度字符串, 如 "user" / "category"
        scope:  scope 名, 如 "ops" / "audit" / "default"

    返回:
        True / False, 不抛异常。
    """
    allowed = ALLOWED_DIMENSIONS.get(scope, ALLOWED_DIMENSIONS["default"])
    return value in allowed
