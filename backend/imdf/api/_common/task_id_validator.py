"""异步任务 ID 格式校验器 — 严格命名空间模式
====================================

支持以下命名空间 (作为前缀):
  - ``task_``  : 通用异步任务
  - ``job_``   : 调度任务
  - ``batch_`` : 批处理任务
  - ``run_``   : 运行实例
  - ``del_``   : webhook delivery
  - ``wh_``    : webhook 订阅
  - ``mig_``   : 迁移任务

ID 主体: 字母数字 + 下划线, 长度 4..64 (含 4 是为了避免太短易冲突)。

这是**专用**校验器, 仅用于异步任务 ID。 通用资源 ID 仍用
``api._common.validators.validate_id`` (R1)。

错误信息中文化 + 含字段名 (G4)。
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

TASK_ID_PATTERN = re.compile(
    r"^(task|job|batch|run|del|wh|mig)_[a-zA-Z0-9_]{4,64}$"
)


def validate_task_id(value: str, name: str = "task_id") -> str:
    """校验异步任务 ID 格式。

    接受 ``task_`` / ``job_`` / ``batch_`` / ``run_`` / ``del_`` / ``wh_`` /
    ``mig_`` 前缀, 后跟 4-64 位 [a-zA-Z0-9_]。

    失败 raise HTTPException(400)。
    """
    if not isinstance(value, str) or not value:
        raise HTTPException(400, f"{name} 不能为空")
    if TASK_ID_PATTERN.match(value):
        return value
    raise HTTPException(
        400,
        f"{name} 格式非法: {value!r}, 应匹配 ^(task|job|batch|run|del|wh|mig)_"
        f"[a-zA-Z0-9_]{{4,64}}$",
    )
