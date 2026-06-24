# -*- coding: utf-8 -*-
"""R2-3 新增 validators 单元测试 (test_validators_upload)

覆盖:
  - check_upload 合法/非法 Content-Type
  - check_upload 超大文件拦截
  - check_upload 字段名出现在错误信息
  - ALLOWED_AUDIO_TYPES / IMAGE / VIDEO / DOC 白名单常量
  - ImagePathValidator 路径合法 / traversal / 越界
  - ImagePathValidator 后缀白名单
  - ImagePathValidator 不存在 / 不可读
"""
import os
import sys
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock


def _setup_paths():
    """把 imdf/ 加到 sys.path, 同时移除 backend/ 以避免 backend/api/ 抢匹配 `api` 包."""
    _IMDF_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/imdf
    _BACKEND_ROOT = str(_IMDF_ROOT.parent)
    sys.path[:] = [p for p in sys.path if p != _BACKEND_ROOT]
    if str(_IMDF_ROOT) not in sys.path:
        sys.path.insert(0, str(_IMDF_ROOT))


_setup_paths()

from fastapi import HTTPException
from imdf.api._common.validators import (
    check_upload,
    ImagePathValidator,
    ALLOWED_AUDIO_TYPES,
    ALLOWED_IMAGE_TYPES,
    ALLOWED_VIDEO_TYPES,
    ALLOWED_DOC_TYPES,
    DEFAULT_MAX_SIZE,
    DEFAULT_IMAGE_MAX_SIZE,
    DEFAULT_DOC_MAX_SIZE,
)


# ============================================================
# Section 1: 内容类型白名单常量
# ============================================================


class TestContentTypeWhitelists:
    def test_001_audio_types_contains_common(self):
        assert "audio/mpeg" in ALLOWED_AUDIO_TYPES
        assert "audio/wav" in ALLOWED_AUDIO_TYPES
        assert "audio/x-wav" in ALLOWED_AUDIO_TYPES
        assert "audio/ogg" in ALLOWED_AUDIO_TYPES
        assert "audio/flac" in ALLOWED_AUDIO_TYPES

    def test_002_image_types_contains_common(self):
        assert "image/jpeg" in ALLOWED_IMAGE_TYPES
        assert "image/png" in ALLOWED_IMAGE_TYPES
        assert "image/webp" in ALLOWED_IMAGE_TYPES

    def test_003_video_types_contains_common(self):
        assert "video/mp4" in ALLOWED_VIDEO_TYPES
        assert "video/webm" in ALLOWED_VIDEO_TYPES

    def test_004_doc_types_contains_common(self):
        assert "application/pdf" in ALLOWED_DOC_TYPES
        assert "text/csv" in ALLOWED_DOC_TYPES

    def test_005_default_size_limits_reasonable(self):
        # DEFAULT_MAX_SIZE 应该是 100MB
        assert DEFAULT_MAX_SIZE == 100 * 1024 * 1024
        # DEFAULT_IMAGE_MAX_SIZE 应该是 10MB
        assert DEFAULT_IMAGE_MAX_SIZE == 10 * 1024 * 1024
        # DEFAULT_DOC_MAX_SIZE 应该是 20MB
        assert DEFAULT_DOC_MAX_SIZE == 20 * 1024 * 1024


# ============================================================
# Section 2: check_upload — Content-Type 校验
# ============================================================


def _make_upload_file(content_type: str, size: int = None, filename: str = "test.dat"):
    """构造一个 mock UploadFile."""
    f = MagicMock()
    f.content_type = content_type
    f.size = size
    f.filename = filename
    return f


class TestCheckUploadContentType:
    @pytest.mark.asyncio
    async def test_010_check_upload_accepts_allowed(self):
        f = _make_upload_file("audio/mpeg", size=1024)
        out = await check_upload(f, allowed=ALLOWED_AUDIO_TYPES)
        assert out is f  # 原样返回

    @pytest.mark.asyncio
    async def test_011_check_upload_rejects_disallowed(self):
        f = _make_upload_file("application/x-msdownload")  # .exe
        with pytest.raises(HTTPException) as exc:
            await check_upload(f, allowed=ALLOWED_AUDIO_TYPES)
        assert exc.value.status_code == 400
        assert "Content-Type" in exc.value.detail

    @pytest.mark.asyncio
    async def test_012_check_upload_rejects_text_when_audio_required(self):
        f = _make_upload_file("text/plain")
        with pytest.raises(HTTPException) as exc:
            await check_upload(f, allowed=ALLOWED_AUDIO_TYPES)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_013_check_upload_no_allowed_passes(self):
        # 不传 allowed 就不检查 Content-Type
        f = _make_upload_file("application/octet-stream", size=100)
        out = await check_upload(f)
        assert out is f

    @pytest.mark.asyncio
    async def test_014_check_upload_error_includes_field_name(self):
        f = _make_upload_file("text/plain")
        with pytest.raises(HTTPException) as exc:
            await check_upload(f, allowed=ALLOWED_AUDIO_TYPES, field_name="audio")
        assert "audio" in exc.value.detail


