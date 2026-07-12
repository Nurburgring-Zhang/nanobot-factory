"""P19-D1 — Lightweight Prometheus-style metrics registry.

Provides Counter / Gauge / Histogram primitives with ``inc()`` semantics and an
in-process Prometheus text-exposition formatter (no external ``prometheus_client``
required, so the registry works in pure-Python test environments).

Endpoints
---------
* ``GET /api/v1/monitoring/metrics`` (Prometheus text format)
* in-process scrape: ``MetricsRegistry.scrape()`` returns ``bytes`` suitable for
  ``/metrics``.

Design choices
--------------
* Counter is monotonic — only ``inc(amount=1)`` and ``inc()`` are exposed.
* Labels are accepted as a free-form ``labels: dict`` — collisions on
  ``(name, frozenset(labels))`` are summed, never duplicated.
* The exposition format is line-based ``# HELP / # TYPE / <name>{...} <value>``
  matching Prometheus exposition v0.0.4 so it can be scraped by a real
  Prometheus.
* The registry is process-local; for multi-worker deployments each worker
  exposes its own port (or a sidecar exposes the union).

Wiring
------
Call :func:`inc_counter` from any hot business path (e.g. ``agent_service``,
``imdf.engines.dataset_manager``) with a stable ``name`` and optional
``labels`` — the Prometheus scrape at ``/api/v1/monitoring/metrics`` will surface
all counters with their labels.

Tests
-----
The four counter-based smoke tests in ``monitoring/tests/test_prometheus_counter.py``
exercise this module end-to-end.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Core counter / gauge / histogram
# --------------------------------------------------------------------------- #
@dataclass
class _Sample:
    name: str
    labels: FrozenSet[Tuple[str, str]]
    value: float = 0.0


class Counter:
    """Monotonic counter with ``inc()`` / ``inc(amount=N)`` semantics."""

    def __init__(self, name: str, help: str = "", labels: Optional[list] = None) -> None:
        self.name = name
        self.help = help
        self._labels_schema = list(labels or [])
        self._samples: Dict[FrozenSet[Tuple[str, str]], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> float:
        if amount < 0:
            raise ValueError("Counter.inc() requires non-negative amount")
        key = frozenset(labels.items())
        with self._lock:
            self._samples[key] += amount
            return self._samples[key]

    def value(self, **labels: str) -> float:
        key = frozenset(labels.items())
        return self._samples.get(key, 0.0)

    def samples(self) -> Dict[FrozenSet[Tuple[str, str]], float]:
        with self._lock:
            return dict(self._samples)


class Gauge:
    def __init__(self, name: str, help: str = "") -> None:
        self.name = name
        self.help = help
        self._values: Dict[FrozenSet[Tuple[str, str]], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        key = frozenset(labels.items())
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = frozenset(labels.items())
        with self._lock:
            self._values[key] += amount

    def value(self, **labels: str) -> float:
        key = frozenset(labels.items())
        return self._values.get(key, 0.0)


# --------------------------------------------------------------------------- #
# Histogram — Prometheus-compatible bucket-based histogram
# --------------------------------------------------------------------------- #
# Used to emit ``http_request_duration_seconds_bucket{le=...}`` style samples
# that the burn-rate rules in ``prometheus-rules-slo.yml`` reference for the
# ``backend_p99_latency_300ms`` latency SLO. Each ``observe(value, **labels)``
# call increments the right bucket counter, the +Inf bucket, and the
# ``_sum`` / ``_count`` accumulators.
DEFAULT_DURATION_BUCKETS: Tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3,
    0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0,
    float("inf"),
)


class Histogram:
    """Thread-safe bucket histogram with ``_bucket``, ``_sum``, ``_count``.

    Exposes three Prometheus-style samples per ``(labels)`` series:
      * ``<name>_bucket{le=...}`` — cumulative count of observations ≤ le
      * ``<name>_sum``           — sum of all observed values
      * ``<name>_count``         — total number of observations

    Use :func:`observe_request_duration` from hot paths (HTTP middleware,
    FastAPI handler wrapper) so the latency SLO burn-rate rules can compute
    real budget-violating ratios via ``http_request_duration_seconds_bucket``.
    """

    def __init__(
        self,
        name: str,
        help: str = "",
        labels: Optional[list] = None,
        buckets: Tuple[float, ...] = DEFAULT_DURATION_BUCKETS,
    ) -> None:
        self.name = name
        self.help = help
        self._labels_schema = list(labels or [])
        self.buckets: Tuple[float, ...] = tuple(buckets)
        # {series_key: {le: cumulative_count}}
        self._bucket_counts: Dict[FrozenSet[Tuple[str, str]], Dict[str, float]] = {}
        # {series_key: sum_value}
        self._sums: Dict[FrozenSet[Tuple[str, str]], float] = {}
        # {series_key: count}
        self._counts: Dict[FrozenSet[Tuple[str, str]], float] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = frozenset(labels.items())
        with self._lock:
            bucket_map = self._bucket_counts.setdefault(key, {})
            for le in self.buckets:
                # Format ``le=...`` value: ``+Inf`` for inf, otherwise stringified float.
                le_label = "+Inf" if le == float("inf") else _format_le(le)
                cumulative = bucket_map.get(le_label, 0.0)
                # A new observation is in the bucket if ``value <= le``.
                # We accumulate by counting each observation once per matching le.
                # Since bucket counters are cumulative, we just ``+= 1`` when
                # ``value <= le``.
                if value <= le:
                    bucket_map[le_label] = cumulative + 1.0
            self._sums[key] = self._sums.get(key, 0.0) + float(value)
            self._counts[key] = self._counts.get(key, 0.0) + 1.0

    def count(self, **labels: str) -> float:
        return self._counts.get(frozenset(labels.items()), 0.0)

    def sum(self, **labels: str) -> float:
        return self._sums.get(frozenset(labels.items()), 0.0)

    def snapshot(self) -> Dict[str, Dict[FrozenSet[Tuple[str, str]], float]]:
        """Return ``{kind: {series_key: value}}`` for exposition."""
        with self._lock:
            return {
                "_bucket": {k: dict(v) for k, v in self._bucket_counts.items()},
                "_sum": dict(self._sums),
                "_count": dict(self._counts),
            }

    def samples(self) -> Tuple[
        Dict[FrozenSet[Tuple[str, str]], float],
        Dict[FrozenSet[Tuple[str, str]], float],
        Dict[FrozenSet[Tuple[str, str]], Dict[str, float]],
    ]:
        """Return ``(_count, _sum, _bucket)`` maps for the registry scraper."""
        with self._lock:
            return (
                dict(self._counts),
                dict(self._sums),
                {k: dict(v) for k, v in self._bucket_counts.items()},
            )


def _format_le(le: float) -> str:
    """Format a bucket boundary for Prometheus exposition (``le=...`` label)."""
    if le == float("inf"):
        return "+Inf"
    # Trim trailing zeros while keeping at least one digit.
    text = f"{le:.6f}".rstrip("0").rstrip(".")
    return text or "0"


# --------------------------------------------------------------------------- #
# Registry — process singleton
# --------------------------------------------------------------------------- #
class MetricsRegistry:
    """Thread-safe in-process Prometheus-style registry."""

    def __init__(self) -> None:
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()

    # -- register / lookup --------------------------------------------------- #
    def counter(self, name: str, help: str = "", labels: Optional[list] = None) -> Counter:
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                c = Counter(name, help=help, labels=labels)
                self._counters[name] = c
            return c

    def gauge(self, name: str, help: str = "") -> Gauge:
        with self._lock:
            g = self._gauges.get(name)
            if g is None:
                g = Gauge(name, help=help)
                self._gauges[name] = g
            return g

    def histogram(
        self,
        name: str,
        help: str = "",
        labels: Optional[list] = None,
        buckets: Tuple[float, ...] = DEFAULT_DURATION_BUCKETS,
    ) -> Histogram:
        with self._lock:
            h = self._histograms.get(name)
            if h is None:
                h = Histogram(name, help=help, labels=labels, buckets=buckets)
                self._histograms[name] = h
            return h

    # -- convenience: inc on the fly ---------------------------------------- #
    def inc(self, name: str, amount: float = 1.0, help: str = "",
            labels: Optional[list] = None, **kw: str) -> float:
        return self.counter(name, help=help, labels=labels).inc(amount=amount, **kw)

    # -- exposition ---------------------------------------------------------- #
    def scrape(self) -> bytes:
        """Return a Prometheus exposition v0.0.4 text payload (bytes)."""
        lines: list = []
        # Counters
        with self._lock:
            counters = list(self._counters.items())
            gauges = list(self._gauges.items())
            histograms = list(self._histograms.items())
        for name, c in sorted(counters):
            lines.append(f"# HELP {name} {c.help}".rstrip())
            lines.append(f"# TYPE {name} counter")
            for labels_key, val in sorted(c.samples().items()):
                lines.append(_render_sample(name, labels_key, val))
        for name, g in sorted(gauges):
            lines.append(f"# HELP {name} {g.help}".rstrip())
            lines.append(f"# TYPE {name} gauge")
            for labels_key, val in sorted(g._values.items()):
                lines.append(_render_sample(name, labels_key, val))
        # Histograms: emit bucket + sum + count per series
        for name, h in sorted(histograms):
            lines.append(f"# HELP {name} {h.help}".rstrip())
            lines.append(f"# TYPE {name} histogram")
            count_map, sum_map, bucket_map = h.samples()
            for series_key in sorted(set(count_map) | set(sum_map) | set(bucket_map)):
                bucket_dict = bucket_map.get(series_key, {})
                for le in sorted(bucket_dict.keys(), key=_bucket_sort_key):
                    lines.append(
                        _render_sample(
                            f"{name}_bucket",
                            _add_label(series_key, "le", le),
                            bucket_dict[le],
                        )
                    )
                if series_key in count_map:
                    lines.append(
                        _render_sample(
                            f"{name}_count", series_key, count_map[series_key]
                        )
                    )
                if series_key in sum_map:
                    lines.append(
                        _render_sample(
                            f"{name}_sum", series_key, sum_map[series_key]
                        )
                    )
        return ("\n".join(lines) + "\n").encode("utf-8")

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        """Return ``{counter_name: {label_key: value}}`` for test introspection."""
        out: Dict[str, Dict[str, float]] = {}
        with self._lock:
            counters = list(self._counters.items())
            gauges = list(self._gauges.items())
            histograms = list(self._histograms.items())
        for name, c in counters:
            out[name] = {
                ",".join(f'{k}="{v}"' for k, v in sorted(kv)): val
                for kv, val in c.samples().items()
            }
        for name, g in gauges:
            key = f"__gauges__{name}"
            out[key] = {
                ",".join(f'{k}="{v}"' for k, v in sorted(kv)): val
                for kv, val in g._values.items()
            }
        for name, h in histograms:
            count_map, sum_map, bucket_map = h.samples()
            out[f"__histograms__{name}_count"] = {
                ",".join(f'{k}="{v}"' for k, v in sorted(kv)): val
                for kv, val in count_map.items()
            }
            out[f"__histograms__{name}_sum"] = {
                ",".join(f'{k}="{v}"' for k, v in sorted(kv)): val
                for kv, val in sum_map.items()
            }
            for series_key, bucket_dict in bucket_map.items():
                base = ",".join(
                    f'{k}="{v}"' for k, v in sorted(series_key)
                )
                for le, val in bucket_dict.items():
                    full_key = (f"{base}," if base else "") + f'le="{le}"'
                    key = f"__histograms__{name}_bucket"
                    out.setdefault(key, {})[full_key] = val
        return out

    def reset(self) -> None:
        """For tests only — clear all counters, gauges and histograms."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


