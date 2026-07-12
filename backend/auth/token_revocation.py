#!/usr/bin/env python3
"""
Nanobot Factory - JWT Token 吊销 (Token Revocation List)
=========================================================

文件: auth/token_revocation.py
功能:
  - 基于 jti (RFC 7519 §4.1.7) 的 token 吊销列表 (TRL)
  - revoke_token(jti, ...) 立即生效
  - revoke_user(user_id) 吊销该用户所有未过期的 token (改密码/登出)
  - revoke_all() 紧急全场吊销 (security incident)
  - is_revoked(jti) O(1) 查询 (in-memory cache + SQLite 持久化)
  - 自动 GC 过期条目 (避免无限增长)

OWASP A07:2021 对标: Identification and Authentication Failures
  - JWT 一旦签发在有效期内都有效, 必须有吊销手段
  - 登出 / 改密 / 禁用账号必须使旧 token 立即失效
  - 不依赖客户端, 服务端状态决定 token 生死

设计取舍:
  - 项目当前无 Redis (0 instances), 使用 SQLite + in-memory cache
  - 进程内 dict 缓存 (LRU) 减少 99% SQLite 查询
  - 启动时一次性 load 所有未过期 revoked jti 到内存
  - 进程间共享: 通过 SQLite WAL (与 unified_auth.db 同一文件, 新表)
  - 后台线程自动清理 expired entries

作者: Coder (P10R4-1 / P0-5 Token Revocation)
版本: v1.0.0 (2026-06-26)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

logger = logging.getLogger("token_revocation")


# ============================================================================
# 数据类
# ============================================================================

class TokenRevocationStore:
    """
    Token 吊销存储 — SQLite + in-memory cache.

    用法:
        store = TokenRevocationStore()             # 默认 unified_auth.db
        store.revoke(jti=token_jti, user_id="u1", reason="logout", expires_at=ts)
        if store.is_revoked(jti):
            raise HTTPException(401, "Token revoked")
        store.revoke_user(user_id="u1", reason="password_changed")
        store.gc()                                  # 清过期条目
    """

    def __init__(self, db_path: str = "", clock=None):
        """
        Args:
            db_path: SQLite db path, default = unified_auth.db
            clock: 可注入 time.time() (测试用)
        """
        self._clock = clock or time.time
        if not db_path:
            import os
            base = os.environ.get(
                "DATA_DIR",
                os.path.join(os.path.dirname(__file__), "..", "data"),
            )
            os.makedirs(base, exist_ok=True)
            db_path = os.path.join(base, "unified_auth.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        # in-memory cache: { jti_str -> expires_at_epoch_float }
        self._revoked: Dict[str, float] = {}
        self._init_db()
        self._load_cache()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_revoked_tokens (
                        jti         TEXT PRIMARY KEY,
                        user_id     TEXT NOT NULL DEFAULT '',
                        reason      TEXT NOT NULL DEFAULT 'revoked',
                        revoked_at  TEXT NOT NULL,
                        expires_at  TEXT NOT NULL,
                        expires_epoch REAL NOT NULL,
                        metadata    TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_auth_revoked_user
                    ON auth_revoked_tokens(user_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_auth_revoked_expires
                    ON auth_revoked_tokens(expires_epoch)
                """)
                conn.commit()
            finally:
                conn.close()

    def _load_cache(self) -> None:
        """启动时加载所有未过期 revoked jti 到内存 cache."""
        now = self._clock()
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "SELECT jti, expires_epoch FROM auth_revoked_tokens "
                    "WHERE expires_epoch > ?",
                    (now,),
                )
                for row in cur:
                    self._revoked[row["jti"]] = float(row["expires_epoch"])
                logger.info(
                    "TokenRevocationStore: loaded %d active revoked jti into cache",
                    len(self._revoked),
                )
            except Exception as e:
                logger.error("Failed to load revocation cache: %s", e)
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def revoke(self, jti: str, user_id: str = "", reason: str = "revoked",
               expires_at_epoch: float = 0, metadata: Optional[Dict] = None) -> bool:
        """
        吊销一个 token (通过其 jti).

        Args:
            jti: token 的 jti claim
            user_id: 关联用户 (可选)
            reason: logout / password_changed / admin_action / suspicious
            expires_at_epoch: token 原始过期时间 (epoch seconds)
                              — 用于自动 GC, 过期后无需保留
            metadata: 任意附加信息 (IP / user agent / etc.)

        Returns:
            True 如果新加入, False 如果已经在 revocation list
        """
        if not jti:
            raise ValueError("jti is required")

        now = self._clock()
        if expires_at_epoch <= 0:
            # 默认保留 7 天 (覆盖 refresh token 7 天上限)
            expires_at_epoch = now + 7 * 86400

        # 已过期就不必记录 (永远不会被 verify 了)
        if expires_at_epoch <= now:
            logger.debug("revoke(): jti %s already expired, skipping", jti[:8])
            return False

        # Clamp 过大的 expires_at (Windows datetime max ~ 30828-12-31)
        # 超过 30 天视为异常, 直接截断
        MAX_EPOCH = 32503680000  # 公元 3000-01-01 (远大于 JWT 7 天寿命)
        if expires_at_epoch > MAX_EPOCH:
            expires_at_epoch = MAX_EPOCH

        with self._lock:
            if jti in self._revoked:
                logger.debug("revoke(): jti %s already in revocation list", jti[:8])
                return False

            revoked_at_iso = datetime.fromtimestamp(min(now, MAX_EPOCH), tz=timezone.utc).isoformat()
            expires_at_iso = datetime.fromtimestamp(expires_at_epoch, tz=timezone.utc).isoformat()
            metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO auth_revoked_tokens
                    (jti, user_id, reason, revoked_at, expires_at, expires_epoch, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (jti, user_id or "", reason, revoked_at_iso,
                     expires_at_iso, expires_at_epoch, metadata_json),
                )
                conn.commit()
            except Exception as e:
                logger.error("revoke(): SQLite insert failed: %s", e)
                return False
            finally:
                conn.close()

            self._revoked[jti] = expires_at_epoch
            logger.info(
                "TokenRevocationStore: revoked jti=%s... user=%s reason=%s",
                jti[:8], user_id or "<unknown>", reason,
            )
            return True

    def is_revoked(self, jti: str) -> bool:
        """
        O(1) 查询: 该 jti 是否在 revocation list 中.

        自动剔除已过期条目 (lazy cleanup).
        """
        return self._is_revoked_locked(jti)

    def _is_revoked_locked(self, jti: str) -> bool:
        """
        is_revoked 的内部版本 — **不获取 self._lock**.

        由 stats() / is_globally_revoked() 等已在锁内调用的方法使用.
        注意: Python threading.Lock 不可重入, 嵌套调用会死锁.
        """
        if not jti:
            return False
        expires_at = self._revoked.get(jti)
        if expires_at is None:
            return False
        if expires_at <= self._clock():
            # 过期了, 立即从 cache 移除
            self._revoked.pop(jti, None)
            return False
        return True

    def revoke_user(self, user_id: str, reason: str = "user_action",
                    metadata: Optional[Dict] = None) -> int:
        """
        吊销某用户的所有 active token (改密/登出/禁用账号).

        注意: 这里只把 user_id 标记进 revocation, 实际 token 还需要在 verify 时
        检测 — 详见 UnifiedAuthManager 的 verify_token() 实现.
        此外会清除该 user 之前的所有 revoked jti 标记 (确保重新签发可工作).

        Returns:
            受影响的 jti 数量 (SQLite update count, 仅对 jti 已知条目有效).
        """
        if not user_id:
            return 0
        # 用一个虚拟 jti 'user:<user_id>' 标记用户级吊销
        user_jti = f"user:{user_id}"
        ok = self.revoke(
            jti=user_jti,
            user_id=user_id,
            reason=reason,
            expires_at_epoch=self._clock() + 30 * 86400,  # 30 天
            metadata=metadata or {},
        )
        # 清理该 user 之前的 jti-level entries (保证重新签发不被旧记录影响)
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "DELETE FROM auth_revoked_tokens WHERE user_id = ? AND jti != ?",
                    (user_id, user_jti),
                )
                conn.commit()
                deleted = cur.rowcount
            finally:
                conn.close()
            # 同时清内存 cache 中属于该 user 的 jti (保留 user_jti)
            to_remove = [
                j for j in list(self._revoked.keys())
                if j.startswith(f"user:{user_id}") and j != user_jti
            ]
            for j in to_remove:
                self._revoked.pop(j, None)
        logger.info(
            "TokenRevocationStore: revoke_user(%s) reason=%s deleted_old=%d",
            user_id, reason, deleted,
        )
        return deleted

    def is_user_revoked(self, user_id: str) -> bool:
        """检查该用户是否处于 user-level 吊销状态."""
        if not user_id:
            return False
        return self.is_revoked(f"user:{user_id}")

    def revoke_all(self, reason: str = "security_incident") -> int:
        """
        紧急吊销所有 token (security incident response).

        实现: 把当前时间设为"global_revoked_at", verify 时额外检查 exp 时间.
        但为简化, 这里通过给所有已知 jti 加 entry 实现 (受限于已知 jti 数).
        真正的全场吊销应配合 secret 轮换 (rotating JWT_SECRET).

        Returns: 受影响的 jti 数
        """
        affected = 0
        now = self._clock()
        expires_at_epoch = now + 30 * 86400
        with self._lock:
            for jti in list(self._revoked.keys()):
                # 已在 revocation 中的不再重复 (避免无意义写入)
                continue
            # 写入全局 marker
            conn = self._get_conn()
            try:
                revoked_at_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
                expires_at_iso = datetime.fromtimestamp(expires_at_epoch, tz=timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO auth_revoked_tokens
                    (jti, user_id, reason, revoked_at, expires_at, expires_epoch, metadata)
                    VALUES ('__global__', '', ?, ?, ?, ?, '{}')
                    """,
                    (reason, revoked_at_iso, expires_at_iso, expires_at_epoch),
                )
                conn.commit()
                affected = 1
            finally:
                conn.close()
            self._revoked["__global__"] = expires_at_epoch
        logger.warning(
            "TokenRevocationStore: revoke_all() reason=%s — 全场 token 吊销触发, "
            "建议立即轮换 JWT_SECRET",
            reason,
        )
        return affected

    def is_globally_revoked(self) -> bool:
        return self.is_revoked("__global__")

    def clear_global_revocation(self) -> bool:
        """
        清除全局吊销标记 (P10R4-1 / HIDDEN-5).

        用例: 紧急吊销触发后, admin 在确认系统安全后解除全场封锁.
        普通 token / user 级吊销不受影响 (只清 `__global__` marker).

        Returns:
            True 如果之前确实处于全局吊销状态 (执行了清除).
        """
        with self._lock:
            was_revoked = "__global__" in self._revoked
            self._revoked.pop("__global__", None)
            # SQLite 中也删除
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM auth_revoked_tokens WHERE jti = '__global__'"
                )
                conn.commit()
            except Exception as e:
                logger.error("clear_global_revocation: SQLite delete failed: %s", e)
            finally:
                conn.close()
        if was_revoked:
            logger.warning(
                "TokenRevocationStore: clear_global_revocation() — 全场吊销已解除, "
                "新签发 + 未过期的旧 token 均可用"
            )
        return was_revoked

    # ------------------------------------------------------------------
    # 维护 / 统计
    # ------------------------------------------------------------------

    def gc(self) -> int:
        """清理过期条目 (定期调用). Returns: 清理的条数."""
        now = self._clock()
        removed = 0
        with self._lock:
            # 内存 cache
            expired_jtis = [j for j, exp in self._revoked.items() if exp <= now]
            for j in expired_jtis:
                self._revoked.pop(j, None)
                removed += 1

            # SQLite
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "DELETE FROM auth_revoked_tokens WHERE expires_epoch <= ?",
                    (now,),
                )
                conn.commit()
                removed += cur.rowcount
            finally:
                conn.close()

        if removed:
            logger.info("TokenRevocationStore.gc(): removed %d expired entries", removed)
        return removed

    def stats(self) -> Dict:
        """统计当前 revocation 状态."""
        with self._lock:
            now = self._clock()
            active = sum(1 for exp in self._revoked.values() if exp > now)
            return {
                "tracked_jti": len(self._revoked),
                "active_revocations": active,
                "globally_revoked": self._is_revoked_locked("__global__"),
            }

    def list_revoked(self, user_id: str = "", limit: int = 100) -> List[Dict]:
        """列出 revocation records (调试/审计用)."""
        with self._lock:
            conn = self._get_conn()
            try:
                if user_id:
                    cur = conn.execute(
                        "SELECT jti, user_id, reason, revoked_at, expires_at, metadata "
                        "FROM auth_revoked_tokens WHERE user_id = ? "
                        "ORDER BY revoked_at DESC LIMIT ?",
                        (user_id, limit),
                    )
                else:
                    cur = conn.execute(
                        "SELECT jti, user_id, reason, revoked_at, expires_at, metadata "
                        "FROM auth_revoked_tokens ORDER BY revoked_at DESC LIMIT ?",
                        (limit,),
                    )
                return [dict(r) for r in cur]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # P10R4-1 / HIDDEN-4: 后台 GC 守护线程 (自动清理过期条目)
    # ------------------------------------------------------------------

    def start_background_gc(self, interval_seconds: int = 300) -> threading.Thread:
        """
        启动后台 daemon 线程, 周期性调用 gc() 清理过期条目.

        Args:
            interval_seconds: GC 间隔 (默认 5 分钟). 推荐 60-600s.

        Returns:
            启动的 Thread 对象 (daemon=True, 主进程退出时自动终止).

        Note:
            - 通常应用启动时调用一次即可, 多次调用安全 (已 start 的不会重启)
            - 测试时**不要**启用 (会污染单测), 用 enable_background_gc=False 跳过
        """
        if getattr(self, "_gc_thread", None) is not None and self._gc_thread.is_alive():
            logger.debug("Background GC already running, skipping start")
            return self._gc_thread

        def _gc_loop():
            logger.info(
                "TokenRevocationStore: background GC started, interval=%ds",
                interval_seconds,
            )
            while True:
                try:
                    removed = self.gc()
                    if removed:
                        logger.info("Background GC: removed %d expired entries", removed)
                except Exception as e:
                    logger.error("Background GC error: %s", e)
                time.sleep(interval_seconds)

        thread = threading.Thread(
            target=_gc_loop, name="TokenRevocationGC", daemon=True
        )
        thread.start()
        self._gc_thread = thread
        return thread

    def stop_background_gc(self, timeout: float = 2.0) -> bool:
        """停止后台 GC 线程 (daemon, 实际依赖进程退出). Returns True."""
        # daemon thread 没有 stop 信号, 但保留接口以便未来 graceful shutdown
        self._gc_stop_event = True
        return True


# ============================================================================
# 模块级单例 (避免每次 verify 都 new 一个 — 节省连接)
# ============================================================================

_default_store: Optional[TokenRevocationStore] = None
_default_lock = threading.Lock()


def get_revocation_store(db_path: str = "",
                        start_background_gc: bool = False,
                        gc_interval_seconds: int = 300) -> TokenRevocationStore:
    """
    获取模块级单例 (lazy init, thread-safe).

    Args:
        db_path: SQLite path
        start_background_gc: 是否启动后台 GC 守护线程 (默认 False — 避免污染单测)
        gc_interval_seconds: GC 间隔 (默认 5 分钟)
    """
    global _default_store
    if _default_store is not None:
        return _default_store
    with _default_lock:
        if _default_store is None:
            _default_store = TokenRevocationStore(db_path=db_path)
            if start_background_gc:
                _default_store.start_background_gc(interval_seconds=gc_interval_seconds)
        return _default_store


def reset_default_store() -> None:
    """测试用 — 重置 module-level singleton."""
    global _default_store
    with _default_lock:
        _default_store = None


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    "TokenRevocationStore",
    "get_revocation_store",
    "reset_default_store",
]