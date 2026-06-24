"""R2 验证器模块测试 (验证 R2 worker 写的 8 个验证器 + 6 个辅助模块)

不启动 FastAPI app, 直接测验证器逻辑
"""
import sys
from pathlib import Path


def _setup_paths():
    _IMDF_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/imdf
    _BACKEND_ROOT = str(_IMDF_ROOT.parent)
    sys.path[:] = [p for p in sys.path if p != _BACKEND_ROOT]
    if str(_IMDF_ROOT) not in sys.path:
        sys.path.insert(0, str(_IMDF_ROOT))


_setup_paths()

import pytest
from fastapi import HTTPException


# ============================================================
# R2 validators/id.py (从 validators/ 子包)
# ============================================================


class TestR2ValidatorsId:
    def test_001_validate_id_legal(self):
        from imdf.api._common.validators import validate_id
        assert validate_id("img_001") == "img_001"
        assert validate_id("ep-0001", "episode_id") == "ep-0001"

    def test_002_validate_id_rejects(self):
        from imdf.api._common.validators import validate_id
        for bad in ["", "a" * 200, "abc/def", "💥", "../etc"]:
            with pytest.raises(HTTPException):
                validate_id(bad)

    def test_003_validate_id_dep_exists(self):
        from imdf.api._common.validators import validate_id_dep
        dep = validate_id_dep("image_id")
        assert callable(dep)
        assert dep.__name__ == "validate_image_id_dep"


# ============================================================
# R2 validators/upload.py + upload_types.py
# ============================================================


class TestR2UploadValidator:
    def test_010_size_constants(self):
        from imdf.api._common.validators import (
            DEFAULT_MAX_SIZE, DEFAULT_IMAGE_MAX_SIZE, DEFAULT_DOC_MAX_SIZE
        )
        assert DEFAULT_MAX_SIZE == 100 * 1024 * 1024
        assert DEFAULT_IMAGE_MAX_SIZE == 10 * 1024 * 1024
        assert DEFAULT_DOC_MAX_SIZE == 20 * 1024 * 1024

    def test_011_allowed_types(self):
        from imdf.api._common.validators import (
            ALLOWED_IMAGE_TYPES, ALLOWED_VIDEO_TYPES,
            ALLOWED_AUDIO_TYPES, ALLOWED_DOC_TYPES,
        )
        assert "image/jpeg" in ALLOWED_IMAGE_TYPES
        assert "video/mp4" in ALLOWED_VIDEO_TYPES
        assert "audio/mpeg" in ALLOWED_AUDIO_TYPES
        assert "application/pdf" in ALLOWED_DOC_TYPES

    @pytest.mark.asyncio
    async def test_012_check_upload_rejects_oversize(self):
        from imdf.api._common.validators import check_upload
        from starlette.datastructures import UploadFile as StarletteUploadFile
        # 模拟 UploadFile, size > max
        big_size = 200 * 1024 * 1024  # 200MB
        f = StarletteUploadFile(
            filename="big.jpg", file=open(__file__, "rb"),
            size=big_size, headers={"content-type": "image/jpeg"},
        )
        with pytest.raises(HTTPException) as exc:
            await check_upload(f, max_size=100 * 1024 * 1024)
        assert exc.value.status_code == 413

    @pytest.mark.asyncio
    async def test_013_check_upload_rejects_bad_type(self):
        from imdf.api._common.validators import check_upload
        from starlette.datastructures import UploadFile as StarletteUploadFile
        f = StarletteUploadFile(
            filename="x.exe", file=open(__file__, "rb"),
            size=1024, headers={"content-type": "application/x-msdownload"},
        )
        with pytest.raises(HTTPException) as exc:
            await check_upload(f, allowed=["image/jpeg", "image/png"])
        assert exc.value.status_code == 400


# ============================================================
# R2 validators/image_path.py
# ============================================================


class TestR2ImagePath:
    def test_020_traversal_blocked(self):
        from imdf.api._common.validators import ImagePathValidator
        with pytest.raises(HTTPException):
            ImagePathValidator("../../etc/passwd", Path("D:/data/images")).validate()

    def test_021_bad_extension_blocked(self):
        from imdf.api._common.validators import ImagePathValidator
        # 文件不存在, 但会先检查后缀
        with pytest.raises(HTTPException) as exc:
            ImagePathValidator("malware.exe", Path("D:/data/images")).validate()
        # 失败原因可能是后缀或不存在
        assert exc.value.status_code == 400

    def test_022_nonexistent_file(self):
        from imdf.api._common.validators import ImagePathValidator
        with pytest.raises(HTTPException):
            ImagePathValidator("notexist.jpg", Path("D:/data/images")).validate()


