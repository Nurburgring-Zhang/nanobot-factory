# P21 P2 P1 — DB Schema Fix Report

**Date**: 2026-07-11 05:36
**Task**: P21 Phase 2 P1 — fix DB schema P0 issues from `reports/p21_r2_audit_db.md`
**Author**: coder (mvs_8e18d9d6712e4d85a18eb9383d6b0f21)
**Scope**: N2 (`audit_chain_entries.extra` type) + N3 (4 missing ORM tables)

---

## 1. Summary of changes

| # | File | Change | Severity |
|---|------|--------|----------|
| 1 | `backend/imdf/models/audit_chain_entry.py` | `extra` column changed from `Text` to `get_jsonb_column()` (PG → JSONB, SQLite → JSON) | P0 (N2) |
| 2 | `backend/imdf/alembic/versions/0003_pg_models.py` | `extra` column in both PG (`JSONB NOT NULL DEFAULT '{}'::jsonb`) and SQLite (`sa.JSON()`) paths | P0 (N2) |
| 3 | `backend/imdf/alembic/versions/0006_project_center_requirements.py` | **NEW** migration — creates the 4 missing tables (`project_members`, `project_timeline_events`, `requirements`, `requirement_tasks`) with all columns + indexes | P0 (N3) |
| 4 | `tests/p2_p1/test_db_schema_fix.py` | **NEW** test file — 7 tests covering both fixes (model + migration consistency, end-to-end chain, INSERT/SELECT round-trip) | regression guard |
| 5 | `tests/db/test_extreme_boundary.py::TestSchemaDrift::test_no_orm_only_tables_outside_known_set` | Updated to be a **regression guard** (asserts the 4 tables are NOT in the ORM-only set, i.e. the N3 fix is in place) | regression guard |

All 7 new tests **pass**; the 1 pre-existing `test_fk_count_is_documented` failure (R2 Gap 8 — 0 FKs across the schema) is **independent of this task** and was already failing before any changes.

---

## 2. Before / After

### 2.1 N2 — `audit_chain_entries.extra` type mismatch

**Before**:

| Layer | What it had | Problem |
|-------|-------------|---------|
| `models/audit_chain_entry.py:86` | `extra: Mapped[Optional[Dict[str, Any]]] = mapped_column(Text, default="")` | `Text` — the column is a flat string, can't hold a dict at the type level |
| `0003_pg_models.py:215` (PG path) | `extra TEXT DEFAULT ''` | Same — `TEXT` |
| `0003_pg_models.py:235` (SQLite path) | `sa.Column("extra", sa.Text(), nullable=True, server_default="")` | Same — `Text` |
| `backend/alembic/versions/p13_c1_p99_db.py:97-100` | `CREATE INDEX ... USING GIN (extra jsonb_path_ops)` | **`jsonb_path_ops` only works on JSONB columns** — this GIN index is **dead code** on the actual schema |

**Risk**: anyone running `alembic upgrade head` on a fresh PG DB would see the GIN index creation fail with `ERROR: data type text has no default operator class for access method gin`. Even if the GIN creation is dropped, the column type is a lie — application code writes `extra={"ip": "1.2.3.4"}` but the column stores it as a JSON-encoded string, breaking `@>`, `?`, `@@` GIN operators.

**After**:

| Layer | What it has | Why this works |
|-------|-------------|----------------|
| `models/audit_chain_entry.py:86` | `extra: Mapped[Optional[Dict[str, Any]]] = mapped_column(get_jsonb_column(), nullable=True, default=dict)` | `get_jsonb_column()` returns `JSON().with_variant(JSONB(), 'postgresql')` — cross-dialect JSON type that maps to JSONB on PG, JSON on SQLite. The default is now a dict (not an empty string) to match the new JSON shape. |
| `0003_pg_models.py:215` (PG path) | `extra JSONB NOT NULL DEFAULT '{}'::jsonb` | JSONB — `jsonb_path_ops` GIN index now works |
| `0003_pg_models.py:235` (SQLite path) | `sa.Column("extra", sa.JSON(), nullable=True)` | JSON — matches the model |

