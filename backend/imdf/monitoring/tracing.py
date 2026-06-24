"""
P3-8-W2: OpenTelemetry distributed tracing setup
================================================

Initialises the global TracerProvider with OTLP gRPC exporter to Jaeger.
Safe no-op if OpenTelemetry packages are not installed.

Usage:
    from monitoring.tracing import setup_tracing, instrument_fastapi, get_tracer
    setup_tracing(service_name="imdf-main", otlp_endpoint="http://jaeger:4317")
    instrument_fastapi(app)
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("audit.chain.append"):
        ...

The exporter is configured to fail silently in dev (stdout span dump if
OTEL_EXPORTER=console). Production should set OTEL_EXPORTER_OTLP_ENDPOINT
to the Jaeger OTLP gRPC endpoint.
"""
from __future__ import annotations

import os
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level lock to prevent double-init under multi-worker uvicorn
_init_lock = threading.Lock()
_initialised = False

# Default service name (overridden by setup_tracing)
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "imdf-main")
OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://jaeger-collector.monitoring.svc.cluster.local:4317",
)

# OTel presence flags
HAS_OTEL_API = False
HAS_OTEL_SDK = False
HAS_OTEL_EXPORTER_OTLP = False
HAS_OTEL_FASTAPI = False
HAS_OTEL_SQLALCHEMY = False

try:
    from opentelemetry import trace  # noqa: F401
    from opentelemetry.trace import Tracer, Status, StatusCode, SpanKind  # noqa: F401
    HAS_OTEL_API = True
except ImportError:
    pass

try:
    from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: F401
    from opentelemetry.sdk.resources import Resource  # noqa: F401
    HAS_OTEL_SDK = True
except ImportError:
    pass

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: F401
    HAS_OTEL_EXPORTER_OTLP = True
except ImportError:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: F401
        HAS_OTEL_EXPORTER_OTLP = True
    except ImportError:
        pass

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: F401
    HAS_OTEL_FASTAPI = True
except ImportError:
    pass

try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: F401
    HAS_OTEL_SQLALCHEMY = True
except ImportError:
    pass


def setup_tracing(
    service_name: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
    sample_ratio: float = 0.1,
) -> bool:
    """Initialise the global TracerProvider with OTLP exporter to Jaeger.

    Idempotent: safe to call multiple times. Returns True on success.
    Falls back to a no-op tracer if OpenTelemetry packages are not installed.
    """
    global _initialised, SERVICE_NAME, OTLP_ENDPOINT
    svc = service_name or SERVICE_NAME
    ep = otlp_endpoint or OTLP_ENDPOINT

    with _init_lock:
        if _initialised:
            return True
        if not (HAS_OTEL_API and HAS_OTEL_SDK):
            logger.info("OpenTelemetry SDK not installed — tracing disabled")
            _initialised = True
            return False
        try:
            from opentelemetry import trace as _trace
            from opentelemetry.sdk.trace import TracerProvider as _TP
            from opentelemetry.sdk.trace.export import BatchSpanProcessor as _BSP
            from opentelemetry.sdk.resources import Resource as _Resource

            resource = _Resource.create({"service.name": svc})
            provider = _TP(resource=resource)

            if HAS_OTEL_EXPORTER_OTLP:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as _OTLP
                exporter = _OTLP(endpoint=ep, insecure=True)
                provider.add_span_processor(_BSP(exporter))
                logger.info("OTLP tracing initialised: service=%s endpoint=%s", svc, ep)
            else:
                # Console exporter as fallback (dev only)
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter as _CSE
                provider.add_span_processor(_BSP(_CSE()))
                logger.info("Console tracing initialised (no OTLP exporter installed)")

            _trace.set_tracer_provider(provider)
            SERVICE_NAME = svc
            OTLP_ENDPOINT = ep
            _initialised = True
            return True
        except Exception as exc:
            logger.exception("setup_tracing failed: %s", exc)
            return False


def instrument_fastapi(app) -> bool:
    """Attach FastAPI auto-instrumentation to an app instance. Returns True on success."""
    if not HAS_OTEL_FASTAPI:
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        return True
    except Exception as exc:
        logger.debug("FastAPI instrument_app skipped: %s", exc)
        return False


def instrument_sqlalchemy(engine) -> bool:
    """Attach SQLAlchemy auto-instrumentation. Returns True on success."""
    if not HAS_OTEL_SQLALCHEMY:
        return False
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument(engine=engine)
        return True
    except Exception as exc:
        logger.debug("SQLAlchemy instrumentation skipped: %s", exc)
        return False


def get_tracer(name: str):
    """Return a tracer. Returns a no-op tracer if SDK not available."""
    if HAS_OTEL_API:
        from opentelemetry import trace as _trace
        return _trace.get_tracer(name)
    return _NoopTracer()


class _NoopSpan:
    """Minimal no-op span — same context-manager shape as OTel Span."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def set_attribute(self, key, value):
        pass
    def set_status(self, status):
        pass
    def record_exception(self, exc):
        pass
    def end(self):
        pass


class _NoopTracer:
    """Minimal no-op tracer used when OpenTelemetry is not installed."""
    def start_as_current_span(self, name, **kwargs):
        return _NoopSpan()
    def start_span(self, name, **kwargs):
        return _NoopSpan()


__all__ = [
    "setup_tracing", "instrument_fastapi", "instrument_sqlalchemy",
    "get_tracer", "HAS_OTEL_API", "HAS_OTEL_SDK", "HAS_OTEL_EXPORTER_OTLP",
    "HAS_OTEL_FASTAPI", "HAS_OTEL_SQLALCHEMY",
    "SERVICE_NAME", "OTLP_ENDPOINT",
]
