"""P4-4-W2 impact analysis tests.

Coverage:
  1. Upstream / downstream traversal correctness
  2. Risk score: zero (isolated), low (1 team), medium (3 teams), high (model)
  3. Notification plan: lists all owners/teams
  4. Risk level classification (low / medium / high)
"""
from __future__ import annotations

import pytest


def _build_complex_graph(lineage_db_url):
    """raw → cleaned → feature → trained_model → reports
    Two teams consume the model.
    """
    from services.dataset_service.lineage import collector
    from services.dataset_service.lineage.models import AssetORM, get_lineage_session

    collector.record_operator(
        operator_id="clean.image.dedupe",
        inputs=["s3://raw/images"],
        outputs=["s3://clean/images"],
        edge_type="cleaned_by",
    )
    collector.record_operator(
        operator_id="feature.extract",
        inputs=["s3://clean/images"],
        outputs=["s3://features/v1"],
        edge_type="derived_from",
    )
    collector.record_manual(
        from_entity="s3://features/v1",
        to_entity="model.classifier_v3",
        edge_type="trained_by",
    )
    collector.record_operator(
        operator_id="eval.svc",
        inputs=["model.classifier_v3"],
        outputs=["s3://reports/eval"],
        edge_type="scored_by",
    )
    collector.record_operator(
        operator_id="dashboard.svc",
        inputs=["model.classifier_v3"],
        outputs=["s3://reports/dashboard"],
        edge_type="scored_by",
    )

    # Tag teams + owners on downstream assets
    db = get_lineage_session()
    try:
        for qn, team, owner in [
            ("s3://reports/eval", "ml-platform", "alice@corp"),
            ("s3://reports/dashboard", "growth", "bob@corp"),
            ("model.classifier_v3", "ml-research", "carol@corp"),
        ]:
            a = (
                db.query(AssetORM)
                .filter(AssetORM.qualified_name == qn)
                .one_or_none()
            )
            if a is not None:
                a.team = team
                a.owner = owner
        db.commit()
    finally:
        db.close()


# ── 1. Upstream / downstream traversal ──────────────────────────────────────
def test_impact_upstream_and_downstream(lineage_db_url):
    from services.dataset_service.lineage.impact import get_analyzer
    from services.dataset_service.lineage.graph import get_graph

    _build_complex_graph(lineage_db_url)
    g = get_graph()
    g.refresh()
    a = get_analyzer()

    # Model has 1 upstream (features), 2 downstream (eval, dashboard)
    up = a.upstream("model.classifier_v3")
    assert any(n["qualified_name"] == "s3://features/v1" for n in up)
    down = a.downstream("model.classifier_v3")
    assert {n["qualified_name"] for n in down} >= {
        "s3://reports/eval",
        "s3://reports/dashboard",
    }


# ── 2. Risk scoring (medium: 2 teams, 1 model) ─────────────────────────────
def test_impact_risk_score(lineage_db_url):
    from services.dataset_service.lineage.impact import get_analyzer
    from services.dataset_service.lineage.graph import get_graph

    _build_complex_graph(lineage_db_url)
    g = get_graph()
    g.refresh()
    a = get_analyzer()
    report = a.full_impact("s3://features/v1")
    # 1 model + 2 reports + 2 teams = significant
    assert report.has_model is True
    assert report.risk_score >= 30
    assert report.risk_level in ("medium", "high")
    # 2 distinct teams downstream
    assert set(report.affected_teams) >= {"ml-platform", "growth"}


# ── 3. Risk level low for an isolated asset ─────────────────────────────────
def test_impact_isolated_asset_low_risk(lineage_db_url):
    from services.dataset_service.lineage.impact import get_analyzer
    from services.dataset_service.lineage import collector
    from services.dataset_service.lineage.graph import get_graph

    # Build a separate tiny graph
    collector.record_manual(
        from_entity="ds.lonely",
        to_entity="ds.lonely_consumer",
        edge_type="copied_to",
    )
    get_graph().refresh()
    report = get_analyzer().full_impact("ds.lonely")
    assert report.risk_level == "low"
    assert report.has_model is False


# ── 4. Notification plan ────────────────────────────────────────────────────
def test_impact_notification_plan(lineage_db_url):
    from services.dataset_service.lineage.impact import get_analyzer
    from services.dataset_service.lineage.graph import get_graph

    _build_complex_graph(lineage_db_url)
    get_graph().refresh()
    plan = get_analyzer().build_notification(
        "s3://features/v1", change_description="schema change to user_id"
    )
    assert plan.entity == "s3://features/v1"
    assert plan.notification_id
    # At least the model owner + the 2 report owners/teams
    teams_in_plan = {r["team"] for r in plan.recipients}
    assert "ml-platform" in teams_in_plan
    assert "growth" in teams_in_plan
    assert "schema change" in plan.message
    assert "Risk:" in plan.message
