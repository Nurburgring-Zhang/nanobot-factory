"""P6-Fix-B-3 / C7.6: Circuit breaker (CLOSED / OPEN / HALF_OPEN).

Classic three-state breaker with a sliding-window failure counter and
configurable recovery delay.  Used to short-circuit tool calls and
downstream service calls that have started failing en masse, preventing
cascading failures and giving the downstream a chance to recover.

State machine
-------------
::

    CLOSED ──(failures ≥ threshold)──▶ OPEN
       ▲                                │
       │                                │ (timeout_seconds elapsed)
       │                                ▼
       └──(success in probe)──── HALF_OPEN ──(failure in probe)──▶ OPEN

Design choices
--------------
* Thread-safe via a single ``threading.Lock`` — the critical section
  is tiny (state read / write + counter increment) so contention is
  negligible compared to the wrapped call.
* Async-friendly: use :func:`circuit_breaker` decorator on sync
  callables, or instantiate :class:`CircuitBreaker` and call
  :meth:`call` directly from async code with ``await asyncio.to_thread``.
* Failure classification: by default any exception counts as a failure.
  Pass ``expected_exception`` to count only specific error types
  (e.g. ``requests.RequestException``) — everything else propagates
  but does NOT trip the breaker.
"""
from __future__ import annotations

import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the breaker is OPEN."""

    def __init__(self, name: str, retry_after: float):
        super().__init__(
            f"circuit_breaker[{name}] is OPEN; retry after {retry_after:.2f}s"
        )
        self.name = name
        self.retry_after = float(retry_after)


@dataclass
class CircuitBreaker:
    """Classic three-state circuit breaker.

    Parameters
    ----------
    name : str
        Identifier for logs / errors.
    failure_threshold : int
        Number of consecutive failures (within ``failure_window_s``) that
        flip the breaker from CLOSED to OPEN.  Default 5.
    failure_window_s : float
        Sliding window in seconds — failures older than this are
        forgotten.  Default 60s.
    recovery_timeout_s : float
        Time the breaker stays OPEN before flipping to HALF_OPEN.
        Default 30s.
    half_open_max_calls : int
        Number of probe calls allowed in HALF_OPEN.  First success
        closes; any failure re-opens.  Default 1.
    expected_exception : tuple of exception types, optional
        Only count these exceptions as failures.  When ``None`` every
        exception is a failure.
    clock : callable, optional
        Override for testing — returns monotonic time.
    """

    name: str = "default"
    failure_threshold: int = 5
    failure_window_s: float = 60.0
    recovery_timeout_s: float = 30.0
    half_open_max_calls: int = 1
    expected_exception: Optional[Tuple[Type[BaseException], ...]] = None
    clock: Callable[[], float] = time.monotonic

    # Runtime state
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: list = field(default_factory=list, init=False)
    _opened_at: Optional[float] = field(default=None, init=False)
    _half_open_in_flight: int = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self.state == CircuitState.HALF_OPEN

    def stats(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failures_in_window": len(self._failures),
                "opened_at": self._opened_at,
                "half_open_in_flight": self._half_open_in_flight,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_s": self.recovery_timeout_s,
            }

    # ------------------------------------------------------------------
    # Core: pre-call gate + post-call recording
    # ------------------------------------------------------------------
    def _before_call(self) -> None:
        """Gate the call.  Raises :class:`CircuitOpenError` when rejected."""
        with self._lock:
            now = self.clock()
            if self.state == CircuitState.OPEN:
                assert self._opened_at is not None
                if now - self._opened_at >= self.recovery_timeout_s:
                    # Transition OPEN → HALF_OPEN
                    self.state = CircuitState.HALF_OPEN
                    self._half_open_in_flight = 0
                    logger.info("circuit_breaker[%s] OPEN → HALF_OPEN", self.name)
                else:
                    raise CircuitOpenError(self.name, self.recovery_timeout_s - (now - self._opened_at))
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self.half_open_max_calls:
                    raise CircuitOpenError(self.name, self.recovery_timeout_s)
                self._half_open_in_flight += 1

    def _after_call(self, exc: Optional[BaseException]) -> None:
        """Update breaker state after the wrapped call returns / raises."""
        with self._lock:
            now = self.clock()
            # Trim sliding window
            cutoff = now - self.failure_window_s
            self._failures = [t for t in self._failures if t >= cutoff]
            if exc is None:
                # Success
                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.CLOSED
                    self._opened_at = None
                    self._half_open_in_flight = 0
                    self._failures.clear()
                    logger.info("circuit_breaker[%s] HALF_OPEN → CLOSED", self.name)
                elif self.state == CircuitState.CLOSED:
                    self._failures.clear()
                return
            # Failure
            counts = self._is_counted_failure(exc)
            if counts:
                self._failures.append(now)
            if self.state == CircuitState.HALF_OPEN:
                # Probe failed → back to OPEN
                self.state = CircuitState.OPEN
                self._opened_at = now
                self._half_open_in_flight = 0
                logger.warning("circuit_breaker[%s] HALF_OPEN → OPEN (probe failed)", self.name)
                return
            if self.state == CircuitState.CLOSED:
                if counts and len(self._failures) >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self._opened_at = now
                    logger.warning(
                        "circuit_breaker[%s] CLOSED → OPEN (%d failures in %.1fs)",
                        self.name, len(self._failures), self.failure_window_s,
                    )

    def _is_counted_failure(self, exc: BaseException) -> bool:
        if self.expected_exception is None:
            return True
        return isinstance(exc, self.expected_exception)

    # ------------------------------------------------------------------
    # Public call wrapper
    # ------------------------------------------------------------------
    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``fn(*args, **kwargs)`` under the breaker."""
        self._before_call()
        exc: Optional[BaseException] = None
        try:
            return fn(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001
            exc = e
            raise
        finally:
            try:
                self._after_call(exc)
            except Exception as cb_exc:  # noqa: BLE001
                # Never let bookkeeping break the wrapped call.
                logger.warning("circuit_breaker[%s] bookkeeping error: %s", self.name, cb_exc)

    def reset(self) -> None:
        """Force the breaker back to CLOSED — for tests / ops."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self._failures.clear()
            self._opened_at = None
            self._half_open_in_flight = 0


def circuit_breaker(
    name: str = "default",
    *,
    failure_threshold: int = 5,
    failure_window_s: float = 60.0,
    recovery_timeout_s: float = 30.0,
    half_open_max_calls: int = 1,
    expected_exception: Optional[Tuple[Type[BaseException], ...]] = None,
) -> Callable[[F], F]:
    """Decorator form of :class:`CircuitBreaker`.

    Usage::

        @circuit_breaker("downstream_api", failure_threshold=3, recovery_timeout_s=10)
        def call_downstream(x): ...
    """
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        failure_window_s=failure_window_s,
        recovery_timeout_s=recovery_timeout_s,
        half_open_max_calls=half_open_max_calls,
        expected_exception=expected_exception,
    )

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return breaker.call(fn, *args, **kwargs)
        wrapper.__circuit_breaker__ = breaker  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
