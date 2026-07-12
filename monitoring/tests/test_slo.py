"""Tests for monitoring.slo — SLO definitions, error budget, burn-rate alerts.

Covers:
1. SLOTarget / SLIDefinition dataclasses — creation + validation
2. ErrorBudgetCalculator — correct math for availability + latency + success_rate
3. SLORecorder — thread-safe ring buffer + window expiry
4. Prometheus burn-rate rule generation — 4 SLOs × 3 windows = 12 rules
5. YAML rendering — parseable by ``yaml.safe_load``
6. SLO summary JSON — serialization round-trip
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import yaml

from monitoring import slo
from monitoring.slo import (
    DEFAULT_BURN_RATE_SPECS,
    ErrorBudget,
    ErrorBudgetCalculator,
    SLOTarget,
    SLIDefinition,
    SLORecorder,
    all_burn_rate_rules,
    build_slo_report,
    burn_rate_rules_yaml,
    default_slo_catalog,
    get_recorder,
    prometheus_rules_for_slo,
    reset_recorders,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_recordings():
    """Make sure each test starts with a clean recorder registry."""
    reset_recorders()
    yield
    reset_recorders()


# --------------------------------------------------------------------------- #
# 1. Data class sanity
# --------------------------------------------------------------------------- #
def test_slotarget_default_target_is_99_9():
    slo_def = SLOTarget(
        name="x", description="d", service="s",
        sli=SLIDefinition(kind="availability"),
    )
    assert slo_def.target == 0.999
    assert slo_def.window_seconds == 30 * 24 * 3600
    assert slo_def.labels == {}


def test_default_slo_catalog_has_four_targets():
    catalog = default_slo_catalog()
    assert len(catalog) == 4
    names = [c.name for c in catalog]
    assert "api_availability_99_9" in names
    assert "backend_p99_latency_300ms" in names
    assert "gdpr_erasure_success_99_5" in names
    assert "agent_dispatch_success_99_5" in names


# --------------------------------------------------------------------------- #
# 2. ErrorBudgetCalculator math
# --------------------------------------------------------------------------- #
def test_error_budget_compliant_when_no_bad_events():
    catalog = default_slo_catalog()
    api_slo = next(c for c in catalog if c.name == "api_availability_99_9")
    # 1000 events, 0 bad → fully compliant.
    records = [{"success": True} for _ in range(1000)]
    budget = ErrorBudgetCalculator.compute(api_slo, records)
    assert budget.good_count == 1000
    assert budget.valid_count == 1000
    assert budget.burn_rate == 0.0
    assert budget.compliant is True


def test_error_budget_under_budget_when_below_target():
    catalog = default_slo_catalog()
    api_slo = next(c for c in catalog if c.name == "api_availability_99_9")
    # 99.99% of 10000 are good → under-budget (target = 99.9%).
    good = 9999
    bad = 1
    records = [{"success": True}] * good + [{"success": False}] * bad
    budget = ErrorBudgetCalculator.compute(api_slo, records)
    assert budget.good_count == good
    assert budget.valid_count == good + bad
    # budget_total = 10000 * (1 - 0.999) = 10
    assert budget.error_budget_total == pytest.approx(10.0)
    assert budget.error_budget_remaining == pytest.approx(9.0)
    assert budget.compliant is True


def test_error_budget_over_budget_when_above_target():
    catalog = default_slo_catalog()
    api_slo = next(c for c in catalog if c.name == "api_availability_99_9")
    # 1000 events, 50 bad → 95% success, target 99.9% → over-budget.
    records = [{"success": True}] * 950 + [{"success": False}] * 50
    budget = ErrorBudgetCalculator.compute(api_slo, records)
    assert budget.burn_rate > 1.0
    assert budget.compliant is False


def test_latency_sli_evaluates_correctly():
    catalog = default_slo_catalog()
    lat_slo = next(c for c in catalog if c.name == "backend_p99_latency_300ms")
    # 10 requests, 8 under budget, 2 over.
    records = [
        {"latency_ms": 100.0 + i * 10} for i in range(8)
    ] + [{"latency_ms": 350.0}, {"latency_ms": 500.0}]
    budget = ErrorBudgetCalculator.compute(lat_slo, records)
    assert budget.good_count == 8
    assert budget.valid_count == 10
    assert budget.bad_count == 2


def test_error_budget_to_dict_round_trip():
    budget = ErrorBudget(
        slo_name="x", good_count=99, valid_count=100,
        error_budget_total=0.1, error_budget_remaining=0.01,
        burn_rate=0.9, target=0.999, compliant=True,
    )
    d = budget.to_dict()
    assert d["slo_name"] == "x"
    assert d["burn_rate"] == 0.9
    # JSON serializable
    json.dumps(d)


# --------------------------------------------------------------------------- #
# 3. SLORecorder — thread-safe ring buffer
# --------------------------------------------------------------------------- #
def test_recorder_records_outcomes_and_computes_budget():
    rec = get_recorder("api_availability_99_9", target=0.999, kind="availability")
    for _ in range(990):
        rec.record_outcome(success=True, latency_ms=120.0)
    for _ in range(10):
        rec.record_outcome(success=False, latency_ms=550.0)
    budget = rec.compute_budget()
    assert budget.good_count == 990
    assert budget.valid_count == 1000


def test_recorder_window_expiry():
    rec = get_recorder("test_window_expiry", target=0.99, window_seconds=60)
    base = time.time()
    # 50 events 2 minutes ago — should be evicted.
    rec.record_batch(
        [{"success": i % 5 != 0, "latency_ms": 100.0, "ts": base - 120} for i in range(50)]
    )
    # 100 events now — should remain.
    for _ in range(100):
        rec.record_outcome(success=True, latency_ms=120.0, timestamp=base)
    budget = rec.compute_budget()
    # Only the 100 fresh events should be counted.
    assert budget.valid_count == 100
    assert budget.good_count == 100


def test_recorder_thread_safe_under_concurrent_writes():
    rec = get_recorder("test_thread_safe", target=0.999)
    def writer(success: bool, n: int):
        for _ in range(n):
            rec.record_outcome(success=success, latency_ms=120.0)
    threads = []
    for _ in range(4):
        threads.append(threading.Thread(target=writer, args=(True, 250)))
        threads.append(threading.Thread(target=writer, args=(False, 25)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    budget = rec.compute_budget()
    # 4 × 250 = 1000 good, 4 × 25 = 100 bad.
    assert budget.good_count == 1000
    assert budget.valid_count == 1100


def test_recorder_singleton_returns_same_instance():
    a = get_recorder("api_availability_99_9")
    b = get_recorder("api_availability_99_9")
    assert a is b


def test_recorder_reset_clears_buffer():
    rec = get_recorder("test_reset", target=0.999)
    for _ in range(50):
        rec.record_outcome(success=True)
    assert rec.compute_budget().valid_count == 50
    rec.reset()
    assert rec.compute_budget().valid_count == 0


# --------------------------------------------------------------------------- #
# 4. Burn-rate rule generation
# --------------------------------------------------------------------------- #
def test_all_burn_rate_rules_emits_twelve_rules():
    """4 SLOs × 3 burn-rate specs = 12 alerts."""
    rules = all_burn_rate_rules()
    assert len(rules) == 12


def test_burn_rate_rules_have_required_fields():
    rules = all_burn_rate_rules()
    for rule in rules:
        assert rule["alert"].endswith(("FastBurn", "SlowBurn", "VerySlowBurn"))
        assert "and" in rule["expr"]  # two-window expression joined with and
        assert "for" in rule
        assert rule["labels"]["severity"] in ("critical", "warning", "info")
        assert "summary" in rule["annotations"]
        assert rule["annotations"]["runbook_url"].startswith("https://")


def test_burn_rate_specs_match_google_sre_workbook():
    """The 3 specs must match the canonical Google SRE Workbook pattern."""
    fast, slow, very_slow = DEFAULT_BURN_RATE_SPECS
    # Fast burn: 14.4× over 1h short + 6× over 6h long
    assert fast.short_factor == 14.4
    assert fast.short_window == "5m"
    assert fast.long_factor == 6.0
    assert fast.long_window == "1h"
    assert fast.severity == "critical"
    # Slow burn
    assert slow.short_factor == 6.0
    assert slow.long_factor == 3.0
    assert slow.long_window == "6h"
    # Very slow burn
    assert very_slow.long_factor == 1.0
    assert very_slow.long_window == "24h"


def test_prometheus_rules_for_slo_emits_three_rules():
    catalog = default_slo_catalog()
    slo_def = catalog[0]
    sli = slo.DEFAULT_SLI_DATA_SOURCES[slo_def.name]
    rules = prometheus_rules_for_slo(slo_def, sli)
    assert len(rules) == 3


def test_burn_rate_yaml_is_valid():
    yaml_text = burn_rate_rules_yaml()
    parsed = yaml.safe_load(yaml_text)
    assert "groups" in parsed
    assert len(parsed["groups"]) == 1
    rules = parsed["groups"][0]["rules"]
    assert len(rules) == 12
    # Spot-check labels carry SLO metadata.
    assert rules[0]["labels"]["slo"] == "api_availability_99_9"


def test_disk_slo_yaml_is_in_sync_with_generator():
    """F2 fix-5 attempt-7 guardrail: the production-loaded disk YAML must
    match the generator output, otherwise Prometheus loads stale rules even
    though tests pass on the live generator.

    Regenerate locally with::

        python -c "from monitoring.slo import burn_rate_rules_yaml as g; \
            open('monitoring/prometheus-rules-slo.yml','w',encoding='utf-8').write(g())"
    """
    import os

    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "monitoring", "prometheus-rules-slo.yml",
    )
    if not os.path.isfile(yaml_path):
        # Skip if the disk artifact doesn't exist (e.g. minimal CI environments)
        pytest.skip(f"disk SLO YAML not present at {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        disk_text = f.read()
    generator_text = burn_rate_rules_yaml()

    # The generator and disk YAML should produce identical text. If they
    # diverge, the disk file is stale and Prometheus would load the wrong
    # rules.
    assert disk_text == generator_text, (
        f"monitoring/prometheus-rules-slo.yml is stale — generator output "
        f"differs from disk. Run:\n"
        f"  python -c \"from monitoring.slo import burn_rate_rules_yaml as g; "
        f"open('{yaml_path}','w',encoding='utf-8').write(g())\"\n"
        f"to regenerate."
    )

    # Belt-and-braces: assert the disk YAML contains the histogram-bucket
    # rules for the latency SLO (the F2 bug we fixed). If a future refactor
    # re-introduces the placeholder tautology, this fails before the disk
    # YAML even matters.
    parsed = yaml.safe_load(disk_text)
    rules = parsed["groups"][0]["rules"]
    latency_rules = [
        r for r in rules
        if r["labels"].get("slo") == "backend_p99_latency_300ms"
    ]
    assert len(latency_rules) == 3, (
        f"expected 3 backend_p99_latency_300ms rules in disk YAML, got "
        f"{len(latency_rules)}"
    )
    for r in latency_rules:
        expr = r["expr"]
        assert "http_request_duration_seconds_bucket" in expr, (
            f"latency rule {r['alert']} uses placeholder expression "
            f"(missing http_request_duration_seconds_bucket). F2 fix-1 "
            f"regression — disk YAML is stale."
        )
        assert "le=" in expr, (
            f"latency rule {r['alert']} expression missing le= bucket label."
        )


# --------------------------------------------------------------------------- #
# 5. SLO report / JSON serialization
# --------------------------------------------------------------------------- #
def test_slo_report_to_dict_round_trips():
    report = build_slo_report()
    d = report.to_dict()
    assert len(d["slos"]) == 4
    assert len(d["budgets"]) == 4
    assert "generated_at" in d
    text = json.dumps(d, ensure_ascii=False)
    parsed = json.loads(text)
    assert parsed["generated_at"] == d["generated_at"]


def test_slo_report_includes_zero_visibility_budgets_on_fresh_start():
    """On a fresh start (no events), every SLO should report valid=0."""
    report = build_slo_report()
    for name, budget in report.budgets.items():
        assert budget.valid_count == 0
        assert budget.compliant is True
        assert budget.burn_rate == 0.0


def test_api_slo_recorded_budget_reflects_outcomes():
    """10000 events, 8 bad → 99.92% success vs target 99.9% → compliant."""
    rec = get_recorder("api_availability_99_9", target=0.999)
    for _ in range(9992):
        rec.record_outcome(success=True)
    for _ in range(8):
        rec.record_outcome(success=False)
    report = build_slo_report()
    budget = report.budgets["api_availability_99_9"]
    assert budget.valid_count == 10000
    assert budget.good_count == 9992
    assert budget.compliant is True
    assert budget.burn_rate < 0.85


def test_api_slo_recorded_budget_over_budget_when_violating():
    """1000 events, 5 bad → 99.5% vs target 99.9% → budget exhausted."""
    rec = get_recorder("api_availability_99_9", target=0.999)
    for _ in range(995):
        rec.record_outcome(success=True)
    for _ in range(5):
        rec.record_outcome(success=False)
    report = build_slo_report()
    budget = report.budgets["api_availability_99_9"]
    assert budget.valid_count == 1000
    assert budget.bad_count == 5
    assert budget.compliant is False
    assert budget.burn_rate > 1.0


# --------------------------------------------------------------------------- #
# 6. F2 fix-5: Pluggable storage backend (multi-process safe)
# --------------------------------------------------------------------------- #
def test_in_memory_backend_round_trips_records():
    """InMemoryBackend is the default and preserves existing semantics.

    F2 fix-5 attempt-6: ``prune_older_than`` uses strict ``ts < cutoff_ts``
    semantics (records equal to the cutoff are retained). The test data uses
    timestamps 1000.0 (×10) and 1001.0 (×1), so:
      - cutoff 999.5  → 0 records deleted (none strictly older)
      - cutoff 1000.5 → 10 records deleted (the 10 at ts=1000.0)
      - cutoff 1001.5 → 1 record deleted  (the 1 at ts=1001.0)
    """
    from monitoring.recorder_backends import InMemoryBackend

    backend = InMemoryBackend()
    for _ in range(10):
        backend.append({"success": True, "latency_ms": 50.0, "ts": 1000.0})
    backend.append({"success": False, "latency_ms": 600.0, "ts": 1001.0})
    snap = backend.snapshot()
    assert len(snap) == 11
    assert snap[-1]["success"] is False
    assert backend.prune_older_than(999.5) == 0
    assert len(backend.snapshot()) == 11
    assert backend.prune_older_than(1000.5) == 10
    assert len(backend.snapshot()) == 1
    assert backend.snapshot()[0]["ts"] == 1001.0
    assert backend.prune_older_than(1001.5) == 1
    assert len(backend.snapshot()) == 0


def test_in_memory_backend_caps_max_records():
    from monitoring.recorder_backends import InMemoryBackend

    backend = InMemoryBackend()
    for i in range(50):
        backend.append({"ts": float(i)})
    deleted = backend.cap_max(10)
    assert deleted == 40
    assert len(backend.snapshot()) == 10


def test_recorder_with_in_memory_backend_matches_default():
    """SLORecorder.with_backend(InMemoryBackend) behaves like default recorder.

    F2 fix-5 attempt-6: the previous assertion ``target=0.999`` with 10 bad
    events / 1000 total was mathematically non-compliant (burn_rate=10×
    target). Switch to ``target=0.99`` which matches the 990/1000 success
    distribution — burn_rate ≈ 1.0, compliant.
    """
    from monitoring.recorder_backends import InMemoryBackend

    backend = InMemoryBackend()
    rec = SLORecorder.with_backend(
        "test_with_backend", backend,
        target=0.99, kind="availability", window_seconds=3600,
    )
    for _ in range(990):
        rec.record_outcome(success=True, latency_ms=120.0)
    for _ in range(10):
        rec.record_outcome(success=False, latency_ms=550.0)
    budget = rec.compute_budget()
    assert budget.valid_count == 1000
    assert budget.good_count == 990
    assert budget.compliant is True
    assert budget.burn_rate == pytest.approx(1.0, rel=1e-3)


def test_sqlite_backend_persists_across_backend_instances():
    """F2 fix-5: SQLiteBackend acts as a file-backed shared ring buffer.

    Simulates two processes sharing the same DB file by opening two
    separate backend instances against the same path and asserts that
    writes from one are visible to the other.
    """
    import os
    import tempfile
    from monitoring.recorder_backends import SQLiteBackend

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        # Process A: write 100 outcomes
        backend_a = SQLiteBackend(slo_name="api", db_path=path)
        for i in range(100):
            backend_a.append(
                {"success": True, "latency_ms": float(i), "ts": 1000.0 + i}
            )
        backend_a.close()
        # Process B: open a fresh backend against the same file
        backend_b = SQLiteBackend(slo_name="api", db_path=path)
        snap = backend_b.snapshot()
        assert len(snap) == 100
        assert snap[0]["latency_ms"] == 0.0
        assert snap[-1]["latency_ms"] == 99.0
        backend_b.close()
    finally:
        if os.path.exists(path):
            os.unlink(path)
        # WAL/SHM files
        for ext in ("-wal", "-shm"):
            p = path + ext
            if os.path.exists(p):
                os.unlink(p)


def test_recorder_with_sqlite_backend_persists_writes():
    """SLORecorder.with_backend(SQLiteBackend) writes through to SQLite."""
    import os
    import tempfile
    from monitoring.recorder_backends import SQLiteBackend

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        backend = SQLiteBackend(slo_name="api", db_path=path)
        rec = SLORecorder.with_backend(
            "api", backend, target=0.99, kind="availability",
        )
        for _ in range(50):
            rec.record_outcome(success=True, latency_ms=100.0)
        rec.record_outcome(success=False, latency_ms=500.0)
        # Reload via a fresh backend (simulates process restart)
        backend.close()
        backend2 = SQLiteBackend(slo_name="api", db_path=path)
        rec2 = SLORecorder.with_backend(
            "api", backend2, target=0.99, kind="availability",
        )
        snap = rec2.snapshot()
        assert len(snap) == 51
        budget = rec2.compute_budget()
        assert budget.valid_count == 51
        assert budget.good_count == 50
        backend2.close()
    finally:
        if os.path.exists(path):
            os.unlink(path)
        for ext in ("-wal", "-shm"):
            p = path + ext
            if os.path.exists(p):
                os.unlink(p)


def test_sqlite_backend_window_pruning_drops_old_records():
    """``record_outcome`` triggers ``prune_older_than`` so old rows vanish."""
    import os
    import tempfile
    from monitoring.recorder_backends import SQLiteBackend

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        backend = SQLiteBackend(slo_name="api", db_path=path)
        rec = SLORecorder.with_backend(
            "api", backend, target=0.999, kind="availability",
            window_seconds=60,
        )
        # Record events with explicit timestamps so the window pruning
        # has a deterministic cutoff.
        rec.record_outcome(success=True, latency_ms=50.0, timestamp=1000.0)
        rec.record_outcome(success=True, latency_ms=60.0, timestamp=1010.0)
        rec.record_outcome(success=True, latency_ms=70.0, timestamp=1080.0)
        # 1080 - 60 = 1020 cutoff; 1000 and 1010 are old.
        snap = rec.snapshot()
        assert len(snap) == 1
        assert snap[0]["ts"] == 1080.0
        backend.close()
    finally:
        if os.path.exists(path):
            os.unlink(path)
        for ext in ("-wal", "-shm"):
            p = path + ext
            if os.path.exists(p):
                os.unlink(p)
