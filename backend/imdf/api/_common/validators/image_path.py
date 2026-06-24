"""图片路径校验 — R2-3 Worker 产物, 单文件 < 50 行

提供 ImagePathValidator 类: 校验图片路径合法 + 存在 + 可读 + 在 base_dir 之下。

典型用途: GET /api/v1/preview/{file_path:path} 等用户传路径的端点。
"""
from __future__ import annotations

import os
from pathlib import Path
from fastapi import HTTPException


class ImagePathValidator:
    """校验图片路径: 防 traversal + 后缀白名单 + 存在 + 可读。

    使用:
        v = ImagePathValidator(value, base_dir=Path("/data/images"))
        safe = v.validate()  # 返回 str 绝对路径, 失败 raise HTTPException(400)
    """

    ALLOWED_EXTS: set = {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff",
    }

    def __init__(self, value: str, base_dir: Path):
        self.value = value
        self.base_dir = base_dir

    def validate(self) -> str:
        # 1. 防 traversal
        base = self.base_dir.resolve()
        try:
            candidate = (base / self.value).resolve()
            candidate.relative_to(base)  # 必须在 base 之下
        except (ValueError, OSError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"图片路径越界: {self.value!r} 不在 {base} 之下 ({exc})",
            )

        # 2. 后缀白名单
        if candidate.suffix.lower() not in self.ALLOWED_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"图片格式不支持: {candidate.suffix!r} (允许: {sorted(self.ALLOWED_EXTS)})",
            )

        # 3. 存在 + 可读
        if not candidate.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"图片不存在或不是文件: {candidate}",
            )
        if not os.access(candidate, os.R_OK):
            raise HTTPException(
                status_code=400,
                detail=f"图片不可读 (权限不足): {candidate}",
            )

        return str(candidate)
