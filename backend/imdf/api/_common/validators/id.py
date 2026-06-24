"""资源 ID 校验 — 单文件 < 50 行 (R1 + R2-3 扩展)

提供:
  - ID_PATTERN: 资源 ID 字符白名单正则
  - validate_id(value, name): 函数体首行调用, 失败 raise HTTPException(400)
  - validate_id_dep(name): Depends 工厂, 用于新端点

规则: 字母 / 数字 / 下划线 / 连字符, 长度 1-128。
"""
from __future__ import annotations

import re
from fastapi import HTTPException, Path

# 资源 ID 允许的字符: 字母、数字、下划线、连字符, 长度 1-128
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


def validate_id(value: str, name: str = "id") -> str:
    """校验资源 ID 格式, 失败 raise HTTPException(400)。

    参数:
        value: 待校验的 ID 字符串。
        name:  字段名, 用于错误信息, 默认 "id"。

    返回: 校验通过时返回原值。
    异常: HTTPException(400) — 非字符串 / 空 / 非法字符 / 超长。
    """
    if not isinstance(value, str):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name}: must be a string",
        )
    if not value or not ID_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name}: must match {ID_PATTERN.pattern}",
        )
    return value


def validate_id_dep(name: str = "id"):
    """FastAPI Depends 工厂 — 用于新端点声明式校验 (失败 → 422)。"""
    def _dep(value: str = Path(..., regex=ID_PATTERN.pattern)):
        return value
    _dep.__name__ = f"validate_{name}_dep"
    return _dep
