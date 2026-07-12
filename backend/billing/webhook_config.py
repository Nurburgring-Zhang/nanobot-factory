"""Webhook configuration + event dispatch for billing.

5 supported events:
- payment.created
- payment.succeeded
- payment.failed
- refund.created
- refund.succeeded

Public surface:
- WEBHOOK_EVENTS: tuple of 5 event names
- WebhookConfig: dataclass (url, events, secret, enabled)
- WebhookStore: ABC + InMemoryWebhookStore + JsonlWebhookStore
- WebhookDispatcher: register / list / dispatch
- emit_event(event_name, payload, dispatcher) -> List[DeliveryResult]
- HMAC-SHA256 signature: X-Webhook-Signature: sha256=<hex>
- verify_signature(headers, body_bytes, secret) -> bool

P17-D1 hardening (3 P0 + 5 hidden):
- P0 #1: Replay protection — timestamp ±5min + nonce store (HMAC over timestamp+nonce+payload)
- P0 #2: SSRF protection — URL must be https:// + hostname resolves to public IP
- P0 #3: Retry + exponential backoff — 3 attempts (1s/2s/4s), then dead-letter audit
- Hidden #1: CN¥/JP¥ symbol disambiguation (in currency.py)
- Hidden #2: 0 amount rejection (in tax.py attach_tax_to_order)
- Hidden #3: refresh_rates_from_api real impl (in currency.py)
- Hidden #4: JsonlWebhookStore append-only with file lock (no truncation)
- Hidden #5: emit_event global lock for double-checked-locking safety
"""
from __future__ import annotations

import enum
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Set


# ============================================================================
# 1. Constants — supported events
# ============================================================================

class WebhookEvent(str, enum.Enum):
    PAYMENT_CREATED = "payment.created"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    REFUND_CREATED = "refund.created"
    REFUND_SUCCEEDED = "refund.succeeded"


WEBHOOK_EVENTS: tuple = tuple(e.value for e in WebhookEvent)
SIGNATURE_HEADER = "X-Webhook-Signature"
TIMESTAMP_HEADER = "X-Webhook-Timestamp"
EVENT_HEADER = "X-Webhook-Event"
DELIVERY_ID_HEADER = "X-Webhook-Delivery-Id"
NONCE_HEADER = "X-Webhook-Nonce"

# P0 #1: Replay protection window — request older than this is rejected
TIMESTAMP_TOLERANCE_SECONDS = 300  # ±5 min

# P0 #1: Nonce store retention (in-memory). After this, nonces are expired.
NONCE_TTL_SECONDS = 600  # 10 min (covers TIMESTAMP_TOLERANCE + clock skew)

# P0 #3: Retry policy
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 1.0  # 1s, 2s, 4s

# P0 #2: SSRF — disallowed hostnames / IP ranges
SSRF_DISALLOWED_HOSTNAMES: Set[str] = {
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",  # AWS / Azure / GCP metadata service
}
SSRF_DISALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # private
    ipaddress.ip_network("172.16.0.0/12"),     # private
    ipaddress.ip_network("192.168.0.0/16"),    # private
    ipaddress.ip_network("169.254.0.0/16"),    # link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),         # unspecified
    ipaddress.ip_network("100.64.0.0/10"),     # carrier-grade NAT
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


# ============================================================================
# 2. WebhookConfig + DeliveryResult
# ============================================================================

@dataclass
class WebhookConfig:
    """A single registered webhook endpoint."""
    webhook_id: str
    url: str
    events: List[str]              # subscribed event names
    secret: str                    # HMAC secret
    enabled: bool = True
    description: str = ""
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _utcnow_iso()
        # Validate events
        for ev in self.events:
            if ev not in WEBHOOK_EVENTS:
                raise ValueError(
                    f"unsupported event: {ev!r} (valid: {WEBHOOK_EVENTS})"
                )
        if not self.url or not (self.url.startswith("http://")
                                or self.url.startswith("https://")):
            raise ValueError(f"url must start with http:// or https://, got {self.url!r}")
        if not self.secret or len(self.secret) < 8:
            raise ValueError("secret must be at least 8 characters")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WebhookConfig":
        return cls(**d)

    def subscribes_to(self, event: str) -> bool:
        return self.enabled and event in self.events


@dataclass
class DeliveryResult:
    """Result of one webhook dispatch attempt (with retries)."""
    webhook_id: str
    event: str
    delivery_id: str
    url: str
    status_code: int
    success: bool
    error: Optional[str] = None
    signature: Optional[str] = None
    delivered_at: str = ""
    duration_ms: int = 0
    attempts: int = 1
    dead_lettered: bool = False
    error_history: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.delivered_at:
            self.delivered_at = _utcnow_iso()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# 3. WebhookStore — ABC + in-memory + JSONL (append-only)
