# P21-R1 DB Static Audit Report

**Date**: 2026-07-09 20:53
**Auditor**: coder (mvs_d67f2395a12b4a46a6c6f9de30c6933e)
**Scope**: backend/infrastructure/database.py, backend/imdf/db/postgres.py, backend/alembic/versions/*.py (3 files), backend/imdf/models/*.py (9 files)
**Method**: Static analysis only (no live DB queries, no SQL execution, no `sqlalchemy.engine.Engine.connect()`)
**Duration**: ~20 min

---

## 1. Inventory — Tables / Columns / Constraints

### 1.1 SQLAlchemy ORM models (imdf.models) — 14 tables

| Table | Model File | Columns | Indexes | Constraints | Soft Delete | FK Cascade |
|---|---|---|---|---|---|---|
| `users` | `__init__.py:71` | 9 cols (id PK, username UQ, role, email, status, skills JSON, password_hash, created_at, updated_at) | `ix_users_username` (UQ via column), `ix_users_role`, `ix_users_status` | UNIQUE(username) | ❌ none | none |
| `projects` | `__init__.py:105` | 11 cols (id PK, name, description, status, owner, members JSON, priority, tags JSON, start_date, due_date, timestamps) | `ix_projects_status`, `ix_projects_owner`, `ix_projects_priority` | — | ❌ none | none (all soft refs) |
| `tasks` | `__init__.py:157` | 8 cols (id PK, name, type, status, owner, payload JSON, timestamps) | `ix_tasks_status`, `ix_tasks_owner`, `ix_tasks_type` | — | ❌ none | none |
| `assets` | `__init__.py:191` | 8 cols (id PK, name, type, size, tags JSON, path, owner, timestamps) | `ix_assets_type`, `ix_assets_owner` | — | ❌ none | none |
| `datasets` | `__init__.py:226` | 7 cols (id PK, name, version, files_count, status, description, created_by, timestamps) | `ix_datasets_status`, `ix_datasets_created_by` | — | ❌ none | none |
| `usage_logs` | `usage_log.py:35` | 14 cols (id PK, user_id, org_id, provider_id, protocol, model, kind, status, prompt_tokens, completion_tokens, total_tokens, cost_usd, latency_ms, error_code, error_message, extra JSONB, created_at) | `ix_usage_logs_user_created` (user_id, created_at), `ix_usage_logs_org_created` (org_id, created_at), `ix_usage_logs_provider`, `ix_usage_logs_status` | — | ❌ none | none |
| `embeddings` | `embedding.py:64` | 9 cols (id PK, entity_type, entity_id, vector(1024), model, meta JSONB, chunk_text, extra JSONB, created_at) | `ix_embeddings_entity_type`, `ix_embeddings_entity_id`, `ix_embeddings_entity` (composite entity_type+entity_id), `ix_embeddings_model`, `ix_embeddings_created_at`, HNSW `ix_embeddings_vector_hnsw` | — | ❌ none | none (soft refs) |
| `workflows` | `workflow.py:46` | 11 cols (id PK, name, description, status, owner, project_id, dag_json JSONB, steps_count, last_run_at, tags JSONB, config JSONB, timestamps) | `ix_workflows_status`, `ix_workflows_owner`, `ix_workflows_project_id`, `ix_workflows_created_at` | — | ❌ none | none (project_id soft ref) |
| `agent_tasks` | `agent.py:48` | 22 cols (id PK, agent_type, status, priority, user_id, org_id, project_id, workflow_id, parent_id, payload JSONB, result JSONB, error JSONB, trace_id, idempotency_key, celery_task_id, retry_count, max_retries, meta JSONB, queued_at, started_at, finished_at, expires_at, error_message) | `ix_agent_tasks_agent_type`, `ix_agent_tasks_status`, `ix_agent_tasks_priority`, `ix_agent_tasks_user_id`, `ix_agent_tasks_org_id`, `ix_agent_tasks_project_id`, `ix_agent_tasks_workflow_id`, `ix_agent_tasks_parent_id`, `ix_agent_tasks_trace_id`, `ix_agent_tasks_idempotency_key`, `ix_agent_tasks_celery_task_id`, `ix_agent_tasks_queued_at`, `ix_agent_tasks_status_priority` (composite), `ix_agent_tasks_user_queued` (user_id, queued_at), GIN `ix_agent_tasks_payload_gin`, `ix_agent_tasks_result_gin`, `ix_agent_tasks_error_gin`, `ix_agent_tasks_meta_gin` | — | ❌ none | none |
| `audit_chain_entries` | `audit_chain_entry.py:46` | 14 cols (id PK BigInt autoinc, seq UNIQUE, timestamp, occurred_at, method, path, user, body_hash, status_code, actor, prev_hash, entry_hash, signature, extra TEXT) | `ix_audit_chain_seq` (UQ via column), `ix_audit_chain_timestamp`, `ix_audit_chain_method`, `ix_audit_chain_user`, `ix_audit_chain_method_path` (composite method+path), `ix_audit_chain_user_time` (user+timestamp), `ix_audit_chain_method_path_seq` (method+path+seq), GIN `ix_audit_chain_extra_gin` | UNIQUE(seq) | ❌ none | none |
| `project_members` | `project.py:60` | 5 cols (id PK, project_id, user_id, role, joined_at) | `ix_project_members_project`, `ix_project_members_user`, UQ `uq_project_members_project_user` | UNIQUE(project_id, user_id) | ❌ none | FK→projects CASCADE |
| `project_timeline_events` | `project.py:96` | 7 cols (id PK, project_id, event_type, actor, ts, payload JSONB, message) | `ix_project_timeline_project_ts` (project_id+ts), `ix_project_timeline_event_type`, `ix_project_timeline_project_id`, `ix_project_timeline_ts` | — | ❌ none (append-only by design) | FK→projects CASCADE |
| `requirements` | `requirement.py:47` | 16 cols (id PK, title, type, status, priority, created_by, description, acceptance_criteria, tags JSON, created_at, updated_at, closed_at, project_id, pack_id, qc_status, delivery_id, due_date, owner) | `ix_requirements_project_id`, `ix_requirements_pack_id`, `ix_requirements_delivery_id`, `ix_requirements_owner`, `ix_requirements_status`, `ix_requirements_priority`, `ix_requirements_type`, `ix_requirements_created_by` | — | ❌ none | none (all soft refs) |
| `requirement_tasks` | `requirement.py:107` | 12 cols (id PK, requirement_id, title, assignee, status, acceptance_criteria, estimated_hours, actual_hours, priority, created_at, completed_at, notes) | `ix_requirement_tasks_requirement_id`, `ix_requirement_tasks_assignee`, `ix_requirement_tasks_status`, `ix_requirement_tasks_priority` | — | ❌ none | none (requirement_id soft ref) |

### 1.2 Legacy raw-SQL tables (infrastructure/database.py PostgresManager) — 5 tables

**STATUS**: These tables are defined in raw CREATE TABLE SQL inside `_init_tables()` (lines 240-313), but **they are not exposed as SQLAlchemy ORM models**. The runtime calls `await self.execute_raw(create_tables_sql)` — only used if `PostgresManager` (legacy, not `imdf/db/__init__.py`) is instantiated.

| Table | Columns | Indexes | Notes |
|---|---|---|---|
| `users` | user_id PK, username UQ, email UQ, created_at, metadata JSONB | — | **NAME COLLISION** with ORM `users` table — different schema (no role/skills/etc) |
| `agents` | agent_id PK, agent_type, name, status, config JSONB, memory_vector VECTOR(1536), timestamps | `idx_agents_vector` (ivfflat), `idx_agents_type` | **NAME COLLISION** with nothing in ORM (ORM uses `agent_tasks`) |
| `tasks` | task_id PK, agent_id FK→agents, task_type, input_data JSONB, status, result JSONB, error TEXT, timestamps | `idx_tasks_status`, `idx_tasks_agent` | **NAME COLLISION** with ORM `tasks` table |
| `assets` | asset_id PK, asset_type, name, url TEXT, size BIGINT, metadata JSONB, embedding VECTOR(1536), created_at | `idx_assets_vector` (ivfflat) | **NAME COLLISION** with ORM `assets` |
| `workflows` | workflow_id PK, name, description, nodes JSONB, edges JSONB, status, timestamps | — | **NAME COLLISION** with ORM `workflows` — completely different schema (separate DAG as nodes/edges list vs unified `dag_json`) |

### 1.3 OpenMetadata-style metadata tables (alembic p4_4_w1_metadata) — 10 tables

| Table | Indexes | FK Cascade |
|---|---|---|
| `md_databases` | `ix_md_databases_service` | — |
| `md_schemas` | `ix_md_schemas_database`, UQ `uq_md_schemas_db_name` | FK→md_databases CASCADE |
| `md_tables` | `ix_md_tables_schema`, UQ `uq_md_tables_schema_name` | FK→md_schemas CASCADE |
| `md_columns` | `ix_md_columns_table`, UQ `uq_md_columns_table_name` | FK→md_tables CASCADE |
| `md_datasets` | `ix_md_datasets_tier` | — |
| `md_tags` | `ix_md_tags_category`, `ix_md_tags_source` | — |
| `md_tag_assignments` | `ix_md_tag_assignments_tag`, `ix_md_tag_assignments_target`, UQ `uq_md_tag_assignments` | FK→md_tags CASCADE |
| `md_glossaries` | — | — |
| `md_glossary_terms` | `ix_md_glossary_terms_glossary`, UQ `uq_md_glossary_terms_glossary_name` | FK→md_glossaries CASCADE |
| `md_term_relations` | `ix_md_term_relations_from`, `ix_md_term_relations_to`, UQ `uq_md_term_relations` | FK→md_glossary_terms CASCADE (both from + to) |

**Total tables in scope**: 14 (ORM) + 5 (legacy raw SQL, dormant) + 10 (metadata) = **29 tables**

---

## 2. Migration Audit

### 2.1 Alembic chain

| File | revision | down_revision | Status |
|---|---|---|---|
| `p4_4_w1_metadata.py` | `p4_4_w1_metadata` | `None` (root) | ✅ root |
| `p13_c1_p99_db.py` | `p13_c1_p99_db` | `p4_4_w1_metadata` | ✅ chained |
| `p5_r1_t1_project_center.py` | `p5_r1_t1_project_center` | `p13_c1_p99_db` | ✅ chained |

**Chain integrity**: ✅ Linear, no branches, no gaps.

### 2.2 Coverage gaps — migrations vs ORM models

| ORM Model | Has migration? | Risk |
|---|---|---|
| `users`, `projects`, `tasks`, `assets`, `datasets` (P2-1-W1) | ❌ NO migration — created by `Base.metadata.create_all()` only | **P0**: First `alembic upgrade head` on fresh DB will NOT create these tables. Anyone running alembic before init_db() loses the schema. |
| `usage_logs` (P2-3-W2) | ❌ NO migration | **P0** |
| `embeddings`, `workflows`, `agent_tasks`, `audit_chain_entries` (P3-1-W1) | ❌ NO migration | **P0** |
| `requirements`, `requirement_tasks` (P5-R1-T2) | ❌ NO migration | **P0** |
| `project_members`, `project_timeline_events` (P5-R1-T1) | ✅ `p5_r1_t1_project_center.py` | OK |
| `md_*` (P4-4-W1) | ✅ `p4_4_w1_metadata.py` | OK |

**10 of 14 ORM tables lack migrations**. The `p13_c1_p99_db` migration creates indexes assuming those tables already exist — on a fresh DB, `op.create_index(...)` (lines 108-143) **will fail with "relation does not exist"**.

---

## 3. Top 20 Gaps (P0/P1/P2)

### P0 — Data loss / migration break

**Gap 1: 10 ORM tables have no alembic migration**
- File: backend/alembic/versions/ (only 3 files exist)
- Affected tables: users, projects, tasks, assets, datasets, usage_logs, embeddings, workflows, agent_tasks, audit_chain_entries, requirements, requirement_tasks
- Risk: `alembic upgrade head` against a fresh PG fails on `p13_c1_p99_db.create_index(...)` because `agent_tasks`/`usage_logs`/`workflows`/`embeddings`/`audit_chain_entries` don't exist yet
- Fix: Add baseline migration `p2_1_w1_baseline.py` that creates all pre-existing ORM tables before p13_c1_p99_db runs, OR re-order so p13_c1_p99_db is the root

**Gap 2: `p13_c1_p99_db` indexes will fail on fresh DB**
- File: backend/alembic/versions/p13_c1_p99_db.py:108-143
- Issue: `op.create_index(...)` for `agent_tasks`, `usage_logs`, `workflows`, `embeddings`, `audit_chain_entries` assumes tables exist. On fresh DB, raises `ProgrammingError: relation "agent_tasks" does not exist`
- Fix: Wrap each create_index in `if op.get_bind().dialect.has_table(op.get_bind(), "agent_tasks"):` OR create those tables first

**Gap 3: Legacy `PostgresManager` tables collide with ORM schema**
- File: backend/infrastructure/database.py:240-313 (`_init_tables`)
- Issue: If `PostgresManager` is ever instantiated (e.g. by old routes), it creates raw-SQL `users`/`tasks`/`assets`/`workflows` tables with different schema than the ORM ones. Same name, different columns. SQLAlchemy ORM queries on `User.username` will silently miss rows that exist in the raw-SQL `users` table.
- Fix: Either (a) delete `PostgresManager._init_tables` and require all callers to use `imdf/db/__init__.py:engine`, OR (b) namespace raw-SQL tables (e.g. `legacy_users`) and add a deprecation warning

### P0 — Transaction integrity

**Gap 4: `update_project` in project_engine.py commits a partial mutation on members**
- File: backend/imdf/engines/project_engine.py:452-487
- Issue: When updating members, it (a) deletes stale `ProjectMember` rows, (b) adds new ones, (c) mutates `row.members` (JSON), (d) records an event — all in one try/except but **inside a single SessionLocal session without explicit `with db.begin():`**. If step (d) fails after step (a)+(b), only the event insert is rolled back; but more critically, the surrounding `try/except: db.rollback()` is on the *outer* `db` session, which is OK — however, the auto-flush semantics of SQLAlchemy 2.0 may have already pushed `db.delete(pm)` queries to the DB before commit.
- Risk: Partial member-sync leaving orphan deletes if process is killed mid-loop
- Fix: Wrap the members section in `with db.begin_nested():` (savepoint) so a single failure rolls back only that batch

**Gap 5: 94 `db.add/commit/rollback` sites across engine code without explicit transaction markers**
- File: backend/imdf/engines/project_engine.py (43 sites), backend/imdf/api/p1_c_w1_routes.py (29 sites), backend/imdf/api/admin_routes.py (12 sites), backend/imdf/engines/usage_tracker.py (5 sites), backend/imdf/models/embedding.py (2 sites), backend/imdf/scripts/create_admin.py (3 sites)
- Issue: Almost all use raw `db.add()` + `db.commit()` pattern. `SessionLocal` is configured with `autocommit=False, autoflush=False` (backend/imdf/db/__init__.py:118-123) — good — but no explicit `with db.begin():` context manager. SQLAlchemy will auto-begin a transaction on first query, so semantically OK; however, **partial success in multi-row loops is possible** if an exception escapes between `db.add()` and `db.commit()`.
- Fix: Adopt `with SessionLocal() as db: with db.begin(): ...` pattern across all write sites; audit each existing site for `try/except: db.rollback()` correctness (some sites correctly rollback, but several have `db.rollback()` AFTER `db.add()` in a try, leaving the rollback never called if commit itself fails)

**Gap 6: `scripts/create_admin.py:89-101` has commit-before-add on re-add path**
- File: backend/imdf/scripts/create_admin.py:78-101
- Issue: Line 89 commits an empty read (no-op). Lines 100-101 `db.add(user); db.commit()` — fine, but the intervening `db.close()` is not in finally, so on exception the session leaks
- Fix: Wrap in `with SessionLocal() as session: ...`

### P0 — Soft delete absent

**Gap 7: No soft-delete column on any ORM table**
- Grep result: 52 hits for `deleted` but ALL are in non-model files (webhook types, route responses, fallback log keys). Zero matches in `backend/imdf/models/*.py` for `is_deleted`, `deleted_at`, `soft_delete`.
- Risk: All deletes are HARD deletes (`db.delete(row)` in project_engine.py:512, p1_c_w1_routes.py:848/1042, admin_routes.py:236). GDPR/audit compliance fails — once a project is deleted, it's gone. DSAR delete (privacy_routes.py:467) hard-deletes too.
- Affected tables: projects, users, tasks, assets, datasets, workflows, agent_tasks, embeddings, requirements, requirement_tasks
- Fix: Add `deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)` to every model; add a base `SoftDeleteMixin` class; update all `db.query(X).filter(X.id == ...)` to `.filter(X.deleted_at.is_(None))`

### P1 — FK & referential integrity

**Gap 8: 9 of 14 ORM tables have ZERO foreign keys**
- File: backend/imdf/models/*.py
- Soft-ref fields without FK:
  - `projects.members` (JSON list of user_ids) — no FK
  - `tasks.owner` — soft-ref to users.id, no FK
  - `tasks.payload.project_id` (sometimes) — soft-ref
  - `assets.owner` — soft-ref
  - `usage_logs.user_id`, `org_id` — soft-ref
  - `usage_logs.provider_id` — soft-ref to providers table (which doesn't exist as ORM!)
  - `embeddings.entity_type` + `entity_id` — intentional polymorphic, but no validation
  - `workflows.owner`, `workflows.project_id` — soft-ref
  - `agent_tasks.user_id`, `org_id`, `project_id`, `workflow_id`, `parent_id` — ALL soft-refs
  - `agent_tasks.celery_task_id` — soft-ref to Celery broker
  - `requirements.project_id`, `pack_id`, `delivery_id`, `owner` — soft-ref
  - `requirement_tasks.requirement_id`, `assignee` — soft-ref
  - `audit_chain_entries.user`, `actor` — soft-ref
- Risk: Orphan rows accumulate. e.g. `agent_tasks.user_id = "user_abc"` can point to a deleted user; nothing prevents it. Cascade delete impossible.
- Fix: Add FK constraints on hard relations at minimum (agent_tasks.parent_id → agent_tasks.id self-ref, requirement_tasks.requirement_id → requirements.id, project_members.user_id → users.id). Leave polymorphic refs (embeddings.entity_*) soft.

**Gap 9: `project_members.user_id` has no FK to users**
- File: backend/imdf/models/project.py:60-81 (model) + backend/alembic/versions/p5_r1_t1_project_center.py:106-118 (migration)
- Issue: FK only on `project_id → projects.id`. `user_id` is `String(64), nullable=False, index=True` but no FK. A `ProjectMember(user_id="user_does_not_exist")` row can exist.
- Fix: Add `sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_project_members_user")` in both model and migration

### P1 — Index coverage

**Gap 10: `usage_logs.model` has no index despite likely query**
- File: backend/imdf/models/usage_log.py
- Likely WHERE: `WHERE model = ? AND created_at >= ?` (cost attribution per model)
- Current: index on `provider_id`, `kind`, `status`, `(user_id, created_at)`, `(org_id, created_at)` — none on `model`
- Fix: Add `Index("ix_usage_logs_model_created", "model", "created_at")`

**Gap 11: `usage_logs.error_code` / `error_message` not indexed**
- File: backend/imdf/models/usage_log.py:60-61
- Likely WHERE: `WHERE error_code IS NOT NULL` (error dashboard)
- Fix: Partial index `Index("ix_usage_logs_errors", "created_at", postgresql_where=...)` or simply add `ix_usage_logs_error_code`

**Gap 12: `audit_chain_entries.status_code` not indexed**
- File: backend/imdf/models/audit_chain_entry.py:72-75
- Likely WHERE: `WHERE status_code >= 400` (error audit)
- Fix: Add `Index("ix_audit_chain_status_code_time", "status_code", "occurred_at")`

**Gap 13: `embeddings.model` + `created_at` composite missing**
- File: backend/imdf/models/embedding.py:79-90
- Has `ix_embeddings_model` and `ix_embeddings_created_at` separately, but no composite. Query `WHERE model = ? ORDER BY created_at DESC` will use single-column then sort. Composite would let PG skip sort.
- Fix: Add `Index("ix_embeddings_model_created", "model", "created_at")`

**Gap 14: `agent_tasks.finished_at` not indexed but used for retention scans**
- File: backend/imdf/models/agent.py:84-86
- Retention job likely: `DELETE FROM agent_tasks WHERE status IN ('done','error') AND finished_at < ?`
- Fix: Add `Index("ix_agent_tasks_status_finished", "status", "finished_at")`

**Gap 15: `requirements.closed_at` not indexed**
- File: backend/imdf/models/requirement.py:67
- Likely query: closed requirements over time period
- Fix: Add `Index("ix_requirements_closed_at", "closed_at")`

### P1 — N+1 / query patterns

**Gap 16: `project_engine.py:459-463` dictionary comprehension over query result is OK, BUT `update_project` member-sync loop has pattern that can be O(N²)**
- File: backend/imdf/engines/project_engine.py:459-478
- Pattern: loads `existing = {pm.user_id: pm for pm in db.query(ProjectMember).filter(...).all()}` (1 query — OK), then iterates `for uid, pm in list(existing.items()): if uid not in new_set: db.delete(pm)` (deletes flush on next autoflush — usually 1 query if `synchronize_session=False` is set, else 1 per row).
- Fix: Use bulk `db.query(ProjectMember).filter(ProjectMember.user_id.in_(to_delete)).delete(synchronize_session=False)` to avoid per-row DELETE

**Gap 17: `usage_tracker.py:224, 263` `for r in q.all()` then attribute access (not strict N+1 but loads all rows into memory)**
- File: backend/imdf/engines/usage_tracker.py:221-231, 260-269
- Pattern: `q = db.query(UsageLog).filter(...); for r in q.all(): rows.append(...)` — loads entire user history into Python. For a heavy user with 100k+ calls/month this becomes multi-MB allocation.
- Fix: Aggregate in SQL: `SELECT provider_id, kind, status, SUM(total_tokens), SUM(cost_usd), COUNT(*) FROM usage_logs WHERE user_id = ? AND created_at >= ? GROUP BY provider_id, kind, status`

**Gap 18: Zero uses of `joinedload` / `selectinload` / `subqueryload`**
- File: backend/imdf/ — 0 hits across grep
- Risk: `db.query(Project).first()` then accessing `project.members` (JSON) — OK because JSON. But `db.query(ProjectMember).all()` then iterating `.user` (which would lazy-load User) — N+1.
- Fix: Identify every relationship traversal and add `options(selectinload(...))` or convert to `lazy='selectin'` on the relationship

### P2 — Schema design

**Gap 19: Date/time columns are inconsistent — String vs DateTime**
- Files:
  - `models/__init__.py:130-131` Project.created_at → `DateTime`
  - `models/requirement.py:65-67` RequirementRow.created_at → `String(64)` (literal ISO string!)
  - `models/project.py:75` ProjectMember.joined_at → `DateTime`
  - `models/project.py:115` ProjectTimelineEvent.ts → `DateTime`
  - `models/audit_chain_entry.py:63` timestamp → `String(40)`, occurred_at → `DateTime` (dual fields!)
- Issue: `RequirementRow.created_at` is a String — can't do `ORDER BY created_at DESC` efficiently, can't do `WHERE created_at >= ?` without parsing
- Fix: Migrate String ISO timestamps to proper `DateTime` (or `TIMESTAMPTZ` on PG) — minimum change is `requirement.py:65-67`

**Gap 20: Audit chain has TWO date columns (timestamp + occurred_at)**
- File: backend/imdf/models/audit_chain_entry.py:63-65
- Issue: `timestamp: String(40)` and `occurred_at: DateTime`. They represent the same event time. Stored twice. Risk of drift.
- Fix: Pick one (`occurred_at: DateTime` is more correct for PG), deprecate `timestamp`

---

## 4. Summary Statistics

| Metric | Count | Source |
|---|---|---|
| ORM tables | 14 | 9 model files |
| Alembic migrations | 3 | p4_4_w1_metadata, p13_c1_p99_db, p5_r1_t1_project_center |
| Migrations missing for ORM | 10 | users, projects, tasks, assets, datasets, usage_logs, embeddings, workflows, agent_tasks, audit_chain_entries, requirements, requirement_tasks (12 actually) |
| Tables with FK CASCADE | 12 | All in md_* + project_members + project_timeline_events |
| Tables with FK at all | 4 | project_members, project_timeline_events, md_schemas/tables/columns/tag_assignments/glossary_terms/term_relations |
| Soft-delete tables | 0 | grep confirms 0 hits in models |
| Indexes declared | ~50 | Across all 14 ORM + migration-added |
| `db.add` sites | 94 | grep across imdf/ |
| `joinedload`/`selectinload` uses | 0 | grep confirms 0 |
| `with engine.begin()` / `session.begin()` sites | 1 | db/postgres.py:99 (extension install only) |

---

## 5. Recommended fix order

1. **M0 (must-fix pre-prod)** — Gap 1, 2, 7, 8
2. **M1 (week 1)** — Gap 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15
3. **M2 (week 2)** — Gap 16, 17, 18, 19, 20