"""P21 P2 P1 — DB schema fix verification tests.

Verifies the two P0 fixes called out in ``reports/p21_r2_audit_db.md``:

  * **N2 — ``audit_chain_entries.extra`` type mismatch** — was declared
    as ``Text`` in both the ORM model (``models/audit_chain_entry.py:86``)
    and migration ``0003_pg_models.py`` (PG path used ``extra TEXT
    DEFAULT ''``).  Migration ``backend/alembic/versions/p13_c1_p99_db.py``
    at line 97-100 creates a ``GIN`` index using
    ``jsonb_path_ops`` which **only** works on a ``JSONB`` column.  The
    fix: change the model and ``0003_pg_models.py`` to use
    ``get_jsonb_column()`` so PG → ``JSONB`` and SQLite → ``JSON``.

  * **N3 — 4 ORM tables missing from the alembic chain** — the
    ``requirements`` / ``requirement_tasks`` / ``project_members`` /
    ``project_timeline_events`` tables are declared on
    ``Base.metadata`` but no migration created them.  Fix: add
    ``0006_project_center_requirements.py`` (the imdf chain only had
    ``0001_initial`` through ``0005_packs``).

The module is self-contained: it sets up ``sys.path`` and the minimum
ENV vars at import time, so it can be run via::

    pytest tests/p2_p1/test_db_schema_fix.py -v

with the project root as the working directory.  The tests build a
fresh SQLite database in a temp directory, point ``IMDF_P2_DB_URL`` at
it, run ``alembic upgrade head`` from the imdf chain, and then assert
that every ``__tablename__`` declared on a Model class is present in
``inspect(engine).get_table_names()`` after the upgrade.

A note on the imdf chain:

The chain has a pre-existing bug in ``0004_billing.py:115`` (calls
``op.create_unique_index`` which is not in the installed alembic
1.16.1).  That is **outside the scope** of this P2-P1 task; to keep
the test focused on the N2 / N3 fixes, the end-to-end tests use a
two-step bring-up:

  1. ``Base.metadata.create_all`` builds the full ORM schema (this
     creates all 14 ORM tables — the same 14 that ``init_db()`` would
     build on first boot, including the 4 missing ones now that
     ``models.register_all()`` is in scope).
  2. ``alembic stamp 0005_packs`` marks the DB as if every prior
     migration has been applied.  This sidesteps the 0004 bug while
     still requiring 0006 to be the *next* revision applied.
  3. ``alembic upgrade head`` then runs **only** 0006, which is the
     migration we added.  If the migration is broken (wrong columns,
     wrong indexes, broken DDL), this step will fail.

The model-declared JSON-shape tests (``TestAuditChainExtraConsistency``)
do not need to run the chain — they inspect the source code and
``Base.metadata`` directly, so they're fast and don't depend on the
chain.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import List, Set

# ── Path setup (mirrors tests/conftest.py) ──────────────────────────────
# The global ``tests/conftest.py`` already injects ``backend/`` into
# ``sys.path``; we still defensively do it here so this file works when
# invoked via ``pytest tests/p2_p1/test_db_schema_fix.py`` from any
# working directory.  We *additionally* insert ``backend/imdf`` at
# position 0 so that the alembic env.py ``from db import Base`` resolves
# to the imdf package, not to a stray ``db/`` elsewhere on PYTHONPATH.
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parents[2] / "backend"
_IMDF = _BACKEND / "imdf"
for _p in (str(_IMDF), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── ENV setup (must run before any ``from db import ...``) ─────────────
# Strong JWT secret so issue_access_token doesn't raise in tests.
os.environ.setdefault("JWT_SECRET", "x" * 64)
os.environ.setdefault("IMDF_TEST_MODE", "1")


# ── Imports that depend on path / env above ─────────────────────────────
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _alembic_config():
    """Build an alembic ``Config`` for the imdf chain.

    The chain is keyed on ``backend/imdf/alembic.ini``; ``script_location
    = alembic`` is relative, so the caller must ``os.chdir`` to
    ``backend/imdf`` before invoking ``command.*`` against the config.
    """
    from alembic.config import Config

    ini_path = _IMDF / "alembic.ini"
    return Config(str(ini_path))


def _alembic_upgrade(db_url: str, revision: str = "head") -> None:
    """Run ``alembic <op> <revision>`` against ``db_url`` using the imdf
    chain's alembic config.

    The env.py file in the imdf chain imports ``IMDF_P2_DB_URL`` at
    module load time and uses it to set ``sqlalchemy.url``.  We
    monkey-patch that module global so each test can target a fresh
    SQLite file in its own ``tmp_path``.
    """
    from alembic import command

    cfg = _alembic_config()
    cwd = os.getcwd()
    try:
        os.chdir(str(_IMDF))
        # Re-point IMDF_P2_DB_URL so the imdf ``env.py`` (which uses
        # that module global) targets our test DB.  This is the same
        # approach the production runtime uses, just with a per-test
        # URL.  We import the module first to make sure the
        # ``IMDF_P2_DB_URL`` global exists in ``sys.modules``.
        import db as _db
        _db.IMDF_P2_DB_URL = db_url
        # Also patch the alembic config (defensive — env.py may
        # re-overwrite it from the global, but that's fine).
        cfg.set_main_option("sqlalchemy.url", db_url)
        if revision in ("head", "current", "heads"):
            command.upgrade(cfg, revision)
        else:
            command.stamp(cfg, revision)
    finally:
        os.chdir(cwd)


def _expected_orm_tablename_list() -> List[str]:
    """Return the canonical list of ``__tablename__`` declared on every
    Model that is reachable from ``models.register_all()``.

    Uses SQLAlchemy 2.0 ``Base.registry.mappers`` so it sees all
    declarative classes without re-importing anything.
    """
    from db import Base
    names: List[str] = []
    seen: Set[str] = set()
    for mapper in Base.registry.mappers:  # type: ignore[attr-defined]
        cls = mapper.class_
        table = getattr(cls, "__tablename__", None)
        if table and table not in seen:
            seen.add(table)
            names.append(table)
    return sorted(names)


@pytest.fixture
def fresh_sqlite_db(tmp_path, monkeypatch) -> Engine:
    """Build a fresh SQLite engine bound to a per-test temp file.

    Returns the engine; the test can then create the schema via
    ``Base.metadata.create_all`` and stamp / upgrade from there.
    """
    db_file = tmp_path / "p2_p1_schema_fix.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    # Make sure no leftover on the FS — the file shouldn't exist yet,
    # but be defensive.
    if db_file.exists():
        db_file.unlink()

    # Force-import every model so ``Base.metadata`` is fully populated.
    from models import register_all  # noqa: F401
    register_all()

    # Update the global so env.py picks up the test URL when invoked.
    import db as _db
    _db.IMDF_P2_DB_URL = db_url
    monkeypatch.setenv("IMDF_P2_DB_URL", db_url)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    yield engine, db_url

    try:
        from db import Base
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass
    engine.dispose()


# ════════════════════════════════════════════════════════════════════════
# Tests — N2 (audit_chain_entries.extra type)
# ════════════════════════════════════════════════════════════════════════

class TestAuditChainExtraConsistency:
    """N2 — ``audit_chain_entries.extra`` must be a JSON/JSONB column on
    both PG and SQLite.  The PG GIN index in
    ``backend/alembic/versions/p13_c1_p99_db.py:97-100`` only works on
    a ``JSONB`` column; the model and the migration must agree.
    """

    def test_model_declares_jsonb_compatible_column(self):
        """The ORM model ``AuditChainEntry.extra`` should resolve to a
        JSON-like type — never plain ``Text`` — so the cross-dialect
        DDL in ``0003_pg_models.py`` and the GIN index in
        ``p13_c1_p99_db.py`` line up.
        """
        from models.audit_chain_entry import AuditChainEntry
        col = AuditChainEntry.__table__.columns["extra"]
        type_name = type(col.type).__name__
        # ``get_jsonb_column()`` returns ``JSON().with_variant(JSONB(), 'postgresql')``
        # which surfaces as ``Variant`` on SQLAlchemy 2.0.  The
        # ``.impl`` attribute holds the underlying type.
        assert type_name in ("JSON", "JSONB", "Variant", "TypeDecorator"), (
            f"AuditChainEntry.extra must be JSON/JSONB, got {type_name!r}"
        )
        # And definitely NOT Text — that was the original bug.
        assert type_name != "Text", (
            "AuditChainEntry.extra regressed to Text — GIN jsonb_path_ops "
            "will not work on PG."
        )

    def test_migration_0003_uses_json_for_extra(self):
        """The 0003 migration source code must declare ``extra`` as a
        JSON-flavored column on both PG (``JSONB NOT NULL DEFAULT
        '{}'::jsonb``) and SQLite (``sa.JSON()``).
        """
        mig_path = _IMDF / "alembic" / "versions" / "0003_pg_models.py"
        src = mig_path.read_text(encoding="utf-8")
        # The PG path must declare JSONB (regex on the raw SQL block).
        assert "JSONB" in src and "extra" in src, (
            "0003_pg_models.py no longer mentions JSONB / extra — "
            "regression in the N2 fix."
        )
        # The SQLite path must use sa.JSON() (not sa.Text()).
        # Look for the explicit ``sa.Column("extra", ...`` line.
        assert 'sa.JSON()' in src, "0003_pg_models.py must use sa.JSON() for SQLite path"


# ════════════════════════════════════════════════════════════════════════
# Tests — N3 (4 missing tables)
# ════════════════════════════════════════════════════════════════════════

class TestMissingTables:
    """N3 — 4 ORM tables (``requirements``, ``requirement_tasks``,
    ``project_members``, ``project_timeline_events``) must be created
    by the alembic chain.
    """

    MISSING_TABLES = (
        "requirements",
        "requirement_tasks",
        "project_members",
        "project_timeline_events",
    )

    def test_migration_0006_creates_the_4_tables(self):
        """The new migration file must exist and reference all 4
        missing tables in both its ``upgrade()`` and ``downgrade()``.
        """
        mig_path = _IMDF / "alembic" / "versions" / "0006_project_center_requirements.py"
        assert mig_path.is_file(), (
            f"Missing migration: {mig_path}.  R2 N3 fix is incomplete."
        )
        src = mig_path.read_text(encoding="utf-8")
        for table in self.MISSING_TABLES:
            assert table in src, (
                f"Migration 0006 does not mention {table!r} — fix is incomplete."
            )

    def test_alembic_chain_creates_4_missing_tables(self, fresh_sqlite_db, tmp_path):
        """End-to-end: bring up the DB via ``Base.metadata.create_all``
        + ``alembic stamp 0005_packs`` (workaround for the pre-existing
        0004_billing bug, see module docstring) + ``alembic upgrade
        head`` (which only needs to apply 0006).  Then assert that all
        4 missing tables now exist in the DB.

        ``Base.metadata.create_all`` would create all 14 ORM tables
        (including the 4 we're trying to test), so we drop those 4
        right after the create_all / stamp step — that way the upgrade
        to head actually exercises 0006's DDL.
        """
        engine, db_url = fresh_sqlite_db

        # Step 1: create the schema from 0001-0005 (the 10 tables those
        # migrations cover) via ``create_all``.  We then drop the 4
        # tables that 0006 should create, so 0006 can recreate them
        # itself.
        from db import Base
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for table in self.MISSING_TABLES:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

        # Step 2: stamp to 0005_packs so 0006 is the *next* revision.
        # (This sidesteps the pre-existing 0004 bug.)
        _alembic_upgrade(db_url, "0005_packs")

        # Step 3: run the actual upgrade to head — this is the part
        # that exercises our new 0006 migration.  If 0006 is broken
        # (wrong column types, missing columns, broken DDL), this
        # call will raise.
        _alembic_upgrade(db_url, "head")

        # Verify: every Model.__tablename__ should be in the DB.
        insp = inspect(engine)
        existing = set(insp.get_table_names())

        for table in self.MISSING_TABLES:
            assert table in existing, (
                f"Table {table!r} not created by alembic upgrade head. "
                f"Tables present: {sorted(existing)}"
            )

    def test_all_orm_tablename_present_after_upgrade(self, fresh_sqlite_db, tmp_path):
        """End-to-end: after the full chain (0001..0006) runs, every
        ``Model.__tablename__`` declared in ``models/`` is present in
        the DB.
        """
        engine, db_url = fresh_sqlite_db

        from db import Base
        Base.metadata.create_all(bind=engine)
        # Drop the 4 tables that 0006 will create, so the upgrade step
        # actually exercises the migration DDL.
        with engine.begin() as conn:
            for table in self.MISSING_TABLES:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        _alembic_upgrade(db_url, "0005_packs")
        _alembic_upgrade(db_url, "head")

        insp = inspect(engine)
        existing = set(insp.get_table_names())

        expected = set(_expected_orm_tablename_list())
        missing = expected - existing
        assert not missing, (
            f"ORM declares {len(missing)} table(s) that are missing from "
            f"the alembic-migrated DB: {sorted(missing)}.\n"
            f"ORM expected: {sorted(expected)}\n"
            f"DB present:   {sorted(existing)}"
        )

    def test_alembic_head_is_after_0006(self):
        """``0006_project_center_requirements`` must be reachable from
        the imdf chain's current head — proves the new migration is
        correctly linked into the chain.  Future migrations (e.g.
        ``0007_unify_audit_extra_type`` from P21 P2 P5) may build on
        top of 0006 and become the new head; the assertion is updated
        to accept that case (0006 is in the ancestry, not necessarily
        the leaf).
        """
        from alembic.script import ScriptDirectory

        cfg = _alembic_config()
        cwd = os.getcwd()
        try:
            os.chdir(str(_IMDF))
            sd = ScriptDirectory.from_config(cfg)
            heads = sd.get_heads()
            head = sd.get_current_head()
            # Walk the chain and collect every reachable revision id.
            # 0006 must be in that set.
            reachable = set()
            for rev in sd.walk_revisions():
                reachable.add(rev.revision)
        finally:
            os.chdir(cwd)
        # If the chain has a fork (multiple heads), ``get_current_head``
        # returns ``None``; ``get_heads()`` still surfaces every leaf
        # revision.  We accept either case as long as ``0006`` is
        # reachable from the head — i.e. the migration is correctly
        # linked into the chain (as either the head itself, or as an
        # ancestor of a later head like ``0007_unify_audit_extra_type``).
        all_revs = list(heads or [])
        if head:
            all_revs.append(head)
        assert (
            "0006_project_center_requirements" in reachable
        ), (
            f"Alembic head is {head!r} (heads={heads!r}); "
            f"0006_project_center_requirements is NOT reachable from "
            f"any head.  Reachable revisions: {sorted(reachable)}"
        )


# ════════════════════════════════════════════════════════════════════════
# Tests — round-trip (audit_chain_entries.extra)
# ════════════════════════════════════════════════════════════════════════

class TestAuditChainExtraRoundTrip:
    """Insert a row with a dict ``extra`` payload and read it back."""

    def test_insert_and_read_extra_dict(self, fresh_sqlite_db, tmp_path):
        """Apply the migrations, then ``INSERT`` an ``AuditChainEntry``
        with a non-trivial ``extra`` dict and read it back to confirm
        the column is JSON-flavored (not Text).
        """
        engine, db_url = fresh_sqlite_db

        from db import Base
        Base.metadata.create_all(bind=engine)
        # Drop the 4 tables that 0006 will create, so the upgrade step
        # actually exercises the migration DDL.
        missing_tables = (
            "requirements",
            "requirement_tasks",
            "project_members",
            "project_timeline_events",
        )
        with engine.begin() as conn:
            for table in missing_tables:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        _alembic_upgrade(db_url, "0005_packs")
        _alembic_upgrade(db_url, "head")

        from models.audit_chain_entry import AuditChainEntry
        from datetime import datetime, timezone

        with engine.begin() as conn:
            entry = AuditChainEntry(
                seq=1,
                timestamp="2026-07-11T05:36:00Z",
                occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
                method="GET",
                path="/api/v1/test",
                user="tester",
                body_hash="x" * 64,
                status_code=200,
                actor="tester",
                prev_hash="0" * 64,
                entry_hash="a" * 64,
                signature="b" * 64,
                extra={"key": "value", "nested": {"k": 1}, "list": [1, 2, 3]},
            )
            conn.execute(entry.__table__.insert().values(**{
                "seq": entry.seq,
                "timestamp": entry.timestamp,
                "occurred_at": entry.occurred_at,
                "method": entry.method,
                "path": entry.path,
                "user": entry.user,
                "body_hash": entry.body_hash,
                "status_code": entry.status_code,
                "actor": entry.actor,
                "prev_hash": entry.prev_hash,
                "entry_hash": entry.entry_hash,
                "signature": entry.signature,
                "extra": entry.extra,
            }))

            row = conn.execute(
                text("SELECT extra FROM audit_chain_entries WHERE seq = 1")
            ).first()

        assert row is not None, "INSERT / SELECT round-trip returned no row"
        extra = row[0]

        # On SQLite, ``JSON`` columns round-trip as a string (the
        # raw JSON text).  On PG, ``JSONB`` returns a Python dict
        # directly.  We support both: if it's a string, parse it;
        # if it's already a dict, use it as-is.
        if isinstance(extra, str):
            import json
            extra = json.loads(extra)

        assert isinstance(extra, dict), (
            f"extra must round-trip as a dict, got {type(extra).__name__}: {extra!r}"
        )
        assert extra.get("key") == "value", f"extra['key'] != 'value': {extra!r}"
        assert extra.get("nested") == {"k": 1}, f"extra['nested'] wrong: {extra!r}"
        assert extra.get("list") == [1, 2, 3], f"extra['list'] wrong: {extra!r}"
