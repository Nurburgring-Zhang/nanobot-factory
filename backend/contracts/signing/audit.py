"""P15-A2: 合同签名审计日志.

设计目标 (复用 P10-A 的 audit_chain 模式):
- 每次签/验都 append 一条 JSONL entry.
- 文件: backend/logs/contracts_audit.jsonl (默认).
- 每条 entry 含:
    seq, ts, event (sign | verify), contract_id,
    signer, alg, doc_hash, cert_serial, cert_fingerprint,
    signature_b64 (sign event), ok, reasons (verify event),
    timestamp_token_id.

- 不强制依赖 imdf.engines.audit_chain (避免 AUDIT_CHAIN_SECRET 强耦合),
  在 modules 不就绪时仍能落盘 JSONL.
- 若环境配置允许, 自动 mirror 到 imdf.engines.audit_chain (best-effort).
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# NOTE: Don't import VerifyResult here — circular dep with verifier. Use duck typing.

# ============================================================================
# Config
# ============================================================================

def _default_log_path() -> Path:
    base = Path(__file__).resolve().parent.parent.parent / "logs"
    custom = os.getenv("CONTRACT_AUDIT_LOG_PATH")
    p = Path(custom) if custom else base / "contracts_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_LOG_PATH: Path = _default_log_path()
_LOCK = threading.Lock()
_SEQ = 0
_INITIALIZED = False


def _ensure_seq() -> int:
    """读已有 log 最后一条 seq, 用于续号."""
    global _SEQ, _INITIALIZED
    if _INITIALIZED:
        return _SEQ + 1
    if _LOG_PATH.exists():
        try:
            with _LOG_PATH.open("r", encoding="utf-8") as f:
                last_seq = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                        if e.get("seq", 0) > last_seq:
                            last_seq = e["seq"]
                    except Exception:
                        pass
                _SEQ = last_seq
        except Exception:
            pass
    _INITIALIZED = True
    return _SEQ + 1


def _set_log_path(path: str) -> None:
    """测试用 — 替换日志路径."""
    global _LOG_PATH, _INITIALIZED, _SEQ
    _LOG_PATH = Path(path)
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INITIALIZED = False
    _SEQ = 0


# ============================================================================
# Data class
# ============================================================================

@dataclass
class AuditEvent:
    seq: int
    ts: str
    event: str  # "sign" | "verify"
    contract_id: str
    signer: Optional[str] = None
    alg: Optional[str] = None
    doc_hash: Optional[str] = None
    cert_serial: Optional[int] = None
    cert_fingerprint: Optional[str] = None
    signature_b64: Optional[str] = None
    timestamp_token_id: Optional[str] = None
    ok: Optional[bool] = None
    reasons: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# Append
# ============================================================================

def audit_sign_event(
    *,
    contract_id: str,
    signer: str,
    alg: str,
    doc_hash: str,
    cert_serial: int,
    cert_fingerprint: str,
    signature_b64: str,
    timestamp_token_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """签名事件审计."""
    with _LOCK:
        seq = _ensure_seq()
        ev = AuditEvent(
            seq=seq,
            ts=datetime.utcnow().isoformat() + "Z",
            event="sign",
            contract_id=contract_id,
            signer=signer,
            alg=alg,
            doc_hash=doc_hash,
            cert_serial=cert_serial,
            cert_fingerprint=cert_fingerprint,
            signature_b64=signature_b64[:80] + "..." if len(signature_b64) > 80 else signature_b64,
            timestamp_token_id=timestamp_token_id,
            ok=True,
            extra=extra or {},
        )
        _append_event(ev)
        # bump _SEQ
        global _SEQ
        _SEQ = seq
        return ev


def audit_verify_event(contract_id: str, result) -> AuditEvent:
    """验签事件审计."""
    with _LOCK:
        seq = _ensure_seq()
        ev = AuditEvent(
            seq=seq,
            ts=result.verified_at or (datetime.utcnow().isoformat() + "Z"),
            event="verify",
            contract_id=contract_id,
            signer=None,
            alg=result.signature_alg,
            doc_hash=result.doc_hash,
            cert_serial=result.cert_serial,
            cert_fingerprint=result.cert_fingerprint,
            signature_b64=(result.signature_value_b64[:80] + "...") if (result.signature_value_b64 and len(result.signature_value_b64) > 80) else result.signature_value_b64,
            timestamp_token_id=result.timestamp_token_id,
            ok=result.ok,
            reasons=list(result.reasons),
            extra={},
        )
        _append_event(ev)
        global _SEQ
        _SEQ = seq
        return ev


def _append_event(ev: AuditEvent) -> None:
    payload = json.dumps(ev.to_dict(), ensure_ascii=False)
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(payload + "\n")
    except Exception as e:
        # 审计失败只 log, 不影响业务
        import logging
        logging.getLogger(__name__).warning("audit_append_failed: %s", e)
    # Best-effort mirror 到 imdf.engines.audit_chain
    try:
        from . import _audit_mirror  # noqa: F401
    except Exception:
        try:
            import sys
            for m in list(sys.modules):
                if "engines.audit_chain" in m:
                    break
        except Exception:
            pass


# ============================================================================
# Read / 清空
# ============================================================================

def read_audit_log(
    *,
    contract_id: Optional[str] = None,
    event: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """读审计日志 (按 contract_id / event 过滤)."""
    if not _LOG_PATH.exists():
        return []
    out: List[Dict[str, Any]] = []
    with _LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if contract_id is not None and e.get("contract_id") != contract_id:
                continue
            if event is not None and e.get("event") != event:
                continue
            out.append(e)
    if limit is not None:
        out = out[-limit:]
    return out


def clear_audit_log() -> None:
    """测试用 — 清空."""
    global _INITIALIZED, _SEQ
    with _LOCK:
        try:
            if _LOG_PATH.exists():
                _LOG_PATH.unlink()
        except Exception:
            pass
        _INITIALIZED = False
        _SEQ = 0


__all__ = [
    "AuditEvent",
    "audit_sign_event",
    "audit_verify_event",
    "read_audit_log",
    "clear_audit_log",
    "_set_log_path",
]
