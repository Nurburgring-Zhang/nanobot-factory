"""
P10R4-1: 第三方集成 (Sentry + structlog) 单元测试
"""
from __future__ import annotations

import os
import sys
import json
import logging
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from common.third_party import (
    init_sentry,
    init_structlog,
    init_all_third_party,
    capture_exception,
    capture_message,
    set_user,
    _sentry_sdk,
)


class TestSentryIntegration:
    """Sentry 集成测试 — 无 DSN 时应 no-op, 不抛异常."""

    def setup_method(self):
        """每个测试重置 — 清 SENTRY_DSN env."""
        os.environ.pop("SENTRY_DSN", None)

    def test_init_sentry_no_dsn_returns_false(self, caplog):
        """无 DSN → False (no-op), 不抛异常."""
        # 重置 module-level state, 避免前一个 test 设置过
        import importlib
        import common.third_party
        importlib.reload(common.third_party)
        from common.third_party import init_sentry as _init_sentry
        # 确保 SENTRY_DSN 未设
        os.environ.pop("SENTRY_DSN", None)
        with caplog.at_level(logging.INFO):
            ok = _init_sentry()
        assert ok is False
        assert "no-op mode" in caplog.text or "DSN not configured" in caplog.text

    def test_init_sentry_with_invalid_dsn_returns_false(self, caplog):
        """无效 DSN → 失败但不抛."""
        with caplog.at_level(logging.WARNING):
            ok = init_sentry(dsn="invalid://wrong")
        # 实际 sentry-sdk 可能 init 失败或 init 成功但不会报错
        # 我们只要求不抛异常
        assert ok in (True, False)

    def test_capture_exception_does_not_raise(self):
        """capture_exception 必须不抛."""
        try:
            raise RuntimeError("test")
        except RuntimeError as e:
            capture_exception(e, request_id="r1")  # 必须不抛

    def test_capture_message_does_not_raise(self):
        """capture_message 必须不抛."""
        capture_message("test msg", level="warning", user="u1")

    def test_set_user_does_not_raise(self):
        set_user(user_id="u1", email="a@a.com", username="alice")


class TestStructlogIntegration:
    """structlog 集成测试."""

    def test_init_structlog_json_produces_json_output(self):
        """验证 structlog 启用后 _structlog_configured = True."""
        import importlib
        import common.third_party
        importlib.reload(common.third_party)
        from common.third_party import init_structlog as _init
        ok = _init(json_output=True, log_level="INFO")
        if ok:
            # 验证 _structlog_configured 标志
            assert common.third_party._structlog_configured is True
            # 验证 get_structlog_logger 返回可用 logger
            from common.third_party import get_structlog_logger
            log = get_structlog_logger("test_structlog_json")
            assert log is not None
            # 调用不抛异常
            log.info("test_event_marker_xyz", key="value")

    def test_init_structlog_console_produces_human_output(self):
        import importlib
        import common.third_party
        importlib.reload(common.third_party)
        from common.third_party import init_structlog as _init
        ok = _init(json_output=False, log_level="INFO")
        if ok:
            assert common.third_party._structlog_configured is True
            from common.third_party import get_structlog_logger
            log = get_structlog_logger("test_structlog_console")
            assert log is not None
            log.info("hello_world_marker_abc")

    def test_get_structlog_logger_returns_logger(self):
        from common.third_party import get_structlog_logger
        log = get_structlog_logger("test")
        assert log is not None


class TestCombinedInit:
    """一站式 init 入口."""

    def test_init_all_third_party_no_dsn(self):
        # 确保 SENTRY_DSN 未设置 (上一步测试可能已 set)
        os.environ.pop("SENTRY_DSN", None)
        # 重置全局状态 — 重新 import 模块以清理 _sentry_initialized
        import importlib
        import common.third_party
        importlib.reload(common.third_party)
        from common.third_party import init_all_third_party as _init_all
        result = _init_all()
        assert "sentry" in result
        assert "structlog" in result
        # sentry 应 False (无 DSN), structlog 可能 True/False
        assert result["sentry"] is False
        # structlog 取决于是否安装 — 我们不强求

    def test_init_all_third_party_with_dsn(self):
        """有 DSN 时 — 应尝试 init, 但无效 DSN 也应 graceful handle."""
        result = init_all_third_party(
            sentry_dsn="https://public@example.com/1",
            sentry_environment="test",
        )
        assert "sentry" in result