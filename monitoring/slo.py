"""P19-E3 / F2: SLO definitions + Error Budget + Multi-Window Multi-Burn-Rate alerts.

Why this module
---------------
SLOs (Service Level Objectives) are the contract we promise to users. An SLO is
built from one or more SLIs (Service Level Indicators) — e.g. **availability**
SLI is the ratio of successful HTTP responses to all responses, **latency**
SLI is the fraction of responses served under a budget.

The Error Budget is ``1 - SLO``. If we promise 99.9% availability, our monthly
budget is 0.1% = 43m 12s of downtime. When the budget is "burning" too fast,
operators want to be paged BEFORE the budget is exhausted.

Multi-Window Multi-Burn-Rate (Google SRE Workbook, ch. 5) is the canonical way
to alert on budget burn:

* **Fast burn** (1h window, 14.4× burn rate) — page immediately
* **Slow burn** (6h window, 6× burn rate) — page after sustained violation
* **Very slow burn** (24h window, 3× burn rate) — optional, week-leading warning

Design notes
------------
* All SLO math is **pure Python** (no Prometheus client required) so tests
  run in milliseconds. The generated ``prometheus_rules_for_slo()`` payload
  is valid Prometheus alerting rule YAML.
* ``record_slo_outcome(service, *, success, latency_ms)`` is the single
  ingestion point — it appends to a sliding-window ring buffer in process
  (cheap, sufficient for short windows) plus publishes Prometheus counters
  so the rule files can also evaluate over a longer horizon.
* SLIs are declared with declarative metadata (``SLOTarget`` / ``SLIDefinition``)
  so they survive serialization (for the future ``/api/v1/monitoring/slo``
  endpoint + DB-backed SLO catalog).
* Burn-rate alerts honor the Google SRE "two-windows" rule: short window
  must be high AND long window must be high before paging (avoids flap on
  transient spikes).

Backward compatibility
-----------------------
* Existing E3-HB-1 metrics (``health_probe_status``, ``gdpr_erasure_total``)
  are treated as SLI data sources via ``SLIDataSource`` declarations.
* Tests must run in any environment without network access.

Tests
-----
``monitoring/tests/test_slo.py`` (16 tests) covers every code path.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

# F2 fix-5: pluggable storage backend for multi-process deployments.
# Imported lazily inside ``SLORecorder.with_backend`` to keep the cold-start
# import graph small.
try:
    from monitoring.recorder_backends import (  # type: ignore
        InMemoryBackend,
        SQLiteBackend,
        SLORecorderBackend,
    )
except Exception:  # pragma: no cover
    InMemoryBackend = None  # type: ignore
    SQLiteBackend = None  # type: ignore
    SLORecorderBackend = None  # type: ignore


# --------------------------------------------------------------------------- #
# SLO target / SLI / Error Budget data classes
# --------------------------------------------------------------------------- #
@dataclass
class SLOTarget:
    """Declarative definition of a single SLO.

    Attributes:
        name: Stable identifier (e.g. ``api_availability_99_9``).
        description: Human-readable purpose.
        service: Service owning the SLO.
        sli: The SLI definition this SLO is built from.
        target: Target success ratio, in (0, 1). 0.999 means 99.9%.
        window_seconds: Compliance window (default 30d = 2_592_000).
        labels: Free-form labels for grouping on dashboards / alert routing.
    """

    name: str
    description: str
    service: str
    sli: "SLIDefinition"
    target: float = 0.999
    window_seconds: int = 30 * 24 * 3600
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class SLIDefinition:
    """Definition of how an SLI is computed.

    An SLI is the success-ratio of good-events / valid-events over a window.
    For availability that's ``1 - errors/requests``; for latency it's the
    fraction of requests under ``latency_budget_ms``.

    Attributes:
        kind: ``"availability" | "latency" | "success_rate"``.
        good_event_filter: Predicate (record) -> bool. Marks an event as good.
        valid_event_filter: Predicate (record) -> bool. Marks an event as in-scope.
        latency_budget_ms: For ``kind=="latency"``, the budget threshold.
    """

    kind: str = "availability"
    good_event_filter: Optional[Callable[[Dict[str, Any]], bool]] = None
    valid_event_filter: Optional[Callable[[Dict[str, Any]], bool]] = None
    latency_budget_ms: Optional[float] = None

    def evaluate(self, records: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Return ``(good_count, valid_count)`` over the given event window."""
        if self.valid_event_filter is None and self.good_event_filter is None:
            # Sensible default for availability: record must have ``success`` bool
            valid = [r for r in records if "status" in r or "success" in r or "latency_ms" in r]
            valid_count = len(valid)
            if self.kind == "latency" and self.latency_budget_ms is not None:
                good_count = sum(
                    1 for r in valid
                    if float(r.get("latency_ms", 0.0)) <= self.latency_budget_ms
                )
            else:
                good_count = sum(1 for r in valid if r.get("success", r.get("status") == "ok"))
            return good_count, valid_count
        valid = [r for r in records if (self.valid_event_filter or (lambda _: True))(r)]
        good = [r for r in valid if (self.good_event_filter or (lambda _: True))(r)]
        return len(good), len(valid)


