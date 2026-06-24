"""Webhook 订阅/发送引擎 — HMAC 签名 + 指数退避重试 + DLQ
================================================================

P1-A2-W2 真实化实现:

1. **HMAC-SHA256 签名**: 每条消息独立 secret, header ``X-IMDF-Signature: sha256=<hex>``
2. **重试队列**: 指数退避 1s / 4s / 16s / 60s / 300s, 最多 5 次尝试
3. **死信队列 (DLQ)**: 重试 5 次后入 DLQ, 支持手动重投
4. **36 个事件类型**: task / asset / comment / pipeline / model / annotation /
   delivery / user / system / quality / approval 11 大类
5. **订阅过滤**: event_types + user_id + tenant_id (跨用户/跨租户隔离)

数据模型 (与现有 webhook_routes.py 共用 webhooks.db, 平滑升级):

* ``webhooks``        — 订阅表 (新增 user_id, tenant_id, description, active)
* ``deliveries``      — 投递历史 (status: success / failed / pending / retrying / dead)
* ``retry_queue``     — 待重试条目 (next_retry_at 时间戳)
* ``dlq``             — 死信队列 (重试 5 次后)

对外接口 (``WebhookEngine``):

* ``subscribe(url, events, secret=None, user_id=None, tenant_id=None, ...)`` → dict
* ``unsubscribe(subscription_id)`` → bool
* ``list_subscriptions(user_id=None, tenant_id=None)`` → list
* ``rotate_secret(subscription_id)`` → dict (含新 secret)
* ``dispatch(event_type, payload, user_id=None, tenant_id=None)`` → dict (matched count)
* ``_deliver(subscription_id, event, attempt=1)`` → dict (HTTP POST + 重试)
* ``_sign(payload, secret)`` → str (HMAC-SHA256 hex)
* ``_verify_signature(payload, secret, signature)`` → bool (用于测试 401 路径)
* ``list_deliveries(subscription_id, limit=50)`` → list
* ``list_dlq(user_id=None)`` → list
* ``retry_dlq_entry(dlq_id)`` → bool

向后兼容: 复用 webhook_routes.py 的现有 webhooks / deliveries 表; 新增 retry_queue
和 dlq 表用 ``CREATE TABLE IF NOT EXISTS``, 字段缺失时 ``ALTER TABLE`` 平滑补齐。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "webhooks.db"
)

# 指数退避: 1s, 4s, 16s, 60s, 300s (5 次尝试 = 6 个时间点)
BACKOFF_SCHEDULE_SECONDS: List[int] = [1, 4, 16, 60, 300]
MAX_ATTEMPTS = len(BACKOFF_SCHEDULE_SECONDS)  # 5

# 默认 secret 长度 (>= 32 字符, hex 64)
DEFAULT_SECRET_BYTES = 32

# HMAC 算法
HMAC_ALGO = "sha256"
SIGNATURE_HEADER = "X-IMDF-Signature"  # value: "sha256=<hex>"

# ── 事件类型注册表 (36 个, 11 类) ────────────────────────────────────────────

EVENT_TYPES: List[Dict[str, str]] = [
    # task (6)
    {"type": "task.created",        "description": "任务创建",          "category": "task"},
    {"type": "task.started",        "description": "任务开始执行",      "category": "task"},
    {"type": "task.completed",      "description": "任务完成",          "category": "task"},
    {"type": "task.failed",         "description": "任务失败",          "category": "task"},
    {"type": "task.reviewed",       "description": "任务审核完成",      "category": "task"},
    {"type": "task.assigned",       "description": "任务被分配",        "category": "task"},
    # asset (6)
    {"type": "asset.created",       "description": "资源创建",          "category": "asset"},
    {"type": "asset.updated",       "description": "资源更新",          "category": "asset"},
    {"type": "asset.deleted",       "description": "资源删除",          "category": "asset"},
    {"type": "asset.shared",        "description": "资源共享",          "category": "asset"},
    {"type": "asset.archived",      "description": "资源归档",          "category": "asset"},
    {"type": "asset.downloaded",    "description": "资源下载",          "category": "asset"},
    # comment (3)
    {"type": "comment.added",       "description": "评论新增",          "category": "comment"},
    {"type": "comment.edited",      "description": "评论编辑",          "category": "comment"},
    {"type": "comment.deleted",     "description": "评论删除",          "category": "comment"},
    # pipeline (3)
    {"type": "pipeline.started",    "description": "产线启动",          "category": "pipeline"},
    {"type": "pipeline.completed",  "description": "产线完成",          "category": "pipeline"},
    {"type": "pipeline.failed",     "description": "产线失败",          "category": "pipeline"},
    # model (3)
    {"type": "model.deployed",      "description": "模型上线",          "category": "model"},
    {"type": "model.updated",       "description": "模型更新",          "category": "model"},
    {"type": "model.retired",       "description": "模型下线",          "category": "model"},
    # annotation (3)
    {"type": "annotation.submitted","description": "标注提交",          "category": "annotation"},
    {"type": "annotation.reviewed", "description": "标注审核通过",      "category": "annotation"},
    {"type": "annotation.rejected", "description": "标注被驳回",        "category": "annotation"},
    # delivery (3)
    {"type": "delivery.created",    "description": "交付创建",          "category": "delivery"},
    {"type": "delivery.completed",  "description": "交付完成",          "category": "delivery"},
    {"type": "delivery.failed",     "description": "交付失败",          "category": "delivery"},
    # user (3)
    {"type": "user.registered",     "description": "用户注册",          "category": "user"},
    {"type": "user.consent_changed","description": "用户同意变更",      "category": "user"},
    {"type": "user.deleted",        "description": "用户注销",          "category": "user"},
    # system (3)
    {"type": "test.ping",           "description": "测试事件 (ping)",   "category": "system"},
    {"type": "system.health",       "description": "系统健康",          "category": "system"},
    {"type": "system.error",        "description": "系统错误",          "category": "system"},
    # quality (2)
    {"type": "quality.passed",      "description": "质检通过",          "category": "quality"},
    {"type": "quality.failed",      "description": "质检失败",          "category": "quality"},
    # approval (2)
    {"type": "approval.requested",  "description": "审批请求",          "category": "approval"},
    {"type": "approval.granted",    "description": "审批通过",          "category": "approval"},
]
# 总计 6+6+3+3+3+3+3+3+3+2+2 = 37

EVENT_TYPES_BY_TYPE: Dict[str, Dict[str, str]] = {e["type"]: e for e in EVENT_TYPES}
VALID_EVENT_TYPES: set = set(EVENT_TYPES_BY_TYPE.keys())


# ── 错误类 ───────────────────────────────────────────────────────────────────

class WebhookError(Exception):
    """Webhook 子系统错误基类。"""

class WebhookNotFoundError(WebhookError):
    """订阅不存在。"""

class WebhookValidationError(WebhookError):
    """参数非法。"""

class WebhookSignatureError(WebhookError):
    """签名校验失败。"""


# ── 引擎类 ───────────────────────────────────────────────────────────────────

class WebhookEngine:
    """Webhook 订阅/发送引擎 (单例)。

    实例化方式:

    * ``WebhookEngine()`` — 默认 DB 路径 ``backend/data/webhooks.db``
    * ``WebhookEngine(db_path="...")`` — 自定义路径 (测试用 tmp)
    * ``WebhookEngine.instance()`` — 进程级单例
    """

    _instance: Optional["WebhookEngine"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):  # noqa: D401
        # 默认走单例; 测试可用 ``_reset_for_tests`` 重置
        if kwargs.get("singleton", True) and cls._instance is not None:
            return cls._instance
        return super().__new__(cls)

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        singleton: bool = True,
    ) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.db_path = db_path or os.environ.get("WEBHOOK_DB_PATH") or DEFAULT_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialized = True
        # 表结构 / 平滑迁移
        with self._conn() as conn:
            self._ensure_schema(conn)
        # 单例注册
        if singleton:
            WebhookEngine._instance = self

    # ── DB 辅助 ──────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """建表 + 平滑补齐缺失字段 (兼容 R3 已有表)。"""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                description TEXT DEFAULT '',
                events TEXT NOT NULL DEFAULT '[]',
                secret TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                max_retries INTEGER DEFAULT 5,
                retry_interval_seconds INTEGER DEFAULT 60,
                user_id TEXT DEFAULT '',
                tenant_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY,
                webhook_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                attempt INTEGER DEFAULT 1,
                max_attempts INTEGER DEFAULT 5,
                http_status INTEGER,
                request_body TEXT DEFAULT '',
                response_body TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                signature TEXT DEFAULT '',
                payload_json TEXT DEFAULT '',
                sent_at TEXT NOT NULL,
                completed_at TEXT,
                next_retry_at TEXT
            );
            CREATE TABLE IF NOT EXISTS retry_queue (
                id TEXT PRIMARY KEY,
                webhook_id TEXT NOT NULL,
                delivery_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                attempt INTEGER DEFAULT 1,
                next_retry_at TEXT NOT NULL,
                last_error TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dlq (
                id TEXT PRIMARY KEY,
                webhook_id TEXT NOT NULL,
                delivery_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                attempt INTEGER DEFAULT 5,
                last_error TEXT DEFAULT '',
                last_http_status INTEGER,
                last_response TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                retried_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_webhooks_active   ON webhooks(active);
            CREATE INDEX IF NOT EXISTS idx_webhooks_user     ON webhooks(user_id);
            CREATE INDEX IF NOT EXISTS idx_webhooks_tenant   ON webhooks(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_deliveries_wh     ON deliveries(webhook_id);
            CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status);
            CREATE INDEX IF NOT EXISTS idx_deliveries_sent   ON deliveries(sent_at);
            CREATE INDEX IF NOT EXISTS idx_retry_next        ON retry_queue(next_retry_at);
            CREATE INDEX IF NOT EXISTS idx_retry_wh          ON retry_queue(webhook_id);
            CREATE INDEX IF NOT EXISTS idx_dlq_wh            ON dlq(webhook_id);
            """
        )
        # 平滑补齐字段 (兼容 R3 已有 webhooks.db 缺列)
        self._ensure_column(conn, "webhooks", "user_id", "TEXT DEFAULT ''")
        self._ensure_column(conn, "webhooks", "tenant_id", "TEXT DEFAULT ''")
        self._ensure_column(conn, "webhooks", "description", "TEXT DEFAULT ''")
        self._ensure_column(conn, "deliveries", "signature", "TEXT DEFAULT ''")
        self._ensure_column(conn, "deliveries", "payload_json", "TEXT DEFAULT ''")
        self._ensure_column(conn, "deliveries", "max_attempts", "INTEGER DEFAULT 5")
        self._ensure_column(conn, "deliveries", "next_retry_at", "TEXT")
        conn.commit()

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cur.fetchall()}
        if column not in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError as exc:  # pragma: no cover
                logger.warning("ALTER %s ADD %s failed: %s", table, column, exc)

    # ── 工具: secret / id / 时间 ─────────────────────────────────────────

    @staticmethod
    def _generate_secret() -> str:
        """生成 >= 32 字节的随机 secret, 格式 whsec_<hex>。"""
        return f"whsec_{secrets.token_hex(DEFAULT_SECRET_BYTES)}"

    @staticmethod
    def _validate_secret(secret: str) -> str:
        """校验用户提供的 secret 强度: 必须 >= 32 字符, 不能含空白。"""
        if not isinstance(secret, str) or not secret:
            raise WebhookValidationError("secret 不能为空")
        if len(secret) < 32:
            raise WebhookValidationError(
                f"secret 长度 {len(secret)} 不足 32 字符, 建议 >= 32 字节强随机"
            )
        if any(c.isspace() for c in secret):
            raise WebhookValidationError("secret 不能含空白字符")
        return secret

    @staticmethod
    def _new_id(prefix: str = "wh") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── HMAC 签名 ────────────────────────────────────────────────────────

    @staticmethod
    def _sign(payload: bytes, secret: str) -> str:
        """HMAC-SHA256(secret, payload) → hex digest."""
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    @classmethod
    def _verify_signature(cls, payload: bytes, secret: str, signature: str) -> bool:
        """验证 HMAC 签名 (用于 mock 接收端校验)。"""
        if not signature:
            return False
        # 兼容 "sha256=<hex>" 或纯 hex
        sig = signature.split("=", 1)[-1] if signature.startswith("sha256=") else signature
        expected = cls._sign(payload, secret)
        # 常时间比较
        return hmac.compare_digest(expected, sig.lower())

    @classmethod
    def signature_header(cls, payload: bytes, secret: str) -> str:
        """生成 X-IMDF-Signature header 值: ``sha256=<hex>``。"""
        return f"sha256={cls._sign(payload, secret)}"

    # ── 订阅管理 ─────────────────────────────────────────────────────────

    def subscribe(
        self,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        description: str = "",
        max_retries: int = MAX_ATTEMPTS,
    ) -> Dict[str, Any]:
        """创建订阅, 返回 subscription_id + secret (一次性返回完整 secret)。"""
        if not isinstance(url, str) or not url.strip():
            raise WebhookValidationError("url 不能为空")
        if not isinstance(events, list) or not events:
            raise WebhookValidationError("events 不能为空列表")
        invalid = [e for e in events if e not in VALID_EVENT_TYPES]
        if invalid:
            raise WebhookValidationError(f"事件类型非法: {invalid}")

        sub_id = self._new_id("wh")
        sec = self._validate_secret(secret) if secret else self._generate_secret()
        now = self._now_iso()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO webhooks
                  (id, url, description, events, secret, active, max_retries,
                   retry_interval_seconds, user_id, tenant_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id, url, description, json.dumps(events), sec,
                    int(max_retries), 0,
                    user_id or "", tenant_id or "",
                    now, now,
                ),
            )
            conn.commit()
        logger.info("webhook subscribed: %s -> %s (events=%d)", sub_id, url, len(events))
        return {
            "subscription_id": sub_id,
            "url": url,
            "events": events,
            "secret": sec,  # 一次性返回
            "active": True,
            "description": description,
            "user_id": user_id or "",
            "tenant_id": tenant_id or "",
            "max_retries": int(max_retries),
            "created_at": now,
        }

    def unsubscribe(self, subscription_id: str) -> bool:
        """删除订阅 (级联清理 deliveries / retry_queue / dlq)。"""
        if not subscription_id:
            return False
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM webhooks WHERE id = ?", (subscription_id,))
            deleted = cur.rowcount > 0
            if deleted:
                conn.execute(
                    "DELETE FROM retry_queue WHERE webhook_id = ?", (subscription_id,)
                )
                conn.execute(
                    "DELETE FROM dlq WHERE webhook_id = ?", (subscription_id,)
                )
            conn.commit()
        if deleted:
            logger.info("webhook unsubscribed: %s", subscription_id)
        return deleted

    def list_subscriptions(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出订阅。可按 user_id / tenant_id 过滤 (用于跨用户隔离测试)。"""
        sql = "SELECT * FROM webhooks WHERE 1=1"
        params: List[Any] = []
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        if tenant_id is not None:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(self._row_to_sub(r, mask_secret=True))
        return out

    def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM webhooks WHERE id = ?", (subscription_id,)
            ).fetchone()
        return self._row_to_sub(row, mask_secret=False) if row else None

    @staticmethod
    def _row_to_sub(row: sqlite3.Row, mask_secret: bool = True) -> Dict[str, Any]:
        sec = row["secret"] or ""
        masked = (sec[:8] + "****" + sec[-4:]) if mask_secret and len(sec) > 12 else sec
        return {
            "subscription_id": row["id"],
            "url": row["url"],
            "description": row["description"],
            "events": json.loads(row["events"]) if row["events"] else [],
            "secret": masked,
            "active": bool(row["active"]),
            "max_retries": row["max_retries"],
            "user_id": row["user_id"],
            "tenant_id": row["tenant_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def rotate_secret(self, subscription_id: str) -> Dict[str, Any]:
        """轮换订阅的 secret, 返回新 secret (旧 secret 立即失效)。"""
        if not self.get_subscription(subscription_id):
            raise WebhookNotFoundError(f"subscription {subscription_id} 不存在")
        new_sec = self._generate_secret()
        now = self._now_iso()
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE webhooks SET secret = ?, updated_at = ? WHERE id = ?",
                (new_sec, now, subscription_id),
            )
            conn.commit()
        logger.info("webhook secret rotated: %s", subscription_id)
        return {
            "subscription_id": subscription_id,
            "secret": new_sec,  # 一次性返回
            "rotated_at": now,
        }

    # ── 事件分发 ─────────────────────────────────────────────────────────

    def dispatch(
        self,
        event_type: str,
        payload: Dict[str, Any],
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分发事件到所有匹配订阅。

        匹配规则: subscription 包含 event_type, 且 (user_id 为空 OR == caller)
                                  且 (tenant_id 为空 OR == caller)。
        每个匹配的订阅同步触发一次 _deliver (attempt=1); 失败自动入重试队列。
        返回: {"matched": int, "delivered": [...], "retried": [...]}
        """
        if event_type not in VALID_EVENT_TYPES:
            raise WebhookValidationError(f"事件类型非法: {event_type!r}")
        if not isinstance(payload, dict):
            raise WebhookValidationError("payload 必须是 dict")

        sql = "SELECT * FROM webhooks WHERE active = 1"
        params: List[Any] = []
        if user_id is not None:
            sql += " AND (user_id = '' OR user_id = ?)"
            params.append(user_id)
        if tenant_id is not None:
            sql += " AND (tenant_id = '' OR tenant_id = ?)"
            params.append(tenant_id)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        delivered: List[Dict[str, Any]] = []
        for r in rows:
            sub_events = json.loads(r["events"]) if r["events"] else []
            if event_type not in sub_events:
                continue
            result = self._deliver_one(r["id"], r["url"], r["secret"], event_type, payload)
            delivered.append(result)
        return {
            "matched": len(delivered),
            "deliveries": delivered,
            "event_type": event_type,
        }

    # ── 投递 (单次) ──────────────────────────────────────────────────────

    def _deliver_one(
        self,
        subscription_id: str,
        url: str,
        secret: str,
        event_type: str,
        payload: Dict[str, Any],
        attempt: int = 1,
        sync: bool = True,
    ) -> Dict[str, Any]:
        """单次投递: HMAC 签名 + HTTP POST + 记录 deliveries。

        若失败且 attempt < MAX_ATTEMPTS, 同步模式下自动入 retry_queue。
        若 attempt == MAX_ATTEMPTS, 入 DLQ。
        """
        delivery_id = self._new_id("del")
        envelope = {
            "event_type": event_type,
            "delivery_id": delivery_id,
            "webhook_id": subscription_id,
            "timestamp": self._now_iso(),
            "attempt": attempt,
            "max_attempts": MAX_ATTEMPTS,
            "data": payload,
        }
        body_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        signature = self._sign(body_bytes, secret)

        # 真实 HTTP 发送; 测试时可注入 _http_post 替换
        try:
            http_status, response_body, error = self._http_post(
                url, body_bytes, signature, event_type, delivery_id, subscription_id
            )
            success = http_status is not None and 200 <= http_status < 300
        except Exception as exc:  # 网络层崩溃
            http_status, response_body, error = None, "", f"http_exception: {exc!r}"
            success = False

        status = "success" if success else "failed"
        now = self._now_iso()

        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO deliveries
                  (id, webhook_id, event_type, status, attempt, max_attempts,
                   http_status, request_body, response_body, error_message,
                   signature, payload_json, sent_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id, subscription_id, event_type, status, attempt, MAX_ATTEMPTS,
                    http_status,
                    body_bytes.decode("utf-8", errors="replace")[:4096],
                    (response_body or "")[:4096],
                    (error or "")[:512],
                    signature,
                    json.dumps(envelope, ensure_ascii=False)[:8192],
                    now, now,
                ),
            )
            conn.commit()

        result: Dict[str, Any] = {
            "delivery_id": delivery_id,
            "subscription_id": subscription_id,
            "attempt": attempt,
            "http_status": http_status,
            "success": success,
            "signature": f"sha256={signature}",
        }
        if not success:
            result["error"] = error or f"http_status={http_status}"
            if attempt < MAX_ATTEMPTS:
                # 入重试队列
                self._enqueue_retry(
                    subscription_id, delivery_id, event_type,
                    envelope, attempt + 1, error or f"http_status={http_status}",
                )
                result["status"] = "retrying"
                result["next_retry_in_seconds"] = BACKOFF_SCHEDULE_SECONDS[attempt - 1]
            else:
                # 入 DLQ
                self._enqueue_dlq(
                    subscription_id, delivery_id, event_type,
                    envelope, attempt, error or f"http_status={http_status}",
                    http_status, response_body,
                )
                result["status"] = "dead"
        else:
            result["status"] = "success"
        return result

    def _enqueue_retry(
        self,
        subscription_id: str,
        delivery_id: str,
        event_type: str,
        envelope: Dict[str, Any],
        next_attempt: int,
        last_error: str,
    ) -> str:
        retry_id = self._new_id("retry")
        # next_retry_at = now + BACKOFF_SCHEDULE_SECONDS[next_attempt - 2]
        # 当 attempt=1 失败 → next_attempt=2 → 退避 4s? 不, 我们约定:
        # attempt N 失败后, 退避 = BACKOFF_SCHEDULE_SECONDS[N-1]
        # 即: attempt 1 fail → 等 BACKOFF[0]=1s, attempt 2 fail → 等 BACKOFF[1]=4s, ...
        idx = max(0, min(next_attempt - 2, len(BACKOFF_SCHEDULE_SECONDS) - 1))
        delay = BACKOFF_SCHEDULE_SECONDS[idx]
        next_at = datetime.fromtimestamp(
            time.time() + delay, tz=timezone.utc
        ).isoformat()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO retry_queue
                  (id, webhook_id, delivery_id, event_type, payload_json,
                   attempt, next_retry_at, last_error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    retry_id, subscription_id, delivery_id, event_type,
                    json.dumps(envelope, ensure_ascii=False),
                    next_attempt, next_at, last_error[:512],
                    self._now_iso(),
                ),
            )
            conn.commit()
        return retry_id

    def _enqueue_dlq(
        self,
        subscription_id: str,
        delivery_id: str,
        event_type: str,
        envelope: Dict[str, Any],
        attempt: int,
        last_error: str,
        last_http_status: Optional[int],
        last_response: str,
    ) -> str:
        dlq_id = self._new_id("dlq")
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO dlq
                  (id, webhook_id, delivery_id, event_type, payload_json,
                   attempt, last_error, last_http_status, last_response, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dlq_id, subscription_id, delivery_id, event_type,
                    json.dumps(envelope, ensure_ascii=False),
                    attempt, last_error[:512],
                    last_http_status, (last_response or "")[:4096],
                    self._now_iso(),
                ),
            )
            conn.commit()
        return dlq_id

    # ── HTTP 注入点 (便于测试 mock) ──────────────────────────────────────

    _http_post_fn = None  # 测试时设: (url, body, sig, ...) -> (status, body, error)

    def _http_post(
        self,
        url: str,
        body: bytes,
        signature: str,
        event_type: str,
        delivery_id: str,
        subscription_id: str,
    ) -> Tuple[Optional[int], str, str]:
        """默认实现: 真实 aiohttp POST; 可被测试替换。"""
        fn = self._http_post_fn
        if fn is not None:
            return fn(url, body, signature, event_type, delivery_id, subscription_id)
        return self._aiohttp_post(
            url, body, signature, event_type, delivery_id, subscription_id
        )

    @staticmethod
    def _aiohttp_post(
        url: str,
        body: bytes,
        signature: str,
        event_type: str,
        delivery_id: str,
        subscription_id: str,
    ) -> Tuple[Optional[int], str, str]:
        try:
            import aiohttp  # 延迟 import, 让无 aiohttp 的测试环境也能跑
        except ImportError:
            return (None, "", "aiohttp 未安装, 无法 HTTP POST")

        async def _do():
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "IMDF-Webhook/1.0",
                "X-IMDF-Event": event_type,
                "X-IMDF-Signature": f"sha256={signature}",
                "X-IMDF-Delivery": delivery_id,
                "X-IMDF-Webhook-ID": subscription_id,
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=body, headers=headers, timeout=timeout) as resp:
                    text = await resp.text()
                    return (resp.status, text, "")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有 loop 里跑 (FastAPI 内部调用)
                return loop.run_until_complete(_do())
            return loop.run_until_complete(_do())
        except RuntimeError:
            return asyncio.run(_do())
        except Exception as exc:  # noqa: BLE001
            return (None, "", f"{type(exc).__name__}: {exc}"[:512])

    # ── 重试 worker ──────────────────────────────────────────────────────

    def process_retry_queue(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """扫描 retry_queue, 取出 next_retry_at <= now 的条目重新投递。

        返回本次处理的 retry 结果列表。生产环境可以挂定时器每 1-5s 调用一次。
        测试可手动调用 + 注入时间。
        """
        now_ts = now if now is not None else time.time()
        now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        results: List[Dict[str, Any]] = []
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM retry_queue WHERE next_retry_at <= ? ORDER BY next_retry_at",
                (now_iso,),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                qmarks = ",".join("?" * len(ids))
                conn.execute(f"DELETE FROM retry_queue WHERE id IN ({qmarks})", ids)
                conn.commit()
        for r in rows:
            sub_id = r["webhook_id"]
            sub = self.get_subscription(sub_id)
            if not sub or not sub["active"]:
                # 订阅已删除或停用, 把这条 retry 直接转 DLQ
                self._enqueue_dlq(
                    sub_id, r["delivery_id"], r["event_type"],
                    json.loads(r["payload_json"]),
                    r["attempt"], f"subscription {sub_id} inactive/missing",
                    None, "",
                )
                results.append({"retry_id": r["id"], "status": "dead"})
                continue
            envelope = json.loads(r["payload_json"])
            payload = envelope.get("data", {})
            result = self._deliver_one(
                sub_id, sub["url"], sub["secret"],
                r["event_type"], payload,
                attempt=r["attempt"], sync=True,
            )
            result["retry_id"] = r["id"]
            results.append(result)
        return results

    # ── 历史 / DLQ 查询 ─────────────────────────────────────────────────

    def list_deliveries(
        self,
        subscription_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM deliveries WHERE webhook_id = ? "
                "ORDER BY sent_at DESC LIMIT ?",
                (subscription_id, int(limit)),
            ).fetchall()
        return [self._row_to_delivery(r) for r in rows]

    @staticmethod
    def _row_to_delivery(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "delivery_id": row["id"],
            "webhook_id": row["webhook_id"],
            "event_type": row["event_type"],
            "status": row["status"],
            "attempt": row["attempt"],
            "max_attempts": row["max_attempts"] or MAX_ATTEMPTS,
            "http_status": row["http_status"],
            "error_message": row["error_message"],
            "signature": row["signature"],
            "sent_at": row["sent_at"],
            "completed_at": row["completed_at"],
            "next_retry_at": row["next_retry_at"],
        }

    def list_dlq(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT d.* FROM dlq d"
        params: List[Any] = []
        if user_id is not None:
            sql += (
                " LEFT JOIN webhooks w ON d.webhook_id = w.id"
                " WHERE (w.user_id = ? OR w.id IS NULL)"
            )
            params.append(user_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "dlq_id": r["id"],
                "webhook_id": r["webhook_id"],
                "delivery_id": r["delivery_id"],
                "event_type": r["event_type"],
                "attempt": r["attempt"],
                "last_error": r["last_error"],
                "last_http_status": r["last_http_status"],
                "last_response": (r["last_response"] or "")[:512],
                "created_at": r["created_at"],
                "retried_at": r["retried_at"],
            })
        return out

    def retry_dlq_entry(self, dlq_id: str) -> Dict[str, Any]:
        """手动重投 DLQ 条目, 重新进入正常投递链路 (attempt 重置为 1)。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dlq WHERE id = ?", (dlq_id,)
            ).fetchone()
            if not row:
                return {"ok": False, "error": f"dlq entry {dlq_id} not found"}
            sub = self.get_subscription(row["webhook_id"])
            if not sub:
                conn.execute("DELETE FROM dlq WHERE id = ?", (dlq_id,))
                conn.commit()
                return {"ok": False, "error": "subscription gone, dropped"}
            envelope = json.loads(row["payload_json"])
            payload = envelope.get("data", {})
            # 删除 DLQ 记录
            conn.execute("DELETE FROM dlq WHERE id = ?", (dlq_id,))
            conn.commit()
        # 同步重投 (attempt=1)
        result = self._deliver_one(
            sub["subscription_id"], sub["url"], sub["secret"],
            row["event_type"], payload, attempt=1, sync=True,
        )
        result["dlq_id"] = dlq_id
        result["ok"] = True
        return result

    # ── 测试 / 维护 ──────────────────────────────────────────────────────

    def reset_db(self) -> None:
        """清空所有表 (测试用, 不会 DROP 表)。"""
        with self._lock, self._conn() as conn:
            for tbl in ("dlq", "retry_queue", "deliveries", "webhooks"):
                conn.execute(f"DELETE FROM {tbl}")
            conn.commit()

    @classmethod
    def instance(cls) -> "WebhookEngine":
        """获取/创建进程级单例。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_for_tests(cls) -> None:
        """重置单例 (测试隔离)。"""
        cls._instance = None