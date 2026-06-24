"""文件类型白名单 — R2-3 拆分自 upload.py, 单文件 < 50 行

按内容大类分组:
  - ALLOWED_AUDIO_TYPES  mp3 / wav / ogg / flac / m4a / aac
  - ALLOWED_IMAGE_TYPES  jpg / png / webp / gif / bmp / tiff
  - ALLOWED_VIDEO_TYPES  mp4 / webm / mov / avi
  - ALLOWED_DOC_TYPES    pdf / json / txt / csv / xlsx / xls
"""
from __future__ import annotations

ALLOWED_AUDIO_TYPES: frozenset = frozenset({
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg",
    "audio/flac", "audio/mp4", "audio/aac",
})

ALLOWED_IMAGE_TYPES: frozenset = frozenset({
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/gif", "image/bmp", "image/tiff",
})

ALLOWED_VIDEO_TYPES: frozenset = frozenset({
    "video/mp4", "video/webm", "video/quicktime", "video/x-msvideo",
})

ALLOWED_DOC_TYPES: frozenset = frozenset({
    "application/pdf", "application/json", "text/plain", "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
})