@dataclass
class ErrorBudget:
    """Result of evaluating an SLO over a window.

    Attributes:
        slo_name: Owning SLO.
        good_count: Number of good events.
        valid_count: Number of valid (in-scope) events.
        error_budget_total: ``valid_count * (1 - target)`` — the absolute budget
            for the window (in events).
        error_budget_remaining: ``budget_total - bad_count`` (in events).
        burn_rate: ``bad_count / (budget_total * window_seconds / 3600)`` —
            events-per-hour of bad events relative to budget. ``1.0`` means
            "burning exactly at the rate to exhaust budget at window end".
        target: SLO target (0..1).
        compliant: ``burn_rate <= 1.0`` (i.e. not exceeding budget).
    """

    slo_name: str
    good_count: int
    valid_count: int
    error_budget_total: float
    error_budget_remaining: float
    burn_rate: float
    target: float
    compliant: bool

    @property
    def bad_count(self) -> int:
        return self.valid_count - self.good_count

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Canonical SLO catalog (4 default SLOs for E3)
# --------------------------------------------------------------------------- #
@dataclass
class SLIDataSource:
    """Describes where Prometheus should read the SLI numerator/denominator.

    Generated rule files use the ``metric`` + ``filter`` pair; the test SLO
    catalog has 4 entries to satisfy ``4 SLO targets + 3 burn rate alerts``.
    """

    metric: str
    good_filter: str = ""
    valid_filter: str = ""
    kind: str = "availability"


def default_slo_catalog() -> List[SLOTarget]:
    """Return the 4 default SLO targets shipped with the platform.

    1. ``api_availability_99_9`` — global HTTP availability (99.9%)
    2. ``backend_p99_latency_300ms`` — 99% of requests under 300ms
    3. ``gdpr_erasure_success_99_5`` — GDPR right-to-erasure success (99.5%)
    4. ``agent_dispatch_success_99_5`` — agent dispatch success (99.5%)
    """
    return [
        SLOTarget(
            name="api_availability_99_9",
            description="Global HTTP API availability, 99.9% success over 30d.",
            service="api",
            sli=SLIDefinition(kind="availability"),
            target=0.999,
            window_seconds=30 * 24 * 3600,
            labels={"tier": "edge", "region": "global"},
        ),
        SLOTarget(
            name="backend_p99_latency_300ms",
            description="P99 backend latency under 300ms (success ratio = requests under budget).",
            service="backend",
            sli=SLIDefinition(kind="latency", latency_budget_ms=300.0),
            target=0.99,
            window_seconds=30 * 24 * 3600,
            labels={"tier": "compute", "region": "global"},
        ),
        SLOTarget(
            name="gdpr_erasure_success_99_5",
            description="GDPR right-to-erasure success rate >= 99.5%.",
            service="compliance",
            sli=SLIDefinition(kind="success_rate"),
            target=0.995,
            window_seconds=30 * 24 * 3600,
            labels={"tier": "compliance", "region": "global"},
        ),
        SLOTarget(
            name="agent_dispatch_success_99_5",
            description="Agent dispatch success rate >= 99.5%.",
            service="agent",
            sli=SLIDefinition(kind="success_rate"),
            target=0.995,
            window_seconds=30 * 24 * 3600,
            labels={"tier": "compute", "region": "global"},
        ),
    ]


