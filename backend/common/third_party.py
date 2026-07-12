#!/usr/bin/env python3
"""
Nanobot Factory - 第三方集成 (Third-Party)
============================================

文件: common/third_party.py
功能:
  - Sentry SDK 集成 (error monitoring + performance + release tracking)
  - structlog JSON logging (结构化日志, 易于 SIEM/SOC 集成)
  - 全部可选 — 未配置 / 库未装则 graceful degradation

设计取舍:
  - Sentry: 项目当前无 SENTRY_DSN env var, 默认 no-op (logger.error 替代)
  - structlog: 默认尝试 import, 未装则降级 stdlib logging
  - 优雅失败优先 — 不阻塞启动, 不强制依赖

作者: Coder (P10R4-1 / 第三方面对)
版本: v1.0.0 (2026-06-26)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("third_party")


# ============================================================================
# Sentry 集成
# ============================================================================

_sentry_initialized: bool = False
_sentry_sdk: Optional[Any] = None


def init_sentry(
    dsn: str = "",
    environment: str = "development",
    release: str = "",
    traces_sample_rate: float = 0.1,
    enable_performance: bool = True,
    attach_stacktrace: bool = True,
    send_default_pii: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    初始化 Sentry SDK.

    Args:
        dsn: Sentry DSN (空字符串则从 SENTRY_DSN env var 读)
        environment: production / staging / development
        release: 应用版本 (git SHA / semver)
        traces_sample_rate: 性能采样率 (0.0-1.0)
        enable_performance: 是否启用 performance monitoring
        attach_stacktrace: 是否自动附加 stack traces
        send_default_pii: 是否发送 PII (生产建议 False)
        extra_context: 额外的全局 tags

    Returns:
        True 如果初始化成功, False 否则 (no-op 模式).

    Note:
        无 DSN 或 sentry-sdk 未装 → 自动 no-op, 函数返回 False.
        这是 **设计上的安全降级** — 永远不阻塞应用启动.
    """
    global _sentry_initialized, _sentry_sdk

    if _sentry_initialized:
        # 已初始化, 直接返回当前状态 (不再重复尝试)
        return _sentry_sdk is not None

    dsn = dsn or os.environ.get("SENTRY_DSN", "")
    if not dsn:
        logger.info(
            "Sentry DSN not configured — running in no-op mode "
            "(set SENTRY_DSN env var to enable)"
        )
        _sentry_initialized = True  # 标记为已尝试初始化 (避免重复尝试)
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "sentry-sdk not installed — running in no-op mode. "
            "Install with: pip install sentry-sdk"
        )
        _sentry_initialized = True
        return False

    release = release or os.environ.get("GIT_COMMIT", "unknown")

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate if enable_performance else 0.0,
            attach_stacktrace=attach_stacktrace,
            send_default_pii=send_default_pii,
            # PII filter — 不要发送密码 / token / API key
            before_send=_sentry_before_send_pii_filter,
        )
        if extra_context:
            for key, value in extra_context.items():
                sentry_sdk.set_tag(key, value)
        _sentry_sdk = sentry_sdk
        _sentry_initialized = True
        logger.info(
            "Sentry initialized: env=%s release=%s dsn=%s...",
            environment, release, dsn[:20],
        )
        return True
    except Exception as e:
        logger.error("Sentry init failed: %s", e)
        return False


def _sentry_before_send_pii_filter(event: Dict, hint: Dict) -> Optional[Dict]:
    """
    Sentry PII 过滤器 — 在发送前剔除敏感字段.

    防止意外发送: password / token / api_key / secret / jwt 等.
    """
    # Scrub breadcrumbs
    if "breadcrumbs" in event:
        for crumb in event.get("breadcrumbs", {}).get("values", []):
            data = crumb.get("data", {})
            for key in list(data.keys()):
                if any(s in key.lower() for s in ("password", "token", "secret", "api_key", "jwt", "credential")):
                    data[key] = "[REDACTED]"
    # Scrub request data
    if "request" in event:
        req = event["request"]
        if "data" in req and isinstance(req["data"], dict):
            for key in list(req["data"].keys()):
                if any(s in key.lower() for s in ("password", "token", "secret", "api_key", "jwt", "credential")):
                    req["data"][key] = "[REDACTED]"
        if "headers" in req:
            for key in list(req["headers"].keys()):
                if key.lower() in ("authorization", "cookie", "x-api-key"):
                    req["headers"][key] = "[REDACTED]"
    # Scrub extra
    if "extra" in event:
        for key in list(event["extra"].keys()):
            if any(s in key.lower() for s in ("password", "token", "secret", "api_key", "jwt", "credential")):
                event["extra"][key] = "[REDACTED]"
    return event


