"""文件上传校验 — R2-3 Worker 产物, 单文件 < 50 行

调用 ``check_upload(file, max_size, allowed)`` 在 handler 内 await file.read()
之前对 UploadFile 做大小 + Content-Type 校验, 失败 raise HTTPException。

白名单常量 (ALLOWED_AUDIO_TYPES 等) 来自 upload_types.py。
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException, UploadFile

from .upload_types import (
    ALLOWED_AUDIO_TYPES,
    ALLOWED_DOC_TYPES,
    ALLOWED_IMAGE_TYPES,
    ALLOWED_VIDEO_TYPES,
)

# 默认上限: 100MB (worker 可按 endpoint 调小)
DEFAULT_MAX_SIZE = 100 * 1024 * 1024
DEFAULT_IMAGE_MAX_SIZE = 10 * 1024 * 1024
DEFAULT_DOC_MAX_SIZE = 20 * 1024 * 1024

__all__ = [
    "ALLOWED_AUDIO_TYPES", "ALLOWED_DOC_TYPES", "ALLOWED_IMAGE_TYPES",
    "ALLOWED_VIDEO_TYPES", "DEFAULT_DOC_MAX_SIZE", "DEFAULT_IMAGE_MAX_SIZE",
    "DEFAULT_MAX_SIZE", "check_upload",
]


async def check_upload(
    file: UploadFile,
    max_size: int = DEFAULT_MAX_SIZE,
    allowed: Optional[Iterable[str]] = None,
    field_name: str = "file",
) -> UploadFile:
    """校验 UploadFile: 大小 + Content-Type, 失败 raise HTTPException。

    异常: HTTPException(413) — 文件过大; HTTPException(400) — Content-Type 不在白名单。
    """
    # 1. 大小检查 (content-length 头)
    if file.size is not None and file.size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大: 字段 {field_name} 大小 {file.size} 字节超过上限 {max_size} 字节",
        )

    # 2. Content-Type 白名单
    if allowed is not None:
        allowed_set = set(allowed)
        if file.content_type not in allowed_set:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的 Content-Type: 字段 {field_name} 收到 {file.content_type!r}",
            )

    return file
