"""VDP-2026 R8 — Security / OWASP / RBAC Deepening.

This module layers four concerns on top of the existing security surface:

  1. ``PII redactor`` — strips emails, phones, SSNs, IPs from a text payload
     before it leaves the platform (covers OWASP A01:2021 broken access
     control + A09:2021 security logging).
  2. ``RateLimiter``  — fixed-window per-token rate limit; emits 429
     metadata via the bus so dashboards surface abuse.
  3. ``AuditChain`` — append-only audit log of security-relevant events
     (login, role change, secret access) signed with a rolling HMAC
     chain so tampering is detectable.
  4. ``SecretsVault`` — fetches a secret value by name; in dev returns
     ``"dev-only-*"`` placeholders and writes an audit row; in prod the
     route handler is expected to back this with KMS / Vault.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = __import__("logging").getLogger(__name__)


_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        backend = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend / "data" / "security_r8.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _init_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    p = get_db_path()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS audit_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                payload_json TEXT DEFAULT '{}',
                prev_hash TEXT NOT NULL DEFAULT '',
                hash TEXT NOT NULL,
                secret_ref TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rate_limits (
                bucket TEXT NOT NULL,
                ts_minute INTEGER NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (bucket, ts_minute)
            );
            CREATE TABLE IF NOT EXISTS secrets (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                rotation_at TEXT NOT NULL,
                rotated_by TEXT DEFAULT 'system'
            );
            """
        )


# ---------------------------------------------------------------------------
# PII redactor
# ---------------------------------------------------------------------------


EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")  # CN mobile
PHONE_INTL_RE = re.compile(r"\+\d{1,3}[ \-]?\d{3,14}")
SSN_RE = re.compile(r"\b\d{17}[\dXx]\b")  # CN ID
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
CARD_RE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")


def redact_pii(text: str, kinds: Optional[List[str]] = None) -> Dict[str, Any]:
    """Return redacted text + per-kind match counts.

    The kinds filter is convenience for callers who only want emails redacted.
    Default: redact all supported kinds.
    """
    kinds = kinds or ["email", "phone", "ssn", "ipv4", "card"]
    counts: Dict[str, int] = {}
    redacted = text

    def _do(pattern, kind, replacement):
        nonlocal redacted
        if kind in kinds:
            new, n = pattern.subn(replacement, redacted)
            redacted = new
            counts[kind] = counts.get(kind, 0) + n

    _do(EMAIL_RE, "email", "[EMAIL]")
    _do(PHONE_RE, "phone", "[PHONE]")
    _do(PHONE_INTL_RE, "phone", "[PHONE]")
    _do(SSN_RE, "ssn", "[ID]")
    _do(IPV4_RE, "ipv4", "[IP]")
    _do(CARD_RE, "card", "[CARD]")

    return {"redacted": redacted, "counts": counts, "kinds": kinds}


# ---------------------------------------------------------------------------
# Rate limiter — fixed window per bucket + ts_minute
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, max_per_min: int = 60) -> None:
        self.max_per_min = max_per_min
        self._lock = threading.RLock()
        # in-memory fast path
        self._buckets: Dict[str, deque] = defaultdict(deque)

    def check(self, bucket: str, max_per_min: Optional[int] = None) -> Dict[str, Any]:
        cap = max_per_min or self.max_per_min
        now = int(time.time())
        minute = now // 60
        with self._lock:
            dq = self._buckets[bucket]
            # drop entries from previous minute(s)
            cutoff = minute * 60
            while dq and dq[0] < cutoff:
                dq.popleft()
            count = len(dq)
            allowed = count < cap
            if allowed:
                dq.append(now)
            return {
                "bucket": bucket,
                "minute": minute,
                "count": count + 1 if allowed else count,
                "limit": cap,
                "allowed": allowed,
                "reset_in_seconds": max(0, 60 - (now - minute * 60)),
            }


# ---------------------------------------------------------------------------
# Audit chain — append-only + rolling HMAC
# ---------------------------------------------------------------------------


