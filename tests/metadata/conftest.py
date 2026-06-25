"""Shared pytest fixtures for P4-4-W1 metadata tests.

Goals:
  * Isolate each test to a fresh SQLite file under tmp_path
    (monkeypatch METADATA_DB_URL → tmp/metadata.db).
  * Wipe the global view-store + schedule-store between tests.
  * Provide a FastAPI TestClient for ``metadata.routes``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# Make backend/ importable when running ``pytest tests/metadata`` from project root
_BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


@pytest.fixture(autouse=True)
def _isolate_metadata_db(tmp_path, monkeypatch):
    """Per-test fresh SQLite database for metadata."""
    db_dir = tmp_path / "metadata_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "metadata.db"
    monkeypatch.setenv("METADATA_DB_URL", f"sqlite:///{db_file.as_posix()}")
    # Reset cached engine + view store before each test
    from services.dataset_service.metadata import models as _models
    from services.dataset_service.metadata import search as _search
    from services.dataset_service.metadata import discovery as _discovery

    _models.reset_metadata_engine()
    _search.reset_view_store()
    _discovery._SCHEDULES.clear()
    yield
    _models.reset_metadata_engine()


@pytest.fixture
def init_db():
    """Initialise metadata DB and return the engine (also yields session)."""
    from services.dataset_service.metadata.models import init_metadata_db

    eng = init_metadata_db()
    return eng


@pytest.fixture
def metadata_client():
    """FastAPI TestClient for the metadata sub-router."""
    from fastapi.testclient import TestClient

    from services.dataset_service.metadata import models as _models
    _models.init_metadata_db()

    from services.dataset_service.metadata.routes import router

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def seeded_metadata(init_db):
    """Pre-populate the metadata DB with a tiny dataset (1 db, 2 schemas,
    3 tables, 9 columns) so tests can exercise search/glossary/PII."""
    from services.dataset_service.metadata.models import (
        ColumnORM, DatabaseORM, DatabaseSchemaORM, TableORM,
        get_metadata_session,
    )

    with get_metadata_session() as s:
        db = DatabaseORM(name="primary", service="postgres")
        s.add(db); s.flush()
        sch_pub = DatabaseSchemaORM(database_id=db.id, name="public")
        sch_an = DatabaseSchemaORM(database_id=db.id, name="analytics")
        s.add_all([sch_pub, sch_an]); s.flush()

        t_users = TableORM(schema_id=sch_pub.id, name="users",
                            description="End users of the platform")
        t_orders = TableORM(schema_id=sch_pub.id, name="orders",
                             description="Orders placed by users")
        t_daily = TableORM(schema_id=sch_an.id, name="daily_revenue",
                            table_type="view",
                            description="Aggregated daily revenue")
        s.add_all([t_users, t_orders, t_daily]); s.flush()

        s.add_all([
            ColumnORM(table_id=t_users.id, name="id", data_type="bigint",
                       nullable="false", ordinal="1"),
            ColumnORM(table_id=t_users.id, name="email", data_type="string",
                       nullable="false", ordinal="2"),
            ColumnORM(table_id=t_users.id, name="phone", data_type="string",
                       nullable="true", ordinal="3"),
            ColumnORM(table_id=t_users.id, name="real_name", data_type="string",
                       nullable="true", ordinal="4"),

            ColumnORM(table_id=t_orders.id, name="id", data_type="bigint",
                       nullable="false", ordinal="1"),
            ColumnORM(table_id=t_orders.id, name="user_id", data_type="bigint",
                       nullable="false", ordinal="2"),
            ColumnORM(table_id=t_orders.id, name="amount_cents", data_type="int",
                       nullable="false", ordinal="3"),

            ColumnORM(table_id=t_daily.id, name="day", data_type="date",
                       nullable="false", ordinal="1"),
            ColumnORM(table_id=t_daily.id, name="total_cents", data_type="bigint",
                       nullable="false", ordinal="2"),
        ])
        s.commit()

    return {
        "database_name": "primary",
        "schema_public_id": sch_pub.id,
        "schema_analytics_id": sch_an.id,
        "table_ids": {
            "users": t_users.id,
            "orders": t_orders.id,
            "daily_revenue": t_daily.id,
        },
    }