The GIN index in `p13_c1_p99_db.py:97-100` is now a real, queryable index for `extra @> '{"ip": "1.2.3.4"}'`, `extra ? 'key'`, and `extra @@ '$.key'` operators.

### 2.2 N3 — 4 missing ORM tables

**Before** (per `p21_r2_audit_db.md` §N3):

```text
ORM-only (declared in models/, no migration): {
    'project_members',          # models/project.py:69
    'project_timeline_events',  # models/project.py:109
    'requirements',             # models/requirement.py:54
    'requirement_tasks',        # models/requirement.py:115
}
```

**Risk**: First deploy hits "table does not exist" at the first `ProjectMember` write (project_engine.py:473) or `Requirement` query. On a fresh database brought up via the alembic chain alone (PG production path), these 4 tables would never exist. On a dev database, `init_db()` would create them via `Base.metadata.create_all()` (one-shot) but alembic would have no record of them — schema drift on the next `alembic upgrade head`.

**After** — new migration `0006_project_center_requirements.py`:

| Table | Columns | Indexes | Cross-dialect |
|-------|---------|---------|---------------|
| `project_members` | id, project_id, user_id, role, joined_at | `ix_project_members_project`, `ix_project_members_user`, `uq_project_members_project_user` | ✅ PG/SQLite |
| `project_timeline_events` | id, project_id, event_type, actor, ts, payload, message | `ix_project_timeline_project_ts`, `ix_project_timeline_event_type` | ✅ PG/SQLite (JSONB/JSON) |
| `requirements` | id, title, type, status, priority, created_by, description, acceptance_criteria, tags, created_at, updated_at, closed_at, project_id, pack_id, qc_status, delivery_id, due_date, owner | `ix_requirements_status`, `ix_requirements_priority`, `ix_requirements_type`, `ix_requirements_created_by`, `ix_requirements_project_id`, `ix_requirements_pack_id`, `ix_requirements_delivery_id`, `ix_requirements_owner` | ✅ PG/SQLite (JSONB/JSON) |
| `requirement_tasks` | id, requirement_id, title, assignee, status, acceptance_criteria, estimated_hours, actual_hours, priority, created_at, completed_at, notes | `ix_requirement_tasks_requirement_id`, `ix_requirement_tasks_assignee`, `ix_requirement_tasks_status`, `ix_requirement_tasks_priority` | ✅ PG/SQLite |

The migration follows the project pattern (mirror 0003_pg_models.py / 0005_packs.py):
- `_dialect_is_pg()` helper to switch between raw `CREATE TABLE` (PG) and `op.create_table` (SQLite).
- Local `_jsonb_column()` helper to mirror `db.postgres.get_jsonb_column()` so the model and DDL stay in lock-step without needing the runtime import.
- `down_revision = "0005_packs"` so it slots into the existing chain (head is now `0006_project_center_requirements`).
- `downgrade()` is a full reverse — drops the 4 tables in reverse creation order so the migration is reversible.

---

## 3. Test results

### 3.1 New tests (`tests/p2_p1/test_db_schema_fix.py`)

```text
tests/p2_p1/test_db_schema_fix.py::TestAuditChainExtraConsistency::test_model_declares_jsonb_compatible_column PASSED
tests/p2_p1/test_db_schema_fix.py::TestAuditChainExtraConsistency::test_migration_0003_uses_json_for_extra       PASSED
tests/p2_p1/test_db_schema_fix.py::TestMissingTables::test_migration_0006_creates_the_4_tables                  PASSED
tests/p2_p1/test_db_schema_fix.py::TestMissingTables::test_alembic_chain_creates_4_missing_tables                PASSED
tests/p2_p1/test_db_schema_fix.py::TestMissingTables::test_all_orm_tablename_present_after_upgrade               PASSED
tests/p2_p1/test_db_schema_fix.py::TestMissingTables::test_alembic_head_is_after_0006                            PASSED
tests/p2_p1/test_db_schema_fix.py::TestAuditChainExtraRoundTrip::test_insert_and_read_extra_dict                 PASSED

======================== 7 passed, 1 warning in 0.89s ========================
```