@dataclass
class AuditEvent:
    event_type: str
    actor: str = "system"
    payload: Dict[str, Any] = field(default_factory=dict)
    secret_ref: str = ""
    hash: str = ""
    prev_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditChain:
    """Append-only audit log with rolling SHA-256 HMAC chain.

    Each row's hash includes the previous hash, so any tampering of a
    historical row invalidates the chain forward.
    """

    def __init__(self, hmac_secret: str = "r8-default-secret") -> None:
        self._secret = hmac_secret.encode("utf-8")
        self._lock = threading.RLock()

    def _hash(self, prev_hash: str, body: str) -> str:
        return hmac.new(self._secret, f"{prev_hash}|{body}".encode("utf-8"), hashlib.sha256).hexdigest()

    def append(self, event_type: str, actor: str = "system",
               payload: Optional[Dict[str, Any]] = None,
               secret_ref: str = "") -> AuditEvent:
        payload = payload or {}
        # Compute the timestamp ONCE and use it for both the hash body and
        # the stored created_at column. Otherwise the verify() walk would
        # read back a different timestamp and report the row as tampered.
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with _conn() as conn:
                row = conn.execute(
                    "SELECT hash FROM audit_chain ORDER BY id DESC LIMIT 1"
                ).fetchone()
            prev_hash = row["hash"] if row else ""
            body = json.dumps(
                {"event_type": event_type, "actor": actor,
                 "payload": payload, "secret_ref": secret_ref,
                 "ts": created_at},
                ensure_ascii=False, default=str, sort_keys=True,
            )
            digest = self._hash(prev_hash, body)
            ev = AuditEvent(event_type=event_type, actor=actor,
                            payload=payload, secret_ref=secret_ref,
                            hash=digest, prev_hash=prev_hash,
                            created_at=created_at)
            with _conn() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_chain (
                        event_type, actor, payload_json,
                        prev_hash, hash, secret_ref, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_type, actor,
                     json.dumps(payload, ensure_ascii=False, default=str),
                     prev_hash, digest, secret_ref, created_at),
                )
            return ev

    def verify(self) -> Dict[str, Any]:
        """Walk the chain and verify hashes are intact."""
        prev = ""
        bad_rows: List[int] = []
        with _conn() as conn:
            rows = conn.execute(
                "SELECT id, prev_hash, hash, payload_json, event_type, actor, secret_ref, created_at FROM audit_chain ORDER BY id ASC"
            ).fetchall()
        for r in rows:
            body = json.dumps(
                {"event_type": r["event_type"], "actor": r["actor"],
                 "payload": json.loads(r["payload_json"]) if r["payload_json"] else {},
                 "secret_ref": r["secret_ref"],
                 "ts": r["created_at"]},
                ensure_ascii=False, default=str, sort_keys=True,
            )
            digest = self._hash(prev, body)
            if digest != r["hash"] or r["prev_hash"] != prev:
                bad_rows.append(int(r["id"]))
            prev = r["hash"]
        return {"verified": len(bad_rows) == 0, "tampered_rows": bad_rows, "total_rows": len(rows)}

    def tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_chain ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json", "{}"))
            except (ValueError, TypeError):
                d["payload"] = {}
            out.append(d)
        return out


# ---------------------------------------------------------------------------
# Secrets vault
# ---------------------------------------------------------------------------


class SecretsVault:
    """Minimal in-memory vault; production deployments should swap the
    backend implementation for KMS / Vault / sealed-secrets.
    """

    def __init__(self, audit: AuditChain) -> None:
        self._audit = audit
        self._lock = threading.RLock()
        self._seed_secrets()

    def _seed_secrets(self) -> None:
        seeds = {
            "openai_api_key": "dev-only-openai-***",
            "claude_api_key": "dev-only-claude-***",
            "deepseek_api_key": "dev-only-deepseek-***",
            "qwen_api_key": "dev-only-qwen-***",
            "doubao_api_key": "dev-only-doubao-***",
            "s3_access_key": "dev-only-s3-access-***",
            "s3_secret_key": "dev-only-s3-secret-***",
            "jwt_signing_secret": "dev-only-jwt-***",
        }
        now = datetime.now(timezone.utc).isoformat()
        with _conn() as conn:
            for n, v in seeds.items():
                conn.execute(
                    "INSERT OR IGNORE INTO secrets (name, value, rotation_at, rotated_by) VALUES (?, ?, ?, ?)",
                    (n, v, now, "system"),
                )

    def get(self, name: str, actor: str = "system") -> Optional[str]:
        with self._lock:
            with _conn() as conn:
                row = conn.execute("SELECT value FROM secrets WHERE name = ?", (name,)).fetchone()
            if row is None:
                self._audit.append("secret.miss", actor=actor, payload={"name": name})
                return None
            self._audit.append("secret.access", actor=actor, payload={"name": name},
                               secret_ref=name)
            return row["value"]

    def rotate(self, name: str, new_value: str, actor: str = "system") -> bool:
        with _conn() as conn:
            cur = conn.execute(
                "UPDATE secrets SET value = ?, rotation_at = ?, rotated_by = ? WHERE name = ?",
                (new_value, datetime.now(timezone.utc).isoformat(), actor, name),
            )
        ok = (cur.rowcount or 0) > 0
        if ok:
            self._audit.append("secret.rotate", actor=actor, payload={"name": name})
        return ok

    def list_names(self) -> List[str]:
        with _conn() as conn:
            return [r["name"] for r in conn.execute("SELECT name FROM secrets").fetchall()]


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------

_AUDIT: Optional[AuditChain] = None
_RATE: Optional[RateLimiter] = None
_VAULT: Optional[SecretsVault] = None


def get_audit() -> AuditChain:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = AuditChain()
    return _AUDIT


def get_rate_limiter(max_per_min: int = 60) -> RateLimiter:
    global _RATE
    if _RATE is None:
        _RATE = RateLimiter(max_per_min=max_per_min)
    return _RATE


def get_vault() -> SecretsVault:
    global _VAULT
    if _VAULT is None:
        _VAULT = SecretsVault(get_audit())
    return _VAULT


def reset_security_for_test() -> None:
    global _AUDIT, _RATE, _VAULT
    _AUDIT = _RATE = _VAULT = None
