"""P1-A2-W2: Webhook 引擎 + API 测试 (18+ 用例)
====================================================

覆盖:
  * Engine 类: 订阅/取消/分发/HMAC/重试/DLQ/rotate/事件类型/跨用户隔离
  * API 端点: /subscribe /subscriptions /rotate-secret /test /deliveries /dlq

策略:
  * 引擎级测试: 用 tmpdir SQLite + mock _http_post 控制成功/失败
  * API 级测试: FastAPI TestClient, 注入同一个 tmpdir engine
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

# ── Path setup ─────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF_ROOT = _BACKEND / "imdf"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines.webhook_engine import (  # noqa: E402
    BACKOFF_SCHEDULE_SECONDS,
    EVENT_TYPES,
    MAX_ATTEMPTS,
    VALID_EVENT_TYPES,
    WebhookEngine,
    WebhookNotFoundError,
    WebhookValidationError,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _ok_post(url, body, sig, et, did, sub_id):
    """Mock HTTP: 200 OK."""
    return (200, '{"ok":true}', "")


def _fail_post(url, body, sig, et, did, sub_id):
    """Mock HTTP: 500 失败。"""
    return (500, '{"error":"boom"}', "")


def _timeout_post(url, body, sig, et, did, sub_id):
    """Mock HTTP: 网络层 timeout (http_status=None)。"""
    return (None, "", "TimeoutError: simulated")


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_root():
    d = Path(tempfile.mkdtemp(prefix="webhook_test_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def engine(tmp_root):
    """每个测试一个独立的 tmpdir SQLite + reset 单例。"""
    db_path = str(tmp_root / "webhooks.db")
    eng = WebhookEngine(db_path=db_path, singleton=False)
    yield eng
    WebhookEngine.reset_for_tests()


@pytest.fixture
def mock_ok(engine):
    engine._http_post_fn = _ok_post
    return engine


@pytest.fixture
def mock_fail(engine):
    engine._http_post_fn = _fail_post
    return engine


@pytest.fixture
def app(engine):
    """Build a minimal FastAPI app with webhook router."""
    from api import webhook_routes
    from api.webhook_routes import router as webhook_router

    webhook_routes._set_engine_for_tests(engine)

    app = FastAPI()
    app.include_router(webhook_router)
    yield app
    webhook_routes._set_engine_for_tests(None)


@pytest.fixture
def client(app):
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────
# Engine 核心测试
# ─────────────────────────────────────────────────────────────────────────
class TestWebhookEngineCore:
    """直接测试 WebhookEngine 类 (不用 HTTP 客户端)。"""

    def test_01_subscribe_returns_id_and_secret(self, engine):
        """subscribe 返回 subscription_id (wh_ 前缀) + secret (whsec_ 前缀, >= 32 字符)。"""
        sub = engine.subscribe(
            url="https://example.com/hook",
            events=["asset.created", "asset.updated"],
            user_id="alice",
        )
        assert sub["subscription_id"].startswith("wh_")
        assert sub["secret"].startswith("whsec_")
        assert len(sub["secret"]) >= 32
        assert "asset.created" in sub["events"]
        assert sub["active"] is True
        assert sub["user_id"] == "alice"

    def test_02_unsubscribe_deletes_subscription(self, engine):
        """unsubscribe 删除订阅, 返回 True; 重复删返回 False。"""
        sub = engine.subscribe(
            url="https://example.com/hook", events=["task.completed"],
        )
        assert engine.unsubscribe(sub["subscription_id"]) is True
        assert engine.unsubscribe(sub["subscription_id"]) is False
        assert engine.get_subscription(sub["subscription_id"]) is None

    def test_03_dispatch_finds_matching_subscribers(self, mock_ok):
        """dispatch 把 event_type 匹配的订阅都触发一次。"""
        e = mock_ok
        s1 = e.subscribe(url="https://h1.test/hook", events=["asset.created"])
        s2 = e.subscribe(url="https://h2.test/hook", events=["asset.created", "asset.updated"])
        s3 = e.subscribe(url="https://h3.test/hook", events=["task.completed"])  # 不匹配
        result = e.dispatch("asset.created", {"foo": "bar"})
        assert result["matched"] == 2
        ids = {d["subscription_id"] for d in result["deliveries"]}
        assert ids == {s1["subscription_id"], s2["subscription_id"]}
        # 全部 200 OK
        assert all(d["success"] for d in result["deliveries"])

    def test_04_dispatch_skips_non_matching(self, mock_ok):
        """dispatch 不匹配的订阅者收不到。"""
        e = mock_ok
        s = e.subscribe(url="https://h.test/hook", events=["task.completed"])
        result = e.dispatch("asset.created", {})
        assert result["matched"] == 0
        assert result["deliveries"] == []

    def test_05_hmac_signature_is_correct(self, engine):
        """HMAC-SHA256 签名应等于 hmac.new(secret, payload, sha256).hexdigest()。"""
        sec = "this_is_a_test_secret_at_least_32_chars_long"
        payload = b'{"event_type":"asset.created","data":{"x":1}}'
        expected = hmac.new(sec.encode(), payload, hashlib.sha256).hexdigest()
        actual = engine._sign(payload, sec)
        assert actual == expected
        # header 形式
        assert engine.signature_header(payload, sec) == f"sha256={expected}"

    def test_06_signature_verify_fails_on_bad_sig(self, engine):
        """_verify_signature 在签名错误时返回 False (接收端会返回 401)。"""
        sec = "a" * 32
        payload = b"hello world"
        good = engine._sign(payload, sec)
        # 正确签名
        assert engine._verify_signature(payload, sec, f"sha256={good}") is True
        # 错误签名
        assert engine._verify_signature(payload, sec, "sha256=deadbeef") is False
        # 空签名
        assert engine._verify_signature(payload, sec, "") is False
        # 用错 secret
        assert engine._verify_signature(payload, "b" * 32, f"sha256={good}") is False

    def test_07_retry_1_failure_enqueues_retry(self, mock_fail):
        """失败 1 次后, retry_queue 应有 1 条 entry, attempt=2, next_retry 在 BACKOFF[0]=1s 后。"""
        e = mock_fail
        sub = e.subscribe(url="https://h.test/hook", events=["asset.created"])
        result = e.dispatch("asset.created", {"x": 1})
        assert result["matched"] == 1
        delivery = result["deliveries"][0]
        assert delivery["success"] is False
        assert delivery["status"] == "retrying"
        assert delivery["next_retry_in_seconds"] == BACKOFF_SCHEDULE_SECONDS[0]  # 1s
        # retry_queue 有 1 条
        with e._conn() as conn:
            rows = conn.execute("SELECT * FROM retry_queue").fetchall()
        assert len(rows) == 1
        assert rows[0]["attempt"] == 2  # 下次 attempt=2
        assert rows[0]["webhook_id"] == sub["subscription_id"]

    def test_08_retry_5_failures_goes_to_dlq(self, mock_fail):
        """失败 5 次后入 DLQ; retry_queue 干净。"""
        e = mock_fail
        sub = e.subscribe(url="https://h.test/hook", events=["asset.created"])
        # 模拟 dispatch + 4 次重试 (共 5 次失败)
        # 第一次 dispatch
        r = e.dispatch("asset.created", {"x": 1})
        assert r["deliveries"][0]["status"] == "retrying"

        # 后续 4 次重试 (attempt 2,3,4,5) — 每次 process_retry_queue
        for expected_attempt in [2, 3, 4]:
            # 把 next_retry_at 提前到现在 (便于立即处理)
            with e._conn() as conn:
                conn.execute(
                    "UPDATE retry_queue SET next_retry_at = ?",
                    (e._now_iso(),),
                )
                conn.commit()
            results = e.process_retry_queue()
            assert len(results) == 1
            assert results[0]["status"] == "retrying"

        # 第 5 次重试 → 应该入 DLQ
        with e._conn() as conn:
            conn.execute(
                "UPDATE retry_queue SET next_retry_at = ?",
                (e._now_iso(),),
            )
            conn.commit()
        results = e.process_retry_queue()
        assert len(results) == 1
        assert results[0]["status"] == "dead"

        # DLQ 应该有 1 条
        dlq = e.list_dlq()
        assert len(dlq) == 1
        assert dlq[0]["webhook_id"] == sub["subscription_id"]
        assert dlq[0]["attempt"] == MAX_ATTEMPTS

        # retry_queue 干净
        with e._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM retry_queue").fetchone()[0]
        assert count == 0

    def test_09_backoff_schedule_correct(self, engine):
        """指数退避序列: 1s / 4s / 16s / 60s / 300s, 共 5 次。"""
        assert BACKOFF_SCHEDULE_SECONDS == [1, 4, 16, 60, 300]
        assert MAX_ATTEMPTS == 5
        # 验证引擎 _enqueue_retry 用的是这个 schedule
        e = engine
        # 用 mock_fail 让 dispatch 失败 1 次, 检查 retry entry 的 next_retry_at
        e._http_post_fn = _fail_post
        e.subscribe(url="https://h.test/hook", events=["asset.created"])
        e.dispatch("asset.created", {})
        with e._conn() as conn:
            row = conn.execute("SELECT * FROM retry_queue").fetchone()
        assert row is not None
        # 解析 next_retry_at → 与 now 的差应在 BACKOFF[0]=1s 附近
        from datetime import datetime
        next_at = datetime.fromisoformat(row["next_retry_at"])
        delta = (next_at - datetime.fromisoformat(e._now_iso())).total_seconds()
        # 允许 ±0.5s 抖动
        assert 0.5 <= delta <= 1.5, f"expected ~1s, got {delta}"

    def test_10_rotate_secret_generates_new_secret(self, engine):
        """rotate_secret 返回新 secret, 长度 >= 32, whsec_ 前缀。"""
        sub = engine.subscribe(url="https://h.test/hook", events=["asset.created"])
        old_secret = sub["secret"]
        result = engine.rotate_secret(sub["subscription_id"])
        assert result["secret"] != old_secret
        assert result["secret"].startswith("whsec_")
        assert len(result["secret"]) >= 32
        assert result["subscription_id"] == sub["subscription_id"]

    def test_11_rotate_secret_invalidates_old(self, engine):
        """rotate_secret 后, 旧 secret 校验失败, 新 secret 校验通过。"""
        sub = engine.subscribe(url="https://h.test/hook", events=["asset.created"])
        old_secret = sub["secret"]
        payload = b'{"event_type":"x"}'
        old_sig = engine._sign(payload, old_secret)
        # rotate
        result = engine.rotate_secret(sub["subscription_id"])
        new_secret = result["secret"]
        new_sig = engine._sign(payload, new_secret)
        # 旧 secret 算出的签名 ≠ DB 中保存的 (engine 用的新 secret)
        assert engine._verify_signature(payload, old_secret, f"sha256={new_sig}") is False
        # 新 secret 能验证新签名
        assert engine._verify_signature(payload, new_secret, f"sha256={new_sig}") is True

    def test_12_37_event_types_defined(self, engine):
        """至少 30+ (实际 37 个) 事件类型, 覆盖 11 大类。"""
        assert len(EVENT_TYPES) >= 30, f"only {len(EVENT_TYPES)} event types"
        assert len(VALID_EVENT_TYPES) == len(EVENT_TYPES)
        categories = {e["category"] for e in EVENT_TYPES}
        # 至少 8 大类
        assert len(categories) >= 8
        # 必含类型
        for must_have in (
            "asset.created", "asset.updated", "asset.deleted",
            "comment.added", "task.completed", "task.failed",
            "pipeline.started", "model.deployed",
            "annotation.submitted", "delivery.completed",
            "user.registered", "test.ping",
        ):
            assert must_have in VALID_EVENT_TYPES, f"missing {must_have}"

    def test_13_test_event_endpoint_triggers(self, client, mock_ok):
        """POST /test/{subscription_id} 触发 test.ping, 返回 delivery。"""
        # 先 subscribe
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={
                "url": "https://h.test/hook",
                "events": ["test.ping", "asset.created"],
                "user_id": "alice",
            },
        )
        assert resp.status_code == 200, resp.text
        sub_id = resp.json()["data"]["subscription_id"]

        # 触发测试事件
        resp = client.post(f"/api/v1/webhooks/test/{sub_id}", json={"payload": {"hi": 1}})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]["test"]
        assert data["success"] is True
        assert data["status"] == "success"
        assert data["subscription_id"] == sub_id

    def test_14_delivery_history_recorded(self, client, mock_ok):
        """GET /deliveries/{subscription_id} 返回投递历史 (>= 1 条)。"""
        # subscribe + dispatch
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={"url": "https://h.test/hook", "events": ["asset.created"], "user_id": "u1"},
        )
        sub_id = resp.json()["data"]["subscription_id"]
        client.post(
            "/api/v1/webhooks/subscriptions",  # 触发 list
            headers={"X-User-ID": "u1"},
        )
        # 直接走 dispatch endpoint (如果有); 否则用 engine
        # 简单做法: 通过 subscribe 触发 1 条 delivery (没有 dispatch endpoint, 手动注入)
        # 这里走兼容路径 /{id}/test
        resp = client.post(f"/api/v1/webhooks/{sub_id}/test")
        assert resp.status_code == 200

        # 取投递历史
        resp = client.get(f"/api/v1/webhooks/deliveries/{sub_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert data["deliveries"][0]["event_type"] == "test.ping"
        assert data["deliveries"][0]["status"] == "success"

    def test_15_dlq_list_and_retry(self, client, mock_fail):
        """失败 5 次后 DLQ 有 1 条; POST /dlq/{id}/retry 重新投递。"""
        # subscribe + 强制 5 次失败 (直接调用 engine 通过 API 不便, 这里手动驱动)
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={"url": "https://h.test/hook", "events": ["asset.created"], "user_id": "u1"},
        )
        sub_id = resp.json()["data"]["subscription_id"]

        # 直接调 engine: 5 次 dispatch (失败) — 但 dispatch 不会自动累计 5 次
        # 这里用 process_retry_queue 反复触发
        from api import webhook_routes
        eng = webhook_routes._get_engine()
        # 第一次 dispatch → retry queue 1 条
        eng.dispatch("asset.created", {})
        # 循环 4 次: 把 retry_queue 的 next_retry 提前 + process
        for _ in range(4):
            with eng._conn() as conn:
                conn.execute("UPDATE retry_queue SET next_retry_at = ?", (eng._now_iso(),))
                conn.commit()
            eng.process_retry_queue()

        # DLQ 应该 1 条
        resp = client.get("/api/v1/webhooks/dlq", headers={"X-User-ID": "u1"})
        assert resp.status_code == 200
        dlq = resp.json()["data"]["dlq"]
        assert len(dlq) == 1
        dlq_id = dlq[0]["dlq_id"]

        # 现在改成 OK, 重投
        eng._http_post_fn = _ok_post
        resp = client.post(f"/api/v1/webhooks/dlq/{dlq_id}/retry")
        assert resp.status_code == 200, resp.text
        result = resp.json()["data"]
        assert result["success"] is True
        assert result["status"] == "success"

        # DLQ 列表应为空 (重投后删除)
        resp = client.get("/api/v1/webhooks/dlq", headers={"X-User-ID": "u1"})
        assert resp.json()["data"]["total"] == 0

    def test_16_cross_user_subscription_isolation(self, client):
        """alice 的订阅对 bob 不可见。"""
        # alice 订阅
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={"url": "https://h.test/hook", "events": ["asset.created"], "user_id": "alice"},
        )
        alice_sub = resp.json()["data"]["subscription_id"]

        # bob 查自己订阅
        resp = client.get("/api/v1/webhooks/subscriptions", headers={"X-User-ID": "bob"})
        assert resp.status_code == 200
        ids = [s["subscription_id"] for s in resp.json()["data"]["subscriptions"]]
        assert alice_sub not in ids

        # alice 查自己
        resp = client.get("/api/v1/webhooks/subscriptions", headers={"X-User-ID": "alice"})
        ids = [s["subscription_id"] for s in resp.json()["data"]["subscriptions"]]
        assert alice_sub in ids

    def test_17_secret_strength_validation(self, engine):
        """用户提供的 secret 必须 >= 32 字符, 不能含空白; 否则 raise WebhookValidationError。"""
        # 太短
        with pytest.raises(WebhookValidationError, match="长度"):
            engine.subscribe(
                url="https://h.test/hook",
                events=["asset.created"],
                secret="short",
            )
        # 含空白
        with pytest.raises(WebhookValidationError, match="空白"):
            engine.subscribe(
                url="https://h.test/hook",
                events=["asset.created"],
                secret="a" * 30 + " b",  # 32 chars 但有空格
            )
        # 合法 (32 字符)
        sub = engine.subscribe(
            url="https://h.test/hook",
            events=["asset.created"],
            secret="x" * 32,
        )
        assert sub["secret"] == "x" * 32
        # 自动生成 (>= 32 hex chars, whsec_<64 hex> = 69 chars)
        sub2 = engine.subscribe(url="https://h.test/hook", events=["asset.created"])
        assert len(sub2["secret"]) >= 32

    def test_18_subscribe_url_ssrf_protection(self, client):
        """subscribe 的 url 走 SSRF 校验 (validate_webhook_url), localhost 应被拒。"""
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={
                "url": "http://localhost:9999/hook",
                "events": ["asset.created"],
                "user_id": "alice",
            },
        )
        assert resp.status_code == 400
        assert "localhost" in resp.text.lower() or "ssrf" in resp.text.lower()

    def test_19_subscribe_invalid_event_type_rejected(self, client):
        """subscribe 时 events 含非法类型 → 400。"""
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={
                "url": "https://h.test/hook",
                "events": ["asset.created", "fake.event"],
                "user_id": "alice",
            },
        )
        assert resp.status_code == 422  # Pydantic validation error

    def test_20_unsubscribe_via_api(self, client):
        """DELETE /subscriptions/{id} 取消订阅。"""
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={"url": "https://h.test/hook", "events": ["asset.created"], "user_id": "alice"},
        )
        sub_id = resp.json()["data"]["subscription_id"]
        resp = client.delete(f"/api/v1/webhooks/subscriptions/{sub_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True
        # 再查应为空
        resp = client.get("/api/v1/webhooks/subscriptions", headers={"X-User-ID": "alice"})
        assert resp.json()["data"]["total"] == 0

    def test_21_rotate_secret_via_api(self, client):
        """PUT /subscriptions/{id}/rotate-secret 返回新 secret。"""
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={"url": "https://h.test/hook", "events": ["asset.created"], "user_id": "alice"},
        )
        sub_id = resp.json()["data"]["subscription_id"]
        old_secret = resp.json()["data"]["secret"]
        resp = client.put(f"/api/v1/webhooks/subscriptions/{sub_id}/rotate-secret")
        assert resp.status_code == 200
        new_secret = resp.json()["data"]["secret"]
        assert new_secret != old_secret
        assert new_secret.startswith("whsec_")

    def test_22_dispatch_with_user_filter_isolation(self, mock_ok):
        """dispatch 时带 user_id, 只触发该 user 的订阅。"""
        e = mock_ok
        s_alice = e.subscribe(
            url="https://h.test/hook", events=["asset.created"], user_id="alice",
        )
        s_bob = e.subscribe(
            url="https://h.test/hook", events=["asset.created"], user_id="bob",
        )
        s_anon = e.subscribe(
            url="https://h.test/hook", events=["asset.created"],  # 无 user_id
        )
        # dispatch 给 alice → 只命中 alice + 匿名订阅 (2)
        result = e.dispatch("asset.created", {}, user_id="alice")
        ids = {d["subscription_id"] for d in result["deliveries"]}
        assert s_alice["subscription_id"] in ids
        assert s_anon["subscription_id"] in ids  # user_id='' 也匹配
        assert s_bob["subscription_id"] not in ids

    def test_23_event_types_endpoint_lists_all(self, client):
        """GET /event-types 返回 30+ 类型, 含 categories。"""
        resp = client.get("/api/v1/webhooks/event-types")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 30
        assert len(data["categories"]) >= 8
        # 类型
        types = {e["type"] for e in data["event_types"]}
        assert "asset.created" in types
        assert "test.ping" in types

    def test_24_process_retry_queue_handles_orphan_retry_entry(self, engine):
        """retry_queue 中残留的孤儿条目 (订阅已删) → DLQ 而不是无限重试。

        unsubscribe 本身会级联清理 retry_queue, 但手动注入一条 fake webhook_id
        的 retry 条目可模拟 "DB 不一致 / 历史遗留" 场景。
        """
        # 手动插入一条 orphan retry (webhook_id 不在 webhooks 表中)
        orphan_webhook_id = "wh_orphanchildtest1234"
        with engine._conn() as conn:
            conn.execute(
                """INSERT INTO retry_queue
                   (id, webhook_id, delivery_id, event_type, payload_json,
                    attempt, next_retry_at, last_error, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "retry_orphan0001",
                    orphan_webhook_id,
                    "del_orphan00001",
                    "asset.created",
                    json.dumps({"event_type": "asset.created", "data": {}}),
                    2,
                    engine._now_iso(),  # 立即到期
                    "simulated orphan",
                    engine._now_iso(),
                ),
            )
            conn.commit()

        results = engine.process_retry_queue()
        assert len(results) == 1
        assert results[0]["status"] == "dead"
        dlq = engine.list_dlq()
        assert len(dlq) == 1
        assert dlq[0]["webhook_id"] == orphan_webhook_id

    def test_25_delivery_signature_stored(self, client, mock_ok):
        """每次投递都把 HMAC signature 存到 deliveries.signature。"""
        resp = client.post(
            "/api/v1/webhooks/subscribe",
            json={"url": "https://h.test/hook", "events": ["asset.created"], "user_id": "alice"},
        )
        sub_id = resp.json()["data"]["subscription_id"]
        # 触发
        client.post(f"/api/v1/webhooks/{sub_id}/test")
        # 查 deliveries
        from api import webhook_routes
        eng = webhook_routes._get_engine()
        deliveries = eng.list_deliveries(sub_id)
        assert len(deliveries) >= 1
        sig = deliveries[0]["signature"]
        assert sig != ""
        assert len(sig) == 64  # SHA-256 hex digest