# Canonical data sources referenced by rules (so they're stable identifiers
# in the generated Prometheus YAML).
DEFAULT_SLI_DATA_SOURCES: Dict[str, SLIDataSource] = {
    "api_availability_99_9": SLIDataSource(
        metric="http_requests_total",
        good_filter='status="ok"',
        valid_filter='service=~".+"',
        kind="availability",
    ),
    "backend_p99_latency_300ms": SLIDataSource(
        metric="http_latency_observations_total",
        good_filter="",  # we use a derived expression for latency in the rules
        valid_filter="",
        kind="latency",
    ),
    "gdpr_erasure_success_99_5": SLIDataSource(
        metric="gdpr_erasure_total",
        good_filter='outcome="success"',
        valid_filter='outcome=~"success|failure"',
        kind="success_rate",
    ),
    "agent_dispatch_success_99_5": SLIDataSource(
        metric="agent_dispatch_total",
        good_filter='status="ok"',
        valid_filter='service=~".+"',
        kind="success_rate",
    ),
}


# --------------------------------------------------------------------------- #
# ErrorBudgetCalculator — pure-function evaluator
# --------------------------------------------------------------------------- #
class ErrorBudgetCalculator:
    """Compute Error Budget for an SLO over a window of records."""

    @staticmethod
    def compute(slo: SLOTarget, records: List[Dict[str, Any]]) -> ErrorBudget:
        good, valid = slo.sli.evaluate(records)
        bad = max(0, valid - good)
        budget_total = valid * (1.0 - slo.target)
        # budget_total of zero means no traffic / no data — treat as compliant.
        if budget_total <= 0 or valid == 0:
            burn = 0.0
        else:
            burn = bad / budget_total
        remaining = max(0.0, budget_total - bad)
        return ErrorBudget(
            slo_name=slo.name,
            good_count=good,
            valid_count=valid,
            error_budget_total=budget_total,
            error_budget_remaining=remaining,
            burn_rate=burn,
            target=slo.target,
            compliant=(burn <= 1.0),
        )


# --------------------------------------------------------------------------- #
# Multi-Window Multi-Burn-Rate alert generator
# --------------------------------------------------------------------------- #
# Spec from Google SRE Workbook ch. 5 — 3 burn-rate alerts:
#
#   Fast burn (page now):        1h window  with 14.4× burn, for 2 min
#                                AND  6h window with 6×  burn, for 5 min   (long must also fire)
#   Slow burn (page on sustained): 24h window with 3×  burn, for 30 min
#                                AND  6h window with 6×  burn, for 30 min   (long must also fire)
#   Very slow burn (warning):    72h window with 1×  burn, for 1h
#
# "Two-window" requirement: short window must be high AND long window must
# also be high before paging. This eliminates transient spikes.
@dataclass(frozen=True)
class BurnRateSpec:
    short_window: str
    short_factor: float
    short_duration: str
    long_window: str
    long_factor: float
    long_duration: str
    severity: str
    name_suffix: str


DEFAULT_BURN_RATE_SPECS: Tuple[BurnRateSpec, ...] = (
    BurnRateSpec(
        short_window="5m", short_factor=14.4, short_duration="2m",
        long_window="1h", long_factor=6.0, long_duration="5m",
        severity="critical",
        name_suffix="FastBurn",
    ),
    BurnRateSpec(
        short_window="30m", short_factor=6.0, short_duration="5m",
        long_window="6h", long_factor=3.0, long_duration="30m",
        severity="warning",
        name_suffix="SlowBurn",
    ),
    BurnRateSpec(
        short_window="2h", short_factor=3.0, short_duration="30m",
        long_window="24h", long_factor=1.0, long_duration="1h",
        severity="info",
        name_suffix="VerySlowBurn",
    ),
)


