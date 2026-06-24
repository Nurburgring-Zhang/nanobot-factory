"""
P3-8-W2: Service-level Prometheus metrics (template)
====================================================

Lightweight module that 12 backend services can import to expose /metrics.
Each service should call register_service(name) at startup and use the
returned counters/histograms in their request handlers.

Service endpoints follow the convention:
    GET /metrics    — Prometheus text format
    GET /healthz    — liveness
    GET /readyz     — readiness

These are auto-scrape targets via the prometheus.yaml `microservices` job
(label `component=microservice`).
"""
from __future__ import annotations

import os
import time
import threading
from typing import Optional, Dict, Any

# Try prometheus_client; fall back to in-process dict if not available
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, CollectorRegistry,
        generate_latest, CONTENT_TYPE_LATEST,
    )
    HAS_PROM = True
except ImportError:
    HAS_PROM = False

# OpenTelemetry tracing (optional)
try:
    from .tracing import get_tracer
except ImportError:
    try:
        from imdf.monitoring.tracing import get_tracer  # type: ignore
    except ImportError:
        def get_tracer(name):  # type: ignore
            class _T:
                def start_as_current_span(self, *a, **k):
                    class _S:
                        def __enter__(self): return self
                        def __exit__(self, *a): return False
                        def set_attribute(self, k, v): pass
                        def set_status(self, s): pass
                    return _S()
            return _T()


class ServiceMetrics:
    """Per-service metrics bundle. One instance per microservice."""

    def __init__(self, name: str):
        self.name = name
        self._lock = threading.Lock()
        self._service_start = time.time()

        if HAS_PROM:
            self.registry = CollectorRegistry()
            self.request_count = Counter(
                "imdf_requests_total",
                "Total request count",
                ["method", "endpoint", "status_code"],
                registry=self.registry,
            )
            self.request_latency = Histogram(
                "imdf_request_latency_seconds",
                "Request latency in seconds",
                ["method", "endpoint"],
                buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
                registry=self.registry,
            )
            self.error_count = Counter(
                "imdf_errors_total",
                "Total error count",
                ["type"],
                registry=self.registry,
            )
            self.active_connections = Gauge(
                "imdf_active_connections",
                "Currently active connections",
                registry=self.registry,
            )
            self.queue_depth = Gauge(
                "imdf_queue_depth",
                "Current task queue depth",
                registry=self.registry,
            )
            self.running_tasks = Gauge(
                "imdf_running_tasks",
                "Currently running tasks",
                registry=self.registry,
            )
            self.memory_rss = Gauge(
                "imdf_memory_rss_bytes",
                "Process RSS memory in bytes",
                registry=self.registry,
            )
        else:
            self.registry = None
            self.request_count = None
            self.request_latency = None
            self.error_count = None
            self.active_connections = None
            self.queue_depth = None
            self.running_tasks = None
            self.memory_rss = None

        self.tracer = get_tracer(f"imdf.service.{name}")

    def observe_request(self, method: str, endpoint: str, status_code: int, latency_seconds: float):
        """Record a single request — call from middleware on every request."""
        status_label = f"{status_code // 100}xx"
        if HAS_PROM:
            self.request_count.labels(method=method, endpoint=endpoint, status_code=status_label).inc()
            self.request_latency.labels(method=method, endpoint=endpoint).observe(latency_seconds)
            if status_code >= 400:
                self.error_count.labels(type="http_error").inc()
        # No-op fallback if prometheus_client missing
        with self._lock:
            self._last_obs = (method, endpoint, status_code, latency_seconds)

    def set_queue(self, depth: int, running: int):
        if HAS_PROM:
            self.queue_depth.set(depth)
            self.running_tasks.set(running)

    def update_memory(self):
        if not HAS_PROM:
            return
        try:
            import psutil
            process = psutil.Process(os.getpid())
            self.memory_rss.set(process.memory_info().rss)
        except ImportError:
            pass

    def render(self) -> bytes:
        """Render Prometheus text format. Returns bytes."""
        if HAS_PROM:
            self.update_memory()
            return generate_latest(self.registry)
        # Minimal fallback so /metrics still returns valid Prometheus text
        return (
            f"# HELP imdf_service_up Service is up\n"
            f"# TYPE imdf_service_up gauge\n"
            f"imdf_service_up{{service=\"{self.name}\"}} 1\n"
            f"# HELP imdf_service_uptime_seconds Service uptime in seconds\n"
            f"# TYPE imdf_service_uptime_seconds gauge\n"
            f"imdf_service_uptime_seconds{{service=\"{self.name}\"}} {int(time.time() - self._service_start)}\n"
        ).encode("utf-8")


# Module-level registry of service-metric singletons keyed by name
_registry_lock = threading.Lock()
_service_metrics: Dict[str, ServiceMetrics] = {}


def register_service(name: str) -> ServiceMetrics:
    """Get or create a ServiceMetrics instance for the given service name."""
    with _registry_lock:
        if name not in _service_metrics:
            _service_metrics[name] = ServiceMetrics(name)
        return _service_metrics[name]


def get_service(name: str) -> Optional[ServiceMetrics]:
    """Return the ServiceMetrics instance for a service, or None if not registered."""
    return _service_metrics.get(name)


def render_all() -> bytes:
    """Render all registered services' metrics as a single text dump."""
    chunks = []
    for svc in _service_metrics.values():
        try:
            chunks.append(svc.render())
        except Exception:
            pass
    return b"\n".join(chunks)


__all__ = [
    "ServiceMetrics", "register_service", "get_service", "render_all",
    "HAS_PROM",
]
