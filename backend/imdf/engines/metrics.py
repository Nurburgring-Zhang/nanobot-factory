"""
Phase2: Enhanced Metrics Engine
===============================
In-memory metrics with Prometheus integration support.
Provides request counters, latency histograms (P50/P95/P99),
active connections, memory usage, and Prometheus endpoint.

Design:
- Thread-safe via threading.Lock
- Has built-in histogram computation for P50/P95/P99
- Integrates with prometheus_client if available
- Falls back to manual Prometheus text format generation
"""

import os
import time
import threading
import math
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict


# ============================================================================
# Histogram helper — maintains sorted samples for percentile computation
# ============================================================================

class StreamingHistogram:
    """Approximate histogram using sorted buckets.
    Keeps last N samples for accurate percentile calculation."""

    def __init__(self, max_samples: int = 10000, buckets: Optional[List[float]] = None):
        self._lock = threading.Lock()
        self._samples: List[float] = []
        self._max_samples = max_samples
        self._sum: float = 0.0
        self._count: int = 0
        self._buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
        self._bucket_counts: Dict[float, int] = defaultdict(int)

    def observe(self, value: float):
        with self._lock:
            self._sum += value
            self._count += 1
            if len(self._samples) < self._max_samples:
                self._samples.append(value)
            else:
                # Reservoir sampling: replace random element
                import random
                idx = random.randint(0, self._count - 1)
                if idx < len(self._samples):
                    self._samples[idx] = value
            # Track buckets
            for b in self._buckets:
                if value <= b:
                    self._bucket_counts[b] += 1

    def percentile(self, p: float) -> float:
        """Compute the p-th percentile (0 <= p <= 1) from stored samples."""
        with self._lock:
            if not self._samples:
                return 0.0
            sorted_samples = sorted(self._samples)
            k = (len(sorted_samples) - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_samples[int(k)]
            d0 = sorted_samples[int(f)] * (c - k)
            d1 = sorted_samples[int(c)] * (k - f)
            return d0 + d1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            sorted_samples = sorted(self._samples) if self._samples else []
            n = len(sorted_samples)
            return {
                "count": self._count,
                "sum": round(self._sum, 6),
                "min": round(sorted_samples[0], 6) if sorted_samples else 0.0,
                "max": round(sorted_samples[-1], 6) if sorted_samples else 0.0,
                "avg": round(self._sum / self._count, 6) if self._count > 0 else 0.0,
                "p50": round(self._percentile_from_sorted(sorted_samples, 0.50), 6),
                "p95": round(self._percentile_from_sorted(sorted_samples, 0.95), 6),
                "p99": round(self._percentile_from_sorted(sorted_samples, 0.99), 6),
                "buckets": dict(self._bucket_counts),
            }

    def _percentile_from_sorted(self, sorted_samples: List[float], p: float) -> float:
        if not sorted_samples:
            return 0.0
        k = (len(sorted_samples) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_samples[int(k)]
        return sorted_samples[int(f)] * (c - k) + sorted_samples[int(c)] * (k - f)


# ============================================================================
# Metrics Registry
# ============================================================================

class MetricsRegistry:
    """Thread-safe in-memory metrics registry."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()

        # Counters
        self._request_count_total: int = 0
        self._request_count_by_endpoint: Dict[str, int] = defaultdict(int)
        self._request_count_by_status: Dict[str, int] = defaultdict(int)
        self._error_count_total: int = 0

        # Latency histogram
        self._latency_histogram = StreamingHistogram(max_samples=10000)

        # Active connections
        self._active_connections: int = 0

        # Active WebSocket connections
        self._active_ws_connections: int = 0

        # Task queue depth
        self._queue_depth: int = 0
        self._running_tasks: int = 0

        # Memory usage (updated on each /metrics scrape or manually)
        self._last_memory_bytes: int = 0
        self._last_memory_pct: float = 0.0

    # ── Counters ─────────────────────────────────────────────────────────

    def record_request(self, method: str, endpoint: str, status_code: int, latency_seconds: float):
        with self._lock:
            self._request_count_total += 1

            ep_key = f"{method}:{endpoint}"
            self._request_count_by_endpoint[ep_key] += 1

            status_class = f"{status_code // 100}xx"
            self._request_count_by_status[status_class] += 1

            if status_code >= 400:
                self._error_count_total += 1

            self._latency_histogram.observe(latency_seconds)

    def increment_connections(self):
        with self._lock:
            self._active_connections += 1

    def decrement_connections(self):
        with self._lock:
            self._active_connections = max(0, self._active_connections - 1)

    def set_ws_connections(self, count: int):
        with self._lock:
            self._active_ws_connections = count

    def set_queue_metrics(self, depth: int, running: int):
        with self._lock:
            self._queue_depth = depth
            self._running_tasks = running

    def update_memory(self):
        """Update memory usage metrics using psutil if available."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            with self._lock:
                self._last_memory_bytes = mem_info.rss
                self._last_memory_pct = process.memory_percent()
        except ImportError:
            with self._lock:
                self._last_memory_bytes = 0
                self._last_memory_pct = 0.0

    # ── Snapshots ────────────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        self.update_memory()
        uptime = time.time() - self._start_time
        latency_snap = self._latency_histogram.snapshot()
        with self._lock:
            return {
                "uptime_seconds": round(uptime, 1),
                "request_count_total": self._request_count_total,
                "error_count_total": self._error_count_total,
                "active_connections": self._active_connections,
                "active_ws_connections": self._active_ws_connections,
                "queue_depth": self._queue_depth,
                "running_tasks": self._running_tasks,
                "memory_rss_bytes": self._last_memory_bytes,
                "memory_percent": round(self._last_memory_pct, 2),
                "latency": latency_snap,
                "requests_by_endpoint": dict(self._request_count_by_endpoint),
                "requests_by_status": dict(self._request_count_by_status),
            }

    def prometheus_text(self) -> str:
        """Generate Prometheus-compatible text format."""
        snap = self.snapshot()
        lines = []

        def _metric(help_line, type_line, name, labels, value):
            lines.append(f"# HELP {name} {help_line}")
            lines.append(f"# TYPE {name} {type_line}")
            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

        # Uptime
        _metric("Service uptime in seconds", "gauge", "imdf_uptime_seconds", {}, snap["uptime_seconds"])

        # Request total
        _metric("Total request count", "counter", "imdf_requests_total", {}, snap["request_count_total"])

        # Request by status
        _metric("Request count by HTTP status class", "counter", "imdf_requests_by_status", None, 0)
        lines[-1] = ""  # remove placeholder
        lines.pop()
        for status_class, count in snap["requests_by_status"].items():
            _metric("Request count by HTTP status class", "counter", "imdf_requests_by_status",
                   {"status": status_class}, count)

        # Request by endpoint (top 20)
        top_endpoints = sorted(snap["requests_by_endpoint"].items(), key=lambda x: -x[1])[:20]
        _metric("Request count by endpoint (method:path)", "counter", "imdf_requests_by_endpoint", None, 0)
        lines.pop()
        for ep, count in top_endpoints:
            _metric("Request count by endpoint", "counter", "imdf_requests_by_endpoint",
                   {"endpoint": ep}, count)

        # Error total
        _metric("Total error count (status >= 400)", "counter", "imdf_errors_total", {},
               snap["error_count_total"])

        # Active connections
        _metric("Currently active HTTP connections", "gauge", "imdf_active_connections", {},
               snap["active_connections"])

        # Active WebSocket connections
        _metric("Currently active WebSocket connections", "gauge", "imdf_active_ws_connections", {},
               snap["active_ws_connections"])

        # Queue depth
        _metric("Current task queue depth", "gauge", "imdf_queue_depth", {},
               snap["queue_depth"])

        # Running tasks
        _metric("Currently running tasks", "gauge", "imdf_running_tasks", {},
               snap["running_tasks"])

        # Memory
        _metric("Process RSS memory in bytes", "gauge", "imdf_memory_rss_bytes", {},
               snap["memory_rss_bytes"])
        _metric("Process memory usage percent", "gauge", "imdf_memory_percent", {},
               snap["memory_percent"])

        # Latency histogram
        lat = snap["latency"]
        _metric("Request latency histogram (summary)", "summary", "imdf_request_latency_seconds", None, 0)
        lines.pop()
        for quantile_name, quantile_val in [("0.5", lat["p50"]), ("0.95", lat["p95"]), ("0.99", lat["p99"])]:
            _metric("Request latency histogram", "summary", "imdf_request_latency_seconds",
                   {"quantile": quantile_name}, quantile_val)
        _metric("Request latency histogram", "summary", "imdf_request_latency_seconds_sum", {},
               lat["sum"])
        _metric("Request latency histogram", "summary", "imdf_request_latency_seconds_count", {},
               lat["count"])

        # Latency buckets
        for bucket_val, bucket_count in sorted(lat["buckets"].items()):
            _metric("Request latency histogram (buckets)", "histogram", "imdf_request_latency_seconds_bucket",
                   {"le": str(bucket_val)}, bucket_count)
        _metric("Request latency histogram (buckets)", "histogram", "imdf_request_latency_seconds_bucket",
               {"le": "+Inf"}, lat["count"])

        return "\n".join(lines) + "\n"


# ============================================================================
# Prometheus client integration (optional, transparent)
# ============================================================================

HAS_PROMETHEUS_CLIENT = False
_prom_registry = None
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry

    _prom_registry = CollectorRegistry(auto_describe=True)

    P_REQUEST_COUNT = Counter(
        "imdf_requests_total", "Total request count",
        ["method", "endpoint", "status_code"],
        registry=_prom_registry,
    )
    P_REQUEST_LATENCY = Histogram(
        "imdf_request_latency_seconds", "Request latency in seconds",
        ["method", "endpoint"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
        registry=_prom_registry,
    )
    P_ERROR_COUNT = Counter(
        "imdf_errors_total", "Total error count",
        ["type"],
        registry=_prom_registry,
    )
    P_ACTIVE_CONNECTIONS = Gauge(
        "imdf_active_connections", "Currently active connections",
        registry=_prom_registry,
    )
    P_ACTIVE_WS = Gauge(
        "imdf_active_ws_connections", "Active WebSocket connections",
        registry=_prom_registry,
    )
    P_QUEUE_DEPTH = Gauge(
        "imdf_queue_depth", "Current task queue depth",
        registry=_prom_registry,
    )
    P_RUNNING_TASKS = Gauge(
        "imdf_running_tasks", "Currently running tasks",
        registry=_prom_registry,
    )
    P_MEMORY_RSS = Gauge(
        "imdf_memory_rss_bytes", "Process RSS memory in bytes",
        registry=_prom_registry,
    )
    P_MEMORY_PCT = Gauge(
        "imdf_memory_percent", "Process memory percent",
        registry=_prom_registry,
    )
    HAS_PROMETHEUS_CLIENT = True
except ImportError:
    pass


# ============================================================================
# Global singleton
# ============================================================================

_global_registry = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    """Get the global metrics registry singleton."""
    return _global_registry


def record_request(method: str, endpoint: str, status_code: int, latency_seconds: float):
    """Convenience: record a single request."""
    _global_registry.record_request(method, endpoint, status_code, latency_seconds)

    # Also feed prometheus_client if available
    if HAS_PROMETHEUS_CLIENT:
        status_label = f"{status_code // 100}xx"
        P_REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_label).inc()
        P_REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency_seconds)
        if status_code >= 400:
            P_ERROR_COUNT.labels(type="http_error").inc()


def update_prometheus_gauges(registry: MetricsRegistry):
    """Sync gauges to prometheus_client."""
    if not HAS_PROMETHEUS_CLIENT:
        return
    snap = registry.snapshot()
    P_ACTIVE_CONNECTIONS.set(snap["active_connections"])
    P_ACTIVE_WS.set(snap["active_ws_connections"])
    P_QUEUE_DEPTH.set(snap["queue_depth"])
    P_RUNNING_TASKS.set(snap["running_tasks"])
    P_MEMORY_RSS.set(snap["memory_rss_bytes"])
    P_MEMORY_PCT.set(snap["memory_percent"])


def generate_prometheus() -> str:
    """Generate Prometheus format text output."""
    if HAS_PROMETHEUS_CLIENT:
        update_prometheus_gauges(_global_registry)
        return generate_latest(_prom_registry).decode("utf-8")
    return _global_registry.prometheus_text()
