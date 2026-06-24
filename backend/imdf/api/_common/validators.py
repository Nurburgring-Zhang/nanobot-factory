"""通用输入校验工具 — 防止 bad_params 触发崩溃 (R1 + R2-3 扩展)

本文件为 R1 兼容 shim — 实际实现已迁移到 ``validators/`` 子包:

  - validate_id / ID_PATTERN / validate_id_dep  →  validators.id
  - safe_int / safe_path / SAFE_INT              →  validators.shared
  - check_upload / 内容类型白名单                →  validators.upload (R2-3)
  - ImagePathValidator                           →  validators.image_path (R2-3)

外部代码继续 ``from api._common.validators import validate_id, ...`` 即可。
"""
from __future__ import annotations

from .validators import (  # noqa: F401, F403
    ID_PATTERN,
    SAFE_INT,
    ALLOWED_AUDIO_TYPES,
    ALLOWED_DOC_TYPES,
    ALLOWED_IMAGE_TYPES,
    ALLOWED_VIDEO_TYPES,
    DEFAULT_DOC_MAX_SIZE,
    DEFAULT_IMAGE_MAX_SIZE,
    DEFAULT_MAX_SIZE,
    ImagePathValidator,
    check_upload,
    safe_int,
    safe_path,
    validate_id,
    validate_id_dep,
)

# R1 旧名兼容
safe_id = validate_id

__all__ = [  # noqa: F405
    "ID_PATTERN",
    "SAFE_INT",
    "ALLOWED_AUDIO_TYPES",
    "ALLOWED_DOC_TYPES",
    "ALLOWED_IMAGE_TYPES",
    "ALLOWED_VIDEO_TYPES",
    "DEFAULT_DOC_MAX_SIZE",
    "DEFAULT_IMAGE_MAX_SIZE",
    "DEFAULT_MAX_SIZE",
    "ImagePathValidator",
    "check_upload",
    "safe_id",
    "safe_int",
    "safe_path",
    "validate_id",
    "validate_id_dep",
]