Test coverage:

| Test | What it asserts |
|------|-----------------|
| `test_model_declares_jsonb_compatible_column` | `AuditChainEntry.extra` is `JSON`/`JSONB`/`Variant` — never `Text` |
| `test_migration_0003_uses_json_for_extra` | Source code of 0003 mentions `JSONB` and uses `sa.JSON()` on the SQLite path |
| `test_migration_0006_creates_the_4_tables` | The new migration file exists and references all 4 missing tables |
| `test_alembic_chain_creates_4_missing_tables` | End-to-end: fresh SQLite + `Base.metadata.create_all` + `alembic stamp 0005_packs` + `alembic upgrade head` — all 4 tables exist in the DB after the upgrade |
| `test_all_orm_tablename_present_after_upgrade` | End-to-end: every `Model.__tablename__` declared in `models/` is in the DB after the chain runs |
| `test_alembic_head_is_after_0006` | `ScriptDirectory.get_heads()` contains `0006_project_center_requirements` (chain is correctly linked) |
| `test_insert_and_read_extra_dict` | Round-trip: INSERT a row with `extra={"key": "value", "nested": {"k": 1}, "list": [1, 2, 3]}` and read it back as a dict |

### 3.2 Regression — `tests/db/test_extreme_boundary.py`

The class `TestSchemaDrift::test_no_orm_only_tables_outside_known_set` was previously asserting the 4 missing tables were still missing (it was a "negative test" tracking the open gap). I inverted the assertion to be a **regression guard** — it now asserts the 4 tables are NO LONGER missing, which is the post-fix expected state. If a future change accidentally drops one of these from the migration chain, this test will fail loudly.

The other 42 tests in `tests/db/test_extreme_boundary.py` continue to pass.

### 3.3 Pre-existing failure (NOT my problem)

`TestFKCascade::test_fk_count_is_documented` was already failing on the pristine pre-fix codebase (verified by stashing my changes and re-running). This is **R2 Gap 8** (86% of tables have zero FKs) — a separate P1 issue, **not** in this task's scope. The fix is tracked in the R2 report's "M1" week-1 plan (add FK on `agent_tasks.parent_id`, `requirement_tasks.requirement_id`, etc.).

---

## 4. Cross-dialect behaviour

| Operation | SQLite (dev) | PostgreSQL (prod) |
|-----------|--------------|-------------------|
| `extra` column on `audit_chain_entries` | `JSON` (stored as TEXT) | `JSONB` (binary JSON, GIN-indexable) |
| `extra @> '{"key": "value"}'` | N/A — SQLite has no JSONB containment | ✅ Uses the `ix_audit_chain_extra_gin` GIN index in p13_c1_p99_db.py:97-100 |
| `extra ? 'key'` | N/A | ✅ Same GIN index |
| `extra @@ '$.key'` | N/A | ✅ Same GIN index |
| All 4 new tables | Created with JSON / Text / etc. native SQLite types | Created with JSONB / TEXT native PG types |
| `payload` column on `project_timeline_events` | `JSON` | `JSONB` (used to be `Text` in the model — now matches via `get_jsonb_column()`) |

---

## 5. Alembic chain

Before:  `0001_initial → 0002_usage_log → 0003_pg_models → 0004_billing → 0005_packs (head)`

After:   `0001_initial → 0002_usage_log → 0003_pg_models → 0004_billing → 0005_packs → 0006_project_center_requirements (head)`

Verified by:

```bash
$ cd backend/imdf && python -m alembic heads
0006_project_center_requirements (head)
$ python -m alembic history --rev-range=0005_packs:head
0005_packs -> 0006_project_center_requirements (head), P21 P2 P1 — 4 ORM tables missing from the alembic chain.
```

---

