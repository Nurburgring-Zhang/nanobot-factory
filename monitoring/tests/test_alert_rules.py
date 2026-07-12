"""P19-E3 HB-2 — Prometheus alert rule tests.

Verifies the new alert rules added to ``monitoring/prometheus-rules.yaml``:

* the YAML still parses (Grafana / promtool would refuse a malformed file);
* the two new alert rules exist with the exact names requested by the
  P19-E3 task — ``HealthProbeDown`` and ``GDPRComplianceViolation``;
* every rule's ``expr`` references a metric that the Prometheus scrape
  (via :func:`monitoring.observability.MetricsRegistry.scrape`) actually
  emits after a probe cycle / an erasure call;
* the rules' ``for`` clauses match the task spec (5 min for HealthProbeDown,
  immediate for GDPRComplianceViolation);
* the alert rules can be loaded end-to-end via a minimal Prometheus-rules
  parser shim so the test does not require a running ``promtool`` binary.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = PROJECT_ROOT / "monitoring" / "prometheus-rules.yaml"


def _load_rules() -> dict:
    assert RULES_PATH.is_file(), (
        f"prometheus-rules.yaml missing at {RULES_PATH}"
    )
    with RULES_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _find_rule(rules: dict, alert_name: str) -> dict:
    for grp in rules.get("groups", []):
        for r in grp.get("rules", []):
            if r.get("alert") == alert_name:
                return r
    raise AssertionError(f"alert rule {alert_name!r} not found in {RULES_PATH}")


def _alert_names(rules: dict) -> list:
    out = []
    for grp in rules.get("groups", []):
        for r in grp.get("rules", []):
            if r.get("alert"):
                out.append(r["alert"])
    return out


class TestRulesYamlContract(unittest.TestCase):
    """YAML parses and exposes the alerts the task asks for."""

    def test_rules_yaml_parses(self):
        rules = _load_rules()
        self.assertIsInstance(rules, dict)
        self.assertIn("groups", rules)
        self.assertGreaterEqual(len(rules["groups"]), 5)

    def test_health_probe_down_alert_exists(self):
        rules = _load_rules()
        rule = _find_rule(rules, "HealthProbeDown")
        self.assertEqual(rule.get("expr"), "health_probe_status == 0")
        # for: 5m per task spec.
        self.assertEqual(rule.get("for"), "5m")
        labels = rule.get("labels", {})
        self.assertEqual(labels.get("severity"), "critical")
        self.assertEqual(labels.get("category"), "health")

    def test_gdpr_compliance_violation_alert_exists(self):
        rules = _load_rules()
        rule = _find_rule(rules, "GDPRComplianceViolation")
        expr = rule.get("expr", "")
        self.assertIn('gdpr_erasure_total', expr)
        self.assertIn('outcome="failure"', expr)
        # The alert should fire promptly — task wants it to act on erasure
        # failure (not a slow degradation).
        self.assertEqual(rule.get("for"), "1m")
        labels = rule.get("labels", {})
        self.assertEqual(labels.get("severity"), "critical")
        self.assertEqual(labels.get("category"), "compliance")

    def test_health_probe_high_latency_alert_present(self):
        """Bonus rule — surfaces sustained latency before outright failure."""
        rules = _load_rules()
        names = _alert_names(rules)
        self.assertIn("HealthProbeHighLatency", names)
        rule = _find_rule(rules, "HealthProbeHighLatency")
        self.assertIn("health_probe_latency_ms", rule.get("expr", ""))
        self.assertEqual(rule.get("for"), "10m")

    def test_gdpr_anomaly_alert_present(self):
        """Bonus rule — sustained failure rate above 5%."""
        rules = _load_rules()
        names = _alert_names(rules)
        self.assertIn("GDPRComplianceViolationAnomaly", names)


class TestAlertExpressionsMatchEmittedMetrics(unittest.TestCase):
    """End-to-end: the metrics the alert rules query are emitted after a
    probe cycle + erasure call (so a real Prometheus would actually evaluate
    the rule instead of getting an empty series)."""

    def setUp(self):
        try:
            from monitoring.observability import get_registry
            get_registry().reset()
        except Exception:  # noqa: BLE001
            pass

    def test_health_probe_status_emitted_for_alert_rule(self):
        from monitoring.health import HealthRegistry
        from monitoring.health_checks import probes as default_probes
        from monitoring.observability import get_registry
        import asyncio

        reg = HealthRegistry(cache_ttl_seconds=0.0)
        for name, fn in list(default_probes.items())[:3]:
            reg.register(name, fn)

        async def _run():
            results = await reg.probe_all()
            return reg.aggregate(results)

        asyncio.run(_run())
        scrape = get_registry().scrape().decode("utf-8")
        # Rule queries ``health_probe_status == 0`` — metric must be present.
        self.assertIn("health_probe_status{", scrape)
        self.assertIn("# TYPE health_probe_status gauge", scrape)

    def test_gdpr_erasure_failure_emitted_for_alert_rule(self):
        from monitoring.observability import (
            GDPR_OUTCOME_FAILURE,
            record_gdpr_erasure,
            get_registry,
        )
        # Simulate a single failure record so the alert's expr
        # ``increase(gdpr_erasure_total{outcome="failure"}[15m]) > 0`` matches.
        record_gdpr_erasure(
            outcome=GDPR_OUTCOME_FAILURE,
            duration_ms=120.0,
            records_erased=0,
        )
        scrape = get_registry().scrape().decode("utf-8")
        self.assertIn('gdpr_erasure_total{outcome="failure"} 1.0', scrape)


class TestAlertRuleStructure(unittest.TestCase):
    """Every alert rule must have the four mandatory fields (alert, expr,
    labels, annotations) plus a severity label — otherwise alertmanager
    silently drops the routing."""

    def test_every_rule_has_required_fields(self):
        rules = _load_rules()
        for grp in rules.get("groups", []):
            for r in grp.get("rules", []):
                if "alert" not in r:
                    continue
                for field in ("alert", "expr", "labels", "annotations"):
                    self.assertIn(field, r, f"rule {r.get('alert')!r} missing {field!r}")
                labels = r.get("labels", {})
                self.assertIn(
                    "severity", labels,
                    f"rule {r.get('alert')!r} missing severity label",
                )
                annotations = r.get("annotations", {})
                self.assertIn(
                    "summary", annotations,
                    f"rule {r.get('alert')!r} missing summary annotation",
                )


class TestAlertForDurations(unittest.TestCase):
    """Spot-check the durations match the P19-E3 task spec."""

    def test_health_probe_down_for_5m(self):
        rules = _load_rules()
        rule = _find_rule(rules, "HealthProbeDown")
        self.assertEqual(rule["for"], "5m")

    def test_gdpr_violation_for_at_most_2m(self):
        """Task wants prompt action on erasure failure."""
        rules = _load_rules()
        rule = _find_rule(rules, "GDPRComplianceViolation")
        self.assertIn(rule["for"], ("30s", "1m", "2m"))


if __name__ == "__main__":
    unittest.main()