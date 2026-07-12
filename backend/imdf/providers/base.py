"""P20: Provider base class + response model.

Common interface that all P20+ LLM providers must implement:

    class XxxProvider(BaseProvider):
        async def invoke(self, prompt: str, params: InvokeParams) -> ProviderResponse
        async def list_models(self) -> List[str]
        async def health_check(self) -> HealthStatus

Design notes
------------
- Pydantic v2 (BaseModel + ConfigDict(extra='allow') to stay forward-compatible
  with vendor-specific fields like Perplexity's ``citations``).
- Streaming is exposed via ``invoke_stream(prompt, params) -> AsyncIterator[ProviderChunk]``
  — default implementation in BaseProvider calls invoke() then yields a single
  chunk, subclasses override for real SSE / chunked HTTP.
- Errors are returned via ProviderResponse.success=False (not raised) so the
  caller (engine router / batch dispatcher) can record + fall back without
  try/except noise.  Network / programming errors still raise.

P21 P2 P2 (2026-07-11) — retry / 429 backoff / circuit-breaker:
- ``_request()`` is the per-provider HTTP primitive.  Subclasses MAY override
  (e.g. to use a different client) but the default implementation is a thin
  httpx wrapper.
- ``_request_with_retry()`` is the public retry entrypoint: it calls
  ``_request()`` up to 3 times, honours ``Retry-After`` on 429, exponential
  backoff (1s/2s/4s) on 5xx, and trips an in-memory circuit breaker after 3
  consecutive failures.  All 23 providers that inherit from this class gain
  the wrapper for free — subclasses only need to call ``self._request_with_retry``
  instead of ``httpx.AsyncClient.post`` directly.
- State (``_consecutive_failures`` / ``_circuit_open_until``) is per-instance,
  not global — keeps the fix simple, multiple providers do not share trips.
- No new third-party deps: ``time`` + ``asyncio`` only.
"""
from __future__ import annotations

import abc
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field


# ─── Request-side container ─────────────────────────────────────────────────


class InvokeParams(BaseModel):
    """Standard call params.

    ``model`` may be None → use provider default.  Other fields are optional —
    subclasses extract what they need.
    """

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    stop: Optional[List[str]] = None
    stream: bool = False
    # vendor-specific (Perplexity search options, Groq reasoning_format, etc.)
    extra: Dict[str, Any] = Field(default_factory=dict)


# ─── Response-side containers ───────────────────────────────────────────────


