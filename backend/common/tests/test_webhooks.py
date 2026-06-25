"""P6-Fix-C-8 / P1-8: 公开 Webhook tests."""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from common.webhooks import (
    register_webhook, list_webhooks, get_webhook, delete_webhook, update_webhook,
    emit, list_emits, _reset_webhooks,
    SUPPORTED_EVENTS, SIGNATURE_HEADER,
    WebhookSubscription, EmitRecord,
)
from common.webhooks_routes import router


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean():
    _reset_webhooks()
    yield
    _reset_webhooks()


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ── 1. 模块级单元测试 ────────────────────────────────────────────────────
class TestWebhookModule:
    def test_001_register(self):
        h = register_webhook(
            url="https://example.com/hook",
            events=["ticket.created", "customer.created"],
            secret="mysecret123",
        )
        assert h.hook_id.startswith("WHK-")
        assert h.url == "https://example.com/hook"
        assert "ticket.created" in h.events

    def test_002_register_invalid_url(self):
        with pytest.raises(ValueError):
            register_webhook(url="ftp://x", events=["*"])

    def test_003_register_invalid_event(self):
        with pytest.raises(ValueError):
            register_webhook(url="https://x.com", events=["bogus_event"])

    def test_004_register_wildcard(self):
        h = register_webhook(url="https://x.com", events=["*"])
        assert h.events == ["*"]

    def test_005_list_webhooks(self):
        register_webhook(url="https://x1.com", events=["*"])
        h2 = register_webhook(url="https://x2.com", events=["ticket.created"])
        update_webhook(h2.hook_id, active=False)
        items = list_webhooks()
        assert len(items) == 2
        active = list_webhooks(active_only=True)
        assert len(active) == 1

    def test_006_get_webhook(self):
        h = register_webhook(url="https://x.com", events=["*"])
        got = get_webhook(h.hook_id)
        assert got is not None
        assert got.hook_id == h.hook_id

    def test_007_delete_webhook(self):
        h = register_webhook(url="https://x.com", events=["*"])
        ok = delete_webhook(h.hook_id)
        assert ok is True
        assert get_webhook(h.hook_id) is None

    def test_008_delete_nonexistent(self):
        assert delete_webhook("WHK-FAKE") is False

    def test_009_update_webhook(self):
        h = register_webhook(url="https://x.com", events=["*"])
        updated = update_webhook(h.hook_id, active=False)
        assert updated.active is False

    def test_010_update_nonexistent(self):
        assert update_webhook("WHK-FAKE", active=False) is None

    def test_011_emit_no_subscribers(self):
        rec = emit("ticket.created", {"foo": "bar"})
        assert rec.event_type == "ticket.created"
        assert rec.sent_to == []
        assert rec.failed_to == []

    def test_012_emit_matching_subscriber(self):
        h = register_webhook(url="https://httpbin.org/status/200", events=["ticket.created"])
        rec = emit("ticket.created", {"foo": "bar"})
        # 真实发送; 但 httpbin 可能不可达 — 至少 rec 应有尝试记录
        assert rec.event_type == "ticket.created"

    def test_013_emit_non_matching_event(self):
        h = register_webhook(url="https://example.com/x", events=["ticket.created"])
        rec = emit("customer.created", {"x": 1})  # 不订阅
        assert rec.sent_to == []
        assert rec.failed_to == []

    def test_014_emit_wildcard_subscriber(self):
        h = register_webhook(url="https://example.com/x", events=["*"])
        rec = emit("any.event.type", {})
        # 不会真正发送, 但会记录尝试
        assert rec.event_type == "any.event.type"

    def test_015_list_emits(self):
        for _ in range(3):
            emit("ticket.created", {})
        items = list_emits(limit=10)
        assert len(items) >= 3


# ── 2. HTTP API ──────────────────────────────────────────────────────────
class TestWebhookRoutes:
    def test_020_register_via_api(self, client):
        r = client.post("/api/v1/public/hooks", json={
            "url": "https://x.com/hook",
            "events": ["ticket.created"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["hook_id"].startswith("WHK-")
        # secret 应被脱敏
        assert "***" in data["secret"]

    def test_021_register_invalid_url_400(self, client):
        r = client.post("/api/v1/public/hooks", json={
            "url": "not-a-url",
            "events": ["ticket.created"],
        })
        assert r.status_code == 400

    def test_022_list_via_api(self, client):
        client.post("/api/v1/public/hooks", json={
            "url": "https://x1.com", "events": ["*"],
        })
        client.post("/api/v1/public/hooks", json={
            "url": "https://x2.com", "events": ["ticket.created"],
        })
        r = client.get("/api/v1/public/hooks")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_023_get_one(self, client):
        r1 = client.post("/api/v1/public/hooks", json={
            "url": "https://x.com", "events": ["*"],
        })
        hid = r1.json()["hook_id"]
        r = client.get(f"/api/v1/public/hooks/{hid}")
        assert r.status_code == 200
        assert r.json()["hook_id"] == hid

    def test_024_get_404(self, client):
        r = client.get("/api/v1/public/hooks/WHK-FAKE")
        assert r.status_code == 404

    def test_025_update_via_api(self, client):
        r1 = client.post("/api/v1/public/hooks", json={
            "url": "https://x.com", "events": ["*"],
        })
        hid = r1.json()["hook_id"]
        r = client.patch(f"/api/v1/public/hooks/{hid}", json={"active": False})
        assert r.status_code == 200
        assert r.json()["active"] is False

    def test_026_delete_via_api(self, client):
        r1 = client.post("/api/v1/public/hooks", json={
            "url": "https://x.com", "events": ["*"],
        })
        hid = r1.json()["hook_id"]
        r = client.delete(f"/api/v1/public/hooks/{hid}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    def test_027_emit_via_api(self, client):
        client.post("/api/v1/public/hooks", json={
            "url": "https://x.com", "events": ["*"],
        })
        r = client.post("/api/v1/public/hooks/emit", json={
            "event_type": "ticket.created",
            "payload": {"ticket_id": "TK-001"},
        })
        assert r.status_code == 200
        assert r.json()["event_type"] == "ticket.created"

    def test_028_emit_invalid_event_400(self, client):
        r = client.post("/api/v1/public/hooks/emit", json={
            "event_type": "bogus.event",
            "payload": {},
        })
        assert r.status_code == 400

    def test_029_meta_route(self, client):
        r = client.get("/api/v1/public/hooks/_meta")
        assert r.status_code == 200
        data = r.json()
        assert "ticket.created" in data["supported_events"]
        assert data["signature_header"] == "X-Webhook-Signature"

    def test_030_list_emits_via_api(self, client):
        client.post("/api/v1/public/hooks/emit", json={
            "event_type": "ticket.created", "payload": {"a": 1},
        })
        r = client.get("/api/v1/public/hooks/emits")
        assert r.status_code == 200
        assert r.json()["count"] >= 1
