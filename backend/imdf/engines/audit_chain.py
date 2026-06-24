"""Audit Chain — HMAC-SHA256 签名链 (OWASP A08:2021 — Software & Data Integrity)

设计目标:
- 每个 audit_log entry 含 prev_hash + entry_hash + HMAC-SHA256 signature
- 启动时 verify_chain() 校验整条链, 断链则 raise (fail-fast)
- env AUDIT_CHAIN_SECRET 缺失时启动 fail (防止意外部署到无 secret 环境)
- 与 business/audit_log.py 共存: 那个是 sha256-only (无签名), 这个是 HMAC-SHA256 (有签名)

存储:
- 同 audit_log 表, 加 prev_hash / entry_hash / signature 三列
- 启动时 read all entries, 跑 verify_chain()

签名公式:
    signature = HMAC-SHA256(
        key = AUDIT_CHAIN_SECRET,
        msg = prev_hash || "|" || entry_hash || "|" || seq
    )

威胁模型:
- 攻击者修改 SQLite 中的任意 entry → entry_hash 不匹配 → verify_chain 返回 BAD
- 攻击者同时修改 entry_hash → HMAC signature 不匹配 → verify_chain 返回 BAD
- 攻击者没有 AUDIT_CHAIN_SECRET → 无法伪造合法 signature → verify_chain 返回 BAD
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


GENESIS_HASH = "0" * 64


class AuditChainError(RuntimeError):
    """Audit chain 校验失败 — 必须 fail-fast, 不允许 silent corruption."""
    def __init__(self, message: str, bad_seq: int = -1):
        super().__init__(message)
        self.bad_seq = bad_seq


@dataclass
class ChainEntry:
    """Audit chain 单条记录 (SQLite row 镜像)."""
    id: int
    seq: int
    timestamp: str
    method: str
    path: str
    user: str
    body_hash: str
    status_code: int
    prev_hash: str
    entry_hash: str
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "seq": self.seq,
            "timestamp": self.timestamp,
            "method": self.method,
            "path": self.path,
            "user": self.user,
            "body_hash": self.body_hash,
            "status_code": self.status_code,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "signature": self.signature,
        }


# ============================================================================
# 1. 哈希 & 签名
# ============================================================================

def _canonical_payload(timestamp: str, method: str, path: str, user: str,
                       body_hash: str, status_code: int, seq: int,
                       prev_hash: str) -> str:
    """构造签名前的标准化 payload — 字段顺序固定."""
    return json.dumps(
        {
            "seq": seq,
            "timestamp": timestamp,
            "method": method,
            "path": path,
            "user": user,
            "body_hash": body_hash,
            "status_code": status_code,
            "prev_hash": prev_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_entry_hash(timestamp: str, method: str, path: str, user: str,
                       body_hash: str, status_code: int, seq: int,
                       prev_hash: str) -> str:
    """entry_hash = sha256(canonical payload) — 与 HMAC 签名配合做链式校验."""
    payload = _canonical_payload(
        timestamp=timestamp, method=method, path=path, user=user,
        body_hash=body_hash, status_code=status_code, seq=seq,
        prev_hash=prev_hash,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_signature(secret: str, prev_hash: str, entry_hash: str, seq: int) -> str:
    """signature = HMAC-SHA256(secret, prev_hash || "|" || entry_hash || "|" || seq)."""
    msg = f"{prev_hash}|{entry_hash}|{seq}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"),
        msg,
        hashlib.sha256,
    ).hexdigest()


# ============================================================================
# 2. Chain Manager — append / verify / load
# ============================================================================

class AuditChain:
    """HMAC-SHA256 签名链 — SQLite 后端.

    用法:
        chain = AuditChain(db_path, secret=AUDIT_CHAIN_SECRET)
        chain.verify_chain()           # 启动时跑一次, 失败 raise
        chain.append(method=..., path=..., ...)  # 写一条, 自动算 hash + signature
        ok, bad_seq = chain.verify_chain()  # 任何时候可验证
    """
    TABLE_NAME = "audit_chain"

    def __init__(self, db_path: str | os.PathLike, secret: Optional[str] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Secret 解析: 参数 > env AUDIT_CHAIN_SECRET > env AUDIT_SECRET
        # 缺失 → fail-fast, 不允许 silent default (会破坏签名验证的语义)
        secret = secret or os.environ.get("AUDIT_CHAIN_SECRET") or os.environ.get("AUDIT_SECRET")
        if not secret:
            raise AuditChainError(
                "AUDIT_CHAIN_SECRET is required for audit chain integrity. "
                "Set env AUDIT_CHAIN_SECRET=<random-32+bytes> before starting."
            )
        if len(secret) < 16:
            raise AuditChainError(
                f"AUDIT_CHAIN_SECRET too short ({len(secret)} chars, min 16). "
                "Use a strong random secret."
            )
        self.secret = secret
        self._lock = threading.Lock()
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # 并发 append 安全
        conn.execute("PRAGMA synchronous=NORMAL")  # 性能 vs 持久性折中
        return conn

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seq INTEGER NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    user TEXT DEFAULT '',
                    body_hash TEXT DEFAULT '',
                    status_code INTEGER NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL,
                    signature TEXT NOT NULL
                )
            """)
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_seq ON {self.TABLE_NAME}(seq)")
            conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> ChainEntry:
        return ChainEntry(
            id=row["id"],
            seq=row["seq"],
            timestamp=row["timestamp"],
            method=row["method"],
            path=row["path"],
            user=row["user"],
            body_hash=row["body_hash"],
            status_code=row["status_code"],
            prev_hash=row["prev_hash"],
            entry_hash=row["entry_hash"],
            signature=row["signature"],
        )

    def load_all(self) -> List[ChainEntry]:
        """加载所有 audit chain entries (按 seq 排序)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} ORDER BY seq ASC"
            )
            return [self._row_to_entry(row) for row in cur.fetchall()]

    def last_entry(self) -> Optional[ChainEntry]:
        """取最后一条 (用于链式 append)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} ORDER BY seq DESC LIMIT 1"
            )
            row = cur.fetchone()
            return self._row_to_entry(row) if row else None

    def append(self, *, timestamp: str, method: str, path: str,
               user: str = "", body_hash: str = "", status_code: int = 0,
               actor: Optional[str] = None) -> ChainEntry:
        """追加一条 audit entry — 自动算 prev_hash / entry_hash / signature.

        actor: 兼容业务 audit 的 actor 字段, 若提供则记入 user (X-User header 之外)
        """
        if user and actor:
            user = f"{user}|actor={actor}"
        elif actor and not user:
            user = f"actor={actor}"

        # P3-8-W2: Jaeger span — record the chain append operation
        with _audit_tracer.start_as_current_span("audit.chain.append") as _span:
            _span.set_attribute("audit.method", method)
            _span.set_attribute("audit.path", path[:200])
            _span.set_attribute("audit.user", user[:80] if user else "")
            _span.set_attribute("audit.status_code", status_code)
            return self._append_locked(
                timestamp=timestamp, method=method, path=path, user=user,
                body_hash=body_hash, status_code=status_code, span=_span,
            )

    def _append_locked(self, *, timestamp: str, method: str, path: str, user: str,
                       body_hash: str, status_code: int, span) -> ChainEntry:
        """Internal append helper — assumes span context is open."""
        with self._lock:
            last = self.last_entry()
            seq = (last.seq + 1) if last else 1
            prev_hash = last.entry_hash if last else GENESIS_HASH

            entry_hash = compute_entry_hash(
                timestamp=timestamp, method=method, path=path, user=user,
                body_hash=body_hash, status_code=status_code, seq=seq,
                prev_hash=prev_hash,
            )
            signature = compute_signature(
                secret=self.secret, prev_hash=prev_hash,
                entry_hash=entry_hash, seq=seq,
            )

            with self._connect() as conn:
                cur = conn.execute(
                    f"""INSERT INTO {self.TABLE_NAME}
                        (seq, timestamp, method, path, user, body_hash, status_code,
                         prev_hash, entry_hash, signature)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (seq, timestamp, method, path, user, body_hash, status_code,
                     prev_hash, entry_hash, signature),
                )
                conn.commit()
                new_id = cur.lastrowid

            return ChainEntry(
                id=new_id, seq=seq, timestamp=timestamp, method=method, path=path,
                user=user, body_hash=body_hash, status_code=status_code,
                prev_hash=prev_hash, entry_hash=entry_hash, signature=signature,
            )

    def verify_chain(self) -> Tuple[bool, int]:
        """验证整条链 — 任意 entry 篡改/删除/伪造都会返回 BAD.

        Returns:
            (ok, first_bad_seq) — ok=True 时 first_bad_seq = -1
            ok=False 时 first_bad_seq 指向第一条出问题的 entry.
        """
        with _audit_tracer.start_as_current_span("audit.chain.verify") as _span:
            prev_hash = GENESIS_HASH
            expected_seq = 1
            entries = self.load_all()
            _span.set_attribute("audit.chain_length", len(entries))
            for e in entries:
                if e.seq != expected_seq:
                    _span.set_attribute("audit.verify_ok", False)
                    _span.set_attribute("audit.bad_seq", e.seq)
                    return False, e.seq
                if e.prev_hash != prev_hash:
                    _span.set_attribute("audit.verify_ok", False)
                    _span.set_attribute("audit.bad_seq", e.seq)
                    return False, e.seq
                # 1. entry_hash 必须匹配实际内容
                expected_entry_hash = compute_entry_hash(
                    timestamp=e.timestamp, method=e.method, path=e.path, user=e.user,
                    body_hash=e.body_hash, status_code=e.status_code, seq=e.seq,
                    prev_hash=e.prev_hash,
                )
                if expected_entry_hash != e.entry_hash:
                    _span.set_attribute("audit.verify_ok", False)
                    _span.set_attribute("audit.bad_seq", e.seq)
                    return False, e.seq
                # 2. signature 必须用我们的 secret 算出 — 验证 entry_hash 与 prev_hash 没被改
                expected_signature = compute_signature(
                    secret=self.secret, prev_hash=e.prev_hash,
                    entry_hash=e.entry_hash, seq=e.seq,
                )
                if not hmac.compare_digest(expected_signature, e.signature):
                    _span.set_attribute("audit.verify_ok", False)
                    _span.set_attribute("audit.bad_seq", e.seq)
                    return False, e.seq
                prev_hash = e.entry_hash
                expected_seq += 1
            _span.set_attribute("audit.verify_ok", True)
        return True, -1

    def assert_chain(self) -> None:
        """启动时跑一次 — 失败 raise."""
        ok, bad_seq = self.verify_chain()
        if not ok:
            raise AuditChainError(
                f"Audit chain integrity check FAILED at seq={bad_seq}. "
                f"Possible tampering or corruption. Refusing to start.",
                bad_seq=bad_seq,
            )

    def export_json(self) -> str:
        """导出整条链为 JSON (用于审计 / 合规报告)."""
        return json.dumps(
            [e.to_dict() for e in self.load_all()],
            ensure_ascii=False, indent=2,
        )

    def __len__(self) -> int:
        with self._connect() as conn:
            cur = conn.execute(f"SELECT COUNT(*) FROM {self.TABLE_NAME}")
            return cur.fetchone()[0]


# ============================================================================
# P3-8-W2: OpenTelemetry / Jaeger spans for audit chain operations.
# Safe no-op tracer when OTel packages are not installed.
# ============================================================================
try:
    from monitoring.tracing import get_tracer as _get_tracer
except Exception:
    try:
        from imdf.monitoring.tracing import get_tracer as _get_tracer  # type: ignore
    except Exception:
        def _get_tracer(name):  # type: ignore
            class _T:
                def start_as_current_span(self, *a, **k):
                    class _S:
                        def __enter__(self): return self
                        def __exit__(self, *a): return False
                        def set_attribute(self, k, v): pass
                        def set_status(self, s): pass
                        def record_exception(self, e): pass
                    return _S()
            return _T()

_audit_tracer = _get_tracer("imdf.engines.audit_chain")

# ============================================================================
# 3. 模块级单例 (lazy init, 失败 raise, 不静默 fallback)
# ============================================================================

_DEFAULT_DB_PATH: Optional[Path] = None
_chain_singleton: Optional[AuditChain] = None
_chain_lock = threading.Lock()


def configure_default_db_path(db_path: str | os.PathLike) -> Path:
    """设置默认 db 路径 — 在 canvas_web.py 启动时调用."""
    global _DEFAULT_DB_PATH
    _DEFAULT_DB_PATH = Path(db_path)
    return _DEFAULT_DB_PATH


def get_chain() -> AuditChain:
    """获取全局 chain 实例 (lazy 初始化)."""
    global _chain_singleton, _DEFAULT_DB_PATH
    if _chain_singleton is None:
        with _chain_lock:
            if _chain_singleton is None:
                if _DEFAULT_DB_PATH is None:
                    # 默认路径 — canvas_web.py 同级 audit_chain.db
                    from config.settings import DATA_DIR
                    _DEFAULT_DB_PATH = Path(DATA_DIR) / "audit_chain.db"
                _chain_singleton = AuditChain(_DEFAULT_DB_PATH)
                # 启动时验证 — 失败 raise
                _chain_singleton.assert_chain()
    return _chain_singleton


def reset_singleton_for_tests(db_path: str | os.PathLike, secret: str) -> AuditChain:
    """测试钩子 — 重置单例, 用指定 db + secret."""
    global _chain_singleton, _DEFAULT_DB_PATH
    with _chain_lock:
        _DEFAULT_DB_PATH = Path(db_path)
        _chain_singleton = AuditChain(_DEFAULT_DB_PATH, secret=secret)
        _chain_singleton.assert_chain()
    return _chain_singleton


__all__ = [
    "AuditChain", "ChainEntry", "AuditChainError",
    "compute_entry_hash", "compute_signature",
    "GENESIS_HASH",
    "configure_default_db_path", "get_chain", "reset_singleton_for_tests",
]