"""Layer 6 — Sentry tests."""

from __future__ import annotations

import asyncio
import pytest

from monitoring import sentry as sentry_mod


@pytest.fixture(autouse=True)
def _reset_hub():
    """Reset the singleton between tests."""
    sentry_mod._HUB = None
    yield
    sentry_mod._HUB = None


def test_sentry_init_without_dsn_disables_sdk():
    hub = sentry_mod.SentryHub(service="test")
    enabled = hub.init(dsn=None)
    assert enabled is False
    assert hub.enabled is False
    assert hub.dsn_configured is False


def test_capture_exception_appends_to_buffer():
    hub = sentry_mod.SentryHub(service="svc")
    hub.init(dsn=None)
    try:
        raise ValueError("test-error-42")
    except ValueError as exc:
        hub.capture_exception(exc, layer="backend", tags={"k": "v"})
    items = hub.recent(limit=10)
    assert len(items) == 1
    assert items[0]["exception_type"] == "ValueError"
    assert "test-error-42" in items[0]["message"]
    assert items[0]["tags"]["k"] == "v"


def test_capture_message_records_level_and_message():
    hub = sentry_mod.SentryHub(service="svc")
    hub.init(dsn=None)
    hub.capture_message("hello world", layer="frontend", level="warning")
    items = hub.recent(limit=10)
    assert len(items) == 1
    assert items[0]["level"] == "warning"
    assert items[0]["message"] == "hello world"
    assert items[0]["layer"] == "frontend"


def test_stats_aggregate_by_level_and_service():
    hub = sentry_mod.SentryHub(service="svc-a")
    hub.init(dsn=None)
    hub.capture_message("a-err", level="error")
    hub.capture_message("a-warn", level="warning")
    hub2 = sentry_mod.SentryHub(service="svc-b")
    hub2.init(dsn=None)
    hub2.capture_message("b-err", level="error")
    # Force hub to be svc-a (singleton pattern)
    sentry_mod._HUB = hub
    sentry_mod._HUB.buffer.extend(hub2.buffer)
    stats = sentry_mod.get_hub().stats()
    assert stats["by_level"]["error"] == 2
    assert stats["by_level"]["warning"] == 1
    assert stats["by_service"]["svc-a"] >= 1
    assert stats["buffer_size"] >= 2


def test_recent_filter_by_level():
    hub = sentry_mod.SentryHub(service="svc")
    hub.init(dsn=None)
    hub.capture_message("err", level="error")
    hub.capture_message("warn", level="warning")
    errors_only = hub.recent(limit=10, level="error")
    assert len(errors_only) == 1
    assert errors_only[0]["level"] == "error"


def test_recent_limit_capped():
    hub = sentry_mod.SentryHub(service="svc")
    hub.init(dsn=None)
    for i in range(20):
        hub.capture_message(f"msg-{i}")
    items = hub.recent(limit=5)
    assert len(items) == 5
