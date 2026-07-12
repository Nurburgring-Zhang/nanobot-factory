"""Layer 10 — Quality tracking tests."""

from __future__ import annotations

import pytest

from monitoring import quality_tracking as q_mod
from monitoring.quality_tracking import cohens_kappa


@pytest.fixture(autouse=True)
def _reset_tracker():
    q_mod._TRACKER = None
    yield
    q_mod._TRACKER = None


def test_cohens_kappa_perfect_agreement():
    k = cohens_kappa([1, 0, 1, 0], [1, 0, 1, 0])
    assert k == 1.0


def test_cohens_kappa_no_agreement():
    k = cohens_kappa([1, 1, 0, 0], [0, 0, 1, 1])
    assert k == -1.0


def test_cohens_kappa_empty():
    assert cohens_kappa([], []) != cohens_kappa([], [])  # NaN


def test_record_appends():
    t = q_mod.QualityTracker()
    rec = t.record(annotator_id="a1", item_id="i1", label=1, score=0.9)
    assert rec.score == 0.9
    assert len(t.buffer) == 1


def test_drift_detected_when_recent_drops():
    t = q_mod.QualityTracker(drift_window=10, drift_threshold=0.05)
    # Baseline: high scores
    for _ in range(20):
        t.record(annotator_id="a1", item_id=f"old-{_}", label=1, score=0.9)
    # Recent: low scores
    for _ in range(20):
        t.record(annotator_id="a1", item_id=f"new-{_}", label=0, score=0.5)
    rep = t.drift_report()
    assert rep["drift_detected"] is True
    assert rep["delta"] > 0.05


def test_drift_not_detected_when_no_change():
    t = q_mod.QualityTracker(drift_window=10, drift_threshold=0.5)
    for i in range(40):
        t.record(annotator_id="a1", item_id=f"x-{i}", label=1, score=0.8)
    rep = t.drift_report()
    assert rep["drift_detected"] is False


def test_drift_insufficient_data():
    t = q_mod.QualityTracker()
    rep = t.drift_report()
    assert rep["drift_detected"] is False
    assert rep["reason"] == "insufficient-data"


def test_agreement_report_shape():
    t = q_mod.QualityTracker()
    # Two annotators, 20 items each, identical labels
    for i in range(20):
        t.record(annotator_id="a1", item_id=f"i-{i}", label=i % 2, score=0.9)
        t.record(annotator_id="a2", item_id=f"i-{i}", label=i % 2, score=0.9)
    rep = t.agreement()
    assert rep["kappa"] == 1.0
    assert rep["items_compared"] == 20


def test_per_annotator_aggregation():
    t = q_mod.QualityTracker()
    t.record(annotator_id="a1", item_id="x", label=1, score=0.9)
    t.record(annotator_id="a1", item_id="y", label=1, score=0.7)
    t.record(annotator_id="a2", item_id="z", label=0, score=0.5)
    rows = t.per_annotator()
    assert len(rows) == 2
    by_id = {r["annotator_id"]: r for r in rows}
    assert by_id["a1"]["count"] == 2
    assert abs(by_id["a1"]["avg_score"] - 0.8) < 1e-6
