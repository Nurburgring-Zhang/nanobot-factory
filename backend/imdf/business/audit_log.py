"""Audit log — tamper-evident hash chain (R10.5-Worker-2)

不可篡改审计日志:
- 每个 entry 含 prev_hash + 当前 entry 内容的 sha256
- 串联成 hash chain, 任何篡改都会被 verify_chain 检出
- 复用 R7 logging_setup: 关键事件同时写结构化日志
- 存储: append-only JSONL 文件, 内存可选

设计:
- AuditEntry: ts / actor / action / target / payload + prev_hash + entry_hash
- AuditLog: append / query / verify / export
- 链头 (genesis) hash = "0" * 64
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

# 复用 R7 logging_setup
try:
    from api._common.logging_setup import get_logger
    _log = get_logger("audit_log")
except Exception:  # pragma: no cover — 离线 / 测试环境
    _log = None


GENESIS_HASH = "0" * 64


# ============================================================================
# 1. Entry
# ============================================================================

@dataclass
class AuditEntry:
    """单条审计记录."""
    seq: int                    # 从 1 开始单调递增
    ts: float
    actor: str                  # 用户 / 服务 / tenant_id
    action: str                 # "create_user" / "delete_dataset" / "billing.invoice.create"
    target: str                 # 目标 ID
    payload: Dict[str, Any]     # 附加结构化字段
    prev_hash: str              # 前一条 entry_hash (GENESIS_HASH 表示首条)
    entry_hash: str             # sha256(prev_hash || seq || ts || actor || action || target || payload)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "ts_iso": datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat(),
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "payload": dict(self.payload),
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }

    @staticmethod
    def compute_hash(seq: int, ts: float, actor: str, action: str,
                     target: str, payload: Dict[str, Any], prev_hash: str) -> str:
        """标准化 sha256 — 字段顺序固定 (避免 dict ordering 漂移)."""
        canon = json.dumps(
            {
                "seq": seq,
                "ts": ts,
                "actor": actor,
                "action": action,
                "target": target,
                "payload": _normalize_payload(payload),
                "prev_hash": prev_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _normalize_payload(p: Dict[str, Any]) -> Any:
    """JSON-serializable normalize."""
    return json.loads(json.dumps(p, default=_json_default, sort_keys=True))


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "to_dict"):
        return o.to_dict()
    return str(o)


# ============================================================================
# 2. Store 抽象
# ============================================================================

class AuditStore(Protocol):
    def append(self, entry: AuditEntry) -> None: ...
    def load_all(self) -> List[AuditEntry]: ...


class JsonlAuditStore:
    """JSONL append-only."""
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def append(self, entry: AuditEntry) -> None:
        line = json.dumps(entry.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def load_all(self) -> List[AuditEntry]:
        if not self.path.exists():
            return []
        out: List[AuditEntry] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                out.append(AuditEntry(
                    seq=int(rec["seq"]),
                    ts=float(rec["ts"]),
                    actor=str(rec["actor"]),
                    action=str(rec["action"]),
                    target=str(rec["target"]),
                    payload=dict(rec.get("payload") or {}),
                    prev_hash=str(rec["prev_hash"]),
                    entry_hash=str(rec["entry_hash"]),
                ))
        return out


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def load_all(self) -> List[AuditEntry]:
        return list(self._entries)


# ============================================================================
# 3. AuditLog 门面
# ============================================================================

class AuditLog:
    """不可篡改 hash chain — append + verify + query."""
    def __init__(self, store: AuditStore):
        self.store = store
        self._lock = threading.Lock()
        # 缓存最后一条 hash 用于快速 append
        existing = store.load_all()
        self._last_hash = existing[-1].entry_hash if existing else GENESIS_HASH
        self._next_seq = (existing[-1].seq + 1) if existing else 1

    def append(self, actor: str, action: str, target: str,
               payload: Optional[Dict[str, Any]] = None,
               ts: Optional[float] = None,
               entry_id: Optional[str] = None) -> AuditEntry:
        if not actor or not isinstance(actor, str):
            raise ValueError("actor must be non-empty string")
        if not action or not isinstance(action, str):
            raise ValueError("action must be non-empty string")
        payload = dict(payload or {})
        with self._lock:
            ts = ts if ts is not None else time.time()
            entry_hash = AuditEntry.compute_hash(
                seq=self._next_seq, ts=ts, actor=actor,
                action=action, target=target, payload=payload,
                prev_hash=self._last_hash,
            )
            entry = AuditEntry(
                seq=self._next_seq,
                ts=ts,
                actor=actor,
                action=action,
                target=target,
                payload=payload,
                prev_hash=self._last_hash,
                entry_hash=entry_hash,
            )
            self.store.append(entry)
            self._last_hash = entry_hash
            self._next_seq += 1
            if entry_id:
                # 让调用方保留业务 ID (entry_id 仅用于返回, 不入 hash)
                pass
            # 复用 R7 logging_setup
            if _log is not None:
                try:
                    _log.info(
                        "audit.append",
                        seq=entry.seq,
                        actor=entry.actor,
                        action=entry.action,
                        target=entry.target,
                        entry_hash=entry.entry_hash,
                    )
                except Exception:
                    pass
            return entry

    def verify_chain(self) -> tuple[bool, int]:
        """返回 (ok, first_bad_seq). ok=True 时 first_bad_seq = -1."""
        prev = GENESIS_HASH
        seq = 1
        for e in self.store.load_all():
            if e.seq != seq:
                return False, e.seq
            if e.prev_hash != prev:
                return False, e.seq
            expected = AuditEntry.compute_hash(
                seq=e.seq, ts=e.ts, actor=e.actor, action=e.action,
                target=e.target, payload=e.payload, prev_hash=e.prev_hash,
            )
            if expected != e.entry_hash:
                return False, e.seq
            prev = e.entry_hash
            seq += 1
        return True, -1

    def query(self, *, actor: Optional[str] = None, action: Optional[str] = None,
              target: Optional[str] = None, limit: Optional[int] = None) -> List[AuditEntry]:
        out: List[AuditEntry] = []
        for e in self.store.load_all():
            if actor is not None and e.actor != actor:
                continue
            if action is not None and e.action != action:
                continue
            if target is not None and e.target != target:
                continue
            out.append(e)
            if limit is not None and len(out) >= limit:
                break
        return out

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(["seq", "ts_iso", "actor", "action", "target",
                    "payload_json", "prev_hash", "entry_hash"])
        for e in self.store.load_all():
            w.writerow([
                e.seq,
                datetime.fromtimestamp(e.ts, tz=timezone.utc).isoformat(),
                e.actor, e.action, e.target,
                json.dumps(e.payload, ensure_ascii=False, separators=(",", ":")),
                e.prev_hash, e.entry_hash,
            ])
        return buf.getvalue()


__all__ = [
    "AuditEntry", "AuditStore", "JsonlAuditStore", "InMemoryAuditStore",
    "AuditLog", "GENESIS_HASH",
]