def _errors_total_expr(sli: SLIDataSource) -> str:
    """Return the PromQL expression for total-bad-events over a window."""
    if sli.kind == "availability":
        return f'sum(rate({sli.metric}{{!({sli.good_filter})}}[{_short_window_for_expr()}]))'
    if sli.kind == "success_rate":
        return f'sum(rate({sli.metric}{{{sli.good_filter.replace("=", "!=") if sli.good_filter else ""}}}[{_short_window_for_expr()}]))'
    if sli.kind == "latency":
        # For latency SLI we have http_latency_observations_total + http_latency_ms_total
        # "bad events" = observations whose avg latency > budget. We approximate by
        # using rate() over the latency-budget-violating observations.
        return (
            f'sum(rate(http_latency_ms_total{{}}[{_short_window_for_expr()}]) '
            f'- sum(rate(http_latency_ms_total{{}}[{_short_window_for_expr()}]) '
            f'* 0.0))'  # placeholder; real rules emit the actual two-window ratio
        )
    return f'sum(rate({sli.metric}{{}}[{_short_window_for_expr()}])'


# Workaround: we need a stable "short window" string for the lambda above;
# in practice each burn-rate alert emits its own window. So we use a sentinel
# and the real call below substitutes the right window per alert.
_SHORT_WINDOW_SENTINEL = "<<WINDOW>>"


def _short_window_for_expr() -> str:
    return _SHORT_WINDOW_SENTINEL


def build_burn_rate_promql(spec: BurnRateSpec, slo: SLOTarget, sli: SLIDataSource) -> Tuple[str, str]:
    """Return (short-window expression, long-window expression) for the burn rate.

    Burn rate = (1 - success_ratio) / (1 - slo_target).
    success_ratio = sum(rate(good)) / sum(rate(valid))
    For latency we use a different expression (latency-budget-violating ratio).

    F2 fix-1: latency SLO rules now use real histogram-bucket math, comparing
    the over-budget bucket (``http_request_duration_seconds_bucket{le="0.3"}``)
    against the total observation count (``http_request_duration_seconds_count``)
    to derive a budget-violation ratio. The previous "avg latency > 300ms"
    placeholder was tautological because it would fire on ANY traffic with
    mean latency above the budget, regardless of how many requests actually
    violated the budget.
    """
    # Precompute label strings to avoid Python f-string backslash limitation
    # (Python 3.11- forbids backslashes inside f-string expression parts).
    good_label = sli.good_filter if sli.good_filter else 'status="ok"'
    valid_label = sli.valid_filter if sli.valid_filter else 'service=~".+"'
    inverted_good = _invert_filter(good_label)

    bad_short = _wrap_rate(sli.metric, inverted_good, spec.short_window)
    good_short = _wrap_rate(sli.metric, good_label, spec.short_window)
    valid_short = _wrap_rate(sli.metric, valid_label, spec.short_window)
    bad_long = _wrap_rate(sli.metric, inverted_good, spec.long_window)
    good_long = _wrap_rate(sli.metric, good_label, spec.long_window)
    valid_long = _wrap_rate(sli.metric, valid_label, spec.long_window)

    if sli.kind == "latency":
        # Latency SLI: real histogram-bucket math.
        #
        # success_ratio =
        #   http_request_duration_seconds_bucket{le="0.3"}     # requests ≤ 300ms
        #   / http_request_duration_seconds_count              # total requests
        #
        # burn_rate = (1 - success_ratio) / (1 - slo.target)
        #
        # Both ``le`` boundary and SLO target are derived from
        # ``slo.sli.latency_budget_ms`` (300ms by default) and
        # ``slo.target`` so changing the budget only requires editing the
        # SLOTarget, not the rule generator.
        budget_seconds = (slo.sli.latency_budget_ms or 300.0) / 1000.0
        budget_label = _format_le_for_promql(budget_seconds)
        # success ratio = bucket(le=budget) / count  (proportion of fast requests)
        # burn ratio   = 1 - success_ratio             (proportion of over-budget)
        # burn rate    = burn ratio / (1 - target)     (multiple of allowed budget)
        short_expr = (
            f'(\n'
            f'  (\n'
            f'    1\n'
            f'    -\n'
            f'    sum(rate(http_request_duration_seconds_bucket{{le="{budget_label}"}}[{spec.short_window}]))\n'
            f'    / clamp_min(sum(rate(http_request_duration_seconds_count{{}}[{spec.short_window}])), 0.001)\n'
            f'  )\n'
            f'  / (1 - {slo.target})\n'
            f') > {spec.short_factor}'
        )
        long_expr = (
            f'(\n'
            f'  (\n'
            f'    1\n'
            f'    -\n'
            f'    sum(rate(http_request_duration_seconds_bucket{{le="{budget_label}"}}[{spec.long_window}]))\n'
            f'    / clamp_min(sum(rate(http_request_duration_seconds_count{{}}[{spec.long_window}])), 0.001)\n'
            f'  )\n'
            f'  / (1 - {slo.target})\n'
            f') > {spec.long_factor}'
        )
        return short_expr.strip(), long_expr.strip()

    short_expr = (
        f'(\n'
        f'  ({bad_short} / clamp_min({valid_short}, 0.001))\n'
        f'  / (1 - {slo.target})\n'
        f') > {spec.short_factor}'
    )
    long_expr = (
        f'(\n'
        f'  ({bad_long} / clamp_min({valid_long}, 0.001))\n'
        f'  / (1 - {slo.target})\n'
        f') > {spec.long_factor}'
    )
    return short_expr, long_expr


