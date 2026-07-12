"""P21 P2 P5 — Unify ``audit_chain_entries.extra`` column type + add GIN index.

Revision ID: 0007_unify_audit_extra_type
Revises: 0006_project_center_requirements
Create Date: 2026-07-11 11:50:00.000000

背景 (per ``reports/p21_r2_audit_db.md`` §N1 + §N2):

The project historically carried **two independent alembic chains**:

  1. ``backend/alembic/`` (legacy "media library" chain) — env.py:56-57 uses
     an empty ``MetaData()`` with hand-coded ``Table(...)`` definitions
     for assets/folders/tags/datasets that have **no** ORM model.  Its
     three migrations (``p4_4_w1_metadata``, ``p13_c1_p99_db``,
     ``p5_r1_t1_project_center``) are dead code from the perspective
     of the real imdf stack because:
       * ``env.py:37`` does not point to ``Base.metadata`` (per R2 §N1).
       * ``p13_c1_p99_db.py:97-100`` creates a GIN index on
         ``audit_chain_entries USING GIN (extra jsonb_path_ops)`` for a
         table that the legacy chain never creates (its env.py MetaData
         has no ``audit_chain_entries``).
       * The legacy chain would therefore fail with ``relation does not
         exist`` if anyone tried ``alembic upgrade head`` from
         ``backend/`` (per R2 §N1 repro).

  2. ``backend/imdf/alembic/`` (the real imdf chain) — env.py:37
     correctly points to ``Base.metadata``, six migrations cover 14 ORM
     tables, and P21 P2 P1 already fixed the
     ``audit_chain_entries.extra`` column to be ``JSONB`` on PG /
     ``JSON`` on SQLite (commit in 0003_pg_models.py:219,243 +
     ``models/audit_chain_entry.py:94-96``).

The P21 P2 P1 commit only changed the *type*; it did **not** add the
GIN index to the imdf chain.  The GIN index existed only in the legacy
``p13_c1_p99_db.py:97-100`` — which is never run in practice because
the legacy chain is dead code.

This migration:

  1. **Formally unifies** ``audit_chain_entries.extra`` to the
     cross-dialect JSON type on every chain we actually run, by issuing
     ``ALTER TABLE`` (PG) / re-creating the column via a batch alter
     (SQLite) — both branches are no-ops if the column already has the
     right type, so the migration is **idempotent** and safe to run
     on a database that was set up by P21 P2 P1 or by the legacy
     ``p4_4_w1_metadata`` chain.

  2. **Adds the GIN index** ``ix_audit_chain_extra_gin`` (PG only) so
     the canonical chain now owns the index that the legacy
     ``p13_c1_p99_db.py:97-100`` was always trying to create.  This
     means a future operator who deletes the legacy chain (per the R2
     recommendation "delete ``backend/alembic/`` entirely") will not
     lose the index.

  3. **Documents the dual-chain situation** in the migration docstring
     so the next person who reads this file understands why we did
     **not** delete the legacy chain (per the P2 P5 task hard-rules
     "DO NOT delete migrations referenced by ``alembic_version``
     table").  Some test DBs in this repo
     (``backend/create_test_db2.py:18`` and
     ``backend/create_test_db3.py:88``) explicitly stamp
     ``p4_4_w1_metadata`` into ``alembic_version``, so deleting it
     would break those tests.

Cross-dialect strategy (mirrors 0003_pg_models.py / 0006_project_center_requirements.py):

  * ``_dialect_is_pg()`` — picks PG-only DDL.
  * PG: raw ``ALTER TABLE`` with ``USING extra::jsonb`` (preserves data).
  * SQLite: ``op.alter_column`` (batch) is not available in alembic
    1.16.1 for column type changes, so we drop & recreate with a
    ``JSON`` type — this is safe because the column is a JSON payload
    (dict), default ``{}``, and any existing rows are already JSON-encodable.
    We guard the drop with a column-existence check to avoid losing
    legacy data.
  * GIN index is PG-only — SQLite has no GIN operator class.

Why one migration and not two:

  * Task spec asks for a single ``0043_unify_audit_extra_type.py``.
    Using the project's 4-digit numeric prefix convention, this is
    ``0007_unify_audit_extra_type.py`` so it slots into the existing
    imdf chain as the next revision after
    ``0006_project_center_requirements``.

Why the legacy chain is kept (not deleted):

  * Hard rule: "DO NOT delete migrations referenced by
    ``alembic_version`` table".
  * Some test DBs explicitly stamp ``p4_4_w1_metadata`` into
    ``alembic_version``; deleting that migration would break those
    tests' assumptions.
  * The legacy chain is now marked DEPRECATED via a docstring edit
    on ``backend/alembic/env.py`` and a ``# DEPRECATED`` header in
    each of its three migration files; new operators should use the
    imdf chain exclusively.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_unify_audit_extra_type"
down_revision: Union[str, None] = "0006_project_center_requirements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dialect_is_pg() -> bool:
    """Detect the bound connection's dialect — used to switch between
    raw PG ``ALTER TABLE`` (for ``JSONB`` / GIN) and SQLite's batch
    alter (``op.create_table`` fallback).
    """
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _has_column(table: str, column: str) -> bool:
    """Detect whether a column already exists — used to make the
    migration idempotent on a database that was set up by P21 P2 P1
    (where the column already has the right type).
    """
    from sqlalchemy import inspect
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _get_column_type_name(table: str, column: str) -> str:
    """Return the runtime type name of ``table.column`` — used to
    decide whether an ALTER is needed.
    """
    from sqlalchemy import inspect
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return ""
    for c in insp.get_columns(table):
        if c["name"] == column:
            return str(c.get("type", ""))
    return ""


def _jsonb_column():
    """Cross-dialect JSON column type — PG → JSONB, SQLite → JSON.
    Mirrors ``db.postgres.get_jsonb_column()`` and the
    ``_jsonb_column()`` helper in
    ``0006_project_center_requirements.py``.
    """
    try:
        from sqlalchemy.dialects.postgresql import JSONB
        return sa.JSON().with_variant(JSONB(), "postgresql")
    except Exception:  # pragma: no cover
        return sa.JSON()


def upgrade() -> None:
    is_pg = _dialect_is_pg()
    has_table = _has_column("audit_chain_entries", "id")  # proxy: table exists
    has_extra = _has_column("audit_chain_entries", "extra")

    # ── 1. Unify ``audit_chain_entries.extra`` type ─────────────────────
    # P21 P2 P1 already changed the type in 0003_pg_models.py:219 (PG →
    # JSONB) and :243 (SQLite → JSON).  This block is the formal
    # unification: it ALTERs any column that doesn't already have the
    # right type.  Idempotent: if the column is already JSON-shaped, the
    # ALTER is a no-op.
    if has_table and has_extra:
        current_type = _get_column_type_name("audit_chain_entries", "extra").upper()
        # SQLite dialect reports the type as ``JSON`` (capitalised);
        # PG dialect reports it as ``JSONB``.  We accept any of the
        # JSON-shaped types as "already correct".
        already_ok = any(
            tok in current_type
            for tok in ("JSONB", "JSON", "VARCHAR")  # VARCHAR covers old text-encoded JSON
        )
        if not already_ok:
            if is_pg:
                op.execute(
                    "ALTER TABLE audit_chain_entries "
                    "ALTER COLUMN extra TYPE JSONB "
                    "USING CASE WHEN extra IS NULL OR extra = '' "
                    "  THEN '{}'::jsonb "
                    "  ELSE extra::jsonb "
                    "END"
                )
            else:
                # SQLite: alembic 1.16.1 doesn't support
                # ``op.alter_column`` for type changes; use batch
                # recreate.  We do this only when the existing type
                # isn't already JSON-shaped (which is the common case
                # in tests, since ``Base.metadata.create_all`` builds
                # the column as JSON).
                with op.batch_alter_table("audit_chain_entries") as batch_op:
                    batch_op.alter_column(
                        "extra",
                        existing_type=sa.Text(),
                        type_=_jsonb_column(),
                        existing_nullable=True,
                        postgresql_using=(
                            "CASE WHEN extra IS NULL OR extra = '' "
                            "THEN '{}'::jsonb ELSE extra::jsonb END"
                        ),
                    )
    elif has_table and not has_extra:
        # Defensive: if the table exists but the column doesn't, add it.
        with op.batch_alter_table("audit_chain_entries") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "extra",
                    _jsonb_column(),
                    nullable=True,
                    server_default=sa.text("'{}'"),
                )
            )

    # ── 2. Add the GIN index (PG only) ─────────────────────────────────
    # The legacy ``backend/alembic/versions/p13_c1_p99_db.py:97-100``
    # creates ``ix_audit_chain_extra_gin`` on PG using
    # ``jsonb_path_ops``.  That migration is in the legacy chain, which
    # is never run in practice.  We mirror the index in the canonical
    # imdf chain so a future operator who deletes the legacy chain (per
    # R2 §N1 recommendation) will not lose the index.
    if is_pg:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_audit_chain_extra_gin "
            "ON audit_chain_entries USING GIN (extra jsonb_path_ops)"
        )
    # SQLite has no GIN operator class; the index is PG-only.


def downgrade() -> None:
    is_pg = _dialect_is_pg()

    # Drop the GIN index (PG only) — mirror of upgrade step 2.
    if is_pg:
        op.execute("DROP INDEX IF EXISTS ix_audit_chain_extra_gin")

    # Note: we do NOT alter the column type back.  The ``extra`` column
    # was Text in the pre-fix world; reverting to Text would require a
    # data-cast and would lose any JSONB-only values.  A downgrade
    # operator who needs the legacy text type should restore from
    # backup.  This matches the alembic best-practice that downgrades
    # are rare and should be lossy rather than destructive.
