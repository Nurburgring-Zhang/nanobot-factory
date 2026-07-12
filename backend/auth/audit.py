#!/usr/bin/env python3
"""
Nanobot Factory — Audit log helper for unified_auth state changes (P21 P2 P3 R1-02).

文件: auth/audit.py
功能: 提供 ``AuditLog.write`` 统一接口, 把用户管理类状态变更
      (user.created / password.changed / user.deleted / user.updated) 写入
      已有 ``auth_audit_log`` 表 (schema 由 AuthDatabase._init_db 拥有, 此处
      不改动)。

OWASP A09:2021 — Security Logging & Monitoring 修复
      R1 audit gap #02: register_user / change_password / delete_user
      之前完全跳过 audit log, R2 reproducer 验证审计追踪为 ``[]``。

设计原则:
  * 不引入新依赖, 不改 schema — 复用现有 ``auth_audit_log`` 表
  * 与现有 ``UnifiedAuthManager._audit`` 互补: 后者记录 auth.* 事件
    (login / logout / lock), 本类记录 user.* 状态变更
  * 写失败不抛出 — 审计日志失败不应阻塞业务操作, 仅记 logger.error
"""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("auth.audit")


class AuditLog:
    """Audit log writer for user-management state-changing actions.

    Args:
        db: ``AuthDatabase`` instance (must expose ``_get_conn()`` and ``_lock``).
        resource: resource name written to the ``resource`` column (default ``"user"``).

    Schema (owned by ``AuthDatabase._init_db`` — DO NOT modify):
        log_id      TEXT PRIMARY KEY,
        user_id     TEXT,                       # actor (the user performing the change)
        action      TEXT NOT NULL,              # e.g. "user.created"
        resource    TEXT NOT NULL DEFAULT 'auth',
        result      TEXT NOT NULL DEFAULT 'success',
        ip_address  TEXT,
        details     TEXT NOT NULL DEFAULT '{}', # JSON: target + role + extra context
        timestamp   TEXT NOT NULL DEFAULT '',
    """

    def __init__(self, db: Any, resource: str = "user") -> None:
        self._db = db
        self._lock = getattr(db, "_lock", threading.Lock())
        self._resource = resource

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        action: str,
        actor: str,
        target: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        result: str = "success",
    ) -> None:
        """Write one audit log entry to ``auth_audit_log``.

        Args:
            action:    dotted action name, e.g. ``"user.created"``.
            actor:     user_id of the actor performing the change
                       (``"system"`` for bootstrap).
            target:    user_id being acted upon (stored under
                       ``details["target"]`` for forensic queries).
            details:   optional dict with extra context
                       (e.g. ``{"role": "admin", "username": "alice"}``).
            ip_address: optional client IP.
            result:    ``"success"`` / ``"failed"`` — default ``"success"``.

        Returns:
            None. Audit failure is logged but NEVER raised
            (审计失败不应阻塞业务操作).
        """
        if not action:
            logger.error("AuditLog.write called without action; skipping")
            return

        # Merge target into details — this is the forensic join key.
        merged: Dict[str, Any] = dict(details or {})
        if target and target != actor:
            # Only store target separately if it differs from actor
            # (for password.changed actor==target, don't duplicate).
            merged.setdefault("target", target)

        log_id = f"log_{secrets.token_hex(8)}"
        payload = json.dumps(merged, ensure_ascii=False)
        ts = datetime.now().isoformat()
        resource = self._resource

        try:
            with self._lock:
                conn = self._db._get_conn()
                try:
                    conn.execute(
                        """
                        INSERT INTO auth_audit_log
                        (log_id, user_id, action, resource, result,
                         ip_address, details, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (log_id, actor, action, resource, result,
                         ip_address, payload, ts),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error as e:
            # NEVER raise from audit logging
            logger.error(
                "AuditLog.write failed (action=%s actor=%s target=%s): %s",
                action, actor, target, e,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.error(
                "AuditLog.write unexpected error (action=%s): %s",
                action, e,
            )

    # ------------------------------------------------------------------
    # Query helpers (read-only; used by tests + future admin endpoints)
    # ------------------------------------------------------------------

    def list_entries(
        self,
        action: Optional[str] = None,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """List recent audit entries, optionally filtered by action/actor/target.

        ``target`` is matched against the JSON ``details`` column
        (since target is stored there for forensic queries).
        """
        conds: list = []
        params: list = []
        if action:
            conds.append("action = ?")
            params.append(action)
        if actor:
            conds.append("user_id = ?")
            params.append(actor)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""

        with self._lock:
            conn = self._db._get_conn()
            try:
                rows = conn.execute(
                    f"SELECT log_id, user_id, action, resource, result, "
                    f"ip_address, details, timestamp "
                    f"FROM auth_audit_log {where} "
                    f"ORDER BY timestamp DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
            finally:
                conn.close()

        entries = []
        for r in rows:
            try:
                details = json.loads(r["details"] or "{}")
            except (json.JSONDecodeError, TypeError):
                details = {}
            entry = {
                "log_id": r["log_id"],
                "user_id": r["user_id"],
                "action": r["action"],
                "resource": r["resource"],
                "result": r["result"],
                "ip_address": r["ip_address"],
                "details": details,
                "timestamp": r["timestamp"],
            }
            # If a target filter was given and the JSON doesn't have it,
            # skip the row (target lives inside ``details``).
            if target and entry["details"].get("target") != target:
                continue
            entries.append(entry)
        return entries
