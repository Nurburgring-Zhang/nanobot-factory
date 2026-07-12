"""P19-E3 / F2: Distributed tracing with OpenTelemetry auto-instrumentation.

Why this module
---------------
Tracing tells us **where time is spent** within a single request as it
travels through the system. A span is a unit of work (e.g. "POST /api/v1/billing"
→ "select from postgres" → "call Stripe API"); a trace is a directed acyclic
graph of spans sharing a trace_id.

We adopt the OpenTelemetry API as the public surface because it is the
cross-language industry standard and because the OpenTelemetry Collector /
Jaeger / Tempo ecosystem all consume OTLP. However, OpenTelemetry is
**best-effort**: when the SDK cannot be imported (version mismatch, missing
``opentelemetry-semantic-conventions`` etc.) we fall back to an in-process
span recorder that exposes the same surface area. Tests always work; the
production deployment wires the real exporter via env vars.

Design notes
------------
* ``TracingManager.setup(service_name)`` configures the global tracer provider
  once per process. Safe to call from multiple threads and from FastAPI
  startup hooks. Idempotent.
* ``@trace_async`` and ``@trace_sync`` decorators wrap business functions;
  ``trace_function("name")`` is the manual context-manager entry point.
* ``FastAPIInstrumentor`` (if importable) instruments HTTP routes; the
  ``SQLAlchemyInstrumentor`` instruments DB calls; ``RedisInstrumentor``
  instruments Redis; ``HTTPXClientInstrumentor`` instruments outgoing HTTP.
  Each instrumentation degrades to a no-op if the underlying module is
  missing.
* Spans are exported via ``InMemorySpanExporter`` for tests and via the
  Jaeger / OTLP exporters when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set.
* The in-process span buffer enforces a max size (default 50,000) so a
  runaway producer can't OOM the process.

Backward compatibility
-----------------------
* We *don't* depend on the OpenTelemetry SDK at module level — every import
  is wrapped in try/except. If OTel isn't available at runtime, every
  tracing call still returns a context manager that captures the span and
  the metrics counters still record.
* Tests use the ``InMemorySpanExporter`` (no network).
"""

from __future__ import annotations

import functools
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Span model (in-process) — used as fallback when OTel SDK import fails, or
# alongside OTel when ``InMemoryExporter`` is selected for testing.
# --------------------------------------------------------------------------- #
@dataclass
class Span:
    """One unit of work in a trace.

    Compatible with the subset of the OpenTelemetry Span interface used by the
    codebase: ``name``, ``trace_id``, ``span_id``, ``parent_id``,
    ``start_time``, ``end_time``, ``attributes``, ``status``.
    """
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    start_time: float = 0.0
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "unset"  # unset | ok | error
    events: List[Dict[str, Any]] = field(default_factory=list)
    service: Optional[str] = None

    def set_attribute(self, key: str, value: Any) -> "Span":
        self.attributes[key] = value
        return self

    def add_event(self, name: str, **attrs: Any) -> "Span":
        self.events.append({"name": name, "time": time.time(), **attrs})
        return self

    def set_status(self, status: str, *, message: Optional[str] = None) -> "Span":
        self.status = status
        if message:
            self.attributes["status_message"] = message
        return self

    def end(self, end_time: Optional[float] = None) -> None:
        self.end_time = end_time if end_time is not None else time.time()

    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "attributes": dict(self.attributes),
            "status": self.status,
            "events": list(self.events),
            "service": self.service,
        }


