"""R2-Worker-5: 统计 / 报表 / 仪表盘类验证器单测

覆盖:
  - api._common.date_range.DateRangeParams — 22 端点时间范围核心
  - api._common.granularity — 6 个粒度枚举 + 白名单
  - api._common.dimension — scope 维度白名单
"""
import sys
from datetime import date, timedelta
from pathlib import Path

# 路径设置: backend/imdf 放在 sys.path 第一位, 让 from api._common 解析到 imdf/api
_IMDF_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/imdf
sys.path[:] = [p for p in sys.path if str(_IMDF_ROOT) != p]
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api._common.date_range import DateRangeParams, MAX_SPAN_DAYS, DatePreset
from api._common.granularity import (
    Granularity, ALLOWED_GRANULARITIES, MIN_SPAN_DAYS, is_valid_granularity,
)
from api._common.dimension import (
    is_valid_dimension, ALLOWED_DIMENSIONS, COMMON_DIMENSIONS,
)


# ============================================================
# Section 1: DateRangeParams — 22 端点的核心时间范围校验
# ============================================================


class TestDateRangeParams:
    """DateRangeParams 校验 — start/end/preset/start<=end/跨度<=365/无未来/历史窗口"""

    def test_001_preset_1d_resolves_today(self):
        """preset=1d → start=今天, end=今天"""
        dr = DateRangeParams(preset="1d")
        assert dr.end == date.today()
        assert dr.start == date.today()

    def test_002_preset_7d_resolves_week(self):
        """preset=7d → start=6天前, end=今天 (7天窗口含今天)"""
        dr = DateRangeParams(preset="7d")
        assert dr.end == date.today()
        assert dr.start == date.today() - timedelta(days=6)
        assert (dr.end - dr.start).days == 6

    def test_003_preset_30d_resolves_month(self):
        """preset=30d → 30天窗口"""
        dr = DateRangeParams(preset="30d")
        assert (dr.end - dr.start).days == 29  # 30 - 1

    def test_004_preset_90d_resolves_quarter(self):
        """preset=90d → 90天窗口"""
        dr = DateRangeParams(preset="90d")
        assert (dr.end - dr.start).days == 89

    def test_005_preset_1y_resolves_year(self):
        """preset=1y → 365天窗口"""
        dr = DateRangeParams(preset="1y")
        assert (dr.end - dr.start).days == 364

    def test_006_custom_valid_range(self):
        """preset=custom + 合法 start/end"""
        today = date.today()
        dr = DateRangeParams(preset="custom", start=today - timedelta(days=10), end=today)
        assert dr.start == today - timedelta(days=10)
        assert dr.end == today

    def test_007_custom_rejects_start_after_end(self):
        """preset=custom + start>end → HTTPException 400 (start <= end)
        R2.5-W5 修复: model_validator 用 HTTPException 而非 ValueError (FastAPI Depends 兼容)"""
        today = date.today()
        with pytest.raises(HTTPException) as exc:
            DateRangeParams(preset="custom", start=today, end=today - timedelta(days=5))
        assert exc.value.status_code == 400
        assert "必须" in str(exc.value.detail) or "≤" in str(exc.value.detail)

    def test_008_custom_rejects_future_end(self):
        """preset=custom + end>今天 → HTTPException 400"""
        today = date.today()
        with pytest.raises(HTTPException) as exc:
            DateRangeParams(
                preset="custom", start=today, end=today + timedelta(days=7),
            )
        assert exc.value.status_code == 400

    def test_009_custom_rejects_excessive_span(self):
        """preset=custom + 跨度>365 → HTTPException 400"""
        today = date.today()
        with pytest.raises(HTTPException) as exc:
            DateRangeParams(
                preset="custom",
                start=today - timedelta(days=400),
                end=today,
            )
        assert exc.value.status_code == 400
        assert "365" in str(exc.value.detail) or "跨度" in str(exc.value.detail)

    def test_010_custom_requires_both_dates(self):
        """preset=custom 但只给 start → HTTPException 400"""
        with pytest.raises(HTTPException) as exc:
            DateRangeParams(preset="custom", start=date(2024, 1, 1))
        assert exc.value.status_code == 400

    def test_011_invalid_preset_value(self):
        """preset 非法值 → ValidationError (Pydantic Literal)"""
        with pytest.raises(ValidationError):
            DateRangeParams(preset="invalid")

    def test_012_preset_default_is_7d(self):
        """默认 preset='7d'"""
        dr = DateRangeParams()
        assert dr.preset == "7d"
        assert dr.end == date.today()


# ============================================================
# Section 2: Granularity — 6 个粒度枚举
# ============================================================


class TestGranularity:
    """Granularity 枚举 + 白名单函数"""

    def test_020_is_valid_granularity_accepts_six(self):
        for g in ("hour", "day", "week", "month", "quarter", "year"):
            assert is_valid_granularity(g), f"{g} should be valid"

    def test_021_is_valid_granularity_rejects_others(self):
        for g in ("", "min", "second", "5min", "1d", "DAY", "Hour"):
            assert not is_valid_granularity(g), f"{g} should be invalid"

    def test_022_allowed_granularities_is_frozenset(self):
        assert isinstance(ALLOWED_GRANULARITIES, frozenset)
        assert len(ALLOWED_GRANULARITIES) == 6

    def test_023_min_span_days_has_all_keys(self):
        assert set(MIN_SPAN_DAYS.keys()) == ALLOWED_GRANULARITIES
        # sanity: hour 最小跨度 ≤ day ≤ week ≤ month ≤ quarter ≤ year
        assert MIN_SPAN_DAYS["hour"] <= MIN_SPAN_DAYS["day"]
        assert MIN_SPAN_DAYS["day"] < MIN_SPAN_DAYS["week"]
        assert MIN_SPAN_DAYS["week"] < MIN_SPAN_DAYS["month"]
        assert MIN_SPAN_DAYS["month"] < MIN_SPAN_DAYS["quarter"]
        assert MIN_SPAN_DAYS["quarter"] < MIN_SPAN_DAYS["year"]

    def test_024_granularity_type_is_literal(self):
        """Granularity 必须是 Literal[str, str, ...], Pydantic 用作 Query 枚举"""
        from typing import get_args
        args = get_args(Granularity)
        assert set(args) == ALLOWED_GRANULARITIES


