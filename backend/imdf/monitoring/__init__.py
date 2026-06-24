"""P3-8-W2: monitoring package init — tracing + service metrics for IMDF."""
from .tracing import (
    setup_tracing,
    instrument_fastapi,
    instrument_sqlalchemy,
    get_tracer,
    HAS_OTEL_API,
    HAS_OTEL_SDK,
    HAS_OTEL_EXPORTER_OTLP,
    HAS_OTEL_FASTAPI,
    HAS_OTEL_SQLALCHEMY,
)
from .service_metrics import (
    ServiceMetrics,
    register_service,
    get_service,
    render_all,
    HAS_PROM,
)
from .endpoints import (
    SERVICE_NAMES,
    register_metrics_middleware,
    mount_monitoring,
    quick_setup,
)

__all__ = [
    "setup_tracing", "instrument_fastapi", "instrument_sqlalchemy", "get_tracer",
    "HAS_OTEL_API", "HAS_OTEL_SDK", "HAS_OTEL_EXPORTER_OTLP",
    "HAS_OTEL_FASTAPI", "HAS_OTEL_SQLALCHEMY",
    "ServiceMetrics", "register_service", "get_service", "render_all", "HAS_PROM",
    "SERVICE_NAMES", "register_metrics_middleware", "mount_monitoring", "quick_setup",
]
