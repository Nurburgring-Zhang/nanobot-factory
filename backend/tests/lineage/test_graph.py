"""P4-4-W2 asset graph tests.

Coverage:
  1. Build graph from a few edges, check node/edge counts
  2. Upstream / downstream traversal
  3. Stats by edge_type / entity_type
  4. Refresh after new edge is added
"""
from __future__ import annotations

import pytest


def _seed(lineage_db_url):
    """Plant a small lineage graph for tests:

        raw_a ──┐
                ├──> merged ──> model
        raw_b ──┘            │
                             └──> report
    """
    from services.dataset_service.lineage import collector

    # Two clean ops producing merged
    collector.record_operator(
        operator_id="merge.step",
        inputs=["ds.raw_a", "ds.raw_b"],
        outputs=["ds.merged"],
        edge_type="derived_from",
    )
    # Trained model from merged
    collector.record_manual(
        from_entity="ds.merged",
        to_entity="model.scoring_v1",
        edge_type="trained_by",
    )
    # Two consumers of model
    collector.record_operator(
        operator_id="eval.service",
        inputs=["model.scoring_v1"],
        outputs=["ds.eval_report"],
        edge_type="scored_by",
    )
    collector.record_operator(
        operator_id="report.gen",
        inputs=["model.scoring_v1"],
        outputs=["ds.daily_report"],
        edge_type="scored_by",
    )


def test_graph_build_and_counts(lineage_db_url):
    from services.dataset_service.lineage.graph import get_graph

    _seed(lineage_db_url)
    g = get_graph()
    g.refresh()
    s = g.stats()
    assert s["nodes"] == 6  # raw_a, raw_b, merged, model, eval_report, daily_report
    assert s["edges"] == 5
    # Two derived_from edges: raw_a→merged AND raw_b→merged (merge op)
    assert s["by_edge_type"].get("derived_from") == 2
    assert s["by_edge_type"].get("trained_by") == 1
    assert s["by_edge_type"].get("scored_by") == 2


def test_upstream_and_downstream(lineage_db_url):
    from services.dataset_service.lineage.graph import get_graph

    _seed(lineage_db_url)
    g = get_graph()
    g.refresh()

    # model.scoring_v1 has 2 upstream (merged) and 2 downstream (eval, report)
    up = g.neighbors_upstream("model.scoring_v1")
    assert any(n["qualified_name"] == "ds.merged" for n in up)
    down = g.neighbors_downstream("model.scoring_v1")
    assert {n["qualified_name"] for n in down} >= {
        "ds.eval_report",
        "ds.daily_report",
    }

    # ds.merged has 2 upstream (raw_a, raw_b)
    up_merged = g.neighbors_upstream("ds.merged")
    assert {n["qualified_name"] for n in up_merged} >= {"ds.raw_a", "ds.raw_b"}


def test_graph_node_and_edges_of(lineage_db_url):
    from services.dataset_service.lineage.graph import get_graph

    _seed(lineage_db_url)
    g = get_graph()
    g.refresh()
    node = g.node("ds.merged")
    assert node is not None
    assert node["qualified_name"] == "ds.merged"
    edges = g.edges_of("ds.merged")
    # 2 incoming (raw_a, raw_b) + 1 outgoing (model) = 3
    assert len(edges) >= 3


def test_graph_refresh_picks_up_new_edges(lineage_db_url):
    from services.dataset_service.lineage import collector
    from services.dataset_service.lineage.graph import get_graph

    _seed(lineage_db_url)
    g = get_graph()
    g.refresh()
    before = g.stats()["edges"]
    # Add a new edge after the initial refresh
    collector.record_manual(
        from_entity="ds.raw_a",
        to_entity="ds.audit_log",
        edge_type="copied_to",
    )
    g.refresh()
    after = g.stats()["edges"]
    assert after == before + 1
    # The new edge shows up in the right spot
    edges = g.edges_of("ds.raw_a")
    assert any(
        e["to"] == "ds.audit_log" and e["edge_type"] == "copied_to"
        for e in edges
    )
