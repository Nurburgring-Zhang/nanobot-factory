"""Cron 表达式校验器 — 纯 Python 实现, 无外部依赖
=========================================

支持标准 5 字段 cron 表达式:
    ┌───────────── 分钟 (0 - 59)
    │ ┌───────────── 小时 (0 - 23)
    │ │ ┌───────────── 日 (1 - 31)
    │ │ │ ┌───────────── 月 (1 - 12)
    │ │ │ │ ┌───────────── 星期 (0 - 6, 0=周日, 6=周六)
    │ │ │ │ │
    * * * * *

支持语法:
  - 通配符 ``*``     : 任意值
  - 列表 ``1,3,5``  : 多个值
  - 范围 ``1-5``    : 连续范围
  - 步长 ``*/2``    : 间隔
  - 范围步长 ``1-30/5``

不在 cron 范围内的取值 (如 minute=60) 立即拒绝。

错误信息中文化 + 含字段名 (G4)。
"""
from __future__ import annotations

import re
from typing import List, Tuple

from fastapi import HTTPException

# 单个字段的最大值 (不包含 0-based 偏移)
_FIELD_RANGES: List[Tuple[str, int, int]] = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),
]

# 字段是数字 / 范围 / 步长 / 通配 / 列表
_FIELD_TOKEN = re.compile(r"^\*$|^\d+$|^\d+-\d+$|^\*/\d+$|^\d+-\d+/\d+$|^\d+(,\d+)+$")

_CRON_FULL = re.compile(r"^\S+\s+\S+\s+\S+\s+\S+\s+\S+$")


def _parse_field(token: str, name: str, lo: int, hi: int) -> None:
    """校验单字段 token, 失败 raise HTTPException(400)。"""
    if not token or not _FIELD_TOKEN.match(token):
        raise HTTPException(
            status_code=400,
            detail=f"cron {name} 字段非法: {token!r}, 应为 */N, a-b, a-b/N, N 或 *",
        )

    # 通配符 *
    if token == "*":
        return

    # 列表 1,3,5
    if "," in token:
        for part in token.split(","):
            try:
                n = int(part)
            except ValueError:
                raise HTTPException(400, f"cron {name} 列表项非法: {part!r}")
            if not (lo <= n <= hi):
                raise HTTPException(400, f"cron {name} 列表值 {n} 超出 {lo}..{hi}")
        return

    # */N 步长
    if token.startswith("*/"):
        try:
            n = int(token[2:])
        except ValueError:
            raise HTTPException(400, f"cron {name} 步长非法: {token!r}")
        if n < 1 or n > hi:
            raise HTTPException(400, f"cron {name} 步长 {n} 超出范围 1..{hi}")
        return

    # a-b 或 a-b/N
    if "-" in token:
        head, _, step = token.partition("/")
        try:
            a, b = (int(x) for x in head.split("-", 1))
        except ValueError:
            raise HTTPException(400, f"cron {name} 范围非法: {token!r}")
        if step:
            try:
                s = int(step)
            except ValueError:
                raise HTTPException(400, f"cron {name} 步长非法: {token!r}")
            if s < 1 or s > hi:
                raise HTTPException(400, f"cron {name} 步长 {s} 超出范围 1..{hi}")
        if not (lo <= a <= b <= hi):
            raise HTTPException(400, f"cron {name} 范围 {a}-{b} 超出 {lo}..{hi}")
        return

    # 单个 N
    try:
        n = int(token)
    except ValueError:
        raise HTTPException(400, f"cron {name} 值非法: {token!r}")
    if not (lo <= n <= hi):
        raise HTTPException(400, f"cron {name} 值 {n} 超出 {lo}..{hi}")


def validate_cron(expr: str, name: str = "cron") -> str:
    """校验 cron 表达式, 失败 raise HTTPException(400)。

    参数:
        expr: 5 字段 cron 表达式 (e.g. ``"0 3 * * *"``)
        name: 字段名, 用于错误信息

    返回:
        校验通过时原样返回
    """
    if not isinstance(expr, str) or not expr.strip():
        raise HTTPException(400, f"{name} 不能为空")
    expr = expr.strip()
    # 必须恰好 5 字段
    if not _CRON_FULL.match(expr):
        raise HTTPException(
            400,
            f"{name} 字段数错误, 应为 5 字段 (分 时 日 月 周), 实得: {len(expr.split())}",
        )
    parts = expr.split()
    if len(parts) != 5:
        raise HTTPException(400, f"{name} 字段数错误: {len(parts)}, 应为 5")

    for i, (field_name, lo, hi) in enumerate(_FIELD_RANGES):
        _parse_field(parts[i], field_name, lo, hi)
    return expr


def validate_trigger_config(
    trigger_type: str, trigger_config: dict, name: str = "trigger_config"
) -> str:
    """校验 scheduler trigger_config 块。

    - ``cron``     : trigger_config 中必须含 ``cron_expression`` 字段 (5 字段表达式)
    - ``interval`` : trigger_config 中至少含 weeks/days/hours/minutes/seconds 之一
                     且值必须 > 0
    - ``date``     : trigger_config 中必须含 ``run_date`` 字段 (ISO 8601)
    - 其它         : 拒绝

    失败 raise HTTPException(400)。
    """
    if trigger_type == "cron":
        expr = trigger_config.get("cron_expression")
        if not expr:
            raise HTTPException(
                400,
                f"{name}: cron 类型必须包含 cron_expression 字段",
            )
        return validate_cron(expr, "cron_expression")
    if trigger_type == "interval":
        valid = {"weeks", "days", "hours", "minutes", "seconds"}
        if not any(k in trigger_config for k in valid):
            raise HTTPException(
                400,
                f"{name}: interval 类型必须至少含 {sorted(valid)} 之一",
            )
        for k, v in trigger_config.items():
            if k in valid and (not isinstance(v, (int, float)) or v <= 0):
                raise HTTPException(400, f"{name}.{k} 必须 > 0, 实得: {v!r}")
        return trigger_type
    if trigger_type == "date":
        rd = trigger_config.get("run_date")
        if not rd:
            raise HTTPException(400, f"{name}: date 类型必须包含 run_date 字段")
        return trigger_type
    raise HTTPException(
        400,
        f"{name}: trigger_type 非法: {trigger_type!r}, 应为 cron/interval/date",
    )
