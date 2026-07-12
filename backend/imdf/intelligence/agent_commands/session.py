"""智影 V4 — SessionManager: 多用户会话管理 + 上下文维护"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .intent import Intent

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """会话上下文 — 跨轮对话信息"""

    user_id: str = ""
    session_id: str = ""
    started_at: float = 0.0
    last_active: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    last_intent: Optional[Dict[str, Any]] = None
    pending_confirmation: Optional[Dict[str, Any]] = None
    working_set: List[Dict[str, Any]] = field(default_factory=list)  # 当前会话操作的 item 集合
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self):
        self.last_active = time.time()

    def add_turn(self, role: str, text: str, meta: Optional[Dict[str, Any]] = None):
        self.history.append(
            {"role": role, "text": text, "ts": time.time(), "meta": meta or {}}
        )
        # 限制 history 长度
        if len(self.history) > 200:
            self.history = self.history[-100:]
        self.touch()

    def add_to_working_set(self, item: Dict[str, Any]):
        # 去重
        for existing in self.working_set:
            if existing.get("id") == item.get("id") or existing.get("hash") == item.get("hash"):
                return
        self.working_set.append(item)
        if len(self.working_set) > 500:
            self.working_set = self.working_set[-300:]

    def clear_working_set(self):
        self.working_set.clear()

    def set_variable(self, key: str, value: Any):
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)


@dataclass
class AgentSession:
    """Agent 会话"""

    session_id: str
    context: SessionContext
    status: str = "active"  # active / idle / closed
    created_at: float = 0.0
    closed_at: float = 0.0

    def close(self):
        self.status = "closed"
        self.closed_at = time.time()


class SessionManager:
    """会话管理器 — in-memory (生产可换 Redis)"""

    def __init__(self, max_sessions: int = 1000, idle_timeout: int = 3600):
        self.sessions: Dict[str, AgentSession] = {}
        self.user_index: Dict[str, List[str]] = {}  # user_id → [session_id]
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        # 统计
        self.metrics = {
            "total_created": 0,
            "total_closed": 0,
            "expired_cleaned": 0,
        }

    def create_session(
        self, user_id: str = "default", metadata: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None
    ) -> AgentSession:
        if len(self.sessions) >= self.max_sessions:
            self._cleanup_expired()
        if session_id is None:
            session_id = f"sess-{uuid.uuid4().hex[:16]}"
        ctx = SessionContext(
            user_id=user_id,
            session_id=session_id,
            started_at=time.time(),
            last_active=time.time(),
            metadata=metadata or {},
        )
        session = AgentSession(session_id=session_id, context=ctx, created_at=time.time())
        self.sessions[session_id] = session
        self.user_index.setdefault(user_id, []).append(session_id)
        self.metrics["total_created"] += 1
        logger.info(f"created session {session_id} for user {user_id}")
        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        s = self.sessions.get(session_id)
        if s is None or s.status == "closed":
            return None
        s.context.touch()
        return s

    def get_or_create(self, session_id: Optional[str] = None, user_id: str = "default") -> AgentSession:
        if session_id:
            s = self.get_session(session_id)
            if s:
                return s
            # 给定的 session_id 不存在 → 用此 ID 创建 (而非生成新的)
            return self.create_session(user_id=user_id, session_id=session_id)
        return self.create_session(user_id=user_id)

    def close_session(self, session_id: str):
        s = self.sessions.get(session_id)
        if s:
            s.close()
            self.metrics["total_closed"] += 1

    def get_user_sessions(self, user_id: str) -> List[AgentSession]:
        ids = self.user_index.get(user_id, [])
        return [self.sessions[i] for i in ids if i in self.sessions and self.sessions[i].status != "closed"]

    def update_context(self, session_id: str, intent: Optional[Intent] = None, last_result: Optional[Any] = None) -> None:
        s = self.get_session(session_id)
        if not s:
            return
        if intent:
            s.context.last_intent = {
                "category": intent.category.value,
                "action": intent.action,
                "confidence": intent.confidence,
                "entities": intent.entities,
            }
        s.context.touch()

    def _cleanup_expired(self):
        """清理过期 session"""
        now = time.time()
        expired = []
        for sid, s in self.sessions.items():
            if s.status == "closed":
                expired.append(sid)
                continue
            if now - s.context.last_active > self.idle_timeout:
                expired.append(sid)
        for sid in expired:
            self.close_session(sid)
            self.metrics["expired_cleaned"] += 1
        for user_id, sids in list(self.user_index.items()):
            self.user_index[user_id] = [s for s in sids if s in self.sessions]

    def cleanup(self):
        """全量清理"""
        self._cleanup_expired()

    def get_metrics(self) -> Dict[str, Any]:
        active = sum(1 for s in self.sessions.values() if s.status == "active")
        return {
            "active_sessions": active,
            "total_sessions": len(self.sessions),
            **self.metrics,
        }