def _bucket_sort_key(le_label: str) -> float:
    """Sort bucket labels in numeric order (+Inf → math.inf)."""
    if le_label == "+Inf":
        return math.inf
    try:
        return float(le_label)
    except ValueError:
        return math.inf


def _add_label(series_key: FrozenSet[Tuple[str, str]], key: str, value: str):
    """Add ``key=value`` to a frozenset of label tuples."""
    return frozenset(set(series_key) | {(key, value)})


def _render_sample(name: str, labels: FrozenSet[Tuple[str, str]], value: float) -> str:
    if not labels:
        return f"{name} {value}"
    parts = ",".join(f'{k}="{_escape(v)}"' for k, v in sorted(labels))
    return f"{name}{{{parts}}} {value}"


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# --------------------------------------------------------------------------- #
# Singleton + convenience wrappers
# --------------------------------------------------------------------------- #
_REGISTRY: Optional[MetricsRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_registry() -> MetricsRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        with _REGISTRY_LOCK:
            if _REGISTRY is None:
                _REGISTRY = MetricsRegistry()
    return _REGISTRY


def inc_counter(name: str, amount: float = 1.0, *, help: str = "",
                labels: Optional[list] = None, **kw: str) -> float:
    """One-shot helper — register on demand and increment."""
    return get_registry().inc(name, amount=amount, help=help, labels=labels, **kw)


# --------------------------------------------------------------------------- #
# Pre-declared canonical counters (so dashboards have stable metric names)
# --------------------------------------------------------------------------- #
def request_counter(service: str) -> Counter:
    return get_registry().counter(
        "http_requests_total",
        help="Total HTTP/business requests handled.",
        labels=["service", "status"],
    )


def error_counter(service: str) -> Counter:
    return get_registry().counter(
        "http_errors_total",
        help="Total HTTP/business errors.",
        labels=["service", "kind"],
    )


def latency_counter(service: str) -> Counter:
    # Latency is exposed as a counter of summed_ms + a separate counter of
    # observation count — Prometheus computes rate() in PromQL.
    return get_registry().counter(
        "http_latency_ms_total",
        help="Sum of observed request latency in milliseconds.",
        labels=["service"],
    )


def latency_count_counter(service: str) -> Counter:
    return get_registry().counter(
        "http_latency_observations_total",
        help="Number of latency observations.",
        labels=["service"],
    )


# --------------------------------------------------------------------------- #
# P19-E3 / F2 fix-3: missing metrics referenced by ``prometheus-rules-slo.yml``
# --------------------------------------------------------------------------- #
# The burn-rate rules reference ``http_latency_ms_sum`` (sum of latencies)
# and ``http_latency_ms_count`` (count of observations) — different names from
# the existing ``http_latency_ms_total`` / ``http_latency_observations_total``
# pre-declared counters above. Both pairs exist now; the new pair is what the
# SLO rules actually consume, while the legacy pair remains for dashboards
# that already depend on the old names. Eager seeding ensures the metrics
# appear in ``/metrics`` on a fresh deployment with value 0.
def latency_sum_counter(service: str) -> Counter:
    """Canonical latency-sum counter referenced by ``prometheus-rules-slo.yml``.

    Burn-rate alerts consume ``sum(rate(http_latency_ms_sum[5m]))`` — emitted
    alongside :func:`latency_count_counter` for ratio calculation.
    """
    return get_registry().counter(
        "http_latency_ms_sum",
        help="Sum of observed request latency in milliseconds (SLO-consumed).",
        labels=["service"],
    )


def latency_count_metric(service: str) -> Counter:
    """Canonical latency-count counter referenced by ``prometheus-rules-slo.yml``.

    Paired with :func:`latency_sum_counter`. Together they back the
    ``http_latency_ms_sum / clamp_min(http_latency_ms_count, 0.001)`` ratio
    used by the ``backend_p99_latency_300ms`` burn-rate alerts.
    """
    return get_registry().counter(
        "http_latency_ms_count",
        help="Number of latency observations (SLO-consumed).",
        labels=["service"],
    )


def agent_dispatch_counter() -> Counter:
    """Counter referenced by ``prometheus-rules-slo.yml`` for the
    ``agent_dispatch_success_99_5`` SLO."""
    return get_registry().counter(
        "agent_dispatch_total",
        help="Total agent dispatches by status (SLO-consumed).",
        labels=["service", "status"],
    )


def request_duration_histogram(service: str) -> Histogram:
    """Canonical histogram for HTTP request duration in seconds.

    Referenced by ``prometheus-rules-slo.yml`` for the latency SLO — emits
    ``http_request_duration_seconds_bucket{le=...}``,
    ``http_request_duration_seconds_count``,
    ``http_request_duration_seconds_sum`` samples.
    """
    return get_registry().histogram(
        "http_request_duration_seconds",
        help=(
            "HTTP request duration histogram in seconds. Buckets follow the "
            "Prometheus client_default recommendation plus a 300ms bucket "
            "matching the latency SLO budget."
        ),
        labels=["service", "method"],
        buckets=(
            0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3,
            0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0,
            float("inf"),
        ),
    )


# --------------------------------------------------------------------------- #
# Wiring helper — call from any service's hot path
# --------------------------------------------------------------------------- #
def record_request(service: str, *, status: str = "ok",
                   latency_ms: float = 0.0, error_kind: Optional[str] = None,
                   method: str = "GET") -> None:
    """One-line wrapper used by all business hot-paths.

    Increments ``http_requests_total{service=…,status=…}``,
    ``http_latency_ms_total{service=…}`` and
    ``http_latency_observations_total{service=…}`` and, when ``status != "ok"``,
    ``http_errors_total{service=…,kind=…}``.

    F2 fix-3: also emits the SLO-consumed pair
    ``http_latency_ms_sum{service=…}`` / ``http_latency_ms_count{service=…}``
    and observes the value into ``http_request_duration_seconds_bucket``
    so the ``backend_p99_latency_300ms`` burn-rate rules have real data.
    """
    get_registry().counter("http_requests_total", labels=["service", "status"]).inc(
        1.0, service=service, status=status,
    )
    if latency_ms > 0:
        get_registry().counter("http_latency_ms_total", labels=["service"]).inc(
            latency_ms, service=service,
        )
        get_registry().counter("http_latency_observations_total", labels=["service"]).inc(
            1.0, service=service,
        )
        # F2 fix-3: SLO-consumed latency pair (must mirror http_latency_ms_total).
        latency_sum_counter(service).inc(float(latency_ms), service=service)
        latency_count_metric(service).inc(1.0, service=service)
        # F2 fix-3: histogram (seconds, not ms).
        request_duration_histogram(service).observe(
            float(latency_ms) / 1000.0,
            service=service, method=method,
        )
    if status != "ok" or error_kind:
        get_registry().counter("http_errors_total", labels=["service", "kind"]).inc(
            1.0, service=service, kind=(error_kind or status),
        )


def record_agent_dispatch(*, service: str, status: str) -> None:
    """Record an agent dispatch outcome.

    F2 fix-3: emits ``agent_dispatch_total{service=…,status=…}`` consumed by
    the ``agent_dispatch_success_99_5`` burn-rate alert.
    """
    agent_dispatch_counter().inc(1.0, service=service, status=status)


# --------------------------------------------------------------------------- #
# P19-E3 HB-1: Health probe metrics (per-service up/down/unknown + latency)
# --------------------------------------------------------------------------- #
# Status encoding for ``health_probe_status`` gauge:
#   0 = down     (probe failed)
#   1 = up       (probe succeeded)
#   2 = unknown  (module not loaded / not instrumented — still surfaces in
#                 dashboards and alert rules as a soft signal)
HEALTH_STATUS_DOWN = 0
HEALTH_STATUS_UP = 1
HEALTH_STATUS_UNKNOWN = 2


def health_probe_status_gauge() -> Gauge:
    """Return the gauge used to surface per-service health status."""
    return get_registry().gauge(
        "health_probe_status",
        help=(
            "Per-service health probe status (0=down, 1=up, 2=unknown). "
            "Updated after every HealthRegistry.aggregate() call."
        ),
    )


def health_probe_latency_gauge() -> Gauge:
    """Return the gauge used to surface per-service probe latency."""
    return get_registry().gauge(
        "health_probe_latency_ms",
        help="Latency of the most recent health probe per service, in milliseconds.",
    )


def health_probe_up_counter() -> Counter:
    """Counter incremented every time a probe returns healthy=True."""
    return get_registry().counter(
        "health_probe_up_total",
        help="Cumulative count of successful (healthy) probes per service.",
        labels=["service"],
    )


def health_probe_fail_counter() -> Counter:
    """Counter incremented every time a probe returns healthy=False."""
    return get_registry().counter(
        "health_probe_fail_total",
        help="Cumulative count of failed (unhealthy) probes per service.",
        labels=["service"],
    )


def set_health_probe(service: str, *, status: int, latency_ms: float) -> None:
    """Single entry-point used by :mod:`monitoring.health` after each probe cycle.

    ``status`` MUST be one of ``HEALTH_STATUS_DOWN / UP / UNKNOWN``.
    """
    if status not in (HEALTH_STATUS_DOWN, HEALTH_STATUS_UP, HEALTH_STATUS_UNKNOWN):
        raise ValueError(f"invalid health status: {status!r}")
    health_probe_status_gauge().set(float(status), service=service)
    health_probe_latency_gauge().set(float(latency_ms), service=service)
    if status == HEALTH_STATUS_UP:
        health_probe_up_counter().inc(1.0, service=service)
    elif status == HEALTH_STATUS_DOWN:
        health_probe_fail_counter().inc(1.0, service=service)


# --------------------------------------------------------------------------- #
# P19-E3 HB-1: GDPR erasure metrics (count + duration + records erased)
# --------------------------------------------------------------------------- #
GDPR_OUTCOME_SUCCESS = "success"
GDPR_OUTCOME_FAILURE = "failure"


def gdpr_erasure_counter() -> Counter:
    """Counter incremented once per erasure call, labelled by outcome."""
    return get_registry().counter(
        "gdpr_erasure_total",
        help="Total number of GDPR right-to-erasure invocations.",
        labels=["outcome"],
    )


def gdpr_erasure_duration_counter() -> Counter:
    """Counter that accumulates the duration (ms) of every erasure call."""
    return get_registry().counter(
        "gdpr_erasure_duration_ms_total",
        help="Sum of GDPR erasure durations, in milliseconds.",
        labels=["outcome"],
    )


def gdpr_erasure_observations_counter() -> Counter:
    """Counter that counts how many erasure observations contributed to the sum."""
    return get_registry().counter(
        "gdpr_erasure_observations_total",
        help="Number of GDPR erasure observations (for rate()).",
        labels=["outcome"],
    )


def gdpr_erasure_records_counter() -> Counter:
    """Counter that tracks how many individual records were erased."""
    return get_registry().counter(
        "gdpr_erasure_records_total",
        help="Total number of individual records erased across all trackers.",
        labels=["outcome"],
    )


# Eagerly register the canonical GDPR metrics so they appear in every scrape
# even before the first erasure. Prometheus dashboards and alert rules expect
# a metric to exist (with value 0 if nothing has happened yet) — otherwise
# the rule ``increase(gdpr_erasure_total[1h])`` returns "no data" which is
# indistinguishable from "everything is fine" on a fresh deployment.
def _seed_canonical_gdpr_metrics() -> None:
    for outcome in (GDPR_OUTCOME_SUCCESS, GDPR_OUTCOME_FAILURE):
        gdpr_erasure_counter().inc(0.0, outcome=outcome)
        gdpr_erasure_duration_counter().inc(0.0, outcome=outcome)
        gdpr_erasure_observations_counter().inc(0.0, outcome=outcome)
        gdpr_erasure_records_counter().inc(0.0, outcome=outcome)
    # Eagerly register health gauges for the canonical 20 services.
    for _svc in (
        "agent", "annotation", "asset", "cleaning", "collection", "dataset",
        "evaluation", "notification", "scoring", "search", "user", "workflow",
        "billing",
        "imdf_main", "audit_chain", "model_gateway",
        "postgres", "redis", "oss_storage", "queue",
    ):
        health_probe_status_gauge().set(2.0, service=_svc)  # 2 = UNKNOWN until first probe
        health_probe_latency_gauge().set(0.0, service=_svc)
    # F2 fix-3: eagerly register the 3 SLO-consumed metrics so they appear in
    # every scrape on a fresh deployment with value 0. Without this seeding,
    # Prometheus rules like ``sum(rate(http_latency_ms_sum[5m]))`` return
    # "no data" which dashboards interpret as healthy, masking real outages.
    for _svc in ("api", "backend", "billing", "agent", "compliance", "imdf_main"):
        latency_sum_counter(_svc).inc(0.0, service=_svc)
        latency_count_metric(_svc).inc(0.0, service=_svc)
        for _status in ("ok", "error"):
            agent_dispatch_counter().inc(0.0, service=_svc, status=_status)
        # Histogram: call .observe(0.0) to register the buckets. Using 0.0
        # puts the observation into the smallest bucket; that's fine — it
        # only affects the "le=0.005" bucket count.
        request_duration_histogram(_svc).observe(0.0, service=_svc, method="GET")


_seed_canonical_gdpr_metrics()


def record_gdpr_erasure(*, outcome: str, duration_ms: float,
                        records_erased: int) -> None:
    """Single entry-point used by :mod:`monitoring.compliance_reports`.

    Records the four canonical erasure metrics in one shot so the dashboard
    has consistent label tuples.
    """
    if outcome not in (GDPR_OUTCOME_SUCCESS, GDPR_OUTCOME_FAILURE):
        raise ValueError(f"invalid gdpr outcome: {outcome!r}")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if records_erased < 0:
        raise ValueError("records_erased must be non-negative")
    gdpr_erasure_counter().inc(1.0, outcome=outcome)
    gdpr_erasure_duration_counter().inc(float(duration_ms), outcome=outcome)
    gdpr_erasure_observations_counter().inc(1.0, outcome=outcome)
    if records_erased > 0:
        gdpr_erasure_records_counter().inc(float(records_erased), outcome=outcome)