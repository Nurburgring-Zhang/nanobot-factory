#!/usr/bin/env python3
"""
Nanobot Factory - 登录暴力破解防护 (Brute-Force Protection)

文件: auth/bruteforce.py
功能:
  - 失败计数 + 指数退避锁定 (5 失败 → 15 min, 10 失败 → 1 h)
  - IP-based + account-based 双维度限流
  - 锁定期间即使密码正确也拒绝 (防止凭据泄露 + 暴力枚举)
  - 可注入到 UnifiedAuthManager.authenticate() 调用前/后
  - 持久化到 SQLite (auth_audit_log 中 action='auth.locked')
  - in-memory dict 存活跃窗口 (>= 3600s 内失败计数)

设计取舍:
  - 项目当前无 Redis (用户档案记录: 0 个 Redis), 使用 in-memory + SQLite
  - 进程内 dict 性能最佳,重启后通过审计日志恢复计数 (锁定状态保持)
  - 单元测试可注入 _clock() 让时间步进可控 (避免 sleep 5 min)

作者: Coder (P10 Sprint D)
版本: v1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("bruteforce")


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class ThrottleResult:
    """节流检查结果"""
    allowed: bool
    retry_after: int = 0           # 锁定剩余秒数
    reason: str = "ok"             # ok | account_locked | ip_locked
    lockout_level: str = "none"    # none | soft_15min | hard_1h
    failed_count: int = 0
    lockout_seconds: int = 0       # 总锁定时长 (用于 X-RateLimit-Reset)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class BruteForceConfig:
    """防护策略配置"""
    # 软锁定阈值: 5 次失败 → 15 min
    soft_threshold: int = 5
    soft_lock_seconds: int = 15 * 60

    # 硬锁定阈值: 10 次失败 → 1 h
    hard_threshold: int = 10
    hard_lock_seconds: int = 60 * 60

    # 失败计数滑动窗口 (默认 1 h 内失败算)
    window_seconds: int = 60 * 60

    # 是否同时启用 IP-based 限流 (默认 True)
    ip_enabled: bool = True

    # 是否同时启用 account-based 限流 (默认 True)
    account_enabled: bool = True


# ============================================================================
# 防护器 (核心)
# ============================================================================

class BruteForceProtector:
    """
    双维度 (account + IP) 暴力破解防护。

    使用方式:
        protector = BruteForceProtector()
        result = protector.check_lock(username="alice", ip="1.2.3.4")
        if not result.allowed:
            # 返回 429, retry_after = result.retry_after
            ...

        # 登录失败后:
        result = protector.record_failure(username="alice", ip="1.2.3.4")
        # 命中阈值时 result.allowed = False

        # 登录成功后:
        protector.record_success(username="alice", ip="1.2.3.4")
    """

    def __init__(self, config: Optional[BruteForceConfig] = None,
                 clock=None, db_path: str = "", enable_persistence: bool = False):
        """
        Args:
            config: 防护策略配置 (软/硬阈值, 锁定时长, IP/account 启用)
            clock: 可注入 time.time() (测试用)
            db_path: SQLite path (空字符串则用默认 DATA_DIR/unified_auth.db)
            enable_persistence: 是否启用 SQLite 持久化 (P10R4-1 / P0-4 增强)
                True 后, lock state 跨进程重启保留 (multi-worker 部署关键).
        """
        self.config = config or BruteForceConfig()
        self._clock = clock or time.time   # 可注入 (测试时用)
        self._lock = threading.Lock()
        # key -> [timestamps of failures]
        self._failures: Dict[str, List[float]] = {}
        # key -> (lock_until_epoch, level)
        # 存 level 而非重新 heuristic 推导 — 简单可靠
        self._locks: Dict[str, Tuple[float, str]] = {}

        # P10R4-1 / P0-4: SQLite 持久化 (可选, 默认 off — 保持单测兼容)
        self._enable_persistence = bool(enable_persistence and db_path is not None)
        self._db_path = db_path or ""
        if self._enable_persistence:
            if not self._db_path:
                base = os.environ.get(
                    "DATA_DIR",
                    os.path.join(os.path.dirname(__file__), "..", "data"),
                )
                os.makedirs(base, exist_ok=True)
                self._db_path = os.path.join(base, "unified_auth.db")
            self._init_persistence_db()
            self._load_persistent_state()

    # ------------------------------------------------------------------
    # P10R4-1 / P0-4: SQLite 持久化 (lock state 跨重启保留)
    # ------------------------------------------------------------------

    def _get_persistence_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_persistence_db(self) -> None:
        try:
            conn = self._get_persistence_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_bruteforce_state (
                        key             TEXT PRIMARY KEY,
                        failure_count   INTEGER NOT NULL DEFAULT 0,
                        window_start    REAL NOT NULL DEFAULT 0,
                        lock_until      REAL NOT NULL DEFAULT 0,
                        lock_level      TEXT NOT NULL DEFAULT 'none',
                        updated_at      REAL NOT NULL DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_auth_bruteforce_lock_until
                    ON auth_bruteforce_state(lock_until)
                """)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("BruteForce persistence init failed: %s", e)
            self._enable_persistence = False

    def _load_persistent_state(self) -> None:
        """启动时从 SQLite 加载 lock state (跨进程重启关键)."""
        try:
            now = self._now()
            conn = self._get_persistence_conn()
            try:
                cur = conn.execute(
                    "SELECT key, failure_count, window_start, lock_until, lock_level "
                    "FROM auth_bruteforce_state WHERE lock_until > ? OR failure_count > 0",
                    (now,),
                )
                loaded_locks = 0
                loaded_failures = 0
                for row in cur:
                    key = row["key"]
                    fc = int(row["failure_count"])
                    lock_until = float(row["lock_until"])
                    lock_level = row["lock_level"]
                    window_start = float(row["window_start"])
                    if fc > 0:
                        # 重建失败时间戳为 [window_start, now] 内均匀分布的 fc 个点
                        # (精确时间戳不重要, 重要的是 count + lock 状态)
                        if lock_until > now:
                            # 当前被锁 — 保持时间戳新鲜以维持 count
                            timestamps = [
                                now - (lock_until - ts)
                                for ts in [window_start + (now - window_start) * i / max(fc, 1)
                                           for i in range(fc)]
                            ]
                        else:
                            # 仅历史失败记录, 标记 window_start
                            timestamps = [window_start] * fc
                        self._failures[key] = timestamps
                        loaded_failures += fc
                    if lock_until > now:
                        self._locks[key] = (lock_until, lock_level)
                        loaded_locks += 1
                logger.info(
                    "BruteForce persistence: loaded %d locks, %d failure-records",
                    loaded_locks, loaded_failures,
                )
            finally:
                conn.close()
        except Exception as e:
            logger.error("BruteForce persistence load failed: %s", e)

    def _persist_state(self, key: str, failures: List[float]) -> None:
        """单 key 状态写回 SQLite (best-effort, 不抛异常影响主流程)."""
        if not self._enable_persistence:
            return
        try:
            now = self._now()
            fc = len(failures)
            window_start = failures[0] if failures else now
            lock_until, lock_level = self._locks.get(key, (0, "none"))
            conn = self._get_persistence_conn()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO auth_bruteforce_state
                    (key, failure_count, window_start, lock_until, lock_level, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, fc, window_start, lock_until, lock_level, now),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("BruteForce persist failed for key=%s: %s", key, e)

    def _persist_clear(self, key: str) -> None:
        """清除某 key 的持久化状态."""
        if not self._enable_persistence:
            return
        try:
            conn = self._get_persistence_conn()
            try:
                conn.execute(
                    "DELETE FROM auth_bruteforce_state WHERE key = ?",
                    (key,),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("BruteForce persist clear failed for key=%s: %s", key, e)

    # ---- key helpers ----

    @staticmethod
    def _account_key(username: str) -> str:
        u = (username or "").strip().lower()
        return f"acct:{u}" if u else ""

    @staticmethod
    def _ip_key(ip: str) -> str:
        i = (ip or "").strip()
        return f"ip:{i}" if i else ""

    def _keys(self, username: str = None, ip: str = None) -> List[str]:
        keys: List[str] = []
        if username and self.config.account_enabled:
            keys.append(self._account_key(username))
        if ip and self.config.ip_enabled:
            keys.append(self._ip_key(ip))
        return [k for k in keys if k]

    # ---- internal ----

    def _now(self) -> float:
        return float(self._clock())

    def _prune(self, timestamps: List[float]) -> None:
        """滑动窗口剪枝"""
        cutoff = self._now() - self.config.window_seconds
        # timestamps 始终有序 (append-only), 二分或反向 pop
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

    def _compute_lockout(self, count: int) -> Tuple[str, int]:
        """根据失败次数返回 (level, lock_seconds)"""
        if count >= self.config.hard_threshold:
            return "hard_1h", self.config.hard_lock_seconds
        if count >= self.config.soft_threshold:
            return "soft_15min", self.config.soft_lock_seconds
        return "none", 0

    # ---- public API ----

    def check_lock(self, username: str = None, ip: str = None) -> ThrottleResult:
        """
        检查是否被锁定 (只读)。

        Returns:
            ThrottleResult(allowed=False, retry_after=N) 如果任一维度被锁定,
            否则 ThrottleResult(allowed=True)
        """
        keys = self._keys(username=username, ip=ip)
        if not keys:
            return ThrottleResult(allowed=True)

        now = self._now()
        most_restrictive: Optional[ThrottleResult] = None

        with self._lock:
            for key in keys:
                lock_info = self._locks.get(key)
                if lock_info is None:
                    continue
                lock_until, level = lock_info
                if lock_until > now:
                    retry_after = int(lock_until - now)
                    total = (self.config.hard_lock_seconds if level == "hard_1h"
                             else self.config.soft_lock_seconds)
                    reason = "ip_locked" if key.startswith("ip:") else "account_locked"
                    fail_count = len(self._failures.get(key, []))
                    cand = ThrottleResult(
                        allowed=False,
                        retry_after=retry_after,
                        reason=reason,
                        lockout_level=level,
                        failed_count=fail_count,
                        lockout_seconds=total,
                    )
                    if most_restrictive is None or cand.retry_after > most_restrictive.retry_after:
                        most_restrictive = cand
        return most_restrictive or ThrottleResult(allowed=True)

    def record_failure(self, username: str = None, ip: str = None) -> ThrottleResult:
        """
        记录一次登录失败, 必要时触发锁定。

        Returns:
            与 check_lock() 相同 — 调用方可立即知道是否进入了锁定状态。
        """
        keys = self._keys(username=username, ip=ip)
        if not keys:
            return ThrottleResult(allowed=True)

        now = self._now()
        results: List[ThrottleResult] = []
        keys_to_persist: List[str] = []

        with self._lock:
            for key in keys:
                bucket = self._failers(key)
                bucket.append(now)
                self._prune(bucket)
                count = len(bucket)

                level, lock_seconds = self._compute_lockout(count)
                if lock_seconds > 0:
                    self._locks[key] = (now + lock_seconds, level)
                    logger.warning(
                        "BruteForce LOCK: key=%s count=%d level=%s until=%s",
                        key, count, level,
                        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now + lock_seconds)),
                    )

                if level in ("hard_1h", "soft_15min"):
                    results.append(ThrottleResult(
                        allowed=False,
                        retry_after=lock_seconds,
                        reason="ip_locked" if key.startswith("ip:") else "account_locked",
                        lockout_level=level,
                        failed_count=count,
                        lockout_seconds=lock_seconds,
                    ))
                # P10R4-1 / P0-4: 标记需要持久化 (lock 触发时)
                keys_to_persist.append(key)

        # P10R4-1 / P0-4: 持久化 (lock 触发或失败计数变化时)
        for k in keys_to_persist:
            self._persist_state(k, self._failures.get(k, []))

        # 返回最严格的
        blocked = [r for r in results if not r.allowed]
        if blocked:
            return max(blocked, key=lambda r: r.retry_after)
        return ThrottleResult(allowed=True, failed_count=results[0].failed_count if results else 0)

    def _failers(self, key: str) -> List[float]:
        """内部 helper: 获取或创建失败列表"""
        bucket = self._failures.get(key)
        if bucket is None:
            bucket = []
            self._failures[key] = bucket
        return bucket

    def record_success(self, username: str = None, ip: str = None) -> None:
        """登录成功 — 清除该用户/IP 的所有失败计数 + 锁定"""
        keys = self._keys(username=username, ip=ip)
        if not keys:
            return
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)
                self._locks.pop(key, None)
            logger.info("BruteForce CLEAR: keys=%s (login success)", keys)
        # P10R4-1 / P0-4: 持久化清除
        for k in keys:
            self._persist_clear(k)

    def _clear_lock_only(self, key: str) -> None:
        """只清除锁定, 不动失败计数 (内部用)"""
        self._locks.pop(key, None)

    def reset(self, username: str = None, ip: str = None) -> None:
        """强制清除 (管理后台用)"""
        self.record_success(username=username, ip=ip)

    def get_state_snapshot(self) -> Dict:
        """调试用: 当前所有 key 的状态快照"""
        with self._lock:
            now = self._now()
            return {
                "now": now,
                "failures": {k: list(v) for k, v in self._failures.items()},
                "locks": {k: {"until": v[0], "level": v[1]}
                          for k, v in self._locks.items() if v[0] > now},
            }

    # ---- 统计 ----

    def stats(self) -> Dict:
        """统计: 当前活跃 key 数 + 锁定数"""
        with self._lock:
            now = self._now()
            active_locks = sum(1 for (lock_until, _) in self._locks.values() if lock_until > now)
            return {
                "tracked_keys": len(self._failures),
                "active_locks": active_locks,
                "soft_threshold": self.config.soft_threshold,
                "hard_threshold": self.config.hard_threshold,
                "soft_lock_seconds": self.config.soft_lock_seconds,
                "hard_lock_seconds": self.config.hard_lock_seconds,
                "persistence_enabled": self._enable_persistence,
                "db_path": self._db_path if self._enable_persistence else None,
            }

    # ------------------------------------------------------------------
    # P10R4-1 / P0-4: 持久化 GC (清理过期 lock / failure records)
    # ------------------------------------------------------------------

    def gc_persistence(self) -> int:
        """清理持久化表中的过期记录 (定期调用, e.g. 启动时或每日)."""
        if not self._enable_persistence:
            return 0
        removed = 0
        try:
            now = self._now()
            conn = self._get_persistence_conn()
            try:
                # 删除已过期且无活跃 lock 的记录
                cur = conn.execute(
                    """
                    DELETE FROM auth_bruteforce_state
                    WHERE lock_until > 0 AND lock_until <= ? AND updated_at < ?
                    """,
                    (now, now - 86400),  # 至少 1 天前更新过才清
                )
                conn.commit()
                removed = cur.rowcount
            finally:
                conn.close()
        except Exception as e:
            logger.error("BruteForce persistence gc failed: %s", e)
        if removed:
            logger.info("BruteForce persistence gc: removed %d stale records", removed)
        return removed


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    "BruteForceProtector",
    "BruteForceConfig",
    "ThrottleResult",
]