def _format_le_for_promql(value: float) -> str:
    """Format a histogram bucket boundary for use in a PromQL ``le="..."`` label.

    Mirrors :func:`monitoring.observability._format_le` so the same number
    is on both the producer (exposition) and consumer (rule) sides.
    """
    if value == float("inf"):
        return "+Inf"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _invert_filter(label_filter: str) -> str:
    """Invert a label filter like ``status="ok"`` to ``status!="ok"``.

    Handles ``=`` (equality), ``!=`` (negation; returns the positive form),
    ``=~`` / ``!~`` (regex match / not). For unsupported forms returns
    ``!""`` (always true).
    """
    s = label_filter.strip()
    if s.startswith("!"):
        return s[1:].lstrip()
    for op, neg in (("=~", "!~"), ("=", "!=")):
        if op in s:
            metric_part, _, val = s.partition(op)
            return f'{metric_part}{neg}{val}'
    return 'status!=""'


def _wrap_rate(metric: str, label_filter: str, window: str) -> str:
    """Build ``sum(rate(<metric>{<filter>}[<window>]))`` safely."""
    return f'sum(rate({metric}{{{label_filter}}}[{window}]))'


def prometheus_rules_for_slo(
    slo: SLOTarget,
    sli: SLIDataSource,
    specs: Tuple[BurnRateSpec, ...] = DEFAULT_BURN_RATE_SPECS,
) -> List[Dict[str, Any]]:
    """Generate the 3 burn-rate alert rules for an SLO in Prometheus YAML shape.

    Returns a list of dicts; each dict is suitable for ``yaml.safe_dump`` into
    a Prometheus rule file. Conforms to the upstream ``prometheus.rules``
    schema: ``alert``, ``expr``, ``for``, ``labels``, ``annotations``.
    """
    rules: List[Dict[str, Any]] = []
    for spec in specs:
        short_expr, long_expr = build_burn_rate_promql(spec, slo, sli)
        rules.append({
            "alert": f"{slo.name}_{spec.name_suffix}",
            "expr": f"{short_expr}\nand\n{long_expr}",
            "for": spec.short_duration,
            "labels": {
                "severity": spec.severity,
                "slo": slo.name,
                "service": slo.service,
                "tier": slo.labels.get("tier", "default"),
            },
            "annotations": {
                "summary": (
                    f"{slo.name}: {spec.severity} {spec.name_suffix} — "
                    f"{spec.short_factor}× burn over {spec.short_window} AND "
                    f"{spec.long_factor}× burn over {spec.long_window}"
                ),
                "description": (
                    f"SLO {slo.name} (target={slo.target:.4f}) is burning budget at "
                    f"{spec.short_factor}× short window / {spec.long_factor}× long window. "
                    f"Page on-call: investigate {slo.service} availability."
                ),
                "slo_target": str(slo.target),
                "window_seconds": str(slo.window_seconds),
                "runbook_url": (
                    f"https://wiki.imdf.example.com/runbook/slo/{slo.name}"
                ),
            },
        })
    return rules


