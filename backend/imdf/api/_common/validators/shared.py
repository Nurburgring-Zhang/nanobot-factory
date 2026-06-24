"""safe_int + safe_path — 兼容 R1 调用, 单文件 < 50 行

这些函数由 R1 引入, R2-3 保留为兼容层。
新代码应优先使用 validators/ 下的细分工具 (id / upload / image_path)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

# 32 位有符号整数安全范围
SAFE_INT = {"ge": 0, "le": 2**31 - 1}


def safe_int(value: Any, default: int = 0, **kwargs: Any) -> int:
    """安全地将 value 解析为 int, 失败回退到 default。"""
    try:
        return int(value, **kwargs)
    except (TypeError, ValueError, OverflowError):
        return default


def safe_path(value: str, base_dir: Path) -> Path:
    """校验路径在 base_dir 之下, 防 path traversal。"""
    base = base_dir.resolve()
    try:
        candidate = (base / value).resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid path: {exc}",
        ) from exc

    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid path: traversal outside base directory",
        ) from exc

    return candidate
