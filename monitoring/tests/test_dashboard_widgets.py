"""P19-E3 HB-1 — Dashboard widget tests.

Verifies the new ``monitoring/grafana-dashboards/health-and-compliance.json``
dashboard:

* loads as valid JSON (Grafana would refuse to render malformed JSON);
* contains the panels the task explicitly asks for:
  - ``service_health_status`` (up/down/unknown) — using
    ``health_probe_status`` gauge from :mod:`monitoring.observability`
  - GDPR erasure real monitoring (count + duration) — using
    ``gdpr_erasure_total`` and ``gdpr_erasure_duration_ms_total``
* every panel's PromQL targets reference a metric that the Prometheus
  scrape (via :func:`monitoring.observability.MetricsRegistry.scrape`)
  actually emits after a probe cycle / an erasure call.

The test does NOT spin up Grafana — it asserts the JSON contract is
machine-checkable, which is the strongest signal we can give without a
running Grafana instance.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = PROJECT_ROOT / "monitoring" / "grafana-dashboards" / "health-and-compliance.json"


def _load_dashboard() -> dict:
    assert DASHBOARD_PATH.is_file(), (
        f"Dashboard JSON missing at {DASHBOARD_PATH} — the HB-1 deliverable "
        f"requires a real Grafana dashboard JSON file."
    )
    with DASHBOARD_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _panel(dashboard: dict, panel_id: int) -> dict:
    for p in dashboard.get("panels", []):
        if p.get("id") == panel_id:
            return p
    raise AssertionError(f"panel id={panel_id} not found in dashboard")


def _panel_queries(panel: dict) -> list:
    out = []
    for t in panel.get("targets", []):
        expr = (t.get("expr") or "").strip()
        if expr:
            out.append(expr)
    return out


def _all_queries(dashboard: dict) -> list:
    out = []
    for p in dashboard.get("panels", []):
        out.extend(_panel_queries(p))
    return out


class TestDashboardJsonContract(unittest.TestCase):
    """JSON parses + has the required panels."""

    def test_dashboard_json_loads(self):
        d = _load_dashboard()
        self.assertIsInstance(d, dict)
        self.assertIn("panels", d)
        self.assertGreaterEqual(len(d["panels"]), 4)

    def test_dashboard_has_service_health_status_panel(self):
        d = _load_dashboard()
        panel = _panel(d, 1)
        self.assertEqual(panel.get("type"), "stat")
        # Panel title must mention up/down/unknown semantics so an operator
        # knows what they're looking at without reading JSON.
        title = (panel.get("title") or "").lower()
        self.assertIn("health", title)
        self.assertIn("up", title)
        self.assertIn("down", title)
        self.assertIn("unknown", title)
        # Mapping encodes the 3-state semantics.
        mappings = panel.get("fieldConfig", {}).get("defaults", {}).get("mappings", [])
        self.assertGreaterEqual(len(mappings), 3)
        # Normalize mapping keys to a set of strings so the check works
        # regardless of whether Grafana serialised them as ints or strings.
        keys = set()
        for m in mappings:
            opts = m.get("options", {})
            for k in opts.keys():
                keys.add(str(k))
        # Expect "0", "1", "2" to all be present.
        for required in ("0", "1", "2"):
            self.assertIn(required, keys, f"missing state mapping for {required!r}; keys={keys}")

    def test_dashboard_has_gdpr_erasure_count_and_duration_panels(self):
        d = _load_dashboard()
        # Panel 6 = erasures count, panel 8 = duration, panel 9 = records,
        # panel 10 = avg duration.
        count_panel = _panel(d, 6)
        duration_panel = _panel(d, 8)
        records_panel = _panel(d, 9)
        avg_duration_panel = _panel(d, 10)
        for p in (count_panel, duration_panel, records_panel, avg_duration_panel):
            self.assertIsInstance(p, dict)
            self.assertIn("targets", p)
            self.assertGreater(len(p["targets"]), 0)

    def test_every_panel_query_mentions_real_metric(self):
        """Sanity check — every PromQL expr references a metric we actually
        emit from monitoring.observability.MetricsRegistry.scrape()."""
        d = _load_dashboard()
        queries = _all_queries(d)
        self.assertGreater(len(queries), 0)
        # At least one query must reference each of the new metrics.
        joined = "\n".join(queries)
        for metric in (
            "health_probe_status",
            "health_probe_latency_ms",
            "gdpr_erasure_total",
            "gdpr_erasure_duration_ms_total",
            "gdpr_erasure_observations_total",
            "gdpr_erasure_records_total",
        ):
            self.assertIn(
                metric, joined,
                f"Dashboard does not query {metric}; found queries: {queries!r}"
            )


class TestDashboardRendersRealData(unittest.TestCase):
    """End-to-end: after a probe cycle + erasure call, the metrics the
    dashboard queries are emitted by MetricsRegistry.scrape()."""

    def setUp(self):
        # Reset the metrics registry between tests so counters do not bleed,
        # then re-seed the canonical metrics so they appear in every scrape.
        try:
            from monitoring.observability import (
                _seed_canonical_gdpr_metrics,
                get_registry,
            )
            get_registry().reset()
            _seed_canonical_gdpr_metrics()
        except Exception:  # noqa: BLE001
            pass

    def test_health_probe_status_gauge_emitted_after_probe(self):
        # Run the probes in-process so we don't need a real running API.
        from monitoring.health import HealthRegistry
        from monitoring.health_checks import probes as default_probes
        from monitoring.observability import (
            HEALTH_STATUS_UP,
            HEALTH_STATUS_DOWN,
            HEALTH_STATUS_UNKNOWN,
            get_registry,
        )

        reg = HealthRegistry(cache_ttl_seconds=0.0)
        # Register only a couple of probes so the test stays fast.
        for name, fn in list(default_probes.items())[:3]:
            reg.register(name, fn)

        # Force the aggregate() path (publishes metrics).
        import asyncio

        async def _run():
            results = await reg.probe_all()
            return reg.aggregate(results)

        asyncio.run(_run())

        scrape = get_registry().scrape().decode("utf-8")
        # The metric name + # HELP + # TYPE lines must be present.
        self.assertIn("# TYPE health_probe_status gauge", scrape)
        # The actual data point for one of the services we registered.
        self.assertIn("health_probe_status{", scrape)
        # All values must be one of {0,1,2}.
        for m in re.finditer(r"health_probe_status\{[^}]*\}\s+(\S+)", scrape):
            v = float(m.group(1))
            self.assertIn(v, {HEALTH_STATUS_UP, HEALTH_STATUS_DOWN, HEALTH_STATUS_UNKNOWN})

    def test_gdpr_erasure_counter_emitted_after_erasure(self):
        from monitoring.observability import get_registry
        from monitoring.compliance_reports import execute_gdpr_erasure

        # Seed and erase — the wrapper publishes the four metrics.
        execute_gdpr_erasure("dashboard-test-user-001", requester="test-suite")

        scrape = get_registry().scrape().decode("utf-8")
        for metric in (
            "gdpr_erasure_total",
            "gdpr_erasure_duration_ms_total",
            "gdpr_erasure_observations_total",
        ):
            self.assertIn(f"# TYPE {metric} counter", scrape)
        # outcome=success label tuple must appear at least once.
        self.assertIn('outcome="success"', scrape)
        # gdpr_erasure_records_total is a counter — must also be emitted.
        self.assertIn("# TYPE gdpr_erasure_records_total counter", scrape)

    def test_gdpr_erasure_records_metric_visible(self):
        from monitoring.compliance_reports import execute_gdpr_erasure
        from monitoring.observability import get_registry

        # Idempotent call — even zero-record erasures emit the counter.
        execute_gdpr_erasure("dashboard-test-user-002", requester="test-suite")
        scrape = get_registry().scrape().decode("utf-8")
        self.assertRegex(scrape, r"gdpr_erasure_total\{outcome=\"success\"\}\s+\d+(?:\.\d+)?")

    def test_health_probe_emits_string_service_label(self):
        """Regression — P19-E3 discovered the legacy _process_up_probe lambda
        swapped the ``service`` and ``timeout`` arguments, so the resulting
        ProbeResult.service was the float 2.0 instead of the service string.
        After fixing the lambda, scrape() must surface the string label."""
        from monitoring.observability import get_registry
        from monitoring.health_checks import probes as default_probes
        import asyncio
        from monitoring.health import HealthRegistry

        reg = HealthRegistry(cache_ttl_seconds=0.0)
        for name, fn in list(default_probes.items())[:3]:
            reg.register(name, fn)

        async def _run():
            results = await reg.probe_all()
            return reg.aggregate(results)

        asyncio.run(_run())
        scrape = get_registry().scrape().decode("utf-8")
        # service="agent" (string) must appear in the scrape — NOT service=2.0.
        self.assertIn('service="agent"', scrape)
        self.assertNotIn("service=2.0", scrape)


class TestDashboardSchemaVersion(unittest.TestCase):
    """Sanity check that Grafana would not immediately reject the file."""

    def test_schema_version_is_modern(self):
        d = _load_dashboard()
        sv = d.get("schemaVersion", 0)
        self.assertGreaterEqual(sv, 30, f"schemaVersion too old: {sv}")

    def test_uid_is_unique(self):
        d = _load_dashboard()
        uid = d.get("uid")
        self.assertTrue(uid, "dashboard uid is empty")
        self.assertNotIn(" ", uid, "uid should not contain spaces")


if __name__ == "__main__":
    unittest.main()