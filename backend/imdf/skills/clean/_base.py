"""Clean skills shared base.

Provides:
  * Pydantic-friendly SkillInput / SkillOutput wrappers (re-export of
    backend.skills legacy dataclasses)
  * `clean_skill(...)` decorator-style factory used by every clean/* skill
    so each module only declares its parameters + handler.
  * `safe_httpx_call(...)`  — uniform httpx wrapper with offline fallback.
  * ``retry(...)`` decorator + ``RetryContext`` token/cost tracking (P21 P3 N3+N4).

Per-skill modules remain independently importable and don't depend on each
other.  The shared base only normalises I/O contracts and HTTP behaviour.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

try:  # httpx is part of requirements.txt but guard for offline envs
    import httpx  # type: ignore
except Exception:  # pragma: no cover - tolerate missing optional dep
    httpx = None  # type: ignore

# Re-export of project-wide skill contracts so per-skill modules can use
# ``from ._base import SkillInput, SkillOutput``.
from backend.skills import SkillInput, SkillOutput  # type: ignore

# P21 P2 P4 (R2 N8): unified metadata envelope — single source of truth for
# ``result`` + ``metadata`` shape across all 4 imdf skill base files.
from backend.imdf.skills._envelope import make_envelope  # noqa: E402

logger = logging.getLogger("imdf.skills.clean")


# ---------------------------------------------------------------------------
# Retry + cost/token tracking (P21 P3 N3 + N4)
# ---------------------------------------------------------------------------
# We deliberately do NOT pull in ``tenacity`` to avoid a new dep. The pattern
# below is the project's house style: a small stdlib-only decorator plus a
# thread-local context that ``make_metadata`` reads to populate
# ``retry_count`` / ``token_count`` fields.
# ---------------------------------------------------------------------------
import contextvars  # noqa: E402  (kept near retry so the file is readable)


class _RetryState:
    """Mutable counters carried in a contextvar so they survive across
    async/await boundaries without leaking between concurrent calls."""

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
    "imdf_clean_retry_state", default=_RetryState()
)


def get_retry_state() -> _RetryState:
    """Return the per-call retry/usage state. The contextvar default keeps
    the no-decorator path working: counters stay at 0."""
    return _current_retry_state.get()


def reset_retry_state() -> _RetryState:
    """Hard-reset the current state's counters. Useful in tests and at the
    start of a fresh skill invocation."""
    state = _current_retry_state.get()
    state.attempts = 0
    state.input_tokens = 0
    state.output_tokens = 0
    return state


def retry(max_attempts: int = 3, backoff: float = 0.5,
          exceptions: Any = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Async retry decorator (P21 P3 N3) — stdlib only, no tenacity.

    Retries up to ``max_attempts`` times, sleeping ``backoff * 2**attempt``
    seconds between attempts. Records the actual attempt count in the
    per-call ``_RetryState`` (used by ``make_metadata`` to expose
    ``retry_count``).

    Args:
        max_attempts: total number of tries (default 3).
        backoff: base delay in seconds; doubled on each retry.
        exceptions: optional tuple of exception classes to retry on.
            Defaults to ``(httpx.TimeoutException, httpx.NetworkError)`` if
            httpx is available, else ``(Exception,)``.
    """
    if exceptions is None:
        if httpx is not None:
            exceptions = (httpx.TimeoutException, httpx.NetworkError)
        else:  # pragma: no cover - httpx missing
            exceptions = (Exception,)

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
            assert last is not None  # for type-checkers
            raise last

        return wrapper

    return deco


# ---------------------------------------------------------------------------
# Pydantic models — used inside individual modules for input validation.
# Kept here as a lazy import so that callers without pydantic still work.
# ---------------------------------------------------------------------------
def _pyd():
    """Lazy pydantic import — fail soft at runtime if not available."""
    try:
        from pydantic import BaseModel, Field  # type: ignore

        return BaseModel, Field
    except Exception:
        return None, None


def make_input_model(name: str, fields: Dict[str, Any]):
    """Build a Pydantic BaseModel with the given field definitions.

    ``fields`` is ``{field_name: (python_type, default, description)}``.
    """
    BaseModel, Field = _pyd()
    if BaseModel is None:
        return None  # tolerate environments without pydantic
    attrs: Dict[str, Any] = {"__doc__": f"Input schema for {name}"}
    for fname, spec in fields.items():
        py_type, default, desc = spec
        attrs[fname] = Field(default=default, description=desc or "")
    Model = type(name, (BaseModel,), attrs)
    return Model


def make_output_model(name: str, fields: Dict[str, Any]):
    """Same as ``make_input_model`` but for output schemas (defaults default to None)."""
    return make_input_model(name, fields)


