"""F9.2 Webhooks API — P1-A2-W2 重写版
================================================================

基于 :class:`engines.webhook_engine.WebhookEngine` 暴露 HTTP 端点:

* POST   /api/v1/webhooks/subscribe                  — 创建订阅 (返回 secret 一次)
* GET    /api/v1/webhooks/subscriptions              — 列出当前用户的所有订阅
* DELETE /api/v1/webhooks/subscriptions/{id}         — 取消订阅
* PUT    /api/v1/webhooks/subscriptions/{id}/rotate-secret — 轮换 secret
* POST   /api/v1/webhooks/test/{subscription_id}     — 发送测试事件 (test.ping)
* GET    /api/v1/webhooks/deliveries/{subscription_id} — 投递历史
* GET    /api/v1/webhooks/dlq                        — 死信队列 (DLQ)
* POST   /api/v1/webhooks/dlq/{dlq_id}/retry         — 重投 DLQ 条目

向后兼容: 保留 R2/R3 既有端点 (POST/GET/PUT/DELETE ``/api/v1/webhooks[/...]``),
``/event-types`` 列出 36+ 事件类型。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from api._common.task_id_validator import validate_task_id
from api._common.webhook_url_validator import validate_webhook_url
from api._common.pagination_compat import PaginationParams
from engines.webhook_engine import (
    BACKOFF_SCHEDULE_SECONDS,
    EVENT_TYPES,
    MAX_ATTEMPTS,
    VALID_EVENT_TYPES,
    WebhookEngine,
    WebhookNotFoundError,
    WebhookValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# ── Engine 单例 ─────────────────────────────────────────────────────────────

_engine: Optional[WebhookEngine] = None


def _get_engine() -> WebhookEngine:
    global _engine
    if _engine is None:
        _engine = WebhookEngine()
    return _engine


def _set_engine_for_tests(engine: Optional[WebhookEngine]) -> None:
    """测试用: 注入 mock engine (None 表示重置回默认)。"""
    global _engine
    _engine = engine


# ── DB 路径常量 (供测试导入 / 维护使用) ─────────────────────────────────────

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "webhooks.db")


# ── Pydantic 模型 ───────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    url: str = Field(..., max_length=2048, description="Webhook 接收 URL")
    events: List[str] = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=512)
    secret: Optional[str] = Field(default=None, max_length=512)
    user_id: Optional[str] = Field(default=None, max_length=128)
    tenant_id: Optional[str] = Field(default=None, max_length=128)
    max_retries: int = Field(default=MAX_ATTEMPTS, ge=0, le=MAX_ATTEMPTS)

    @field_validator("url")
    @classmethod
    def _v_url(cls, v: str) -> str:
        return validate_webhook_url(v, "url")

    @field_validator("events")
    @classmethod
    def _v_events(cls, v: List[str]) -> List[str]:
        invalid = [e for e in v if e not in VALID_EVENT_TYPES]
        if invalid:
            raise ValueError(f"事件类型非法: {invalid}, 允许: {sorted(VALID_EVENT_TYPES)}")
        return v


class TestEventRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


# ── 工具 ────────────────────────────────────────────────────────────────────

def _caller_id(request: Request, fallback_field: Optional[str] = None) -> str:
    """提取调用者 ID (从 X-User-ID header, 或 fallback 字段)。"""
    uid = request.headers.get("X-User-ID") or request.headers.get("x-user-id")
    if uid:
        return uid
    if fallback_field is not None:
        return fallback_field
    # 测试/匿名调用 → 空字符串 (匹配所有 user_id=空 的订阅)
    return ""


# ── 健康 / 事件类型 ────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "module": "webhooks",
        "version": "1.1.0",
        "engine": "WebhookEngine",
        "event_types_count": len(EVENT_TYPES),
        "max_attempts": MAX_ATTEMPTS,
        "backoff_schedule_seconds": BACKOFF_SCHEDULE_SECONDS,
    }


@router.get("/event-types")
async def list_event_types(category: Optional[str] = None):
    types = EVENT_TYPES
    if category:
        types = [t for t in t if t["category"] == category]
    categories = sorted({t["category"] for t in EVENT_TYPES})
    return {
        "ok": True,
        "data": {
            "event_types": types,
            "total": len(types),
            "categories": categories,
        },
    }


# ── P1-A2 新端点 (注册顺序优先, 避免与 R3 的 /{webhook_id} 路径冲突) ─────────

@router.post("/subscribe")
async def subscribe(req: SubscribeRequest, request: Request):
    """创建订阅。返回 subscription_id + secret (一次性)。"""
    eng = _get_engine()
    # 跨用户隔离: 未登录时把 X-User-ID 作为 owner, 显式 user_id 字段可覆盖
    caller = _caller_id(request)
    user_id = req.user_id or caller or None
    try:
        sub = eng.subscribe(
            url=req.url,
            events=req.events,
            secret=req.secret,
            user_id=user_id,
            tenant_id=req.tenant_id,
            description=req.description,
            max_retries=req.max_retries,
        )
    except WebhookValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "data": sub}


@router.get("/subscriptions")
async def list_subscriptions(
    request: Request,
    user_id: Optional[str] = Query(None, max_length=128),
    tenant_id: Optional[str] = Query(None, max_length=128),
    active_only: bool = False,
):
    """列出订阅。默认按当前 caller (X-User-ID header) 过滤; 显式 user_id 可覆盖。"""
    eng = _get_engine()
    caller = _caller_id(request)
    # 安全: caller 必须显式提供或被 query 指定 (跨用户隔离测试)
    effective_user = user_id if user_id is not None else caller
    subs = eng.list_subscriptions(
        user_id=effective_user if effective_user else None,
        tenant_id=tenant_id,
        active_only=active_only,
    )
    return {"ok": True, "data": {"subscriptions": subs, "total": len(subs)}}


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    validate_task_id(subscription_id, "subscription_id")
    eng = _get_engine()
    ok = eng.unsubscribe(subscription_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"subscription {subscription_id} 不存在")
    return {"ok": True, "data": {"subscription_id": subscription_id, "deleted": True}}


@router.put("/subscriptions/{subscription_id}/rotate-secret")
async def rotate_subscription_secret(subscription_id: str):
    validate_task_id(subscription_id, "subscription_id")
    eng = _get_engine()
    try:
        result = eng.rotate_secret(subscription_id)
    except WebhookNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "data": result}


@router.post("/test/{subscription_id}")
async def send_test_event(subscription_id: str, req: Optional[TestEventRequest] = None):
    """发送 test.ping 事件到指定订阅 (无需真实外部 HTTP, 走本地投递链路)。"""
    validate_task_id(subscription_id, "subscription_id")
    eng = _get_engine()
    sub = eng.get_subscription(subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"subscription {subscription_id} 不存在")
    test_payload = (req.payload if req and req.payload else {"message": "ping", "test": True})
    dispatch_result = eng.dispatch(
        event_type="test.ping",
        payload=test_payload,
        user_id=sub["user_id"] or None,
        tenant_id=sub["tenant_id"] or None,
    )
    # dispatch 已按 user/tenant 过滤; 确认 matched>=1
    matched = dispatch_result["matched"]
    if matched == 0:
        # 显式触发一次 (忽略 user/tenant filter)
        result = eng._deliver_one(
            subscription_id, sub["url"], sub["secret"],
            "test.ping", test_payload, attempt=1,
        )
        return {"ok": True, "data": {"test": result}}
    return {"ok": True, "data": {"test": dispatch_result["deliveries"][0]}}


@router.get("/deliveries/{subscription_id}")
async def list_subscription_deliveries(
    subscription_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    validate_task_id(subscription_id, "subscription_id")
    eng = _get_engine()
    if not eng.get_subscription(subscription_id):
        raise HTTPException(status_code=404, detail=f"subscription {subscription_id} 不存在")
    deliveries = eng.list_deliveries(subscription_id, limit=limit)
    return {"ok": True, "data": {"deliveries": deliveries, "total": len(deliveries)}}


@router.get("/dlq")
async def list_dlq(
    request: Request,
    user_id: Optional[str] = Query(None, max_length=128),
    limit: int = Query(100, ge=1, le=500),
):
    """死信队列。默认按当前 caller 过滤。"""
    eng = _get_engine()
    caller = _caller_id(request)
    effective_user = user_id if user_id is not None else caller
    items = eng.list_dlq(user_id=effective_user or None, limit=limit)
    return {"ok": True, "data": {"dlq": items, "total": len(items)}}


@router.post("/dlq/{dlq_id}/retry")
async def retry_dlq_entry_endpoint(dlq_id: str):
    """手动重投一条 DLQ 条目。"""
    eng = _get_engine()
    result = eng.retry_dlq_entry(dlq_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "retry failed"))
    return {"ok": True, "data": result}


# ── 向后兼容: R2/R3 既有端点 (使用 engine 包装) ───────────────────────────

@router.get("")
async def list_webhooks_compat(p: PaginationParams = Depends()):
    """R2/R3 兼容: 列出所有订阅 (无 user 过滤, 仅管理视图)。"""
    eng = _get_engine()
    subs = eng.list_subscriptions(active_only=False)
    # 取 limit/skip
    sliced = subs[p.skip:p.skip + p.limit]
    return {"ok": True, "data": {"webhooks": sliced, "total": len(subs)}}


@router.get("/{webhook_id}")
async def get_webhook_compat(webhook_id: str):
    validate_task_id(webhook_id, "webhook_id")
    eng = _get_engine()
    sub = eng.get_subscription(webhook_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} not found")
    return {"ok": True, "data": sub}


@router.delete("/{webhook_id}")
async def delete_webhook_compat(webhook_id: str):
    validate_task_id(webhook_id, "webhook_id")
    eng = _get_engine()
    if not eng.unsubscribe(webhook_id):
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} not found")
    return {"ok": True, "data": {"webhook_id": webhook_id, "deleted": True}}


@router.post("/{webhook_id}/test")
async def test_webhook_compat(webhook_id: str):
    """R2/R3 兼容: 旧版 /{id}/test 路径。"""
    validate_task_id(webhook_id, "webhook_id")
    eng = _get_engine()
    sub = eng.get_subscription(webhook_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} not found")
    result = eng._deliver_one(
        webhook_id, sub["url"], sub["secret"],
        "test.ping", {"message": "compat test ping"}, attempt=1,
    )
    return {
        "ok": True,
        "data": {
            "webhook_id": webhook_id,
            "delivery_id": result["delivery_id"],
            "http_status": result["http_status"],
            "success": result["success"],
            "status": result["status"],
        },
    }