class ProviderResponse(BaseModel):
    """Single-shot provider response.

    Set ``success=False`` + ``error`` for any caller-visible failure (HTTP 4xx,
    5xx, rate limit).  Network / DNS / programming errors still raise — those
    should be handled by the router fallback layer.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: Dict[str, int] = Field(default_factory=dict)
    error: str = ""
    latency_ms: float = 0.0
    # Perplexity-style citations / search_results are kept as raw dict so we
    # don't need to keep up with vendor schema changes.
    raw: Dict[str, Any] = Field(default_factory=dict)


class ProviderChunk(BaseModel):
    """A single streaming chunk emitted by ``invoke_stream``."""

    model_config = ConfigDict(extra="allow")

    delta: str = ""
    done: bool = False
    finish_reason: Optional[str] = None
    model: str = ""
    provider: str = ""


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "ok"            # ok | error | placeholder | mock
    provider: str = ""
    latency_ms: float = 0.0
    error: str = ""
    model: str = ""


# ─── P21 P2 P2: retry / circuit-breaker plumbing ────────────────────────────


class CircuitOpenError(RuntimeError):
    """Raised by ``_request_with_retry`` when the in-memory circuit is open.

    The circuit opens after ``BaseProvider._retry_max_consecutive_failures``
    consecutive failures (default 3) and stays open for
    ``BaseProvider._retry_circuit_cooldown_sec`` seconds (default 60).

    This is a per-instance counter — each ``BaseProvider`` subclass instance
    has its own state, so a tripped Claude provider does not block Groq.
    """


@dataclass
class _ProviderResponse:
    """Lightweight response container returned by ``BaseProvider._request()``.

    Subclasses that override ``_request()`` MUST return one of these.  The
    dataclass keeps the contract simple (no httpx dependency at the
    boundary) so test doubles can build canned responses trivially.
    """

    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    text: str = ""

    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


# ─── Base class ─────────────────────────────────────────────────────────────


class BaseProvider(abc.ABC):
    """Abstract LLM provider.

    Subclasses MUST set:
        provider_name:  short id used in registry / log lines
        family:         enum-style group label

    Subclasses MUST implement:
        async invoke(prompt, params) -> ProviderResponse
        async list_models() -> List[str]

    Subclasses SHOULD override:
        async health_check() -> HealthStatus  (default uses list_models ping)
        async invoke_stream(prompt, params) -> AsyncIterator[ProviderChunk]
    """

    provider_name: str = "base"
    family: str = "base"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or self.default_base_url()).rstrip("/")
        self.timeout = float(timeout)

        # ── P21 P2 P2: per-instance retry / circuit-breaker state ─────────
        # Per-instance (not global) so multiple providers do not share trips.
        # Subclasses may override these constants before __init__ if needed.
        self._retry_max_attempts: int = 3
        self._retry_max_consecutive_failures: int = 3
        self._retry_circuit_cooldown_sec: float = 60.0
        self._retry_5xx_base_backoff: float = 1.0  # exponential: 1s, 2s, 4s
        self._retry_429_default: float = 1.0      # fallback when no Retry-After

        self._consecutive_failures: int = 0
        self._circuit_open_until: float = 0.0     # epoch seconds, 0 = closed
        self._retry_attempts: int = 0             # total attempts this session
        self._retry_successes: int = 0            # total successful responses
        self._retry_circuit_trips: int = 0        # total times breaker opened

    # -- P21 P2 P2: retry / circuit-breaker ---------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> _ProviderResponse:
        """Default HTTP primitive — thin httpx wrapper.

        Subclasses MAY override this (e.g. to use a different client) but
        the default is good enough for OpenAI-compatible providers.  Tests
        override this to inject canned responses without touching the network.
        """
        client_timeout = float(timeout) if timeout is not None else self.timeout
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            resp = await client.request(
                method,
                url,
                headers=headers or {},
                json=json,
                params=params,
            )
            return _ProviderResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                text=resp.text,
            )

    def _circuit_is_open(self, now: Optional[float] = None) -> bool:
        """Return True if the circuit is currently open (blocking all calls).

        Half-open behaviour: when the cooldown elapses, the next call is
        allowed through (treated as a probe).  We do NOT auto-close on
        timeout — the probe call itself decides (success closes, failure
        re-opens with a fresh cooldown).
        """
        if self._circuit_open_until <= 0:
            return False
        now = now if now is not None else time.time()
        if now >= self._circuit_open_until:
            return False  # cooldown elapsed → half-open, allow one probe
        return True

    def _trip_circuit(self, now: Optional[float] = None) -> None:
        """Open the circuit for ``_retry_circuit_cooldown_sec`` seconds."""
        now = now if now is not None else time.time()
        self._circuit_open_until = now + self._retry_circuit_cooldown_sec
        self._retry_circuit_trips += 1

    def _record_failure(self) -> None:
        """Increment the failure counter; trip the breaker if threshold hit."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._retry_max_consecutive_failures:
            self._trip_circuit()

    def _record_success(self) -> None:
        """Reset the breaker on a 2xx response."""
        self._consecutive_failures = 0
        if self._circuit_open_until > 0:
            # Close the breaker on a successful probe.
            self._circuit_open_until = 0.0

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> _ProviderResponse:
        """Call :meth:`_request` with retry + circuit-breaker.

        Rules (per P21 P2 P2 spec):
          - Up to ``_retry_max_attempts`` (3) total tries.
          - 429 → read ``Retry-After`` header (seconds), sleep that long, retry.
          - 5xx → exponential backoff ``1s, 2s, 4s`` (multiplier
            ``_retry_5xx_base_backoff``), retry.
          - 4xx other than 429 → no retry, return immediately.
          - 2xx → success, reset breaker.
          - Exception (timeout, ConnectionError, etc.) → retry with backoff.
          - After ``_retry_max_consecutive_failures`` (3) consecutive failures
            trip the breaker for ``_retry_circuit_cooldown_sec`` (60s).

        Raises:
            CircuitOpenError: if the breaker is open at call time.
        """
        if self._circuit_is_open():
            raise CircuitOpenError(
                f"circuit_open: provider={self.provider_name} "
                f"cooldown_remaining={max(0.0, self._circuit_open_until - time.time()):.1f}s"
            )

        attempts = max(1, int(self._retry_max_attempts))
        last_response: Optional[_ProviderResponse] = None
        last_exc: Optional[BaseException] = None

        for attempt in range(attempts):
            self._retry_attempts += 1
            try:
                resp = await self._request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=timeout,
                )
            except Exception as exc:  # noqa: BLE001
                # Network / timeout / programming error — treat as failure
                # and back off like a 5xx.
                last_exc = exc
                self._record_failure()
                if self._circuit_is_open():
                    # Another concurrent call may have tripped the breaker
                    # while we were awaiting; bail out.
                    raise CircuitOpenError(
                        f"circuit_open_during_retry: provider={self.provider_name} "
                        f"exc={type(exc).__name__}: {exc}"
                    ) from exc
                if attempt < attempts - 1:
                    backoff = self._retry_5xx_base_backoff * (2 ** attempt)
                    await asyncio.sleep(backoff)
                continue

            last_response = resp
            if resp.is_success():
                self._record_success()
                self._retry_successes += 1
                return resp

            # Non-2xx: classify and either retry or return.
            if resp.status_code == 429:
                # Honour Retry-After if present, else use default.
                retry_after_raw = (resp.headers or {}).get("Retry-After")
                try:
                    sleep_for = float(retry_after_raw) if retry_after_raw else self._retry_429_default
                except (TypeError, ValueError):
                    sleep_for = self._retry_429_default
                self._record_failure()
                if attempt < attempts - 1:
                    await asyncio.sleep(sleep_for)
                continue
            if 500 <= resp.status_code < 600:
                backoff = self._retry_5xx_base_backoff * (2 ** attempt)
                self._record_failure()
                if attempt < attempts - 1:
                    await asyncio.sleep(backoff)
                continue
            # 4xx other than 429: caller error, do not retry.
            return resp

        # All attempts exhausted.  If we still hold a response, return it
        # (the caller's parsing layer will see the final status).  Otherwise
        # re-raise the last exception so the caller can distinguish "all
        # attempts raised" from "all attempts returned a non-2xx".
        if last_response is not None:
            return last_response
        assert last_exc is not None
        raise last_exc

    def retry_stats(self) -> Dict[str, int]:
        """Return current retry / circuit-breaker state for observability."""
        return {
            "consecutive_failures": int(self._consecutive_failures),
            "circuit_open": 1 if self._circuit_is_open() else 0,
            "circuit_open_until_epoch": int(self._circuit_open_until),
            "attempts": int(self._retry_attempts),
            "successes": int(self._retry_successes),
            "circuit_trips": int(self._retry_circuit_trips),
        }

    # -- subclasses override these ------------------------------------------

    @abc.abstractmethod
    async def invoke(self, prompt: str, params: InvokeParams) -> ProviderResponse:
        """Run a single chat completion."""

    @abc.abstractmethod
    async def list_models(self) -> List[str]:
        """Return the curated list of model ids this provider supports."""

    # -- defaults / hooks ---------------------------------------------------

    def default_base_url(self) -> str:
        return ""

    def has_credentials(self) -> bool:
        return bool(self.api_key)

    async def health_check(self) -> HealthStatus:
        """Default health probe: confirm we can list models.

        Subclasses may override to send a cheap request (e.g. ``GET /models``).
        """
        t0 = time.time()
        try:
            models = await self.list_models()
            latency = (time.time() - t0) * 1000.0
            return HealthStatus(
                status="ok" if models else "error",
                provider=self.provider_name,
                latency_ms=round(latency, 1),
                model=models[0] if models else "",
            )
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(
                status="error",
                provider=self.provider_name,
                latency_ms=round((time.time() - t0) * 1000.0, 1),
                error=f"{type(exc).__name__}: {exc}",
            )

    async def invoke_stream(
        self, prompt: str, params: InvokeParams,
    ) -> AsyncIterator[ProviderChunk]:
        """Default streaming impl: call invoke() then yield one final chunk.

        Subclasses override for real SSE / chunked HTTP.
        """
        resp = await self.invoke(prompt, params)
        yield ProviderChunk(
            delta=resp.content,
            done=True,
            finish_reason="stop" if resp.success else "error",
            model=resp.model,
            provider=self.provider_name,
        )


__all__ = [
    "BaseProvider",
    "InvokeParams",
    "ProviderResponse",
    "ProviderChunk",
    "HealthStatus",
    # P21 P2 P2: retry / circuit-breaker plumbing
    "CircuitOpenError",
    "_ProviderResponse",
]