# ============================================================
# R2 date_range.py
# ============================================================


class TestR2DateRange:
    def test_030_preset_default(self):
        from imdf.api._common.date_range import DateRangeParams
        p = DateRangeParams()
        assert p.preset == "7d"
        assert p.start is not None
        assert p.end is not None
        from datetime import date
        assert p.end == date.today()

    def test_031_custom_valid(self):
        from imdf.api._common.date_range import DateRangeParams
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=7)
        p = DateRangeParams(preset="custom", start=start, end=end)
        assert p.start == start
        assert p.end == end

    def test_032_custom_reversed(self):
        from imdf.api._common.date_range import DateRangeParams
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=7)
        # start > end 应该 422
        with pytest.raises(Exception):  # Pydantic ValidationError
            DateRangeParams(preset="custom", start=end, end=start)

    def test_033_custom_future_end(self):
        from imdf.api._common.date_range import DateRangeParams
        from datetime import date, timedelta
        # 未来日期应该 422
        with pytest.raises(Exception):
            DateRangeParams(
                preset="custom",
                start=date.today() + timedelta(days=1),
                end=date.today() + timedelta(days=10),
            )

    def test_034_custom_too_long_span(self):
        from imdf.api._common.date_range import DateRangeParams
        from datetime import date, timedelta
        with pytest.raises(Exception):
            DateRangeParams(
                preset="custom",
                start=date.today() - timedelta(days=400),
                end=date.today(),
            )


# ============================================================
# R2 pagination_compat.py + granularity.py + dimension.py
# ============================================================


class TestR2PaginationCompat:
    def test_040_imports(self):
        # 验证 R2-W1 写的 pagination_compat 存在
        try:
            from imdf.api._common import pagination_compat  # noqa
        except ImportError as e:
            pytest.fail(f"pagination_compat import failed: {e}")


class TestR2Granularity:
    def test_050_imports(self):
        try:
            from imdf.api._common import granularity  # noqa
        except ImportError as e:
            pytest.fail(f"granularity import failed: {e}")


class TestR2Dimension:
    def test_060_imports(self):
        try:
            from imdf.api._common import dimension  # noqa
        except ImportError as e:
            pytest.fail(f"dimension import failed: {e}")


# ============================================================
# R2 cron_validator + webhook_url_validator + task_id_validator
# ============================================================


class TestR2SchedulerValidators:
    def test_070_cron(self):
        try:
            from imdf.api._common import cron_validator  # noqa
            assert hasattr(cron_validator, "validate_cron")
        except (ImportError, AttributeError) as e:
            pytest.fail(f"cron_validator issue: {e}")

    def test_071_webhook(self):
        try:
            from imdf.api._common import webhook_url_validator  # noqa
            assert hasattr(webhook_url_validator, "validate_webhook_url")
        except (ImportError, AttributeError) as e:
            pytest.fail(f"webhook_url_validator issue: {e}")

    def test_072_task_id(self):
        try:
            from imdf.api._common import task_id_validator  # noqa
            assert hasattr(task_id_validator, "validate_task_id")
        except (ImportError, AttributeError) as e:
            pytest.fail(f"task_id_validator issue: {e}")


# ============================================================
# R2 body_schemas.py
# ============================================================


class TestR2BodySchemas:
    def test_080_body_schemas_imports(self):
        try:
            from imdf.api._common import body_schemas  # noqa
            # body_schemas.py 实际有 200+ Pydantic BaseModel (Crowd/Delivery/IAA/Search 等)
            classes = [n for n in dir(body_schemas) if n[0].isupper() and not n.startswith("_")]
            assert len(classes) >= 30, f"body_schemas 只有 {len(classes)} 个 Pydantic 类"
        except ImportError as e:
            pytest.fail(f"body_schemas import failed: {e}")

    def test_081_body_schemas_class_sample(self):
        """抽样几个 body schema, 验证都是合法 Pydantic"""
        from imdf.api._common import body_schemas
        from pydantic import BaseModel
        # 抽样 IdPayload / CohenKappaRequest / SearchRequest
        for name in ["IdPayload", "CohenKappaRequest", "SearchRequest"]:
            cls = getattr(body_schemas, name, None)
            assert cls is not None, f"{name} 不存在"
            assert issubclass(cls, BaseModel), f"{name} 不是 BaseModel"