# ============================================================
# Section 3: Dimension — scope 维度白名单
# ============================================================


class TestDimension:
    """is_valid_dimension + ALLOWED_DIMENSIONS scope 字典"""

    def test_030_common_dimensions_basics(self):
        for d in ("user", "team", "category", "status", "action", "date"):
            assert d in COMMON_DIMENSIONS

    def test_031_default_scope_accepts_common(self):
        assert is_valid_dimension("user", scope="default")
        assert is_valid_dimension("team", scope="default")
        assert is_valid_dimension("category", scope="default")

    def test_032_default_scope_rejects_specific(self):
        """default scope 拒绝 module 专属字段"""
        assert not is_valid_dimension("metric", scope="default")
        assert not is_valid_dimension("cron_expression", scope="default")

    def test_033_ops_scope_allows_metric(self):
        """ops scope 允许 metric, source"""
        assert is_valid_dimension("metric", scope="ops")
        assert is_valid_dimension("source", scope="ops")

    def test_034_audit_scope_restricts_to_audit_fields(self):
        """audit scope 只允许审计字段"""
        assert is_valid_dimension("method", scope="audit")
        assert is_valid_dimension("path", scope="audit")
        assert not is_valid_dimension("metric", scope="audit")
        assert not is_valid_dimension("worker", scope="audit")

    def test_035_templates_scope_includes_rating_tag(self):
        """templates scope 包含 rating, tag"""
        assert is_valid_dimension("rating", scope="templates")
        assert is_valid_dimension("tag", scope="templates")
        assert not is_valid_dimension("metric", scope="templates")

    def test_036_quality_scope_includes_industry_format(self):
        assert is_valid_dimension("industry", scope="quality")
        assert is_valid_dimension("format", scope="quality")
        assert not is_valid_dimension("metric", scope="quality")

    def test_037_webhook_scope(self):
        assert is_valid_dimension("webhook", scope="webhook")
        assert is_valid_dimension("event", scope="webhook")
        assert not is_valid_dimension("user", scope="webhook")

    def test_038_unknown_scope_falls_back_to_default(self):
        """scope 字典中找不到 → 兜底 default"""
        # 'default' 是有效 key, 测试不存在的 scope
        assert is_valid_dimension("user", scope="does_not_exist") is True
        assert is_valid_dimension("metric", scope="does_not_exist") is False

    def test_039_all_scopes_have_overlap_with_common(self):
        """所有 scope 都应至少包含 1 个 common dimension (放宽到 ≥ 1, 允许 domain-specific scope)"""
        for scope, allowed in ALLOWED_DIMENSIONS.items():
            if scope == "default":
                continue
            overlap = allowed & COMMON_DIMENSIONS
            assert len(overlap) >= 1, f"{scope} 与 common 无交集: {overlap}"

    def test_040_sql_injection_dimension_rejected(self):
        """SQL 注入式 dimension 全部拒绝"""
        for bad in ("user.password", "users.email", "1=1", "user; DROP TABLE", "*"):
            for scope in ["default", "ops", "audit", "templates", "quality"]:
                assert not is_valid_dimension(bad, scope=scope), (
                    f"scope={scope} 应该拒绝 {bad!r}"
                )

    def test_041_dimension_empty_string_rejected(self):
        for scope in ALLOWED_DIMENSIONS:
            assert not is_valid_dimension("", scope=scope)


# ============================================================
# Section 4: 集成 — 模拟 FastAPI Query 注入, 端到端验证
# ============================================================


class TestIntegrationWithFastAPI:
    """模拟 FastAPI 把 Pydantic 模型当作 Query/Body 注入"""

    def test_050_date_range_preset_serializes_to_dict(self):
        """DateRangeParams.model_dump() 含 start/end/preset (preset 模式)"""
        dr = DateRangeParams(preset="30d")
        d = dr.model_dump()
        assert d["preset"] == "30d"
        # model_dump() 默认返回 date 对象 (非 str); 用 mode="json" 转字符串
        d_json = dr.model_dump(mode="json")
        assert d_json["end"] == date.today().isoformat()
        assert d_json["start"] == (date.today() - timedelta(days=29)).isoformat()

    def test_051_date_range_custom_serializes_correctly(self):
        today = date.today()
        dr = DateRangeParams(preset="custom", start=today - timedelta(days=7), end=today)
        d = dr.model_dump(mode="json")
        assert d["preset"] == "custom"
        assert d["start"] == (today - timedelta(days=7)).isoformat()
        assert d["end"] == today.isoformat()

    def test_052_granularity_passes_pydantic_validation(self):
        """Granularity 走 Pydantic str 验证 — 非法值 422"""
        from pydantic import BaseModel, Field
        class M(BaseModel):
            g: Granularity = Field(..., description="粒度")
        m = M(g="day")
        assert m.g == "day"
        with pytest.raises(ValidationError):
            M(g="invalid")