# ============================================================
# Section 3: check_upload — Size 校验
# ============================================================


class TestCheckUploadSize:
    @pytest.mark.asyncio
    async def test_020_check_upload_rejects_oversize(self):
        f = _make_upload_file("audio/mpeg", size=200 * 1024 * 1024)  # 200MB
        with pytest.raises(HTTPException) as exc:
            await check_upload(f, max_size=100 * 1024 * 1024)  # 100MB 上限
        assert exc.value.status_code == 413
        assert "过大" in exc.value.detail

    @pytest.mark.asyncio
    async def test_021_check_upload_accepts_undersize(self):
        f = _make_upload_file("audio/mpeg", size=1024)  # 1KB
        out = await check_upload(f, max_size=100 * 1024 * 1024)
        assert out is f

    @pytest.mark.asyncio
    async def test_022_check_upload_none_size_passes(self):
        # size 为 None (client 未传 Content-Length) 应不报错
        f = _make_upload_file("audio/mpeg", size=None)
        out = await check_upload(f, max_size=100)
        assert out is f


# ============================================================
# Section 4: ImagePathValidator
# ============================================================


class TestImagePathValidator:
    def test_030_image_path_accepts_legit(self, tmp_path):
        # 在 tmp_path 下创建一个合法图片文件
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")  # 假 JPEG 头
        v = ImagePathValidator("test.jpg", base_dir=tmp_path)
        result = v.validate()
        assert result == str(img.resolve())

    def test_031_image_path_blocks_traversal(self, tmp_path):
        v = ImagePathValidator("../../etc/passwd", base_dir=tmp_path)
        with pytest.raises(HTTPException) as exc:
            v.validate()
        assert exc.value.status_code == 400
        assert "越界" in exc.value.detail

    def test_032_image_path_rejects_bad_ext(self, tmp_path):
        # 文件存在但后缀不在白名单
        bad = tmp_path / "test.exe"
        bad.write_bytes(b"MZ")
        v = ImagePathValidator("test.exe", base_dir=tmp_path)
        with pytest.raises(HTTPException) as exc:
            v.validate()
        assert exc.value.status_code == 400
        assert "格式不支持" in exc.value.detail

    def test_033_image_path_rejects_missing_file(self, tmp_path):
        v = ImagePathValidator("notexist.jpg", base_dir=tmp_path)
        with pytest.raises(HTTPException) as exc:
            v.validate()
        assert exc.value.status_code == 400
        assert "不存在" in exc.value.detail

    def test_034_image_path_rejects_subdir_traversal(self, tmp_path):
        # 试图访问 base_dir 之外的子目录
        v = ImagePathValidator("../sibling.jpg", base_dir=tmp_path)
        with pytest.raises(HTTPException) as exc:
            v.validate()
        assert exc.value.status_code == 400

    def test_035_image_path_accepts_png_webp(self, tmp_path):
        for ext in ["png", "webp", "gif", "bmp", "tiff"]:
            img = tmp_path / f"test.{ext}"
            img.write_bytes(b"x")
            v = ImagePathValidator(f"test.{ext}", base_dir=tmp_path)
            result = v.validate()
            assert result.endswith(f"test.{ext}")


# ============================================================
# Section 5: 与 R1 兼容
# ============================================================


class TestBackwardCompat:
    def test_040_validate_id_still_importable(self):
        # R1 引入的 validate_id 必须仍可用
        from imdf.api._common.validators import validate_id, safe_int, safe_path, ID_PATTERN
        assert validate_id("img_001") == "img_001"
        with pytest.raises(HTTPException):
            validate_id("../etc/passwd")
        assert safe_int("42") == 42
        assert ID_PATTERN.match("img_001") is not None

    def test_041_legacy_shim_module_path(self):
        # 旧路径 imdf.api._common.validators (作为 shim) 也能用
        from imdf.api._common import validators as shim_module
        assert hasattr(shim_module, "validate_id")
        assert hasattr(shim_module, "check_upload")
        assert hasattr(shim_module, "ImagePathValidator")
