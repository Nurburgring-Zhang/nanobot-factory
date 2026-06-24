"""P4-4-W2 lineage collector tests.

Coverage:
  1. SQL parser (sqlglot) — table-level + column-level
  2. SQL collect (one-shot persist) — dedup
  3. Python AST parser — read/write/derive
  4. Operator hook — record_operator
  5. Manual entry — record_manual
"""
from __future__ import annotations

import pytest


# ── 1. SQL parser ────────────────────────────────────────────────────────────
def test_parse_sql_table_join(lineage_db_url):
    """SELECT user.*, order.id FROM user JOIN order → user.id → user_order_join.user_id"""
    from services.dataset_service.lineage.collector import parse_sql_lineage

    sql = """
        SELECT user.id AS user_id, order.id AS order_id
        FROM public.user
        JOIN public."order" ON user.id = order.user_id
    """
    parsed = parse_sql_lineage(sql, target_entity="public.user_order_join")
    assert parsed["ok"] is True
    srcs = parsed["source_tables"]
    assert "public.user" in srcs
    assert 'public."order"' in srcs or "public.order" in srcs
    assert parsed["target_table"] == "public.user_order_join"
    cols = parsed["column_edges"]
    assert any(c["from"] == "user.id" for c in cols), cols
    assert any(c["to"].endswith("user_id") for c in cols), cols


def test_collect_from_sql_persists(lineage_db_url):
    from services.dataset_service.lineage import collector
    from services.dataset_service.lineage.models import EdgeORM, get_lineage_session

    sql = "SELECT * FROM analytics.events JOIN analytics.users ON events.user_id = users.id"
    res = collector.collect_from_sql(
        sql=sql, target_entity="analytics.events_with_user"
    )
    assert res.ok is True
    assert res.edges_added >= 2
    # Persisted in DB
    db = get_lineage_session()
    try:
        edges = db.query(EdgeORM).all()
        assert len(edges) >= 2
    finally:
        db.close()
    # Re-running is idempotent (dedup)
    res2 = collector.collect_from_sql(
        sql=sql, target_entity="analytics.events_with_user"
    )
    assert res2.edges_added == 0
    assert res2.edges_skipped >= 2


# ── 2. SQL parser (CTE) ─────────────────────────────────────────────────────
def test_parse_sql_with_cte(lineage_db_url):
    from services.dataset_service.lineage.collector import parse_sql_lineage

    sql = """
        WITH user_stats AS (
            SELECT user_id, COUNT(*) AS cnt FROM public.events GROUP BY user_id
        )
        SELECT u.id, s.cnt FROM public.user u JOIN user_stats s ON u.id = s.user_id
    """
    parsed = parse_sql_lineage(sql, target_entity="public.user_with_stats")
    assert parsed["ok"] is True
    assert "public.events" in parsed["source_tables"]
    assert "public.user" in parsed["source_tables"]


# ── 3. Python AST parser ─────────────────────────────────────────────────────
def test_parse_python_pandas(lineage_db_url):
    from services.dataset_service.lineage.collector import parse_python_lineage

    script = (
        "import pandas as pd\n"
        "df1 = pd.read_csv('data/raw.csv')\n"
        "df2 = pd.read_parquet('data/aux.parquet')\n"
        "merged = df1.merge(df2, on='user_id')\n"
        "out = merged.assign(total=merged.x + merged.y)\n"
        "out.to_parquet('data/out.parquet')\n"
    )
    parsed = parse_python_lineage(script, target_entity="data/out.parquet")
    assert parsed["ok"] is True
    assert "data/raw.csv" in parsed["reads"]
    assert "data/aux.parquet" in parsed["reads"]
    assert "data/out.parquet" in parsed["writes"]


# ── 4. Operator hook ────────────────────────────────────────────────────────
def test_record_operator(lineage_db_url):
    from services.dataset_service.lineage import collector
    from services.dataset_service.lineage.models import EdgeORM, AssetORM, get_lineage_session

    res = collector.record_operator(
        operator_id="clean.image.dedupe",
        inputs=["ds.images_raw"],
        outputs=["ds.images_deduped"],
        edge_type="cleaned_by",
    )
    assert res.ok is True
    assert res.edges_added == 1
    # Verify both assets + the edge were persisted
    db = get_lineage_session()
    try:
        assets = db.query(AssetORM).all()
        assert {a.qualified_name for a in assets} >= {
            "ds.images_raw",
            "ds.images_deduped",
        }
        edge = db.query(EdgeORM).one()
        assert edge.edge_type == "cleaned_by"
        assert edge.source == "operator"
    finally:
        db.close()


# ── 5. Manual entry ─────────────────────────────────────────────────────────
def test_record_manual(lineage_db_url):
    from services.dataset_service.lineage import collector

    res = collector.record_manual(
        from_entity="pg.public.user",
        to_entity="ds.user_parquet",
        edge_type="copied_to",
        note="daily ETL",
    )
    assert res.ok is True
    assert res.edges_added == 1
    assert res.assets_added == 2
    # Duplicate is a no-op
    res2 = collector.record_manual(
        from_entity="pg.public.user",
        to_entity="ds.user_parquet",
        edge_type="copied_to",
    )
    assert res2.ok is True
    assert res2.edges_added == 0
    assert res2.edges_skipped == 1
