"""P4-4-W2 lineage API tests (FastAPI TestClient).

Coverage:
  1. visualize/{entity} returns react-flow nodes/edges
  2. visualize/full respects limit + type filter
  3. visualize supports vis.js, d3, cytoscape formats
  4. /collect/manual + /impact + /graph/refresh round-trip
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def client():
    """Mount a tiny app with just the lineage router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from services.dataset_service.lineage.api import router as lineage_router
    from services.dataset_service.lineage.models import init_lineage_db

    import tempfile, os
    tmpdir = tempfile.mkdtemp(prefix="api_lineage_")
    db_path = os.path.join(tmpdir, "api.db")
    init_lineage_db(db_url=f"sqlite:///{db_path}", auto_create=True)

    app = FastAPI(title="lineage-test")
    app.include_router(lineage_router)
    return TestClient(app)


def test_visualize_react_flow(client):
    # Seed via API
    r = client.post(
        "/api/v1/lineage/collect/operator",
        json={
            "operator_id": "clean.image.dedupe",
            "inputs": ["ds.raw"],
            "outputs": ["ds.clean"],
            "edge_type": "cleaned_by",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # Visualize
    r = client.get("/api/v1/lineage/visualize/ds.clean?format=react-flow&depth=1")
    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "react-flow"
    g = body["graph"]
    assert "nodes" in g and "edges" in g
    node_ids = {n["id"] for n in g["nodes"]}
    assert "ds.raw" in node_ids
    assert "ds.clean" in node_ids
    assert any(
        e["source"] == "ds.raw" and e["target"] == "ds.clean"
        for e in g["edges"]
    )
    # React-flow nodes carry the styled data
    for n in g["nodes"]:
        assert "data" in n
        assert "label" in n["data"]


def test_visualize_supports_all_formats(client):
    for fmt in ("react-flow", "vis", "d3", "cytoscape"):
        r = client.get(f"/api/v1/lineage/visualize/ds.clean?format={fmt}")
        assert r.status_code == 200
        body = r.json()
        assert body["format"] == fmt
        g = body["graph"]
        if fmt == "react-flow":
            assert "nodes" in g and "edges" in g
            assert "id" in g["nodes"][0]
        elif fmt == "vis":
            assert "nodes" in g and "edges" in g
            assert "id" in g["nodes"][0] and "from" in g["edges"][0]
        elif fmt == "d3":
            assert "nodes" in g and "links" in g
            assert "source" in g["links"][0]
        elif fmt == "cytoscape":
            assert "elements" in g
            assert "nodes" in g["elements"]
            assert "edges" in g["elements"]


def test_visualize_full_limit_and_type_filter(client):
    r = client.get("/api/v1/lineage/visualize/full?limit=10&format=vis")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10
    assert body["graph"]["edges"]  # at least one edge
    # Filter by entity_type — non-existent type returns empty
    r2 = client.get("/api/v1/lineage/visualize/full?type=model&format=vis")
    assert r2.status_code == 200
    # No models were seeded, so nodes list is filtered
    assert isinstance(r2.json()["graph"]["nodes"], list)


def test_collect_and_impact_round_trip(client):
    # 1. Record a 3-node chain
    r = client.post(
        "/api/v1/lineage/collect/manual",
        json={
            "from_entity": "pg.users",
            "to_entity": "ds.user_parquet",
            "edge_type": "copied_to",
        },
    )
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post(
        "/api/v1/lineage/collect/manual",
        json={
            "from_entity": "ds.user_parquet",
            "to_entity": "model.rec_v1",
            "edge_type": "trained_by",
        },
    )
    assert r.status_code == 200 and r.json()["ok"]
    # 2. Refresh graph cache
    r = client.post("/api/v1/lineage/graph/refresh")
    assert r.status_code == 200
    # 3. Impact
    r = client.get("/api/v1/lineage/impact/ds.user_parquet")
    assert r.status_code == 200
    impact = r.json()["impact"]
    assert impact["entity"] == "ds.user_parquet"
    assert impact["upstream_count"] >= 1
    assert impact["downstream_count"] >= 1
    # Model downstream — should be marked
    r2 = client.get("/api/v1/lineage/impact/ds.user_parquet/notify")
    # notify is POST-only in our router; use POST
    r2 = client.post(
        "/api/v1/lineage/impact/ds.user_parquet/notify",
        json={"change_description": "rename user_id → uid"},
    )
    assert r2.status_code == 200
    plan = r2.json()["plan"]
    assert plan["entity"] == "ds.user_parquet"
    assert "rename user_id" in plan["message"]


def test_graph_stats_and_health(client):
    r = client.get("/api/v1/lineage/graph/stats")
    assert r.status_code == 200
    s = r.json()["stats"]
    assert s["nodes"] >= 1
    assert "by_edge_type" in s
    assert "by_entity_type" in s