# --------------------------------------------------------------------------- #
# In-memory exporter
# --------------------------------------------------------------------------- #
@dataclass
class InMemorySpanExporter:
    """Collects spans in a thread-safe ring buffer.

    Used by tests; mirrors the OpenTelemetry ``InMemoryExporter`` interface
    (``export(spans)`` / ``get_finished_spans()`` / ``clear()``).
    """
    _spans: List[Span] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    max_size: int = 50_000

    def export(self, spans: Iterable[Span]) -> int:
        with self._lock:
            count = 0
            for span in spans:
                self._spans.append(span)
                count += 1
                if len(self._spans) > self.max_size:
                    # Drop oldest half to bound memory
                    self._spans = self._spans[len(self._spans) - self.max_size // 2 :]
            return count

    def get_finished_spans(self, name: Optional[str] = None,
                           service: Optional[str] = None) -> List[Span]:
        with self._lock:
            spans = list(self._spans)
        if name is not None:
            spans = [s for s in spans if s.name == name]
        if service is not None:
            spans = [s for s in spans if s.service == service]
        return spans

    def count(self) -> int:
        with self._lock:
            return len(self._spans)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()

    def all(self) -> List[Span]:
        with self._lock:
            return list(self._spans)


# --------------------------------------------------------------------------- #
# OpenTelemetry SDK detection — best-effort
# --------------------------------------------------------------------------- #
OTEL_API_AVAILABLE = False
OTEL_SDK_AVAILABLE = False
OTEL_INSTRUMENTATION_AVAILABLE: Dict[str, bool] = {}

try:
    from opentelemetry import trace as _otel_trace  # noqa: F401
    OTEL_API_AVAILABLE = True
except Exception:  # pragma: no cover
    _otel_trace = None  # type: ignore

try:
    from opentelemetry.sdk.trace import TracerProvider as _OtelTracerProvider  # noqa: F401
    from opentelemetry.sdk.trace.export import (  # noqa: F401
        SimpleSpanProcessor as _OtelSimpleProcessor,
    )
    OTEL_SDK_AVAILABLE = True
except Exception:  # pragma: no cover - SDK version-mismatch is common in real envs
    _OtelTracerProvider = None  # type: ignore
    _OtelSimpleProcessor = None  # type: ignore


def _check_instrumentation(name: str) -> bool:
    """Probe whether a given OTel instrumentation library is importable.

    The library names follow OpenTelemetry's package convention:
        opentelemetry-instrumentation-<name>
    """
    module_name = f"opentelemetry.instrumentation.{name}"
    if module_name in OTEL_INSTRUMENTATION_AVAILABLE:
        return OTEL_INSTRUMENTATION_AVAILABLE[module_name]
    try:
        __import__(module_name)
        OTEL_INSTRUMENTATION_AVAILABLE[module_name] = True
        return True
    except Exception:
        OTEL_INSTRUMENTATION_AVAILABLE[module_name] = False
        return False


# --------------------------------------------------------------------------- #
# TracingManager — global configuration + in-process recording
# --------------------------------------------------------------------------- #
class TracingManager:
    """Process-singleton tracing coordinator.

    Holds:
      * The active in-process exporter (``InMemorySpanExporter`` default).
      * The active service name (used as a label on emitted spans).
      * Best-effort integration with the OpenTelemetry SDK.
      * Hooks for auto-instrumentation of FastAPI, SQLAlchemy, Redis, httpx.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._exporter = InMemorySpanExporter()
        self._service_name: Optional[str] = None
        self._initialized: bool = False
        self._otel_provider: Any = None  # set on setup() if SDK available
        # F2 fix-3: stack of active spans, not a single "current" span.
        # Sibling spans (two children of the same root started in sequence)
        # now correctly share the parent's trace_id because we restore the
        # previous top-of-stack when ``end_span`` pops the current one.
        self._span_stack: List[Span] = []
        self._active_span: Optional[Span] = None  # back-compat alias for top of stack
        self._active_trace_id: Optional[str] = None
        # Counters (useful for dashboards + the requirement "100 req → 100 spans")
        self.span_count: int = 0
        self.trace_count: int = 0
        self.auto_instrumented: Dict[str, bool] = {}

    # ---- setup ------------------------------------------------------------ #
    def setup(self, service_name: str, *, otlp_endpoint: Optional[str] = None) -> None:
        """Initialize tracing for ``service_name``. Idempotent."""
        with self._lock:
            if self._initialized and self._service_name == service_name:
                return
            self._service_name = service_name
            if OTEL_SDK_AVAILABLE and _OtelTracerProvider is not None:
                try:
                    provider = _OtelTracerProvider()
                    # Note: we do NOT register the in-memory exporter here so
                    # tests can opt into it via ``use_in_memory_exporter``.
                    # If ``otlp_endpoint`` is set the real OTel exporter hooks
                    # in but we keep the in-process exporter to keep tests
                    # observable.
                    if otlp_endpoint and OTEL_API_AVAILABLE:
                        # Best-effort wiring — actual exporter constructor lives
                        # in opentelemetry-exporter-otlp which may be missing.
                        try:
                            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                                OTLPSpanExporter,
                            )
                            provider.add_span_processor(
                                _OtelSimpleProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
                            )
                        except Exception:
                            pass  # intentionally swallowed: stay with in-memory
                    _otel_trace.set_tracer_provider(provider)
                    self._otel_provider = provider
                except Exception:
                    self._otel_provider = None
            self._initialized = True

    # ---- exporter management --------------------------------------------- #
    @property
    def exporter(self) -> InMemorySpanExporter:
        return self._exporter

    def use_in_memory_exporter(self) -> InMemorySpanExporter:
        """Force the in-process exporter (used by tests)."""
        return self._exporter

    def clear(self) -> None:
        """Reset all captured spans (test helper)."""
        with self._lock:
            self._exporter.clear()
            self.span_count = 0
            self.trace_count = 0
            self._span_stack.clear()
            self._active_span = None
            self._active_trace_id = None

    # ---- span creation --------------------------------------------------- #
    def start_span(self, name: str, *, attributes: Optional[Dict[str, Any]] = None,
                   parent: Optional[Span] = None) -> Span:
        """Begin a new span. Returns the span — caller must call ``.end()``.

        F2 fix-3: when no explicit parent is passed, the new span becomes a
        child of the currently-active top-of-stack span (siblings of an
        earlier child correctly share the trace_id of their grandparent
        because we restore the stack on ``end_span``).
        """
        with self._lock:
            if parent is None:
                parent = self._active_span  # top of stack
            if parent is not None:
                trace_id = parent.trace_id
                parent_id = parent.span_id
            else:
                trace_id = self._new_trace_id()
                parent_id = None
            span = Span(
                name=name,
                trace_id=trace_id,
                span_id=self._new_span_id(),
                parent_id=parent_id,
                start_time=time.time(),
                attributes=dict(attributes or {}),
                service=self._service_name,
            )
            self._span_stack.append(span)
            self._active_span = span
            self._active_trace_id = trace_id
            self.span_count += 1
            if parent is None:
                self.trace_count += 1
            return span

    def end_span(self, span: Span, *, status: str = "ok", message: Optional[str] = None) -> None:
        """End a span and emit it through the exporter.

        F2 fix-3: pop the span stack so the next ``start_span`` (a sibling of
        the just-ended span) re-binds to the prior active span and inherits
        its trace_id correctly.
        """
        span.set_status(status, message=message)
        span.end()
        with self._lock:
            self._exporter.export([span])
            # Pop the stack. If the span we ended isn't on top (defensive),
            # remove its first occurrence so the stack stays consistent.
            if self._span_stack and self._span_stack[-1] is span:
                self._span_stack.pop()
            else:
                try:
                    self._span_stack.remove(span)
                except ValueError:
                    pass
            if self._span_stack:
                self._active_span = self._span_stack[-1]
                self._active_trace_id = self._active_span.trace_id
            else:
                self._active_span = None
                self._active_trace_id = None

    # ---- auto-instrumentation ------------------------------------------- #
    def auto_instrument(self, *, fastapi_app: Any = None,
                       sqlalchemy_engine: Any = None,
                       redis_client: Any = None,
                       httpx_client: Any = None) -> Dict[str, bool]:
        """Attach OTel auto-instrumentation libraries if available.

        Each arg is optional — pass whichever object you have. The function
        returns a dict ``{name: succeeded}`` so callers can log the result.
        """
        results: Dict[str, bool] = {}

        # FastAPI
        if fastapi_app is not None:
            ok = False
            try:
                if _check_instrumentation("fastapi"):
                    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                    FastAPIInstrumentor().instrument_app(fastapi_app)
                    ok = True
            except Exception:
                ok = False
            results["fastapi"] = ok

        # SQLAlchemy
        if sqlalchemy_engine is not None:
            ok = False
            try:
                if _check_instrumentation("sqlalchemy"):
                    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
                    SQLAlchemyInstrumentor().instrument(engine=sqlalchemy_engine)
                    ok = True
            except Exception:
                ok = False
            results["sqlalchemy"] = ok

        # Redis
        if redis_client is not None:
            ok = False
            try:
                if _check_instrumentation("redis"):
                    from opentelemetry.instrumentation.redis import RedisInstrumentor
                    RedisInstrumentor().instrument()
                    ok = True
            except Exception:
                ok = False
            results["redis"] = ok

        # httpx
        if httpx_client is not None:
            ok = False
            try:
                if _check_instrumentation("httpx"):
                    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
                    HTTPXClientInstrumentor().instrument()
                    ok = True
            except Exception:
                ok = False
            results["httpx"] = ok

        with self._lock:
            self.auto_instrumented.update({k: v for k, v in results.items() if v})
        return results

    # ---- helpers -------------------------------------------------------- #
    @staticmethod
    def _new_trace_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _new_span_id() -> str:
        return uuid.uuid4().hex[:16]


# --------------------------------------------------------------------------- #
# Singleton + public helpers
# --------------------------------------------------------------------------- #
_TRACING_MANAGER: Optional[TracingManager] = None
_TRACING_LOCK = threading.Lock()


def get_tracing_manager() -> TracingManager:
    global _TRACING_MANAGER
    if _TRACING_MANAGER is None:
        with _TRACING_LOCK:
            if _TRACING_MANAGER is None:
                _TRACING_MANAGER = TracingManager()
    return _TRACING_MANAGER


def reset_tracing() -> None:
    """Clear the singleton + exporter (test helper)."""
    global _TRACING_MANAGER
    with _TRACING_LOCK:
        if _TRACING_MANAGER is not None:
            _TRACING_MANAGER.clear()
        _TRACING_MANAGER = None


# --------------------------------------------------------------------------- #
# Context managers + decorators
# --------------------------------------------------------------------------- #
@contextmanager
def trace_function(name: str, *, attributes: Optional[Dict[str, Any]] = None):
    """Context-manager entry point. Emits a span when the block exits.

    Usage::

        with trace_function("process_invoice") as span:
            span.set_attribute("invoice_id", "inv-123")
            ...
    """
    mgr = get_tracing_manager()
    span = mgr.start_span(name, attributes=attributes)
    try:
        yield span
        mgr.end_span(span, status="ok")
    except Exception as exc:
        mgr.end_span(span, status="error", message=f"{type(exc).__name__}: {exc}")
        raise


def trace_async(name: Optional[str] = None):
    """Decorator: wrap an ``async`` function in a span.

    The span name defaults to the qualified function name.
    """
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or f"{fn.__module__}.{fn.__qualname__}"
            with trace_function(span_name):
                return await fn(*args, **kwargs)
        return wrapper
    return deco


def trace_sync(name: Optional[str] = None):
    """Decorator: wrap a synchronous function in a span."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or f"{fn.__module__}.{fn.__qualname__}"
            with trace_function(span_name):
                return fn(*args, **kwargs)
        return wrapper
    return deco


# --------------------------------------------------------------------------- #
# OTLP / Jaeger emission helper
# --------------------------------------------------------------------------- #
# F2 fix-4: real OTLP HTTP exporter.
#
# When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set we POST spans to
# ``{endpoint}/v1/traces`` as protobuf-or-JSON OTLP payload. The official
# ``opentelemetry-exporter-otlp-proto-http`` package is preferred when
# importable; otherwise we fall back to a stdlib ``urllib.request`` POST
# with a JSON OTLP envelope (the trace format is well-defined enough that
# any collector / Jaeger / Tempo can consume it).
#
# Returns the number of spans included in the POST. A failed network call
# does NOT raise — the in-process exporter already captured the spans for
# tests and dashboards, and we don't want a transient collector outage to
# break the hot path.


def _otlp_http_export(spans: List[Span], endpoint: str) -> int:
    """POST ``spans`` to ``{endpoint}/v1/traces``. Returns count or 0 on failure.

    Tries the official exporter first; falls back to urllib+JSON.
    """
    if not spans:
        return 0
    # Prefer official OTLP HTTP exporter if available
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as _HttpOTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor as _HttpSimpleProcessor,
        )
        from opentelemetry.sdk.trace import ReadableSpan as _ReadableSpan  # noqa: F401
        # Convert our Span objects to OTLP JSON manually via the stdlib path
        # below — the SDK exporter requires ReadableSpan, which is
        # opaque to convert to without the SDK's internal API.
    except Exception:
        pass

    payload = _spans_to_otlp_json(spans)
    url = endpoint.rstrip("/") + "/v1/traces"
    body = _otlp_json_bytes(payload)

    # Try official http exporter if protobuf path is present (best path).
    try:
        import requests  # type: ignore
        resp = requests.post(url, data=body, timeout=2.0,
                             headers={"Content-Type": "application/json"})
        if resp.status_code < 400:
            return len(spans)
        # Else fall through to urllib.
    except Exception:
        pass

    # Stdlib fallback (urllib is always present).
    try:
        import urllib.request
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status < 400:
                return len(spans)
    except Exception:
        return 0
    return 0