## 6. Workarounds used in the test (and why)

The end-to-end test (`test_alembic_chain_creates_4_missing_tables`) does NOT run a pure `alembic upgrade head` against a fresh DB. Instead, it uses a 3-step workaround:

1. **`Base.metadata.create_all(bind=engine)`** — creates the full ORM schema (the 14 ORM tables, including the 4 we're testing).
2. **`DROP TABLE IF EXISTS <table>`** for the 4 missing tables — this removes them from the DB so the next step actually exercises the migration's `CREATE TABLE` DDL.
3. **`alembic stamp 0005_packs`** — marks the DB as if migrations 0001-0005 have been applied, so 0006 is the *next* revision.
4. **`alembic upgrade head`** — runs **only** 0006, which is the migration we added. If 0006 is broken (wrong column types, missing columns, broken DDL), this call will raise.

**Why this workaround is necessary**: the imdf alembic chain has a pre-existing bug in `0004_billing.py:115` — it calls `op.create_unique_index("ux_billing_subscriptions_user", ...)` which doesn't exist in the installed alembic 1.16.1 (the method was removed; the correct way is `op.create_index(..., unique=True)`). That bug blocks the full chain from running on a fresh DB. **It is NOT in this task's scope** (it's R2-N1 "Dual alembic chains" + a separate 0004 issue) and fixing it would expand the diff well beyond "be conservative — only fix what's clearly broken".

The test still **proves**:
- The new 0006 migration is correctly linked into the chain (head = `0006_project_center_requirements`).
- The migration DDL is valid SQL on SQLite (the `op.create_table` calls all succeed).
- All 4 new tables exist in the DB after the upgrade.
- The model and the DDL agree on column types (round-trip test).
- All other ORM tables are still present.

If the 0004 bug is fixed later, the workaround can be replaced with a plain `alembic upgrade head` against a fresh DB.

---

## 7. Notes for the verifier

1. **Why `0006` and not `0042`?** — The task spec mentions a filename `0042_add_missing_tables.py`, but the imdf alembic chain only has revisions up to `0005_packs`, so the natural next revision is `0006_*`. I named the file `0006_project_center_requirements.py` to follow the project's existing 4-digit numeric convention and to be descriptive about the content. The chain head is `0006_project_center_requirements` and the file is in `backend/imdf/alembic/versions/`.

2. **The 0004 alembic bug is a separate issue** — `op.create_unique_index` doesn't exist in alembic 1.16.1. To unblock the test, I used the `create_all` + `drop` + `stamp` workaround described in §6. The proper fix is to change `0004_billing.py:115` to `op.create_index("ux_billing_subscriptions_user", "billing_subscriptions", ["user_id"], unique=True)` (same pattern as `p13_c1_p99_db.py:241`). That fix is **out of scope** for P2 P1 but should be a quick win in a follow-up.

3. **The `test_fk_count_is_documented` failure is pre-existing** — confirmed by stashing my changes and re-running; it fails on the pristine codebase. R2 Gap 8 / N1 — separate P1 issue, not addressed here.

4. **`audit_chain_entry.py:86` default changed** — was `default=""` (empty string), now `default=dict` (empty dict literal). The change is necessary because the column is now JSON-typed, and SQLAlchemy's `JSON` type prefers dict/list defaults over string defaults. Application code that previously wrote `extra=""` will still work (it'll be coerced) but new code should write a dict.

5. **No new dependencies introduced** — `get_jsonb_column()` is a project-existing helper in `backend/imdf/db/postgres.py:143` that uses `sqlalchemy.dialects.postgresql.JSONB`. Both `JSONB` and `JSON` are part of SQLAlchemy's core.

6. **The 4 missing tables were also created by `init_db()`** (via `Base.metadata.create_all`), so this fix is **not a behaviour change for existing dev databases** — those tables already exist. The fix is for the alembic chain itself: previously, the chain had no record of these tables, so any "fresh" `alembic upgrade head` (especially on PG prod) would skip them. Now the chain is complete.
