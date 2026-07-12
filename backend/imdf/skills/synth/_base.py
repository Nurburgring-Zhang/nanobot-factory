"""Synth skills — base adapters, offline mock helpers, httpx wrapper.

Each ``backend/imdf/skills/synth/<name>.py`` exposes:

    async def <name>(input: SkillInput) -> SkillOutput

The function:
  1. Validates input via a Pydantic ``XxxInput`` model
  2. Calls an external service via ``httpx.AsyncClient`` (with timeout)
  3. Falls back to a deterministic offline mock when network fails
  4. Returns ``SkillOutput`` with structured ``result`` + ``metadata``

This base module is intentionally tiny — keeps each skill module ~150 lines.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import os
import random
import socket
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput

# P21 P2 P4 (R2 N8): unified metadata envelope — single source of truth for
# ``result`` + ``metadata`` shape across all 4 imdf skill base files.
from backend.imdf.skills._envelope import make_envelope  # noqa: E402


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
    "imdf_synth_retry_state", default=_RetryState()
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
    attempt count in ``_RetryState`` so ``_build_output`` can surface
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

    Skipped in CI / when ``SYNTH_OFFLINE=1`` is set (offline-by-default).
    """
    if os.environ.get("SYNTH_OFFLINE", "").strip().lower() in {"1", "true", "yes"}:
        return False
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False


NETWORK_OK: bool = _network_available()


# ── Common Pydantic schemas ────────────────────────────────────────────────
class _BaseOutput(BaseModel):
    """Common metadata envelope — every skill output embeds these fields."""

    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "synth"  # "live" or "mock" or "synth"
    confidence: float = 0.85  # [0, 1]
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


async def _post_json(
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: float = 5.0,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """POST JSON to ``url`` and return the response body, or None on failure.

    P21 P3 N3: retried up to 3× on transient network/timeout errors
    before falling back to ``None``. Any other failure (4xx/5xx, bad
    JSON) still returns ``None`` immediately so callers drop into offline
    mock mode.
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
def _stable_seed(*parts: Any) -> int:
    """Stable seed derived from hashing the input parts (so mocks are reproducible)."""
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"|")
    return int.from_bytes(h.digest()[:4], "big", signed=False)


def _mock_pick(prompt: str, choices: List[str]) -> str:
    rng = random.Random(_stable_seed(prompt, len(choices)))
    return rng.choice(choices)


# ── SkillOutput builder ────────────────────────────────────────────────────
def _build_output(
    *,
    success: bool,
    result: Any,
    error: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    elapsed_ms: float = 0.0,
) -> SkillOutput:
    """Assemble a ``SkillOutput`` with the synth metadata envelope.

    P21 P3 N3+N4: ``retry_count`` / ``token_count`` / ``input_tokens`` /
    ``output_tokens`` are auto-populated from the per-call ``_RetryState``
    unless the caller overrides them via the ``metadata`` dict.

    P21 P2 P4 (R2 N8): ``elapsed_ms`` is now a first-class parameter
    forwarded to :func:`make_envelope` (the unified envelope builder)
    so all 4 imdf bases produce the same ``metadata`` shape. Callers can
    use :class:`backend.imdf.skills._envelope.ElapsedTimer` to record
    wall-clock duration, or pass ``t0`` deltas they already track.
    """
    state = get_retry_state()
    extra = dict(metadata or {})
    # Pop the canonical fields make_envelope will set; keep the rest in
    # `extra` for merging into metadata (e.g. "skill_module", "ts",
    # "input_tokens", "output_tokens", "validation_error", "source").
    source = extra.pop("source", "synth")
    extra.setdefault("skill_module", "synth")
    extra.setdefault("ts", datetime.now(timezone.utc).isoformat())
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


# ── Async noop guard (for tests that bypass real network) ──────────────────
async def _sleep_ms(ms: float) -> None:
    if ms > 0:
        await asyncio.sleep(ms / 1000.0)


__all__ = [
    "SkillInput",
    "SkillOutput",
    "NETWORK_OK",
    "_BaseOutput",
    "_post_json",
    "_stable_seed",
    "_mock_pick",
    "_build_output",
    "_sleep_ms",
    # P21 P3 N3+N4
    "retry",
    "get_retry_state",
    "reset_retry_state",
]