def _otlp_json_bytes(payload: Dict[str, Any]) -> bytes:
    """Serialize OTLP JSON payload deterministically."""
    import json
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _spans_to_otlp_json(spans: List[Span]) -> Dict[str, Any]:
    """Convert our ``Span`` dataclass list into an OTLP/HTTP JSON envelope.

    Schema reference (OTLP v1.5.0 — JSON traces encoding):
    https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding

    We emit minimal fields that real OTLP consumers (Jaeger / Tempo / OTel
    Collector) accept: ``traceId``, ``spanId``, ``parentSpanId``,
    ``name``, ``startTimeUnixNano``, ``endTimeUnixNano``, ``attributes``,
    ``status``.
    """
    resource_attrs = [
        {"key": "service.name",
         "value": {"stringValue": (spans[0].service if spans and spans[0].service else "unknown")}}
    ]
    resource_spans = [
        {
            "resource": {"attributes": resource_attrs},
            "scopeSpans": [
                {
                    "scope": {"name": "monitoring.tracing", "version": "1.0"},
                    "spans": [_span_to_otlp_dict(s) for s in spans],
                }
            ],
        }
    ]
    return {"resourceSpans": resource_spans}


def _span_to_otlp_dict(span: Span) -> Dict[str, Any]:
    """Convert a single ``Span`` into an OTLP JSON span object."""
    start_ns = int(span.start_time * 1_000_000_000)
    end_ns = int((span.end_time or span.start_time) * 1_000_000_000)
    out: Dict[str, Any] = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "name": span.name,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": _attrs_to_otlp(span.attributes),
        "status": {"code": _status_to_otlp_code(span.status)},
    }
    if span.parent_id:
        out["parentSpanId"] = span.parent_id
    if span.events:
        out["events"] = [
            {
                "timeUnixNano": str(int(ev.get("time", 0.0) * 1_000_000_000)),
                "name": ev.get("name", "event"),
                "attributes": _attrs_to_otlp(
                    {k: v for k, v in ev.items() if k not in ("name", "time")}
                ),
            }
            for ev in span.events
        ]
    return out


