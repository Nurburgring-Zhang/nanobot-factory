"""通用输入校验工具 — pytest 单元测试
======================================

测试覆盖:
  - validate_id  : 合法 / 注入 / emoji / 空 / 超长 / 非字符串
  - safe_int     : int / str-int / 异常输入 / 边界
  - safe_path    : 合法 / 路径穿越 / 绝对路径

每个测试都断言 HTTPException(400) 在非法输入时被触发, 合法输入原样返回。
"""
from pathlib import Path

import pytest
from fastapi import HTTPException

import sys

# 直接添加 imdf 到 sys.path, 避免依赖 pytest.ini 的 pythonpath
_IMDF_ROOT = Path(__file__).resolve().parent.parent.parent / "backend" / "imdf"
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

from api._common.validators import validate_id, safe_int, safe_path, ID_PATTERN, SAFE_INT  # noqa: E402


# ─────────────────────────── validate_id ──────────────────────────────────


class TestValidateId:
    """validate_id 测试组"""

    def test_valid_simple(self):
        """合法 ID:字母+数字+下划线"""
        assert validate_id("img_001") == "img_001"

    def test_valid_with_hyphen(self):
        """合法 ID:含连字符"""
        assert validate_id("ep-0001-A") == "ep-0001-A"

    def test_valid_min_length(self):
        """边界:1 字符 ID"""
        assert validate_id("a") == "a"

    def test_sql_injection_rejected(self):
        """SQL 注入: 经典 'OR 1=1' 必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id("OR 1=1", "episode_id")
        assert exc_info.value.status_code == 400
        assert "episode_id" in exc_info.value.detail

    def test_drop_table_rejected(self):
        """SQL 注入: 'DROP TABLE' 含空格, 必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id("DROP TABLE", "image_id")
        assert exc_info.value.status_code == 400

    def test_emoji_rejected(self):
        """Emoji: '💥' (4 字节 UTF-8) 必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id("💥", "element_id")
        assert exc_info.value.status_code == 400

    def test_empty_rejected(self):
        """空字符串必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id("", "id")
        assert exc_info.value.status_code == 400

    def test_too_long_rejected(self):
        """129 字符 (超过 128 上限) 必须 400"""
        long_id = "a" * 129
        with pytest.raises(HTTPException) as exc_info:
            validate_id(long_id, "id")
        assert exc_info.value.status_code == 400

    def test_non_string_rejected(self):
        """非字符串(int) 必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id(123, "id")
        assert exc_info.value.status_code == 400
        assert "must be a string" in exc_info.value.detail

    def test_none_rejected(self):
        """None 输入必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id(None, "id")
        assert exc_info.value.status_code == 400

    def test_path_traversal_rejected(self):
        """路径穿越: '../../etc/passwd' 含 / 必须 400"""
        with pytest.raises(HTTPException) as exc_info:
            validate_id("../../etc/passwd", "id")
        assert exc_info.value.status_code == 400


# ─────────────────────────── safe_int ─────────────────────────────────────


class TestSafeInt:
    """safe_int 测试组"""

    def test_int_input(self):
        """int 输入原样返回"""
        assert safe_int(42) == 42

    def test_string_int_input(self):
        """'42' 解析为 42"""
        assert safe_int("42") == 42

    def test_negative_default(self):
        """异常输入回退到 default"""
        assert safe_int("not_a_number", default=-1) == -1

    def test_none_default(self):
        """None 回退到 default"""
        assert safe_int(None, default=0) == 0

    def test_float_with_default(self):
        """'abc' 不能转 int, 回退 default"""
        assert safe_int("abc", default=99) == 99

    def test_overflow_falls_back(self):
        """超大字符串触发异常, 回退 default"""
        # Python int() 对大整数不抛 OverflowError, 但 float("inf") 会触发
        assert safe_int(float("inf"), default=42) == 42
        # NaN 也触发 ValueError
        assert safe_int(float("nan"), default=42) == 42
        # 字符串形式的"无穷大"也触发 ValueError
        assert safe_int("not_a_number_at_all", default=42) == 42


# ─────────────────────────── safe_path ────────────────────────────────────


class TestSafePath:
    """safe_path 测试组 — 防 path traversal"""

    def test_legitimate_subpath(self, tmp_path: Path):
        """合法子路径解析成功, 仍在 base_dir 下"""
        result = safe_path("subdir/file.txt", tmp_path)
        # 解析后必须在 tmp_path 之下
        assert tmp_path.resolve() in result.parents

    def test_traversal_blocked(self, tmp_path: Path):
        """'../escape' 触发 400"""
        with pytest.raises(HTTPException) as exc_info:
            safe_path("../escape.txt", tmp_path)
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

    def test_absolute_traversal_blocked(self, tmp_path: Path):
        """绝对路径在 base_dir 之外时也拒绝"""
        with pytest.raises(HTTPException) as exc_info:
            safe_path(str(Path("/etc/passwd")), tmp_path)
        assert exc_info.value.status_code == 400

    def test_legitimate_filename(self, tmp_path: Path):
        """纯文件名(无 /) 也合法"""
        result = safe_path("only_filename.txt", tmp_path)
        assert result.name == "only_filename.txt"
        assert result.is_absolute()


# ─────────────────────────── 常量 / 模式 ──────────────────────────────────


class TestModuleConstants:
    """ID_PATTERN 与 SAFE_INT 常量"""

    def test_id_pattern_format(self):
        """ID_PATTERN 必须符合预期"""
        assert ID_PATTERN.pattern == r"^[a-zA-Z0-9_\-]{1,128}$"

    def test_safe_int_range(self):
        """SAFE_INT 必须覆盖 0..2**31-1"""
        assert SAFE_INT["ge"] == 0
        assert SAFE_INT["le"] == 2**31 - 1
