"""Shared base helpers for 17 crawl skills.

All 17 crawl skills (Reddit / Twitter / YouTube / TikTok / Instagram /
Pinterest / Tumblr / Flickr / Unsplash / 500px / DeviantArt / Behance /
Dribbble / ArtStation / Pixiv / Danbooru / Gelbooru) follow the same
shape:

    async def crawl_<site>(input: SkillInput) -> SkillOutput

The Skill contract comes from ``backend.skills.legacy`` (dataclass pair).
The site-specific request/response payload is modelled as Pydantic
schemas (``BaseModel`` subclasses) so they are trivially serialisable
and editable.

This base module centralises:
  * A common metadata block (timestamp / source / confidence)
  * An offline mock dispatcher (``_OFFLINE_FIXTURES`` registry)
  * A ``fetch_or_mock`` helper wrapping ``httpx.AsyncClient`` with
    a hard 5 s timeout + automatic fallback to the mock when the
    network is unavailable.
  * A ``to_skill_output`` helper that wraps a Pydantic model in a
    SkillOutput with the metadata block attached.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel

from backend.skills.legacy import SkillInput, SkillOutput

# P21 P2 P4 (R2 N8): unified metadata envelope — single source of truth for
# ``result`` + ``metadata`` shape across all 4 imdf skill base files.
from backend.imdf.skills._envelope import make_envelope  # noqa: E402

logger = logging.getLogger(__name__)


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
    "imdf_crawl_retry_state", default=_RetryState()
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
    attempt count in ``_RetryState`` so ``build_metadata`` can surface
    ``retry_count`` in metadata.
    """
    if exceptions is None:
        exceptions = (httpx.TimeoutException, httpx.NetworkError, OSError)

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


# ---------------------------------------------------------------------------
# Network availability probe (cheap, no DNS, just socket reach test)
# ---------------------------------------------------------------------------

_DEFAULT_PROBE_HOST = "1.1.1.1"
_DEFAULT_PROBE_PORT = 443
_NETWORK_OK: Optional[bool] = None


def is_network_available(host: str = _DEFAULT_PROBE_HOST,
                        port: int = _DEFAULT_PROBE_PORT,
                        timeout: float = 1.0) -> bool:
    """Return ``True`` if a TCP socket can be opened to ``host:port``.

    Used to short-circuit crawlers when the host runs offline (CI,
    air-gapped build agents). Result is cached for the lifetime of the
    process because the network state does not flip rapidly inside one
    skill invocation.
    """
    global _NETWORK_OK
    if _NETWORK_OK is not None:
        return _NETWORK_OK
    try:
        with socket.create_connection((host, port), timeout=timeout):
            _NETWORK_OK = True
    except OSError:
        _NETWORK_OK = False
    return _NETWORK_OK


def reset_network_probe() -> None:
    """Clear the network probe cache (for tests)."""
    global _NETWORK_OK
    _NETWORK_OK = None


# ---------------------------------------------------------------------------
# Offline mock registry
# ---------------------------------------------------------------------------

# Each crawler registers a callable that produces a list[dict] of mock
# items given the request query.  This makes every skill "work in
# offline mode" as required by the task spec.
_OFFLINE_FIXTURES: Dict[str, Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = {}


def register_offline_fixture(
    skill_id: str,
) -> Callable[[Callable[[Dict[str, Any]], List[Dict[str, Any]]]],
              Callable[[Dict[str, Any]], List[Dict[str, Any]]]]:
    """Decorator — registers a fixture builder for ``skill_id``."""

    def decorator(
        fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
    ) -> Callable[[Dict[str, Any]], List[Dict[str, Any]]]:
        _OFFLINE_FIXTURES[skill_id] = fn
        return fn

    return decorator


def get_offline_fixture(
    skill_id: str,
) -> Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]]:
    return _OFFLINE_FIXTURES.get(skill_id)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def build_metadata(skill_id: str,
                   query: Dict[str, Any],
                   extra: Optional[Dict[str, Any]] = None,
                   confidence: float = 0.85,
                   source: str = "live_api",
                   elapsed_ms: float = 0.0) -> Dict[str, Any]:
    """Standard metadata block injected into every SkillOutput.

    P21 P3 N3+N4: ``retry_count`` (from the ``retry`` decorator) and
    ``token_count`` (from a future LLM call site) are auto-populated from
    the per-call ``_RetryState`` unless the caller overrides them via
    ``extra``. This guarantees the fields exist on every SkillOutput.

    P21 P2 P4 (R2 N8): ``elapsed_ms`` is now a first-class keyword
    parameter forwarded to :func:`make_envelope` (the unified envelope
    builder) so all 4 imdf bases produce the same ``metadata`` shape.
    Callers can use
    :class:`backend.imdf.skills._envelope.ElapsedTimer` to record
    wall-clock duration, or pass ``t0`` deltas they already track.
    """
    state = get_retry_state()
    extras = dict(extra or {})
    # Pop canonical fields so they go through make_envelope; everything
    # else (e.g. "query", custom per-skill bookkeeping) is preserved.
    confidence_v = float(extras.pop("confidence", confidence))
    source_v = extras.pop("source", source)
    cost_usd = float(extras.pop("cost_usd", 0.0))
    retry_count = int(extras.pop("retry_count", max(0, state.attempts - 1)))
    token_count = int(extras.pop(
        "token_count", state.input_tokens + state.output_tokens,
    ))
    input_tokens = int(extras.pop("input_tokens", state.input_tokens))
    output_tokens = int(extras.pop("output_tokens", state.output_tokens))
    # Crawl-specific: preserve the query dict verbatim (P3 contract).
    extras.setdefault("query", dict(query))
    extras.setdefault("skill_id", skill_id)
    extras["confidence"] = round(confidence_v, 4)
    envelope = make_envelope(
        result=extras.pop("result", None),
        elapsed_ms=elapsed_ms,
        source=source_v,
        retry_count=retry_count,
        token_count=token_count,
        cost_usd=cost_usd,
        extra=extras,
    )
    md = envelope["metadata"]
    # Restore per-call input_tokens / output_tokens if the caller didn't
    # override (preserves P21 P3 N4 contract).
    md.setdefault("input_tokens", input_tokens)
    md.setdefault("output_tokens", output_tokens)
    return md


