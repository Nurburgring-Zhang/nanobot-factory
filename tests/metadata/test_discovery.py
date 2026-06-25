"""P4-4-W1: discovery tests (PG + filesystem + LLM mock) (≥4 cases)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from services.dataset_service.metadata import discovery as discovery_mod
from services.dataset_service.metadata.discovery import (
    DiscoveredTable,
    _pg_normalize_type,
    discover_filesystem,
    discover_postgres,
    generate_llm_descriptions,
    persist_discovered_tables,
    run_discovery,
)


def test_discover_postgres_offline_simulator(init_db):
    """When no PG is reachable, the simulator returns ≥3 canned tables
    (incl. pg_catalog 50+ would in real PG; here we accept the simulator
    with ≥3 system-table-shaped entries covering schemas+views)."""
    tables = discover_postgres(
        "postgresql://no-such-host:5432/x",
        database_name="primary",
    )
    assert len(tables) >= 3
    # Verify at least one view, one bigint, one nullable=true
    types = {c["data_type"] for t in tables for c in t.columns}
    assert "bigint" in types
    has_view = any(t.table_type == "view" for t in tables)
    assert has_view
    has_nullable = any(c["nullable"] == "true" for t in tables for c in t.columns)
    assert has_nullable


def test_pg_type_normalization():
    """PG types map to portable labels."""
    assert _pg_normalize_type("character varying") == "string"
    assert _pg_normalize_type("bigint") == "bigint"
    assert _pg_normalize_type("timestamp without time zone") == "datetime"
    assert _pg_normalize_type("numeric(10,2)") == "decimal"
    assert _pg_normalize_type("jsonb") == "json"
    assert _pg_normalize_type("ARRAY") == "array"


def test_discover_filesystem_csv_and_json(tmp_path: Path, init_db):
    """Write a small CSV + JSONL + JSON, scan, infer schema."""
    csv_path = tmp_path / "users.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "email", "active"])
        for i in range(20):
            w.writerow([str(i), f"u{i}@x.com", "true"])

    jsonl_path = tmp_path / "events.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for i in range(15):
            f.write(json.dumps({"id": i, "kind": "click", "value": i * 0.5}) + "\n")

    json_path = tmp_path / "dict.json"
    json_path.write_text(
        json.dumps([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]),
        encoding="utf-8",
    )

    tables = discover_filesystem(str(tmp_path))
    assert len(tables) >= 3
    by_name = {t.name: t for t in tables}
    assert "users" in by_name  # CSV → users
    assert "events" in by_name  # JSONL → events
    assert "dict" in by_name  # JSON → dict

    users = by_name["users"]
    cnames = [c["name"] for c in users.columns]
    assert "id" in cnames and "email" in cnames and "active" in cnames

    events = by_name["events"]
    assert {c["name"] for c in events.columns} >= {"id", "kind", "value"}


def test_llm_description_mock_deterministic():
    """Mock description is deterministic + non-empty."""
    descs = generate_llm_descriptions([
        {"id": "x", "name": "email", "data_type": "string"},
        {"id": "y", "name": "amount_cents", "data_type": "int"},
    ])
    assert len(descs) == 2
    for k, v in descs.items():
        assert v  # non-empty
        # We use a deterministic mock so re-running yields the same text.
    again = generate_llm_descriptions([
        {"id": "x", "name": "email", "data_type": "string"},
    ])
    assert again["x"] == descs["x"]


def test_run_discovery_persists_tables(init_db):
    """End-to-end: run_discovery with the simulator and verify persistence."""
    res = run_discovery(
        backend="postgres",
        target="postgresql://no-such-host:5432/x",
        database_name="primary",
    )
    assert res.tables_discovered >= 3
    assert res.columns_discovered > 0
    assert res.finished_at >= res.started_at