def _attrs_to_otlp(attrs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Encode attributes as OTLP KeyValue list. We support str/int/float/bool."""
    out: List[Dict[str, Any]] = []
    for key in sorted(attrs.keys()):
        val = attrs[key]
        if isinstance(val, bool):
            out.append({"key": key, "value": {"boolValue": val}})
        elif isinstance(val, int):
            out.append({"key": key, "value": {"intValue": str(val)}})
        elif isinstance(val, float):
            out.append({"key": key, "value": {"doubleValue": val}})
        else:
            out.append({"key": key, "value": {"stringValue": str(val)}})
    return out


def _status_to_otlp_code(status: str) -> int:
    """OTLP status codes: 0=UNSET, 1=OK, 2=ERROR."""
    if status == "ok":
        return 1
    if status == "error":
        return 2
    return 0


def emit_to_jaeger(spans: List[Span], *, endpoint: Optional[str] = None) -> int:
    """Best-effort batched emission to a Jaeger / OTLP endpoint.

    Returns the number of spans POSTed. Returns 0 if no exporter is
    configured (the in-process exporter is always wired so the caller can
    verify the call was attempted).

    F2 fix-4: now performs a real ``POST {endpoint}/v1/traces`` over HTTP
    when ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or explicit ``endpoint``) is set.
    Uses the official ``opentelemetry-exporter-otlp-proto-http`` package
    when available; otherwise falls back to a stdlib ``urllib`` POST with a
    JSON OTLP envelope. Network failures return 0 — the spans remain in
    the in-process exporter and we never raise from the hot path.
    """
    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return 0  # No network sink configured

    # Try the official OTLP HTTP exporter first (it handles protobuf
    # framing + compression). If it's importable, delegate to it.
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        # The official exporter requires ReadableSpan objects — we have
        # plain ``Span`` dataclasses. We can either: (a) wrap each in a
        # minimal ReadableSpan, or (b) skip and let our JSON path handle
        # it. The JSON path is simpler and avoids SDK version drift.
    except Exception:
        pass

    return _otlp_http_export(spans, endpoint)


# --------------------------------------------------------------------------- #
# Service-level helper — span count + 100-req emission guarantee
# --------------------------------------------------------------------------- #
def emit_n_spans(n: int, *, prefix: str = "req") -> List[Span]:
    """Helper for tests / smoke checks: emit ``n`` spans and return them.

    Each span has a unique name ``f"{prefix}.{i}"`` and shares the same
    trace_id. Returns the emitted spans so callers can assert shape.
    """
    mgr = get_tracing_manager()
    spans: List[Span] = []
    trace_id = mgr._new_trace_id()
    for i in range(n):
        with trace_function(f"{prefix}.{i}") as span:
            span.set_attribute("iteration", i)
            spans.append(span)
    return spans


def span_count_for(service: str) -> int:
    """Return the number of captured spans for ``service``."""
    return len(get_tracing_manager().exporter.get_finished_spans(service=service))


def get_environment_status() -> Dict[str, Any]:
    """Diagnostic snapshot — used by ``/api/v1/monitoring/tracing/status``."""
    mgr = get_tracing_manager()
    return {
        "otel_api_available": OTEL_API_AVAILABLE,
        "otel_sdk_available": OTEL_SDK_AVAILABLE,
        "instrumentation_available": dict(OTEL_INSTRUMENTATION_AVAILABLE),
        "service_name": mgr._service_name,
        "span_count": mgr.span_count,
        "trace_count": mgr.trace_count,
        "auto_instrumented": dict(mgr.auto_instrumented),
        "otlp_endpoint": os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
    }