def capture_exception(error: Exception, **context) -> None:
    """捕获异常上报 Sentry (no-op if未初始化)."""
    if _sentry_sdk is not None:
        try:
            with _sentry_sdk.push_scope() as scope:
                for k, v in context.items():
                    scope.set_extra(k, v)
                _sentry_sdk.capture_exception(error)
        except Exception:
            pass
    # 同时本地记录
    logger.exception("Exception: %s", error)


def capture_message(message: str, level: str = "info", **context) -> None:
    """上报消息到 Sentry (no-op if未初始化)."""
    if _sentry_sdk is not None:
        try:
            with _sentry_sdk.push_scope() as scope:
                for k, v in context.items():
                    scope.set_extra(k, v)
                _sentry_sdk.capture_message(message, level=level)
        except Exception:
            pass
    logger.log(getattr(logging, level.upper(), logging.INFO), message)


def set_user(user_id: str, email: str = "", username: str = "",
             ip_address: str = "") -> None:
    """设置 Sentry user context (供 breadcrumb / issue 关联)."""
    if _sentry_sdk is not None:
        try:
            _sentry_sdk.set_user({
                "id": user_id,
                "email": email,
                "username": username,
                "ip_address": ip_address,
            })
        except Exception:
            pass


# ============================================================================
# structlog 集成 (结构化 JSON logging)
# ============================================================================

_structlog_configured: bool = False


def init_structlog(
    json_output: bool = True,
    log_level: str = "INFO",
    include_timestamp: bool = True,
    add_request_context: bool = False,
) -> bool:
    """
    初始化 structlog — 统一 JSON 格式日志输出.

    Args:
        json_output: True → JSON Renderer (生产), False → Console (dev)
        log_level: DEBUG/INFO/WARNING/ERROR
        include_timestamp: 是否包含 ISO 8601 timestamp
        add_request_context: 是否启用 request_id / user_id processor

    Returns:
        True 如果配置成功.
    """
    global _structlog_configured
    if _structlog_configured:
        return True

    try:
        import structlog
    except ImportError:
        logger.warning(
            "structlog not installed — falling back to stdlib logging. "
            "Install with: pip install structlog"
        )
        return False

    try:
        timestamper = structlog.processors.TimeStamper(fmt="iso") if include_timestamp else None
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),
        ]
        if timestamper:
            shared_processors.insert(0, timestamper)
        if add_request_context:
            shared_processors.insert(0, structlog.contextvars.merge_contextvars)

        if json_output:
            # 生产 JSON — 易于 SIEM 采集 (Splunk/ELK/Datadog)
            renderer = structlog.processors.JSONRenderer()
        else:
            # 开发 Console — 彩色 + 易读
            renderer = structlog.dev.ConsoleRenderer()

        structlog.configure(
            processors=shared_processors + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper(), logging.INFO)
            ),
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Configure stdlib root logger to use structlog formatter
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        # 移除已有 handler (避免重复)
        root_logger.handlers = [handler]
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        _structlog_configured = True
        logger.info(
            "structlog configured: json=%s level=%s timestamp=%s",
            json_output, log_level, include_timestamp,
        )
        return True
    except Exception as e:
        logger.error("structlog init failed: %s", e)
        return False


def get_structlog_logger(name: str = "app"):
    """获取 structlog logger (未配置则降级 stdlib)."""
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)


# ============================================================================
# 一次性初始化 (供 main 入口调用)
# ============================================================================

def init_all_third_party(
    sentry_dsn: str = "",
    sentry_environment: str = "",
    sentry_release: str = "",
    structlog_json: bool = True,
    structlog_level: str = "INFO",
) -> Dict[str, bool]:
    """
    一站式初始化所有第三方集成 — 在应用启动时调用.

    Returns:
        dict {"sentry": bool, "structlog": bool} 报告各组件是否启用
    """
    sentry_ok = init_sentry(
        dsn=sentry_dsn,
        environment=sentry_environment or os.environ.get("ENVIRONMENT", "development"),
        release=sentry_release,
    )
    structlog_ok = init_structlog(
        json_output=structlog_json,
        log_level=structlog_level,
    )
    return {"sentry": sentry_ok, "structlog": structlog_ok}


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    "init_sentry",
    "capture_exception",
    "capture_message",
    "set_user",
    "init_structlog",
    "get_structlog_logger",
    "init_all_third_party",
]