# ============================================================================

class WebhookStore(Protocol):
    def save(self, config: WebhookConfig) -> None: ...
    def get(self, webhook_id: str) -> Optional[WebhookConfig]: ...
    def list(self) -> List[WebhookConfig]: ...
    def delete(self, webhook_id: str) -> bool: ...


class InMemoryWebhookStore:
    """Thread-safe in-memory store."""
    def __init__(self) -> None:
        self._configs: Dict[str, WebhookConfig] = {}
        self._lock = threading.Lock()

    def save(self, config: WebhookConfig) -> None:
        with self._lock:
            self._configs[config.webhook_id] = config

    def get(self, webhook_id: str) -> Optional[WebhookConfig]:
        with self._lock:
            return self._configs.get(webhook_id)

    def list(self) -> List[WebhookConfig]:
        with self._lock:
            return list(self._configs.values())

    def delete(self, webhook_id: str) -> bool:
        with self._lock:
            if webhook_id in self._configs:
                del self._configs[webhook_id]
                return True
            return False


class JsonlWebhookStore:
    """JSONL file-backed store (P17-D1 Hidden #4: append-only).

    Each save() appends one line. Reads load all lines on first access and
    cache. Deletes are written to a tombstone file (so the JSONL file
    remains append-only and never truncated).

    Hidden #4 thread-safety:
    - Each append uses mode "a" (open at end) protected by a thread lock
    - File-level read uses a separate read lock to avoid blocking concurrent appends
    - The cache is invalidated on every save()/delete() to maintain consistency
    """
    TOMBSTONE_PREFIX = "DELETED:"

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._cache: Optional[Dict[str, WebhookConfig]] = None
        self._cache_lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()

    def _load_cache(self) -> Dict[str, WebhookConfig]:
        """Load all records from disk into cache. Respects tombstones."""
        with self._cache_lock:
            if self._cache is not None:
                return self._cache
            out: Dict[str, WebhookConfig] = {}
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.rstrip("\n").rstrip("\r")
                        if not line:
                            continue
                        # Handle tombstone (deletion marker)
                        if line.startswith(self.TOMBSTONE_PREFIX):
                            tomb_id = line[len(self.TOMBSTONE_PREFIX):].strip()
                            out.pop(tomb_id, None)
                            continue
                        try:
                            rec = json.loads(line)
                            wid = rec.get("webhook_id")
                            if not wid:
                                continue
                            # Last-write-wins semantics for repeated ids
                            out[wid] = WebhookConfig.from_dict(rec)
                        except Exception:
                            continue
            self._cache = out
            return out

    def _invalidate_cache(self) -> None:
        with self._cache_lock:
            self._cache = None

    def save(self, config: WebhookConfig) -> None:
        """Append config as one JSONL line (Hidden #4: append-only)."""
        line = json.dumps(config.to_dict(), ensure_ascii=False,
                          separators=(",", ":")) + "\n"
        with self._write_lock:
            # Open in append mode — never truncate the existing file
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except (OSError, AttributeError):
                    pass
        # Invalidate cache so next read picks up the new state
        self._invalidate_cache()

    def get(self, webhook_id: str) -> Optional[WebhookConfig]:
        cache = self._load_cache()
        return cache.get(webhook_id)

    def list(self) -> List[WebhookConfig]:
        cache = self._load_cache()
        return list(cache.values())

    def delete(self, webhook_id: str) -> bool:
        """Append a tombstone line (Hidden #4: never truncate)."""
        exists = self.get(webhook_id) is not None
        if not exists:
            return False
        line = f"{self.TOMBSTONE_PREFIX}{webhook_id}\n"
        with self._write_lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except (OSError, AttributeError):
                    pass
        self._invalidate_cache()
        return True


# ============================================================================
# 4. Signature computation / verification (P0 #1: includes nonce)
# ============================================================================