# ---------------------------------------------------------------------------
# HTTP helper — uniform httpx + offline mock fallback (now retry-wrapped)
# ---------------------------------------------------------------------------
@retry(max_attempts=3, backoff=0.5)
async def _safe_httpx_call_inner(
    url: str,
    *,
    method: str = "POST",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
    mock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Inner httpx call — only raises network/timeout exceptions. The outer
    wrapper converts other failures to the offline fallback."""
    if httpx is None:
        return {"status": "offline", "data": mock or {}}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, json=payload, headers=headers or {})
        resp.raise_for_status()
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"raw": resp.text}
    return {"status": "ok", "data": data}


async def safe_httpx_call(
    url: str,
    *,
    method: str = "POST",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
    mock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Issue a JSON httpx request and return ``{"status": ..., "data": ...}``.

    Retries up to 3× on transient network/timeout errors (P21 P3 N3). After
    all retries fail or httpx is missing, falls back to ``mock`` (or empty
    dict) so skills remain importable in offline test environments.
    """
    try:
        return await _safe_httpx_call_inner(
            url, method=method, payload=payload, headers=headers,
            timeout=timeout, mock=mock,
        )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("clean_skill httpx failed after retries (%s); falling back to mock", exc)
        return {"status": "offline", "data": mock or {}, "error": str(exc)}
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("clean_skill httpx failed (%s); falling back to mock", exc)
        return {"status": "offline", "data": mock or {}, "error": str(exc)}


# ---------------------------------------------------------------------------
# Wrapping helper for clean/<name>.py modules
# ---------------------------------------------------------------------------
Handler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


def clean_skill(
    *,
    name: str,
    input_schema: Any,
    output_schema: Any,
    handler: Handler,
    category: str = "clean",
    description: str = "",
) -> Dict[str, Any]:
    """Return a metadata dict; the public async wrapper is generated in each
    module so that the function ``name`` is importable as required.

    Modules typically call this only for the side-effect of validating their
    schemas at import time.
    """
    return {
        "id": f"skill_{name}",
        "name": name,
        "category": category,
        "description": description or f"{name} ({category})",
        "input_schema": input_schema,
        "output_schema": output_schema,
        "handler": handler,
    }


def make_metadata(
    skill_id: str,
    name: str,
    *,
    elapsed_ms: float = 0.0,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a SkillOutput metadata dict — timestamp + source + confidence.

    P21 P3 N4: ``retry_count`` (from the ``retry`` decorator) and
    ``token_count`` (from a future LLM call site) are auto-populated from
    the per-call ``_RetryState`` unless the caller overrides them via
    ``extra``. This guarantees the fields exist on every SkillOutput
    even when no LLM was invoked.

    P21 P2 P4 (R2 N8): ``elapsed_ms`` is now a first-class keyword
    parameter forwarded to :func:`make_envelope` (the unified envelope
    builder) so all 4 imdf bases produce the same ``metadata`` shape.
    Callers can use
    :class:`backend.imdf.skills._envelope.ElapsedTimer` to record
    wall-clock duration, or pass ``t0`` deltas they already track.

    Returns
    -------
    dict
        A metadata dict that callers pass as ``metadata=make_metadata(...)``
        to a ``SkillOutput`` (or attach to a return envelope directly).
    """
    state = get_retry_state()
    source = extra.pop("source", "imdf.skills.clean")
    confidence = float(extra.pop("confidence", 1.0))
    cost_usd = float(extra.pop("cost_usd", 0.0))
    # Anything still in `extra` is preserved verbatim and merged after the
    # canonical fields (so per-skill keys win on collision).
    extra.setdefault("skill_id", skill_id)
    extra.setdefault("skill_name", name)
    extra["confidence"] = confidence
    envelope = make_envelope(
        result=extra.pop("result", None),
        elapsed_ms=elapsed_ms,
        source=source,
        retry_count=int(extra.pop("retry_count", max(0, state.attempts - 1))),
        token_count=int(extra.pop("token_count",
                                  state.input_tokens + state.output_tokens)),
        cost_usd=cost_usd,
        extra=extra,
    )
    # make_envelope already populated input_tokens/output_tokens via
    # the per-call state — restore them from state if the caller didn't
    # override (preserves P21 P3 N4 contract).
    md = envelope["metadata"]
    md.setdefault("input_tokens", state.input_tokens)
    md.setdefault("output_tokens", state.output_tokens)
    return md


def run_async(coro: Awaitable[Any]) -> Any:
    """Convenience wrapper for tests that need to call async handlers."""
    return asyncio.get_event_loop().run_until_complete(coro)


__all__ = [
    "SkillInput",
    "SkillOutput",
    "safe_httpx_call",
    "make_input_model",
    "make_output_model",
    "make_metadata",
    "clean_skill",
    "run_async",
    # P21 P3 N3+N4
    "retry",
    "get_retry_state",
    "reset_retry_state",
]