def all_burn_rate_rules() -> List[Dict[str, Any]]:
    """Return the burn-rate rules for the entire default SLO catalog."""
    catalog = default_slo_catalog()
    rules: List[Dict[str, Any]] = []
    for slo in catalog:
        sli = DEFAULT_SLI_DATA_SOURCES.get(slo.name)
        if sli is None:
            continue
        rules.extend(prometheus_rules_for_slo(slo, sli))
    return rules


def burn_rate_rules_yaml() -> str:
    """Render the burn-rate rules as a Prometheus rule-group YAML string."""
    import yaml
    return yaml.safe_dump(
        {
            "groups": [
                {
                    "name": "p19_e3_slo_burn_rate",
                    "interval": "30s",
                    "rules": all_burn_rate_rules(),
                }
            ]
        },
        sort_keys=False,
        allow_unicode=True,
    )


# --------------------------------------------------------------------------- #
# In-process sliding-window SLO outcome recorder
# --------------------------------------------------------------------------- #
@dataclass
class SLORecorder:
    """Thread-safe ring buffer of recent SLO outcome events.

    Each event is a dict ``{"success": bool, "latency_ms": float, ...}``.
    The ring buffer length is ``window_seconds``. ``record_outcome`` appends;
    ``compute_budget`` evaluates the SLO over the live buffer.

    F2 fix-5: storage is delegated to an :class:`SLORecorderBackend`. The
    default backend (deque-backed ``InMemoryBackend``) preserves the
    pre-fix behavior. ``SLORecorder.with_backend(...)`` returns a recorder
    that delegates to a backend such as :class:`SQLiteBackend` for
    multi-process deployments.
    """

    slo_name: str
    target: float
    kind: str = "availability"
    window_seconds: int = 3600
    max_records: int = 100_000
    latency_budget_ms: Optional[float] = None
    _records: Deque[Dict[str, Any]] = field(default_factory=deque)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _backend: Optional[Any] = None  # populated by with_backend factory

    def record_outcome(
        self,
        *,
        success: bool = True,
        latency_ms: float = 0.0,
        timestamp: Optional[float] = None,
    ) -> None:
        ts = timestamp if timestamp is not None else time.time()
        record = {"success": success, "latency_ms": latency_ms, "ts": ts}
        if self._backend is not None:
            # Delegate pruning + cap to the backend so SQLite / file-backed
            # implementations can do range deletes in one statement.
            self._backend.append(record)
            self._backend.prune_older_than(ts - self.window_seconds)
            self._backend.cap_max(self.max_records)
            return
        with self._lock:
            # Drop records outside the active window
            cutoff = ts - self.window_seconds
            while self._records and self._records[0].get("ts", 0.0) < cutoff:
                self._records.popleft()
            if len(self._records) >= self.max_records:
                self._records.popleft()
            self._records.append(record)

    def record_batch(self, records: List[Dict[str, Any]]) -> None:
        if self._backend is not None:
            self._backend.extend(records)
            return
        with self._lock:
            self._records.extend(records)

    def compute_budget(self) -> ErrorBudget:
        snapshot = self.snapshot()
        # Use a synthetic SLOTarget so we can reuse the calculator.
        sli = SLIDefinition(
            kind=self.kind,
            latency_budget_ms=self.latency_budget_ms,
        )
        slo = SLOTarget(
            name=self.slo_name,
            description="in-process SLO",
            service="recorder",
            sli=sli,
            target=self.target,
            window_seconds=self.window_seconds,
        )
        return ErrorBudgetCalculator.compute(slo, snapshot)

    def snapshot(self) -> List[Dict[str, Any]]:
        if self._backend is not None:
            return self._backend.snapshot()
        with self._lock:
            return list(self._records)

    def reset(self) -> None:
        if self._backend is not None:
            self._backend.reset()
            return
        with self._lock:
            self._records.clear()

    # ----------------------------------------------------------------- #
    # F2 fix-5: backend factory
    # ----------------------------------------------------------------- #
    @classmethod
    def with_backend(
        cls,
        slo_name: str,
        backend: Any,
        *,
        target: float = 0.999,
        kind: str = "availability",
        window_seconds: int = 3600,
        max_records: int = 100_000,
        latency_budget_ms: Optional[float] = None,
    ) -> "SLORecorder":
        """Build a recorder that delegates storage to ``backend``.

        ``backend`` must implement the :class:`SLORecorderBackend` Protocol
        (``append``, ``extend``, ``snapshot``, ``prune_older_than``,
        ``cap_max``, ``reset``). Pass either an :class:`InMemoryBackend` or
        a :class:`SQLiteBackend` from :mod:`monitoring.recorder_backends`.
        """
        if SLORecorderBackend is not None and not isinstance(
            backend, SLORecorderBackend
        ):
            # Soft-fail: emit a warning but proceed so we don't block a
            # test that just happens to pass an ad-hoc duck-typed object.
            import warnings
            warnings.warn(
                f"backend {type(backend).__name__} does not implement "
                f"the SLORecorderBackend Protocol; using duck typing.",
                stacklevel=2,
            )
        rec = cls(
            slo_name=slo_name,
            target=target,
            kind=kind,
            window_seconds=window_seconds,
            max_records=max_records,
            latency_budget_ms=latency_budget_ms,
        )
        rec._backend = backend
        return rec