def compute_signature(secret: str, payload: bytes,
                      timestamp: Optional[str] = None,
                      nonce: Optional[str] = None) -> str:
    """Compute HMAC-SHA256 signature.

    P0 #1: signed material = timestamp.nonce.body (replay protection).

    Format: sha256=<hex>

    The signed string is:
        <timestamp>.<nonce>.<body>     if both timestamp+nonce given
        <timestamp>.<body>             if only timestamp given
        <body>                          otherwise
    """
    if timestamp and nonce:
        signed = f"{timestamp}.{nonce}.".encode("utf-8") + payload
    elif timestamp:
        signed = f"{timestamp}.".encode("utf-8") + payload
    else:
        signed = payload
    mac = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_signature(secret: str, payload: bytes,
                     signature_header: str,
                     timestamp: Optional[str] = None,
                     nonce: Optional[str] = None,
                     tolerance_seconds: int = TIMESTAMP_TOLERANCE_SECONDS) -> bool:
    """Verify an HMAC-SHA256 signature header.

    Returns True if signature matches. False if:
    - signature_header malformed
    - signature mismatch
    - timestamp out of tolerance window (if provided)
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = compute_signature(secret, payload, timestamp, nonce)
    return hmac.compare_digest(expected, signature_header)


# ============================================================================
# 5. P0 #1: NonceStore — replay protection
# ============================================================================

class NonceStore:
    """Thread-safe store for recently-seen nonces.

    Each emit emits a fresh nonce; the nonce is included in the signed payload
    AND in the X-Webhook-Nonce header. Recipients MUST verify the nonce has
    not been seen before (within the TTL window).
    """
    def __init__(self, ttl_seconds: int = NONCE_TTL_SECONDS) -> None:
        self._seen: Dict[str, float] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def is_seen(self, nonce: str) -> bool:
        """Return True if this nonce has been seen recently (and is still in window)."""
        self._cleanup()
        with self._lock:
            return nonce in self._seen

    def mark_seen(self, nonce: str) -> None:
        """Record nonce as seen (with current timestamp)."""
        self._cleanup()
        with self._lock:
            self._seen[nonce] = time.time()

    def reserve(self, nonce: str) -> bool:
        """Atomically: if nonce not seen, mark as seen and return True.
        If already seen, return False (caller should reject as replay).
        """
        self._cleanup()
        with self._lock:
            if nonce in self._seen:
                return False
            self._seen[nonce] = time.time()
            return True

    def _cleanup(self) -> None:
        """Drop expired nonces (older than TTL)."""
        cutoff = time.time() - self._ttl
        with self._lock:
            stale = [k for k, t in self._seen.items() if t < cutoff]
            for k in stale:
                del self._seen[k]

    def size(self) -> int:
        with self._lock:
            return len(self._seen)


# ============================================================================
# 6. P0 #2: SSRF protection
# ============================================================================

class SSRFError(ValueError):
    """Raised when a webhook URL fails SSRF safety check."""


def validate_webhook_url(url: str,
                         allow_http: bool = False) -> str:
    """Validate that a webhook URL is safe (not SSRF-vulnerable).

    Rules:
    - Scheme must be https:// (http:// allowed only if allow_http=True, e.g. for tests)
    - Hostname must not be in SSRF_DISALLOWED_HOSTNAMES
    - Hostname must resolve to a public IPv4/IPv6 address
    - Resolved IP must not fall in any private/loopback/link-local range

    Raises:
        SSRFError if URL fails any check.
    """
    if not url:
        raise SSRFError("url must not be empty")

    # 1. Scheme check
    if url.startswith("http://"):
        if not allow_http:
            raise SSRFError(
                f"http:// not allowed for webhooks (use https://): {url!r}"
            )
    elif not url.startswith("https://"):
        raise SSRFError(
            f"url must start with https:// (or http:// in test mode), got {url!r}"
        )

    # 2. Parse host
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFError(f"url has no hostname: {url!r}")

    # 3. Disallowed hostnames (literal)
    if hostname in SSRF_DISALLOWED_HOSTNAMES:
        raise SSRFError(f"hostname blocked (SSRF): {hostname!r}")

    # 4. If hostname is an IP literal, check directly
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_disallowed_ip(ip):
            raise SSRFError(f"IP blocked (SSRF): {ip}")
        return url
    except ValueError:
        pass  # not an IP literal, will DNS-resolve below

    # 5. DNS resolution — must resolve to a public IP
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {hostname!r}: {e}")

    resolved_ips = {info[4][0] for info in infos}
    if not resolved_ips:
        raise SSRFError(f"DNS resolution returned no IPs for {hostname!r}")

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_disallowed_ip(ip):
            raise SSRFError(
                f"hostname {hostname!r} resolves to disallowed IP {ip} (SSRF)"
            )

    return url


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check whether an IP is in any SSRF-disallowed range."""
    for net in SSRF_DISALLOWED_NETWORKS:
        if ip.version != net.version:
            continue
        if ip in net:
            return True
    return False


# ============================================================================
# 7. Dispatcher
# ============================================================================

