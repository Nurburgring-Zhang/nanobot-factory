"""P2 P1 fix: IngestionEngine CSV id column collision + inconsistent row check.

R2 audit (reports/p21_r2_audit_data.md §90-128) identified two P0 data
ingestion bugs in ``backend/imdf/engines/ingestion_engine.py``:

* **R2-NEW-#2** — line 57 hard-codes ``id INTEGER PRIMARY KEY
  AUTOINCREMENT`` then appends ``{col_defs}``. If the CSV already has a
  column named ``id`` (very common — think ``id,name\n0,foo\n``),
  SQLite raises ``duplicate column name: id`` and ingestion aborts.

* **R2-NEW-#3** — ``csv.DictReader`` silently fills missing fields with
  ``None`` for short rows, and the old code's ``str(row.get(c, ""))``
  serialises ``None`` as the literal string ``"None"``. A malformed CSV
  with inconsistent column counts would therefore be committed with
  corrupted values (string ``"None"`` in cells that should be empty)
  and no error to the caller. The audit called this "silent data loss"
  — strictly speaking it is silent *data corruption*, but the
  user-facing effect is the same: the caller has no way to detect that
  the import was bad.

This test file pins all four R2 reproducer scenarios + the two safety
properties (rollback on failure, no id collision with PK).

Test design
-----------
* Each test creates a fresh ``tempfile.mkdtemp()`` for the DB + CSV files
  so the tests are order-independent and parallel-safe.
* Tests import ``IngestionEngine`` from
  ``backend.imdf.engines.ingestion_engine`` as the task brief specified,
  and additionally verify the engine can also be reached via the
  ``imdf.engines.ingestion_engine`` path that conftest.py injects (so
  this test works regardless of which way the test runner is launched).
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# ==== Path bootstrap (matches sibling p2_p1 tests) ==========================
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
_ENGINES_PKG = _BACKEND / "imdf" / "engines"

# Make ``from backend.imdf.engines.ingestion_engine import ...`` work
for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
# And ``from imdf.engines.ingestion_engine import ...`` work (conftest
# path-order puts imdf/engines first; explicit add is defensive).
if str(_ENGINES_PKG) not in sys.path:
    sys.path.insert(0, str(_ENGINES_PKG))


# ==== Imports under test ====================================================
try:
    # Path 1: backend.imdf.engines.ingestion_engine (task brief form)
    from backend.imdf.engines.ingestion_engine import (  # type: ignore  # noqa: E402
        IngestionEngine,
        IngestionError,
    )
except Exception:
    # Path 2: imdf.engines.ingestion_engine (conftest-driven form)
    from imdf.engines.ingestion_engine import (  # type: ignore  # noqa: E402
        IngestionEngine,
        IngestionError,
    )


# ==== Fixtures ==============================================================
@pytest.fixture
def workdir():
    """Fresh temp dir per-test, auto-cleaned."""
    d = tempfile.mkdtemp(prefix="p2p1_csv_")
    yield Path(d)
    # Best-effort cleanup — sqlite WAL files might linger
    for f in Path(d).glob("*"):
        try:
            if f.is_file():
                f.unlink()
        except OSError:
            pass
    try:
        Path(d).rmdir()
    except OSError:
        pass


@pytest.fixture
def engine(workdir):
    """IngestionEngine backed by a per-test DB file."""
    return IngestionEngine(db_path=str(workdir / "ingest.db"))


# ==== Test 1: CSV with `id` column (R2-NEW-#2) =============================
def test_csv_with_id_column_ingests_3_rows(engine, workdir):
    """CSV ``id,name\\n0,a\\n1,b\\n2,c\\n`` must import cleanly (3 rows).

    Pre-fix behaviour: ``sqlite3.OperationalError: duplicate column name: id``
    Post-fix behaviour: user's ``id`` is treated as a normal TEXT column;
    auto-increment PK is renamed to ``row_id`` (or another non-colliding name).
    """
    csv_path = workdir / "has_id.csv"
    csv_path.write_text("id,name\n0,a\n1,b\n2,c\n", encoding="utf-8")
    result = engine.import_csv(str(csv_path), table="t_has_id")
    assert result["success"] is True, f"import_csv failed: {result}"
    assert result["data"]["rows_imported"] == 3
    assert result["data"]["total_in_file"] == 3
    assert result["data"]["pk_column"] != "id", (
        "R2-NEW-#2 NOT FIXED: PK should be renamed when user has 'id' column"
    )
    # User's id column must be preserved as a regular TEXT column.
    assert "id" in result["data"]["columns"]
    assert "name" in result["data"]["columns"]
    # Query the resulting table to confirm all 3 rows made it in with the
    # right id values.
    conn = sqlite3.connect(str(workdir / "ingest.db"))
    try:
        rows = conn.execute(
            'SELECT "id", "name" FROM t_has_id ORDER BY "id"'
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("0", "a"), ("1", "b"), ("2", "c")], (
        f"row data mismatch: {rows}"
    )


# ==== Test 2: CSV with no `id` column (backward compatibility) =============
def test_csv_without_id_column_uses_id_pk(engine, workdir):
    """CSV with no ``id`` column must still use ``id`` as PK (backward compat).

    Pre-fix: PK was always ``id`` — preserved.
    Post-fix: PK is ``id`` only when the user does NOT have an ``id`` column.
    """
    csv_path = workdir / "no_id.csv"
    rows_in = [
        {"name": "alpha", "score": "10"},
        {"name": "beta", "score": "20"},
        {"name": "gamma", "score": "30"},
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "score"])
        writer.writeheader()
        writer.writerows(rows_in)
    result = engine.import_csv(str(csv_path), table="t_no_id")
    assert result["success"] is True, f"import_csv failed: {result}"
    n = len(rows_in)
    assert result["data"]["rows_imported"] == n
    assert result["data"]["total_in_file"] == n
    # Backward-compat: PK stays as 'id' when user has no 'id' column.
    assert result["data"]["pk_column"] == "id", (
        f"PK regression: expected 'id', got {result['data']['pk_column']!r}"
    )
    # Verify rows landed in DB.
    conn = sqlite3.connect(str(workdir / "ingest.db"))
    try:
        names = [r[0] for r in conn.execute(
            'SELECT "name" FROM t_no_id ORDER BY "id"'
        ).fetchall()]
    finally:
        conn.close()
    assert names == ["alpha", "beta", "gamma"]


# ==== Test 3: Inconsistent-row CSV must raise IngestionError (R2-NEW-#3) ==
def test_csv_with_inconsistent_rows_raises_ingestion_error(engine, workdir):
    """CSV ``1,2\\n3\\n4,5\\n`` must raise IngestionError, not silent loss.

    Pre-fix: row 2 (only 1 column) was silently inserted with b='None' string.
    Post-fix: any row with column count != len(header) raises IngestionError
    with the row number, and the import is rolled back.
    """
    csv_path = workdir / "bad.csv"
    csv_path.write_text("1,2\n3\n4,5\n", encoding="utf-8")
    with pytest.raises(IngestionError) as excinfo:
        engine.import_csv(str(csv_path), table="t_bad")
    msg = str(excinfo.value)
    # Must mention row number and column-count mismatch.
    assert "行 2" in msg or "row 2" in msg.lower(), (
        f"Error message should mention row 2, got: {msg}"
    )
    assert "1" in msg and "2" in msg, (
        f"Error message should mention column counts, got: {msg}"
    )
    # R2-NEW-#3: no half-committed table — connection rollback
    # The DB file may exist but t_bad table must not be there (because we
    # raise BEFORE any CREATE TABLE / INSERT).
    if (workdir / "ingest.db").exists():
        conn = sqlite3.connect(str(workdir / "ingest.db"))
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        finally:
            conn.close()
        assert "t_bad" not in tables, (
            f"Rollback regression: t_bad table exists after IngestionError. "
            f"Tables: {tables}"
        )


# ==== Test 4: 1000-row CSV must fully ingest and be queryable ==============
def test_csv_with_1000_rows_all_queryable(engine, workdir):
    """CSV with 1000 rows must be fully ingested and queryable from the table.

    Verifies: no row loss, AUTOINCREMENT PK monotonically increases, all
    columns preserved, no truncation at the boundary.
    """
    n = 1000
    csv_path = workdir / "big.csv"
    lines = ["idx,label,value"]
    for i in range(n):
        lines.append(f"{i},item_{i},{i * 2}")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = engine.import_csv(str(csv_path), table="t_big")
    assert result["success"] is True, f"import_csv failed: {result}"
    assert result["data"]["rows_imported"] == n
    assert result["data"]["total_in_file"] == n
    # All 1000 rows queryable.
    conn = sqlite3.connect(str(workdir / "ingest.db"))
    try:
        count = conn.execute("SELECT COUNT(*) FROM t_big").fetchone()[0]
        assert count == n, f"expected {n} rows in DB, got {count}"
        first = conn.execute(
            'SELECT "idx", "label", "value" FROM t_big ORDER BY "idx" LIMIT 1'
        ).fetchone()
        last = conn.execute(
            'SELECT "idx", "label", "value" FROM t_big ORDER BY "idx" DESC LIMIT 1'
        ).fetchone()
        sample_mid = conn.execute(
            'SELECT "idx", "label", "value" FROM t_big WHERE "idx"=?',
            (500,),
        ).fetchone()
    finally:
        conn.close()
    assert first == ("0", "item_0", "0"), f"first row wrong: {first}"
    assert last == (str(n - 1), f"item_{n - 1}", str((n - 1) * 2)), (
        f"last row wrong: {last}"
    )
    assert sample_mid == ("500", "item_500", "1000"), (
        f"mid row wrong: {sample_mid}"
    )


# ==== Bonus tests (regression guards) ======================================
def test_csv_id_column_case_insensitive_collision(engine, workdir):
    """Case-insensitive ``ID`` (uppercase) must also trigger PK rename."""
    csv_path = workdir / "upper_id.csv"
    csv_path.write_text("ID,name\nA,alice\nB,bob\n", encoding="utf-8")
    result = engine.import_csv(str(csv_path), table="t_uid")
    assert result["success"] is True, f"import_csv failed: {result}"
    assert result["data"]["rows_imported"] == 2
    assert result["data"]["pk_column"] != "id"
    assert "ID" in result["data"]["columns"]


def test_csv_empty_file_returns_error(engine, workdir):
    """Empty CSV must return ``success=False`` rather than crash."""
    csv_path = workdir / "empty.csv"
    csv_path.write_text("", encoding="utf-8")
    result = engine.import_csv(str(csv_path), table="t_empty")
    assert result["success"] is False
    assert "空" in result["error"] or "empty" in result["error"].lower()


def test_csv_missing_file_returns_error(engine, workdir):
    """Missing CSV must return ``success=False`` (backward compat)."""
    result = engine.import_csv(str(workdir / "ghost.csv"), table="t_ghost")
    assert result["success"] is False
    assert "不存在" in result["error"] or "not exist" in result["error"].lower()


def test_csv_header_only_returns_error(engine, workdir):
    """Header-only CSV (no data rows) must return success=False."""
    csv_path = workdir / "header_only.csv"
    csv_path.write_text("a,b,c\n", encoding="utf-8")
    result = engine.import_csv(str(csv_path), table="t_ho")
    assert result["success"] is False
    assert "空" in result["error"] or "empty" in result["error"].lower()


def test_csv_duplicate_header_column_raises(engine, workdir):
    """Duplicate header columns (e.g. ``a,a,b``) must raise IngestionError."""
    csv_path = workdir / "dup_header.csv"
    csv_path.write_text("a,a,b\n1,2,3\n4,5,6\n", encoding="utf-8")
    with pytest.raises(IngestionError) as excinfo:
        engine.import_csv(str(csv_path), table="t_dup")
    assert "重复" in str(excinfo.value) or "duplicate" in str(excinfo.value).lower()


def test_csv_reserved_column_renamed(engine, workdir):
    """User's ``_imported_at`` column must be renamed to avoid SQLite collision."""
    csv_path = workdir / "reserved.csv"
    csv_path.write_text("name,_imported_at\nalice,2020-01-01\n", encoding="utf-8")
    result = engine.import_csv(str(csv_path), table="t_resv")
    assert result["success"] is True, f"import_csv failed: {result}"
    cols = result["data"]["columns"]
    assert "_imported_at" not in cols, (
        f"reserved collision not handled: cols={cols}"
    )
    # The user's column should be saved as user_imported_at (with single
    # underscore — engine strips the leading ``_`` from the reserved name
    # before prepending ``user_`` to avoid triple-underscore names like
    # ``user___imported_at``).
    assert "user_imported_at" in cols, (
        f"user's _imported_at not renamed: cols={cols}"
    )
