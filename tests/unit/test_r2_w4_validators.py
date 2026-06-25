"""R2-Worker-4 新增验证器 — pytest 单元测试
====================================

覆盖:
  - validate_cron         : 合法 / 越界 / 步长 / 步长边界 / 字段数
  - validate_trigger_config : cron/interval/date 各分支 + 错误
  - validate_webhook_url  : 合法 / SSRF (私网/回环/metadata/字面 hostname)
  - validate_task_id      : 合法 7 种命名空间 / 越界 / 非法字符
  - SchedulerHistoryParams: 分页 + 日期 + status 枚举
  - PaginationParams      : 通用分页 (兼容)

错误信息中文化 + 含字段名 (G4)。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

# 添加 imdf 到 sys.path
_IMDF_ROOT = Path(__file__).resolve().parent.parent.parent / "backend" / "imdf"
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

from api._common.cron_validator import validate_cron, validate_trigger_config  # noqa: E402
from api._common.webhook_url_validator import validate_webhook_url  # noqa: E402
from api._common.task_id_validator import validate_task_id  # noqa: E402
from api._common.scheduler_validators import SchedulerHistoryParams  # noqa: E402
from api._common.pagination_compat import PaginationParams  # noqa: E402


# ─────────────────────────── validate_cron ─────────────────────────────────


class TestValidateCron:
    """validate_cron 测试组"""

    def test_valid_simple(self):
        """标准 cron: 0 3 * * *"""
        assert validate_cron("0 3 * * *") == "0 3 * * *"

    def test_valid_with_step(self):
        """步长: */5 9-17 * * 1-5"""
        assert validate_cron("*/5 9-17 * * 1-5") == "*/5 9-17 * * 1-5"

    def test_valid_with_step_in_range(self):
        """范围 + 步长: 1-30/5"""
        assert validate_cron("0 0 1-30/5 * *") == "0 0 1-30/5 * *"

    def test_valid_wildcard_all(self):
        """通配符"""
        assert validate_cron("* * * * *") == "* * * * *"

    def test_valid_list(self):
        """列表: 1,15 * * * *"""
        assert validate_cron("1,15,45 * * * *") == "1,15,45 * * * *"

    def test_hour_out_of_range(self):
        """hour=25 越界 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("0 25 * * *")
        assert exc.value.status_code == 400
        assert "hour" in exc.value.detail

    def test_minute_out_of_range(self):
        """minute=60 越界 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("60 * * * *")
        assert exc.value.status_code == 400
        assert "minute" in exc.value.detail

    def test_month_out_of_range(self):
        """month=13 越界 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("0 0 1 13 *")
        assert exc.value.status_code == 400
        assert "month" in exc.value.detail

    def test_dow_out_of_range(self):
        """day_of_week=7 越界 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("0 0 * * 7")
        assert exc.value.status_code == 400
        assert "day_of_week" in exc.value.detail

    def test_wrong_field_count(self):
        """3 字段 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("* * *")
        assert exc.value.status_code == 400
        assert "5 字段" in exc.value.detail

    def test_empty(self):
        """空字符串 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("")
        assert exc.value.status_code == 400
        assert "不能为空" in exc.value.detail

    def test_none(self):
        """None → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_cron(None)
        assert exc.value.status_code == 400

    def test_garbage_field(self):
        """非法 token: 'abc'"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("abc * * * *")
        assert exc.value.status_code == 400

    def test_range_inverted(self):
        """a > b 在范围中"""
        with pytest.raises(HTTPException) as exc:
            validate_cron("0 0 5-1 * *")
        assert exc.value.status_code == 400


# ─────────────────────────── validate_trigger_config ───────────────────────


class TestValidateTriggerConfig:
    """validate_trigger_config 测试组"""

    def test_cron_valid(self):
        out = validate_trigger_config("cron", {"cron_expression": "0 3 * * *"})
        assert out == "0 3 * * *"

    def test_cron_missing_expression(self):
        """cron 类型但缺 cron_expression → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("cron", {})
        assert exc.value.status_code == 400
        assert "cron_expression" in exc.value.detail

    def test_cron_bad_expression(self):
        """cron 表达式非法 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("cron", {"cron_expression": "bad cron"})
        assert exc.value.status_code == 400

    def test_interval_valid_hours(self):
        out = validate_trigger_config("interval", {"hours": 2})
        assert out == "interval"

    def test_interval_valid_multiple(self):
        out = validate_trigger_config("interval", {"minutes": 30, "hours": 1})
        assert out == "interval"

    def test_interval_empty(self):
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("interval", {})
        assert exc.value.status_code == 400

    def test_interval_zero_value(self):
        """hours=0 拒绝"""
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("interval", {"hours": 0})
        assert exc.value.status_code == 400

    def test_interval_negative_value(self):
        """days=-1 拒绝"""
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("interval", {"days": -1})
        assert exc.value.status_code == 400

    def test_date_valid(self):
        out = validate_trigger_config("date", {"run_date": "2025-01-01T00:00:00"})
        assert out == "date"

    def test_date_missing_run_date(self):
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("date", {})
        assert exc.value.status_code == 400

    def test_unknown_trigger_type(self):
        with pytest.raises(HTTPException) as exc:
            validate_trigger_config("daily", {})
        assert exc.value.status_code == 400
        assert "cron/interval/date" in exc.value.detail


# ─────────────────────────── validate_webhook_url ──────────────────────────


class TestValidateWebhookUrl:
    """validate_webhook_url 测试组 — 包含 SSRF 防护"""

    def test_valid_https(self):
        assert validate_webhook_url("https://example.com/webhook") == \
            "https://example.com/webhook"

    def test_valid_http(self):
        assert validate_webhook_url("http://example.com/hook") == \
            "http://example.com/hook"

    def test_valid_with_port(self):
        assert validate_webhook_url("http://example.com:8080/hook") == \
            "http://example.com:8080/hook"

    def test_empty(self):
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("")
        assert exc.value.status_code == 400

    def test_too_long(self):
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("https://example.com/" + "a" * 3000)
        assert exc.value.status_code == 400

    def test_invalid_scheme(self):
        """ftp 拒绝"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("ftp://example.com/file")
        assert exc.value.status_code == 400
        assert "scheme" in exc.value.detail

    def test_file_scheme_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("file:///etc/passwd")
        assert exc.value.status_code == 400

    def test_localhost_rejected(self):
        """localhost 字面 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://localhost/webhook")
        assert exc.value.status_code == 400
        assert "禁用" in exc.value.detail or "SSRF" in exc.value.detail

    def test_localhost_localdomain_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://localhost.localdomain/")

    def test_private_ip_v4_rejected(self):
        """192.168.1.1 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://192.168.1.1/webhook")
        assert exc.value.status_code == 400
        assert "私网" in exc.value.detail

    def test_private_ip_10_rejected(self):
        """10.0.0.1 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://10.0.0.1/")

    def test_loopback_ip_rejected(self):
        """127.0.0.1 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://127.0.0.1/")

    def test_link_local_rejected(self):
        """169.254.169.254 (AWS metadata) → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://169.254.169.254/latest/meta-data/")
        assert exc.value.status_code == 400

    def test_unspecified_ip_rejected(self):
        """0.0.0.0 → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://0.0.0.0/")

    def test_gcp_metadata_rejected(self):
        """metadata.google.internal → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_no_hostname(self):
        """空 hostname → 400"""
        with pytest.raises(HTTPException) as exc:
            validate_webhook_url("http://")
        assert exc.value.status_code == 400


# ─────────────────────────── validate_task_id ──────────────────────────────


class TestValidateTaskId:
    """validate_task_id 测试组"""

    @pytest.mark.parametrize("tid", [
        "task_abc12345",
        "task_abcdefghi",
        "job_xyz_001",
        "batch_20240101_xyz",
        "run_12345678",
        "del_abcdef123456",
        "wh_abc12345",
        "mig_init_001",
    ])
    def test_valid_namespaces(self, tid):
        assert validate_task_id(tid) == tid

    def test_too_short_main(self):
        """task_abc 太短 (主体 3 位 < 4)"""
        with pytest.raises(HTTPException) as exc:
            validate_task_id("task_abc")
        assert exc.value.status_code == 400

    def test_unknown_namespace(self):
        """未知前缀 x_ 拒绝"""
        with pytest.raises(HTTPException) as exc:
            validate_task_id("x_abcdefghi")
        assert exc.value.status_code == 400

    def test_img_legacy_id_rejected(self):
        """R1 通用 ID (如 img_001) 走通用 validate_id, 不走本 task_id 校验器"""
        with pytest.raises(HTTPException) as exc:
            validate_task_id("img_001")
        assert exc.value.status_code == 400

    def test_empty(self):
        with pytest.raises(HTTPException) as exc:
            validate_task_id("")

    def test_none(self):
        with pytest.raises(HTTPException) as exc:
            validate_task_id(None)

    def test_legacy_id_with_emoji_rejected(self):
        """Emoji 拒绝"""
        with pytest.raises(HTTPException) as exc:
            validate_task_id("💥")
        assert exc.value.status_code == 400

    def test_too_long(self):
        """超 64 字符主体拒绝"""
        with pytest.raises(HTTPException) as exc:
            validate_task_id("task_" + "a" * 65)
        assert exc.value.status_code == 400


# ─────────────────────────── SchedulerHistoryParams ───────────────────────


class TestSchedulerHistoryParams:
    """SchedulerHistoryParams Pydantic 模型测试组"""

    def test_valid_default(self):
        p = SchedulerHistoryParams()
        assert p.skip == 0
        assert p.limit == 20
        assert p.order == "asc"
        assert p.job_id is None

    def test_valid_with_pagination(self):
        p = SchedulerHistoryParams(skip=20, limit=50, sort_by="created_at", order="desc")
        assert p.skip == 20
        assert p.limit == 50
        assert p.sort_by == "created_at"
        assert p.order == "desc"

    def test_valid_with_filters(self):
        p = SchedulerHistoryParams(
            job_id="preset_health_check",
            status="success",
            start=date(2024, 1, 1),
            end=date(2024, 1, 7),
        )
        assert p.job_id == "preset_health_check"
        assert p.status == "success"
        assert p.start == date(2024, 1, 1)
        assert p.end == date(2024, 1, 7)

    def test_skip_negative_rejected(self):
        with pytest.raises(Exception) as exc:
            SchedulerHistoryParams(skip=-1)
        # pydantic ValidationError
        assert "skip" in str(exc.value) or "greater_than_equal" in str(exc.value)

    def test_limit_too_large_rejected(self):
        with pytest.raises(Exception) as exc:
            SchedulerHistoryParams(limit=999)
        assert "limit" in str(exc.value) or "less_than_equal" in str(exc.value)

    def test_start_after_end_rejected(self):
        with pytest.raises(Exception) as exc:
            SchedulerHistoryParams(start=date(2024, 12, 1), end=date(2024, 1, 1))
        assert "start" in str(exc.value) and "end" in str(exc.value)

    def test_span_too_large_rejected(self):
        with pytest.raises(Exception) as exc:
            SchedulerHistoryParams(
                start=date(2020, 1, 1), end=date(2024, 1, 1),
            )
        assert "365" in str(exc.value) or "跨度" in str(exc.value)

    def test_status_invalid_rejected(self):
        with pytest.raises(Exception) as exc:
            SchedulerHistoryParams(status="invalid")
        assert "status" in str(exc.value)

    def test_extra_field_rejected(self):
        with pytest.raises(Exception) as exc:
            SchedulerHistoryParams(extra_field="x")
        assert "extra" in str(exc.value).lower() or "Extra" in str(exc.value)


# ─────────────────────────── PaginationParams ─────────────────────────────


class TestPaginationParams:
    """PaginationParams 通用分页测试组"""

    def test_valid(self):
        p = PaginationParams()
        assert p.skip == 0 and p.limit == 20

    def test_skip_negative(self):
        with pytest.raises(Exception):
            PaginationParams(skip=-1)

    def test_limit_too_large(self):
        with pytest.raises(Exception):
            PaginationParams(limit=9999)

    def test_order_invalid(self):
        with pytest.raises(Exception):
            PaginationParams(order="invalid")

    def test_sort_by_pattern(self):
        with pytest.raises(Exception):
            PaginationParams(sort_by="123abc")