# ---------------------------------------------------------------------------
# fetch_or_mock
# ---------------------------------------------------------------------------

@retry(max_attempts=3, backoff=0.5)
async def _fetch_inner(
    skill_id: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Inner fetch — only raises on network/timeout errors. Wrapped by retry."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            params=params,
            headers=headers,
            json=json_body,
        )
        response.raise_for_status()
        data = response.json() if response.headers.get(
            "content-type", "").startswith("application/json") else {}
        items = _extract_items(data, skill_id)
        return {
            "items": items,
            "source": "live_api",
            "ok": True,
            "error": "",
            "url": str(response.url),
            "raw_status": response.status_code,
        }


async def fetch_or_mock(
    skill_id: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
    offline: Optional[bool] = None,
) -> Dict[str, Any]:
    """Fetch ``url`` with httpx; fall back to offline mock on failure.

    P21 P3 N3: live fetches are retried up to 3× on transient network /
    timeout errors before falling back to the offline mock. The number of
    retries that actually fired is exposed in the return dict as
    ``retry_count`` (read from the per-call ``_RetryState``).

    Returns a dict with at least:
        * ``items``       : list[dict] of normalised records
        * ``source``      : "live_api" | "offline_mock"
        * ``ok``          : True on live fetch, False on mock
        * ``error``       : error string (empty on success)
        * ``retry_count`` : int — number of retries before success/fallback
    """
    query = dict(params or json_body or {})
    should_offline = (
        offline if offline is not None else not is_network_available()
    )

    if should_offline:
        items = _run_fixture(skill_id, query)
        return {
            "items": items,
            "source": "offline_mock",
            "ok": False,
            "error": "network_unavailable",
            "url": url,
            "retry_count": max(0, get_retry_state().attempts - 1),
        }

    try:
        result = await _fetch_inner(
            skill_id, url,
            params=params, headers=headers, method=method,
            json_body=json_body, timeout=timeout,
        )
        result["retry_count"] = max(0, get_retry_state().attempts - 1)
        return result
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("[%s] live fetch failed after retries, falling back to mock: %s",
                       skill_id, exc)
        items = _run_fixture(skill_id, query)
        return {
            "items": items,
            "source": "offline_mock",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "url": url,
            "retry_count": max(0, get_retry_state().attempts - 1),
        }


def _run_fixture(skill_id: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
    fn = _OFFLINE_FIXTURES.get(skill_id)
    if fn is None:
        return []
    try:
        return list(fn(query))
    except Exception as exc:  # pragma: no cover
        logger.error("[%s] fixture raised: %s", skill_id, exc)
        return []


def _extract_items(data: Any, skill_id: str) -> List[Dict[str, Any]]:
    """Best-effort: locate the item list inside an arbitrary API response.

    Different providers wrap their arrays differently
    (``{"data": [...]}`` vs ``{"results": [...]}`` vs top-level list).
    Try a handful of conventions before giving up.
    """
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("data", "results", "items", "posts", "tweets",
                "videos", "images", "pins", "blogs", "entries"):
        if key in data and isinstance(data[key], list):
            return [d for d in data[key] if isinstance(d, dict)]
    return []


# ---------------------------------------------------------------------------
# to_skill_output
# ---------------------------------------------------------------------------

def to_skill_output(
    skill_id: str,
    response_model: BaseModel,
    query: Dict[str, Any],
    *,
    source: str = "live_api",
    confidence: float = 0.85,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> SkillOutput:
    """Wrap a Pydantic response model in a SkillOutput with metadata."""
    meta = build_metadata(skill_id, query, extra=extra_meta,
                          confidence=confidence, source=source)
    return SkillOutput(
        success=True,
        result=response_model.model_dump(),
        error="",
        metadata=meta,
    )


def error_output(skill_id: str, message: str,
                 query: Optional[Dict[str, Any]] = None) -> SkillOutput:
    return SkillOutput(
        success=False,
        result=None,
        error=message,
        metadata=build_metadata(skill_id, dict(query or {}), confidence=0.0),
    )


# ---------------------------------------------------------------------------
# Pydantic convenience mixins
# ---------------------------------------------------------------------------

class TimestampedModel(BaseModel):
    """Common mixin: every record has an ``id`` and ``fetched_at``."""
    id: str
    fetched_at: str = ""

    def touch(self) -> None:
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()


__all__ = [
    "TimestampedModel",
    "build_metadata",
    "error_output",
    "fetch_or_mock",
    "get_offline_fixture",
    "is_network_available",
    "register_offline_fixture",
    "reset_network_probe",
    "to_skill_output",
    # P21 P3 N3+N4
    "retry",
    "get_retry_state",
    "reset_retry_state",
]