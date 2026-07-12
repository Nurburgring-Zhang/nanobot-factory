"""Label skills shared base.

Mirrors the `synth/_base.py` and `clean/_base.py` patterns. Each label skill:

    async def <name>(input: SkillInput) -> SkillOutput

does the following:
    1. Validate the payload via a per-skill Pydantic ``<Name>Input`` model
    2. Call an external inference service via ``httpx.AsyncClient`` (when online)
    3. Fall back to a deterministic offline mock when network is unavailable
    4. Return ``SkillOutput`` with structured ``result`` + ``metadata``
       (timestamp / source / confidence / elapsed_ms)

``source`` is one of ``{"label", "live", "mock"}``:
  * ``"live"`` — real network call succeeded
  * ``"mock"`` — offline fallback or forced via ``LABEL_OFFLINE=1`` env var
  * ``"label"`` — default tag for label module skills

Use ``NETWORK_OK = False`` (set ``LABEL_OFFLINE=1``) in tests / CI.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import logging
import os
import random
import socket
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput

# P21 P2 P4 (R2 N8): unified metadata envelope — single source of truth for
# ``result`` + ``metadata`` shape across all 4 imdf skill base files.
from backend.imdf.skills._envelope import make_envelope  # noqa: E402

logger = logging.getLogger("imdf.skills.label")


# ---------------------------------------------------------------------------
# Retry + cost/token tracking (P21 P3 N3 + N4)
# ---------------------------------------------------------------------------
# Stdlib-only retry decorator (no tenacity). State lives in a contextvar so
# concurrent skill invocations don't share counters.
# ---------------------------------------------------------------------------
class _RetryState:
    __slots__ = ("attempts", "input_tokens", "output_tokens")

    def __init__(self) -> None:
        self.attempts = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def record(self) -> None:
        self.attempts += 1

    def add_usage(self, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)


_current_retry_state: contextvars.ContextVar[_RetryState] = contextvars.ContextVar(
    "imdf_label_retry_state", default=_RetryState()
)


def get_retry_state() -> _RetryState:
    return _current_retry_state.get()


def reset_retry_state() -> _RetryState:
    state = _current_retry_state.get()
    state.attempts = 0
    state.input_tokens = 0
    state.output_tokens = 0
    return state


def retry(max_attempts: int = 3, backoff: float = 0.5,
          exceptions: Any = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Async retry decorator — stdlib only.

    Retries up to ``max_attempts`` times on the given exception types,
    sleeping ``backoff * 2**attempt`` seconds between attempts. Records
    attempt count in ``_RetryState`` so ``build_output`` can surface
    ``retry_count`` in metadata.
    """
    if exceptions is None:
        exceptions = (httpx.TimeoutException, httpx.NetworkError)

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            state = get_retry_state()
            last: Optional[BaseException] = None
            for attempt in range(max_attempts):
                state.record()
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:  # type: ignore[misc]
                    last = exc
                    if attempt + 1 >= max_attempts:
                        break
                    await asyncio.sleep(backoff * (2 ** attempt))
            assert last is not None
            raise last

        return wrapper

    return deco


# ── Network availability probe ─────────────────────────────────────────────
def _network_available(timeout: float = 0.4) -> bool:
    """Best-effort check: can we reach the public internet?

    Skipped when ``LABEL_OFFLINE=1`` (offline-by-default for tests / CI).
    """
    if os.environ.get("LABEL_OFFLINE", "").strip().lower() in {"1", "true", "yes"}:
        return False
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False


NETWORK_OK: bool = _network_available()


# ── Common Pydantic schemas ────────────────────────────────────────────────
class LabelBaseOutput(BaseModel):
    """Common metadata envelope — every label skill output embeds these fields.

    All label skill modules return a dict shaped like this inside
    ``SkillOutput.result``.
    """

    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "label"
    confidence: float = 0.85
    elapsed_ms: float = 0.0


# ── httpx wrapper (timeout + fallback + retry) ────────────────────────────
@retry(max_attempts=3, backoff=0.5)
async def _post_json_inner(
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: float = 5.0,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Inner POST — only raises on network/timeout errors. Wrapped by retry."""
    if not NETWORK_OK:
        return None
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


async def post_json(
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: float = 5.0,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """POST JSON to ``url`` and return the response body, or None on failure.

    P21 P3 N3: now retried up to 3× on transient network/timeout errors
    before falling back to ``None``. Any non-network failure (4xx/5xx,
    ValueError on bad JSON) still returns ``None`` immediately so callers
    can drop into offline mock mode.
    """
    try:
        return await _post_json_inner(
            url, payload, timeout=timeout, headers=headers,
        )
    except (httpx.TimeoutException, httpx.NetworkError):
        return None
    except (httpx.HTTPError, asyncio.TimeoutError, ValueError):
        return None


# ── Deterministic pseudo-output ─────────────────────────────────────────────
def stable_seed(*parts: Any) -> int:
    """Stable seed derived from hashing the input parts (so mocks are reproducible)."""
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"|")
    return int.from_bytes(h.digest()[:4], "big", signed=False)


def mock_pick(prompt: str, choices: List[str]) -> str:
    rng = random.Random(stable_seed(prompt, len(choices)))
    return rng.choice(choices)


# ── SkillOutput builder ────────────────────────────────────────────────────
def build_output(
    *,
    success: bool,
    result: Any = None,
    error: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    elapsed_ms: float = 0.0,
    source: str = "label",
    confidence: float = 0.85,
) -> SkillOutput:
    """Assemble a ``SkillOutput`` with the canonical metadata envelope.

    P21 P3 N3+N4: ``retry_count`` / ``token_count`` / ``input_tokens`` /
    ``output_tokens`` are auto-populated from the per-call ``_RetryState``
    unless the caller overrides them via the ``metadata`` dict.

    P21 P2 P4 (R2 N8): ``elapsed_ms`` is now a first-class parameter
    forwarded to :func:`make_envelope` (the unified envelope builder)
    so all 4 imdf bases produce the same ``metadata`` shape. Callers can
    use :class:`backend.imdf.skills._envelope.ElapsedTimer` to record
    wall-clock duration, or pass ``t0`` deltas they already track.

    ``result`` is optional — error paths can omit it.
    """
    state = get_retry_state()
    extra = dict(metadata or {})
    extra.setdefault("skill_module", "label")
    extra.setdefault("ts", datetime.now(timezone.utc).isoformat())
    extra.setdefault("confidence", confidence)
    extra.setdefault("input_tokens", state.input_tokens)
    extra.setdefault("output_tokens", state.output_tokens)
    envelope = make_envelope(
        result=result,
        elapsed_ms=elapsed_ms,
        source=source,
        retry_count=max(0, state.attempts - 1),
        token_count=state.input_tokens + state.output_tokens,
        cost_usd=float(extra.pop("cost_usd", 0.0)),
        extra=extra,
    )
    return SkillOutput(
        success=success,
        result=envelope["result"],
        error=error,
        metadata=envelope["metadata"],
    )


async def sleep_ms(ms: float) -> None:
    """Tiny helper for deterministic-test timing — optional."""
    if ms > 0:
        await asyncio.sleep(ms / 1000.0)


# ── Common light validation utilities ──────────────────────────────────────
def require_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "SkillInput",
    "SkillOutput",
    "LabelBaseOutput",
    "NETWORK_OK",
    "post_json",
    "stable_seed",
    "mock_pick",
    "build_output",
    "sleep_ms",
    "require_non_empty",
    "clamp",
    "now_iso",
    # P21 P3 N3+N4
    "retry",
    "get_retry_state",
    "reset_retry_state",
]