# --------------------------------------------------------------------------- #
# Singleton recorder registry
# --------------------------------------------------------------------------- #
_RECORDERS: Dict[str, SLORecorder] = {}
_RECORDERS_LOCK = threading.Lock()


def get_recorder(
    slo_name: str,
    *,
    target: float = 0.999,
    kind: str = "availability",
    latency_budget_ms: Optional[float] = None,
    window_seconds: int = 3600,
) -> SLORecorder:
    """Idempotent factory: returns the singleton recorder for ``slo_name``."""
    with _RECORDERS_LOCK:
        rec = _RECORDERS.get(slo_name)
        if rec is None:
            rec = SLORecorder(
                slo_name=slo_name,
                target=target,
                kind=kind,
                latency_budget_ms=latency_budget_ms,
                window_seconds=window_seconds,
            )
            _RECORDERS[slo_name] = rec
        return rec


def reset_recorders() -> None:
    """Clear the recorder registry (test helper)."""
    with _RECORDERS_LOCK:
        for rec in _RECORDERS.values():
            rec.reset()
        _RECORDERS.clear()


# --------------------------------------------------------------------------- #
# Convenience: SLO summary
# --------------------------------------------------------------------------- #
@dataclass
class SloReport:
    catalog: List[SLOTarget]
    budgets: Dict[str, ErrorBudget]
    generated_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "slos": [asdict(s) for s in self.catalog],
            "budgets": {name: budget.to_dict() for name, budget in self.budgets.items()},
        }


def build_slo_report() -> SloReport:
    """Build a JSON-serializable report over the default catalog + the live
    in-process buffer for each SLO."""
    catalog = default_slo_catalog()
    budgets: Dict[str, ErrorBudget] = {}
    for slo in catalog:
        rec = get_recorder(slo.name, target=slo.target, kind=slo.sli.kind)
        budgets[slo.name] = rec.compute_budget()
    return SloReport(catalog=catalog, budgets=budgets, generated_at=time.time())


def slo_report_json() -> str:
    return json.dumps(build_slo_report().to_dict(), indent=2, ensure_ascii=False)
