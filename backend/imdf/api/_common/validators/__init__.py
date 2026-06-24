"""validators 子包入口 — 重新导出 R1 + R2-3 工具

外部代码继续 `from api._common.validators import validate_id, ...` 即可使用。
"""
from __future__ import annotations

# R1 兼容导出
from .id import ID_PATTERN, validate_id, validate_id_dep
from .shared import SAFE_INT, safe_int, safe_path

# R2-3 新增
from .upload_types import (
    ALLOWED_AUDIO_TYPES,
    ALLOWED_DOC_TYPES,
    ALLOWED_IMAGE_TYPES,
    ALLOWED_VIDEO_TYPES,
)
from .upload import (
    DEFAULT_DOC_MAX_SIZE,
    DEFAULT_IMAGE_MAX_SIZE,
    DEFAULT_MAX_SIZE,
    check_upload,
)
from .image_path import ImagePathValidator

# R1 旧名兼容 (有些早期代码可能用过 safe_id 别名)
safe_id = validate_id

__all__ = [
    # id
    "ID_PATTERN", "validate_id", "validate_id_dep", "safe_id",
    # shared
    "SAFE_INT", "safe_int", "safe_path",
    # upload
    "ALLOWED_AUDIO_TYPES", "ALLOWED_DOC_TYPES", "ALLOWED_IMAGE_TYPES",
    "ALLOWED_VIDEO_TYPES", "DEFAULT_DOC_MAX_SIZE", "DEFAULT_IMAGE_MAX_SIZE",
    "DEFAULT_MAX_SIZE", "check_upload",
    # image_path
    "ImagePathValidator",
]