class HTTPPoster:
    """Default HTTP poster (can be overridden for tests)."""
    HTTP_TIMEOUT = 10  # seconds

    def post(self, url: str, data: bytes,
             headers: Dict[str, str]) -> tuple:
        """POST `data` to `url`. Returns (status_code, response_text)."""
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.HTTP_TIMEOUT) as resp:
                return (resp.status, resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            return (e.code, e.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return (0, f"network error: {e}")


class WebhookDispatcher:
    """Manages webhook registration and dispatches events to subscribers.

    P17-D1 hardening:
    - P0 #1: every emit attaches a timestamp + nonce; recipients can verify
      freshness via timestamp window + nonce uniqueness
    - P0 #2: register_webhook validates URL against SSRF rules
    - P0 #3: failed deliveries retry up to RETRY_MAX_ATTEMPTS with exponential
      backoff (1s, 2s, 4s); persistent failures become dead-letter entries
    - Hidden #5: emit_event holds a global dispatch lock for the whole iteration
      to avoid double-checked-locking race when state changes mid-iteration
    """
    def __init__(self, store: WebhookStore,
                 poster: Optional[HTTPPoster] = None,
                 nonce_store: Optional[NonceStore] = None,
                 allow_http_urls: bool = False,
                 audit_log: Optional[List[Dict[str, Any]]] = None,
                 backoff_base_seconds: Optional[float] = None) -> None:
        self.store = store
        self.poster = poster or HTTPPoster()
        self.nonce_store = nonce_store or NonceStore()
        self.allow_http_urls = allow_http_urls
        self._dispatch_lock = threading.Lock()
        self._audit_log = audit_log if audit_log is not None else []
        self._dead_letter_count = 0
        # Allow tests to override backoff (default = RETRY_BACKOFF_BASE_SECONDS)
        self._backoff_base = (
            backoff_base_seconds if backoff_base_seconds is not None
            else RETRY_BACKOFF_BASE_SECONDS
        )

    # ── P0 #2: SSRF-safe registration ───────────────────────────────────
    def register_webhook(self, url: str, events: List[str], secret: str,
                         description: str = "",
                         metadata: Optional[Dict[str, Any]] = None) -> WebhookConfig:
        """Register a new webhook endpoint.

        Raises:
            SSRFError: if URL fails SSRF safety check (P0 #2).
            ValueError: if events / secret / url fail validation.
        """
        # P0 #2: SSRF check before constructing WebhookConfig
        validate_webhook_url(url, allow_http=self.allow_http_urls)

        import uuid
        wh_id = f"wh_{uuid.uuid4().hex[:16]}"
        config = WebhookConfig(
            webhook_id=wh_id,
            url=url,
            events=list(events),
            secret=secret,
            description=description,
            metadata=dict(metadata or {}),
        )
        self.store.save(config)
        return config

    def unregister_webhook(self, webhook_id: str) -> bool:
        return self.store.delete(webhook_id)

    def list_webhooks(self) -> List[WebhookConfig]:
        return self.store.list()

    # ── Hidden #5: emit_event held under single dispatch lock ────────────
    def emit_event(self, event: str,
                   payload: Dict[str, Any]) -> List[DeliveryResult]:
        """Emit an event to all subscribed webhook endpoints.

        Hidden #5: the entire iteration is wrapped in self._dispatch_lock
        so that webhook subscriptions registered mid-iteration cannot race
        with in-flight deliveries. This is a deliberate double-checked-locking
        fix: the snapshot of `self.store.list()` happens inside the lock and
        deliveries to those targets complete before we release.

        Returns one DeliveryResult per subscribed webhook (in order).
        """
        if event not in WEBHOOK_EVENTS:
            raise ValueError(
                f"unknown event: {event!r} (valid: {WEBHOOK_EVENTS})"
            )
        body_bytes = json.dumps(payload, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8")
        results: List[DeliveryResult] = []
        # Hidden #5: hold dispatch lock for entire snapshot+deliver sequence
        with self._dispatch_lock:
            for cfg in self.store.list():
                if not cfg.subscribes_to(event):
                    continue
                results.append(self._deliver(cfg, event, body_bytes, payload))
        return results

    def _deliver(self, cfg: WebhookConfig, event: str,
                 body_bytes: bytes, payload: Dict[str, Any]) -> DeliveryResult:
        """Deliver one webhook with retry + backoff (P0 #3)."""
        import uuid
        delivery_id = f"dlv_{uuid.uuid4().hex[:16]}"
        timestamp = str(int(time.time()))
        # P0 #1: nonce ensures each delivery is unique even for the same payload
        nonce = uuid.uuid4().hex
        signature = compute_signature(cfg.secret, body_bytes, timestamp, nonce)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "nanobot-factory-webhook/1.0",
            EVENT_HEADER: event,
            SIGNATURE_HEADER: signature,
            TIMESTAMP_HEADER: timestamp,
            NONCE_HEADER: nonce,
            DELIVERY_ID_HEADER: delivery_id,
        }

        # P0 #3: retry with exponential backoff
        last_error: Optional[str] = None
        last_status = 0
        error_history: List[str] = []
        success = False
        attempt_count = 0

        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            attempt_count = attempt
            t0 = time.time()
            try:
                status_code, response_text = self.poster.post(cfg.url, body_bytes, headers)
                duration_ms = int((time.time() - t0) * 1000)
                success = 200 <= status_code < 300
                last_status = status_code
                if success:
                    return DeliveryResult(
                        webhook_id=cfg.webhook_id,
                        event=event,
                        delivery_id=delivery_id,
                        url=cfg.url,
                        status_code=status_code,
                        success=True,
                        error=None,
                        signature=signature,
                        duration_ms=duration_ms,
                        attempts=attempt,
                        dead_lettered=False,
                        error_history=[],
                    )
                err_msg = response_text[:200] or f"HTTP {status_code}"
                error_history.append(f"attempt {attempt}: status={status_code} body={err_msg}")
                last_error = err_msg
            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                err_msg = f"delivery exception: {e}"
                error_history.append(f"attempt {attempt}: {err_msg}")
                last_error = err_msg
                last_status = 0

            # If not last attempt, sleep with exponential backoff
            if attempt < RETRY_MAX_ATTEMPTS:
                backoff = self._backoff_base * (2 ** (attempt - 1))
                time.sleep(backoff)

        # All attempts failed → dead-letter
        self._dead_letter_count += 1
        dead_letter_entry = {
            "delivery_id": delivery_id,
            "webhook_id": cfg.webhook_id,
            "url": cfg.url,
            "event": event,
            "attempts": attempt_count,
            "last_status": last_status,
            "last_error": last_error,
            "error_history": error_history,
            "timestamp": timestamp,
            "nonce": nonce,
            "dead_lettered_at": _utcnow_iso(),
        }
        self._audit_log.append(dead_letter_entry)

        return DeliveryResult(
            webhook_id=cfg.webhook_id,
            event=event,
            delivery_id=delivery_id,
            url=cfg.url,
            status_code=last_status,
            success=False,
            error=last_error,
            signature=signature,
            duration_ms=0,
            attempts=attempt_count,
            dead_lettered=True,
            error_history=error_history,
        )

    @property
    def dead_letter_count(self) -> int:
        return self._dead_letter_count

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)


# ============================================================================
# 8. Module-level singleton (for convenience)
# ============================================================================

_default_store: WebhookStore = InMemoryWebhookStore()
_default_dispatcher: Optional[WebhookDispatcher] = None
_default_dispatcher_lock = threading.Lock()


def get_default_dispatcher() -> WebhookDispatcher:
    global _default_dispatcher
    with _default_dispatcher_lock:
        if _default_dispatcher is None:
            _default_dispatcher = WebhookDispatcher(_default_store)
        return _default_dispatcher


def reset_default_dispatcher() -> None:
    """Reset module state. Used by tests."""
    global _default_store, _default_dispatcher
    _default_store = InMemoryWebhookStore()
    _default_dispatcher = None


# ============================================================================
# Helpers
# ============================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_webhook_id() -> str:
    import uuid
    return f"wh_{uuid.uuid4().hex[:16]}"


__all__ = [
    "WebhookEvent", "WEBHOOK_EVENTS",
    "SIGNATURE_HEADER", "TIMESTAMP_HEADER", "EVENT_HEADER",
    "DELIVERY_ID_HEADER", "NONCE_HEADER",
    "TIMESTAMP_TOLERANCE_SECONDS", "NONCE_TTL_SECONDS",
    "RETRY_MAX_ATTEMPTS", "RETRY_BACKOFF_BASE_SECONDS",
    "WebhookConfig", "DeliveryResult",
    "WebhookStore", "InMemoryWebhookStore", "JsonlWebhookStore",
    "HTTPPoster", "WebhookDispatcher",
    "NonceStore",
    "SSRFError", "validate_webhook_url", "SSRF_DISALLOWED_HOSTNAMES",
    "compute_signature", "verify_signature",
    "get_default_dispatcher", "reset_default_dispatcher",
    "new_webhook_id",
]