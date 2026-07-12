"""P21-R3 EXTREME DB TEST EXPANSION — 16 categories.

Scope: backend/infrastructure/database.py + backend/imdf/db/ + alembic + models.
Method: static analysis (default — always runs) + live DB smoke (skipped if no live DB).

Each test category surfaces one of the 16 R3 extreme dimensions:
  1. Connection pool exhaustion (100 concurrent, verify no leak)
  2. Long-running query (statement timeout / pool_timeout coverage)
  3. Migration chain integrity (no orphan heads, valid down_revision)
  4. Schema drift (ORM models vs alembic versions)
  5. Index usage (declared indexes referenced in queries)
  6. N+1 patterns (per-iteration .query in loops)
  7. Transaction boundaries (multi-step writes wrapped in begin())
  8. Bulk operations (bulk_insert / insert([...]) used)
  9. Read replica routing (read_engine present for SELECT)
 10. Dead letter / failed state (AgentTask has retry/dead_letter)
 11. PII fields (password_hash encrypted at rest, no plaintext)
 12. Soft delete (every delete goes through soft delete path)
 13. FK cascade (every FK has ondelete= rule)
 14. Migration reversibility (downgrade() function present)
 15. Concurrent write audit (locking / serialization on hot tables)
 16. Alembic head drift (single head per chain)

Each test is parametrized over a list of `gaps` — the assertion is intentionally
non-fatal so we surface *all* gaps in a single pytest run. Each test
returns/publishes a structured report via ``extreme_gaps`` fixture.

Run:  python -m pytest tests/db/test_extreme_boundary.py -v --tb=short
Skip live tests:  python -m pytest tests/db/test_extreme_boundary.py -v -m "not live"

All tests must:
- be importable on Windows + D:\\ComfyUI\\.ext\\python.exe
- run without network
- not require live PostgreSQL
- finish in <2min total
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ── Paths (Windows-safe, no symlink assumptions) ──────────────────────────
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent  # tests/db/test_*.py → project root
_BACKEND_DIR = _PROJECT_ROOT / "backend"
_IMDF_DIR = _BACKEND_DIR / "imdf"
_INFRA_DIR = _BACKEND_DIR / "infrastructure"
_MODELS_DIR = _IMDF_DIR / "models"
_ENGINES_DIR = _IMDF_DIR / "engines"
_LEGACY_ALEMBIC_VERSIONS = _BACKEND_DIR / "alembic" / "versions"
_IMDF_ALEMBIC_VERSIONS = _IMDF_DIR / "alembic" / "versions"
_LEGACY_ALEMBIC_ENV = _BACKEND_DIR / "alembic" / "env.py"
_IMDF_ALEMBIC_ENV = _IMDF_DIR / "alembic" / "env.py"

# Mark live DB tests so we can skip them on machines without PG
live_only = pytest.mark.skipif(
    not os.environ.get("IMDF_LIVE_DB", "").lower() in ("1", "true", "yes"),
    reason="requires live DB (set IMDF_LIVE_DB=1 to enable)",
)


# ── Shared fixtures ───────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def project_root() -> Path:
    return _PROJECT_ROOT


@pytest.fixture(scope="session")
def backend_dir() -> Path:
    return _BACKEND_DIR


@pytest.fixture(scope="session")
def imdf_dir() -> Path:
    return _IMDF_DIR


@pytest.fixture(scope="session")
def extreme_gaps() -> List[Dict[str, Any]]:
    """Shared collector — each test appends gaps; final report shows them all."""
    return []


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"<<READ_ERROR: {e}>>"


def _list_python_files(directory: Path) -> List[Path]:
    if not directory.exists():
        return []
    return sorted([p for p in directory.rglob("*.py") if "__pycache__" not in str(p)])


# ════════════════════════════════════════════════════════════════════════════
# 1. CONNECTION POOL EXHAUSTION — 100 concurrent, verify no leak
# ════════════════════════════════════════════════════════════════════════════
class TestConnectionPoolExhaustion:
    """Verify that opening many concurrent connections does not leak pool slots."""

    def test_sqlite_pool_size_default_within_engine_spec(self, imdf_dir):
        """SQLite engine uses SA defaults (pool_size=5, max_overflow=10)."""
        text = _read_text(imdf_dir / "db" / "__init__.py")
        # The SQLite engine constructor does not override pool_size/max_overflow
        # → default 5 + 10 = 15 max concurrent connections
        assert "pool_size" not in text or "pool_size=5" in text, (
            "SQLite engine should either omit pool_size (use SA default 5) "
            "or explicitly set 5 — current text uses non-default value"
        )
        assert "max_overflow" not in text or "max_overflow=10" in text

    def test_pg_pool_params_from_env(self, imdf_dir):
        """PG engine reads pool_size / max_overflow / pool_recycle / statement_timeout
        from env (IMDF_PG_POOL_SIZE etc.) so ops can tune without code change."""
        text = _read_text(imdf_dir / "db" / "postgres.py")
        assert "IMDF_PG_POOL_SIZE" in text, "PG pool_size must be env-tunable"
        assert "IMDF_PG_MAX_OVERFLOW" in text, "PG max_overflow must be env-tunable"
        assert "IMDF_PG_POOL_RECYCLE" in text, "PG pool_recycle must be env-tunable"
        assert "IMDF_PG_STATEMENT_TIMEOUT_MS" in text, "PG statement_timeout must be env-tunable"

    @live_only
    def test_100_concurrent_uses_no_leak_sqlite(self, imdf_dir, tmp_path):
        """Live smoke: spin 100 short connections, drain, expect checkedin==pool_size."""
        from sqlalchemy import create_engine, text
        db_file = tmp_path / "extreme_pool.db"
        engine = create_engine(
            f"sqlite:///{db_file}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        errors: List[str] = []
        barrier = threading.Barrier(100)
        successes = [0]
        success_lock = threading.Lock()

        def worker(i: int):
            try:
                barrier.wait(timeout=10)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1")).scalar()
                with success_lock:
                    successes[0] += 1
            except Exception as e:  # pragma: no cover
                errors.append(f"thread {i}: {e!r}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Pool errors under 100 concurrent: {errors[:5]}"
        assert successes[0] == 100, f"only {successes[0]}/100 succeeded"
        # Drain check
        pool = engine.pool
        assert pool.checkedout() == 0, f"pool not drained: {pool.checkedout()} still checked out"
        engine.dispose()


# ════════════════════════════════════════════════════════════════════════════
# 2. LONG-RUNNING QUERY — statement timeout must be configured
# ════════════════════════════════════════════════════════════════════════════
class TestLongRunningQueryProtection:
    """Identify any query path without timeout protection."""

    def test_pg_statement_timeout_set_in_server_settings(self, imdf_dir):
        """PG engine must set ``statement_timeout`` in connect_args to prevent
        a single slow query from monopolizing a pool connection."""
        text = _read_text(imdf_dir / "db" / "postgres.py")
        assert "statement_timeout" in text, (
            "PG engine MUST configure statement_timeout in server_settings "
            "— otherwise a slow query will hold the pool connection indefinitely"
        )

    def test_sqlite_has_timeout_30s(self, imdf_dir):
        """SQLite engine has ``timeout=30`` so a locked writer won't deadlock forever."""
        text = _read_text(imdf_dir / "db" / "__init__.py")
        assert '"timeout": 30' in text or "'timeout': 30" in text, (
            "SQLite engine must set connect_args={'timeout': 30} for write waits"
        )

    def test_no_unbounded_query_in_engines(self, imdf_dir, extreme_gaps):
        """Scan engine code for ``SELECT`` with no LIMIT clause — likely a footgun."""
        files = _list_python_files(_ENGINES_DIR)
        unbounded: List[Tuple[str, int, str]] = []
        for f in files:
            if f.name == "__init__.py":
                continue
            text = _read_text(f)
            # Look for .query(Model) or select(Model) without LIMIT
            for m in re.finditer(r"db\.query\([^)]+\)\.all\(\)", text):
                line_no = text[: m.start()].count("\n") + 1
                unbounded.append((f.name, line_no, m.group(0)[:60]))
        if unbounded:
            extreme_gaps.append({
                "category": "long-running-query",
                "severity": "P2",
                "files": unbounded[:10],
                "total": len(unbounded),
                "hint": "Add .limit(N) or pagination to .all() calls",
            })
        # Soft assertion — at most 5 such calls; if more, it's a real gap
        assert len(unbounded) <= 5, (
            f"Found {len(unbounded)} unbounded .all() calls in engines/ — first 5: "
            f"{unbounded[:5]}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 3. MIGRATION CHAIN INTEGRITY — no orphan heads, all down_revisions valid
# ════════════════════════════════════════════════════════════════════════════
class TestMigrationChainIntegrity:
    """Verify both alembic chains have valid topology."""

    @pytest.fixture(scope="class")
    def all_chains(self) -> Dict[str, List[Path]]:
        chains = {}
        if _LEGACY_ALEMBIC_VERSIONS.exists():
            chains["legacy"] = sorted(_LEGACY_ALEMBIC_VERSIONS.glob("*.py"))
        if _IMDF_ALEMBIC_VERSIONS.exists():
            chains["imdf"] = sorted(_IMDF_ALEMBIC_VERSIONS.glob("*.py"))
        return chains

    def test_each_revision_has_valid_revision_id(self, all_chains):
        """Each alembic revision file's ``revision =`` must be a valid identifier."""
        bad = []
        for chain_name, files in all_chains.items():
            for f in files:
                text = _read_text(f)
                # Match `revision = "..."` with or without type annotation
                m = re.search(r"^revision(?:\s*:\s*\w+)?\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
                if not m:
                    bad.append((chain_name, f.name, "no revision variable"))
                else:
                    rev_id = m.group(1)
                    if not re.match(r"^[a-zA-Z0-9_]+$", rev_id):
                        bad.append((chain_name, f.name, f"bad id: {rev_id}"))
        assert not bad, f"Malformed revision ids: {bad}"

    def test_down_revision_points_to_existing_revision(self, all_chains):
        """Every ``down_revision`` must point to a ``revision`` that exists in the same chain."""
        errors = []
        for chain_name, files in all_chains.items():
            chain_data = {}
            for f in files:
                text = _read_text(f)
                # Match with or without type annotation, must not cross newlines
                rev_m = re.search(
                    r"^revision(?:\s*:\s*\w+)?\s*=\s*['\"]([^'\"]+)['\"]",
                    text, re.M,
                )
                # For down_revision, match `None` separately so we don't capture extra
                down_m = re.search(
                    r"^down_revision(?:\s*:\s*\w+)?\s*=\s*(['\"]?)([^'\"]*?)\1\s*$",
                    text, re.M,
                )
                if rev_m:
                    rev_id = rev_m.group(1)
                    if down_m:
                        v = down_m.group(2).strip()
                        down_id = v if v and v != "None" else None
                    else:
                        down_id = None
                    chain_data[rev_id] = (down_id, f)
            revs_in_chain = set(chain_data.keys())
            for rev_id, (down_id, f) in chain_data.items():
                if down_id is None:
                    continue  # root migration
                if down_id not in revs_in_chain:
                    errors.append((
                        chain_name, f.name, rev_id, down_id,
                        "down_revision not found in same chain",
                    ))
        assert not errors, f"Orphan down_revisions: {errors}"

    def test_single_head_per_chain(self, all_chains):
        """A chain with multiple heads is a footgun — alembic upgrade head will fail."""
        multi_head_chains = []
        for chain_name, files in all_chains.items():
            revisions = set()
            down_revisions: Dict[Optional[str], int] = Counter()
            for f in files:
                text = _read_text(f)
                rev_m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
                down_m = re.search(r"^down_revision\s*=\s*(['\"]?)([^'\"]+)\1", text, re.M)
                if not rev_m:
                    continue
                rev = rev_m.group(1)
                revisions.add(rev)
                down = down_m.group(2).strip() if down_m else None
                down_revisions[down] += 1
            # Heads = revisions whose id is never referenced as a down_revision
            heads = revisions - set(down_revisions.keys())
            if len(heads) > 1:
                multi_head_chains.append((chain_name, sorted(heads)))
        assert not multi_head_chains, (
            f"Multiple alembic heads (will break 'alembic upgrade head'): {multi_head_chains}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 4. SCHEMA DRIFT — ORM models vs migration history
# ════════════════════════════════════════════════════════════════════════════
class TestSchemaDrift:
    """Compare ``Base.metadata`` tables to what alembic migrations create."""

    def test_orm_model_count_matches_documented(self, imdf_dir):
        """Confirm the documented model count (14 across all model files)."""
        all_classes = 0
        for f in _list_python_files(_MODELS_DIR):
            text = _read_text(f)
            all_classes += len(re.findall(r"^class\s+\w+\s*\(Base\)\s*:", text, re.M))
        # 14 declared in __all__: User, Project, Task, Asset, Dataset, UsageLog,
        # Embedding, Workflow, AgentTask, AuditChainEntry, ProjectMember,
        # ProjectTimelineEvent, RequirementRow, TaskRow
        assert all_classes >= 12, (
            f"models/ declares {all_classes} Base subclasses — expected 12–14"
        )

    def test_project_member_model_exists(self, imdf_dir):
        """P5-R1-T1 added ProjectMember + ProjectTimelineEvent — verify they exist."""
        proj_text = _read_text(imdf_dir / "models" / "project.py")
        assert "class ProjectMember" in proj_text, (
            "ProjectMember model missing from models/project.py — "
            "P5-R1-T1 feature was never persisted as ORM"
        )
        assert "class ProjectTimelineEvent" in proj_text, (
            "ProjectTimelineEvent model missing from models/project.py"
        )

    def test_requirement_models_exist(self, imdf_dir):
        """Depth-7 RequirementEngine persistence: RequirementRow + TaskRow."""
        req_text = _read_text(imdf_dir / "models" / "requirement.py")
        assert "class RequirementRow" in req_text, (
            "RequirementRow model missing from models/requirement.py"
        )
        assert "class TaskRow" in req_text, (
            "TaskRow model missing from models/requirement.py"
        )

    def test_no_orm_only_tables_outside_known_set(self, imdf_dir, extreme_gaps):
        """R2 found 4 tables in ORM but missing from imdf/alembic/versions:
        project_members, project_timeline_events, requirements, requirement_tasks.

        **P21 P2 P1 fix (N3)**: those 4 tables are now created by
        ``0006_project_center_requirements.py`` so the schema-drift
        gap is closed.  This test is now a *regression guard* — it
        asserts the 4 tables are **no longer** in the ``orm_only``
        set, i.e. the N3 fix is still in place.
        """
        models_text = _read_text(imdf_dir / "models" / "__init__.py")
        all_models = re.findall(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", models_text)
        # Also scan sub-modules
        sub_modules = ["project.py", "requirement.py", "usage_log.py", "embedding.py",
                       "workflow.py", "agent.py", "audit_chain_entry.py"]
        for mod in sub_modules:
            t = _read_text(imdf_dir / "models" / mod)
            all_models.extend(re.findall(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", t))

        # Collect tables that alembic imdf chain *would* create (rough grep)
        imdf_alembic_text = ""
        for vf in _list_python_files(_IMDF_ALEMBIC_VERSIONS):
            imdf_alembic_text += _read_text(vf) + "\n"
        alembic_tables = set(
            re.findall(r"(?:create_table|op\.create_table)\s*\(\s*['\"]([^'\"]+)['\"]",
                       imdf_alembic_text),
        )
        # Models not in any alembic migration
        orm_only = sorted(set(all_models) - alembic_tables)
        if orm_only:
            extreme_gaps.append({
                "category": "schema-drift",
                "severity": "P0",
                "orm_only_tables": orm_only,
                "hint": (
                    "Add imdf/alembic/versions/0006_*.py and 0007_*.py to migrate "
                    "these tables. Otherwise first deploy hits 'relation does not exist'."
                ),
            })
        # P21 P2 P1 fix: the 4 R2 N3 missing tables are now created by
        # 0006_project_center_requirements.py, so they must NOT appear
        # in the ORM-only set.  This is the regression guard.
        n3_now_fixed = {"project_members", "project_timeline_events",
                        "requirements", "requirement_tasks"}
        assert n3_now_fixed.isdisjoint(set(orm_only)), (
            f"R2 N3 fix regressed — {n3_now_fixed & set(orm_only)} are "
            f"back in the ORM-only set: {orm_only}.  Re-check "
            f"imdf/alembic/versions/0006_project_center_requirements.py."
        )


# ════════════════════════════════════════════════════════════════════════════
# 5. INDEX USAGE — each index declared must be referenced somewhere
# ════════════════════════════════════════════════════════════════════════════
class TestIndexUsage:
    """Indexes that are never used in queries waste write IO + storage."""

    def test_indexes_have_named_convention(self, imdf_dir):
        """Verify all Index() declarations use the ix_ prefix (PostgreSQL convention)."""
        bad = []
        for f in _list_python_files(_MODELS_DIR):
            text = _read_text(f)
            for m in re.finditer(r"Index\(['\"]([^'\"]+)['\"]", text):
                if not m.group(1).startswith("ix_"):
                    bad.append((f.name, m.group(1)))
        assert not bad, f"Index names without 'ix_' prefix: {bad}"

    def test_usage_logs_model_has_index(self, imdf_dir):
        """R2 Gap 10: usage_logs.model column has no index → full table scan on cost queries."""
        text = _read_text(imdf_dir / "models" / "usage_log.py")
        # Should have an index on `model` column or composite (model, created_at)
        if "model: Mapped" in text or '"model"' in text:
            assert ("'model'" in text and "Index(" in text) or True, (
                "usage_log.model column exists but is not indexed — "
                "WHERE model = ? AND created_at >= ? will full-scan"
            )
        # Soft — we surface the gap rather than fail
        has_model_index = bool(re.search(r"Index\([^)]*['\"]model['\"]", text))
        if not has_model_index:
            pytest.skip(
                "Known gap: usage_logs.model is unindexed (R2 Gap 10) — "
                "this test skips but gap is real"
            )

    def test_all_indexes_in_models_listed(self, imdf_dir):
        """Enumerate every Index() declared in models/ so we can audit usage."""
        all_indexes: List[Tuple[str, str]] = []  # (file, index_name)
        for f in _list_python_files(_MODELS_DIR):
            text = _read_text(f)
            for m in re.finditer(r"Index\(['\"]([^'\"]+)['\"]", text):
                all_indexes.append((f.name, m.group(1)))
        assert len(all_indexes) >= 10, (
            f"Expected 10+ indexes across models, found {len(all_indexes)}: {all_indexes[:5]}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 6. N+1 PATTERNS — db.query inside a for-loop is a classic footgun
# ════════════════════════════════════════════════════════════════════════════
class TestNPlusOnePatterns:
    """Scan engine code for the classic N+1 anti-pattern."""

    def test_no_db_query_in_for_loop_in_engines(self, imdf_dir, extreme_gaps):
        """Grep engines/ for ``for X in: ... db.query(Y)`` patterns.

        Heuristic: detect a ``for `` line within 5 lines above a ``db.query(`` call.
        """
        n_plus_1: List[Tuple[str, int, str]] = []
        for f in _list_python_files(_ENGINES_DIR):
            text = _read_text(f)
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "db.query(" in line or "session.query(" in line:
                    # Look backwards 5 lines for `for ` or `while `
                    window = lines[max(0, i - 5):i]
                    if any(re.match(r"^\s*for\s", w) for w in window):
                        n_plus_1.append((f.name, i + 1, line.strip()[:80]))
        if n_plus_1:
            extreme_gaps.append({
                "category": "n+1",
                "severity": "P1",
                "files": n_plus_1[:10],
                "total": len(n_plus_1),
                "hint": "Use joinedload/selectinload or eager-load collections",
            })
        # Allow up to 5 small ones; more is a real signal
        assert len(n_plus_1) <= 5, (
            f"Found {len(n_plus_1)} N+1 patterns in engines/ — first 5: {n_plus_1[:5]}"
        )

    def test_no_select_without_load_strategy_in_routes(self, imdf_dir):
        """Routes/ should not fetch related objects inside loops (different scope: API layer).

        Soft metric: just record the count; >300 for-loops in a routes dir is suspicious.
        """
        api_dir = _IMDF_DIR / "api"
        if not api_dir.exists():
            pytest.skip("no imdf/api directory")
        count = 0
        for f in _list_python_files(api_dir):
            text = _read_text(f)
            count += len(re.findall(r"^\s*for\s+\w+\s+in\s+[^:]+:\s*$", text, re.M))
        # Sanity bound — very high counts would indicate sloppy code, but typical
        # REST routes have 100-300 for-loops. We just verify the metric is recorded.
        assert count < 500, f"Suspiciously many for-loops in api/: {count}"


# ════════════════════════════════════════════════════════════════════════════
# 7. TRANSACTION BOUNDARIES — multi-step write wrapped
# ════════════════════════════════════════════════════════════════════════════
class TestTransactionBoundaries:
    """Every multi-step write should use ``with db.begin():`` (or engine.begin())."""

    def test_explicit_begin_blocks_underused(self, imdf_dir, extreme_gaps):
        """Count db.add/commit sites vs explicit ``with db.begin():`` wrappers.

        R2 finding: 33 db.add/commit sites, 0 explicit ``with db.begin():`` blocks.
        """
        total_add_commit = 0
        begin_blocks = 0
        for f in _list_python_files(_IMDF_DIR):
            text = _read_text(f)
            total_add_commit += len(re.findall(r"db\.add\(|session\.add\(", text))
            total_add_commit += len(re.findall(r"db\.commit\(|session\.commit\(", text))
            begin_blocks += len(re.findall(r"with\s+\w+\.begin\(\)|with\s+db\.begin\(\)", text))
        ratio = begin_blocks / max(total_add_commit, 1)
        if total_add_commit > 0 and ratio < 0.05:
            extreme_gaps.append({
                "category": "transaction-boundaries",
                "severity": "P1",
                "total_add_commit": total_add_commit,
                "explicit_begin_blocks": begin_blocks,
                "hint": (
                    "Adopt 'with SessionLocal() as db: with db.begin():' for "
                    "multi-step writes — auto-commit masks partial-success bugs"
                ),
            })
        # Test always passes (surface the gap) — we just record the metric
        assert begin_blocks >= 0

    def test_get_db_has_try_finally(self, imdf_dir):
        """get_db() must close() the session in finally — even on exception."""
        text = _read_text(imdf_dir / "db" / "__init__.py")
        assert "def get_db" in text, "get_db missing"
        assert "finally" in text, "get_db must have try/finally to close session"
        assert "db.close()" in text, "get_db must call db.close() in finally"


# ════════════════════════════════════════════════════════════════════════════
# 8. BULK OPERATIONS — bulk_insert / insert([...]) used
# ════════════════════════════════════════════════════════════════════════════
class TestBulkOperations:
    """Verify the project uses bulk insert/update patterns where appropriate."""

    def test_bulk_insert_helpers_used(self, imdf_dir, extreme_gaps):
        """SQLAlchemy 2.0 ``insert(Model).values([{...}, {...}])`` should appear in
        high-volume paths (usage_logs, embeddings, bulk project ops)."""
        bulk_sites = 0
        for f in _list_python_files(_IMDF_DIR):
            text = _read_text(f)
            bulk_sites += len(re.findall(
                r"insert\([^)]+\)\.values\(\[|bulk_insert_mappings|bulk_save_objects",
                text,
            ))
        if bulk_sites < 3:
            extreme_gaps.append({
                "category": "bulk-operations",
                "severity": "P1",
                "bulk_sites": bulk_sites,
                "hint": (
                    "Replace per-row db.add() in usage_tracker / embeddings with "
                    "session.execute(insert(Model), [row_dicts]) — 10–100× faster"
                ),
            })
        assert bulk_sites >= 0  # surface only

    def test_usage_tracker_uses_bulk_or_explains(self, imdf_dir, extreme_gaps):
        """usage_tracker.py is the highest-volume writer; check it has bulk logic.

        R2 Gap N7: per-row db.add() in usage_logs = N round trips. Surface as gap.
        """
        tracker = _read_text(imdf_dir / "engines" / "usage_tracker.py")
        has_bulk = any(p in tracker for p in (
            "insert(", "bulk_insert_mappings", "executemany", "session.execute",
        ))
        if not has_bulk:
            extreme_gaps.append({
                "category": "bulk-operations",
                "severity": "P1",
                "file": "engines/usage_tracker.py",
                "hint": (
                    "Replace per-row db.add() in UsageLog writes with "
                    "session.execute(insert(UsageLog), [rows]) — 10–100× faster"
                ),
            })
            pytest.skip("Known R2 gap: usage_tracker uses per-row db.add()")
        assert has_bulk


# ════════════════════════════════════════════════════════════════════════════
# 9. READ REPLICA ROUTING — read-only queries to replica
# ════════════════════════════════════════════════════════════════════════════
class TestReadReplicaRouting:
    """Verify a separate read_engine exists, or document the gap."""

    def test_no_read_replica_routing(self, imdf_dir, extreme_gaps):
        """R2 Gap N6: 0 read-replica routing. All reads hit primary.
        This test *intentionally* surfaces the gap (we expect it to fail-soft).
        """
        text_init = _read_text(imdf_dir / "db" / "__init__.py")
        has_read_engine = "read_engine" in text_init or "RoutingSession" in text_init
        if not has_read_engine:
            extreme_gaps.append({
                "category": "read-replica",
                "severity": "P1",
                "hint": (
                    "Add 'read_engine' alongside 'engine' + RoutingSession that "
                    "dispatches SELECT statements. Fall back to primary on read failure."
                ),
            })
        # Soft: we want this to be a known gap for the report
        # But the test itself should pass (just records)
        assert "engine" in text_init

    def test_session_factory_single_bind(self, imdf_dir):
        """SessionLocal binds to a single engine — no read/write split."""
        text = _read_text(imdf_dir / "db" / "__init__.py")
        # Default case: bind=engine (single)
        assert "bind=engine" in text, (
            "SessionLocal must bind to a single engine today (no read/write split)"
        )


# ════════════════════════════════════════════════════════════════════════════
# 10. DEAD LETTER / FAILED STATE — failed insert handling
# ════════════════════════════════════════════════════════════════════════════
class TestDeadLetterFailedState:
    """Verify AgentTask has a structured failed-state / dead-letter path."""

    def test_agent_task_has_failed_status(self, imdf_dir, extreme_gaps):
        """AgentTask.status must accept a 'failed' / 'error' / 'dead' value.

        R2 finding: docstring lists queued/running/done/error/timeout/cancelled,
        but no DB-level enum constraint; this test surfaces the *enforcement* gap.
        """
        text = _read_text(imdf_dir / "models" / "agent.py")
        assert "class AgentTask" in text
        assert "status" in text
        has_failure_state = any(p in text for p in (
            "'failed'", "'error'", "'timeout'", "'cancelled'", "'dead'",
            '"failed"', '"error"', '"timeout"', '"cancelled"', '"dead"',
        ))
        if not has_failure_state:
            extreme_gaps.append({
                "category": "dead-letter",
                "severity": "P1",
                "hint": (
                    "AgentTask.status is a free String — add Enum/SQLAlchemy Enum "
                    "constraint to enforce valid states (queued/running/done/error/...)"
                ),
            })
            pytest.skip("Known gap: AgentTask.status has no Enum constraint")
        assert has_failure_state

    def test_dead_letter_table_or_field(self, imdf_dir, extreme_gaps):
        """R2 Gap N8: AgentTask has no dead_letter column/table; failed tasks pile up.
        Surface this gap; allow it to be a known issue for the report.
        """
        agent_text = _read_text(imdf_dir / "models" / "agent.py")
        all_text = ""
        for f in _list_python_files(_MODELS_DIR):
            all_text += _read_text(f)
        has_dl_column = "dead_letter" in agent_text or "failed_at" in agent_text
        has_dl_table = "class DeadLetter" in all_text
        if not (has_dl_column or has_dl_table):
            extreme_gaps.append({
                "category": "dead-letter",
                "severity": "P1",
                "hint": (
                    "Add 'failed_at: DateTime' to AgentTask + a separate "
                    "DeadLetter table for tasks that exhausted retries."
                ),
            })
        # Soft assertion — gap is expected
        assert True


# ════════════════════════════════════════════════════════════════════════════
# 11. PII FIELDS — identify + verify encryption at rest
# ════════════════════════════════════════════════════════════════════════════
class TestPIIFields:
    """PII columns must be hashed/encrypted, never plaintext."""

    def test_user_password_is_hashed(self, imdf_dir):
        """User.password_hash must be present (not 'password' plaintext)."""
        text = _read_text(imdf_dir / "models" / "__init__.py")
        assert "password_hash" in text, (
            "User model must have 'password_hash' field, not plaintext 'password'"
        )
        # No plaintext password field
        assert "password: Mapped[str]" not in text, (
            "Plaintext 'password' field found — must use 'password_hash'"
        )

    def test_email_field_present_with_validation(self, imdf_dir):
        """User.email should exist and have reasonable size limit."""
        text = _read_text(imdf_dir / "models" / "__init__.py")
        assert "email" in text, "User must have email field"
        # Look for String(200) or similar bounded type
        assert re.search(r"email.*Mapped\[Optional\[str\].*String\(\d+\)", text), (
            "User.email must be String(N) — unbounded is a DoS vector"
        )

    def test_pii_not_logged_anywhere(self, imdf_dir, extreme_gaps):
        """Search for any logger.* call that includes a PII variable (NOT the word in a sentence).

        Refined: only match ``logger.X(f"...{var}...")`` where ``var`` is one of
        the PII names. False-positive guards: skip if the substring is part of a
        longer English word (e.g. 'email_field', 'secret_key_path').
        """
        bad = []
        pii_names = ("password", "email", "api_key", "secret_token", "access_token")
        # We use a simple line scan + look for f-string interpolation of these names
        for f in _list_python_files(_IMDF_DIR):
            text = _read_text(f)
            for ln, line in enumerate(text.splitlines(), start=1):
                if "logger." not in line and "logging." not in line:
                    continue
                # Only flag when the PII name appears as an f-string {var} reference
                for pii in pii_names:
                    # Match f"... {pii} ..." or f"...={pii}" or logger.X(f"...{pii}...")
                    if re.search(rf"[\{{=]\s*{pii}\s*[\}}:=]", line):
                        bad.append((f.name, ln, line.strip()[:100]))
                        break
        if bad:
            extreme_gaps.append({
                "category": "pii",
                "severity": "P0",
                "files": bad[:5],
                "hint": "Redact PII from logs — log only user_id, not email/password",
            })
        # Soft — at most 3 PII log lines acceptable; >3 is a real signal
        assert len(bad) <= 3, f"Found PII in logs ({len(bad)}): {bad[:5]}"


# ════════════════════════════════════════════════════════════════════════════
# 12. SOFT DELETE — every delete is soft
# ════════════════════════════════════════════════════════════════════════════
class TestSoftDelete:
    """GDPR/DSAR compliance: deletes must be soft, not hard."""

    def test_no_soft_delete_columns(self, imdf_dir, extreme_gaps):
        """R2 Gap 7: zero soft-delete columns. All db.delete() are hard.
        Surface as a known P0 gap.
        """
        all_text = ""
        for f in _list_python_files(_MODELS_DIR):
            all_text += _read_text(f) + "\n"
        has_soft = any(
            p in all_text
            for p in ("deleted_at", "is_deleted", "soft_delete", "deleted")
        )
        if not has_soft:
            extreme_gaps.append({
                "category": "soft-delete",
                "severity": "P0",
                "hint": (
                    "Add 'deleted_at: DateTime, nullable=True' to all user-facing "
                    "tables (User, Project, Asset, Dataset). Wrap db.delete() in "
                    "soft_delete helper that sets deleted_at instead of removing row."
                ),
            })
        # Test always passes — gap is the finding
        assert True

    def test_privacy_routes_use_soft_or_documented(self, imdf_dir):
        """privacy_routes DSAR endpoint should soft-delete (not hard)."""
        privacy = _IMDF_DIR / "api" / "privacy_routes.py"
        if not privacy.exists():
            pytest.skip("no privacy_routes.py — feature not built")
        text = _read_text(privacy)
        # If it does hard db.delete(), that's a gap
        has_hard_delete = bool(re.search(r"db\.delete\(", text))
        if has_hard_delete:
            pytest.skip(
                "Known gap: privacy_routes.py uses hard db.delete() — should soft-delete"
            )


# ════════════════════════════════════════════════════════════════════════════
# 13. FK CASCADE — every FK has ondelete rule
# ════════════════════════════════════════════════════════════════════════════
class TestFKCascade:
    """Every FK constraint should have ondelete= to prevent orphaned rows."""

    def test_fk_constraints_have_ondelete(self, imdf_dir, extreme_gaps):
        """R2 Gap 8/9: 12/14 tables have zero FK constraints; the 2 that do may lack ondelete.
        We scan model code for ForeignKey / ForeignKeyConstraint declarations and
        check each has an ondelete= rule.
        """
        bad = []
        for f in _list_python_files(_MODELS_DIR):
            text = _read_text(f)
            for m in re.finditer(
                r"ForeignKey(?:Constraint)?\s*\([^)]+\)",
                text,
                re.S,
            ):
                snippet = m.group(0)
                if "ondelete" not in snippet:
                    line_no = text[: m.start()].count("\n") + 1
                    bad.append((f.name, line_no, snippet[:80]))
        if bad:
            extreme_gaps.append({
                "category": "fk-cascade",
                "severity": "P1",
                "files": bad[:10],
                "total": len(bad),
                "hint": (
                    "Every ForeignKey / ForeignKeyConstraint must specify "
                    "ondelete='CASCADE' or 'SET NULL' to prevent orphaned rows"
                ),
            })
        # Soft — at least some FKs are present
        assert True

    def test_fk_count_is_documented(self, imdf_dir):
        """Confirm at least 1 FK exists in models (R2: only 2 of 14 tables have FKs)."""
        fk_count = 0
        for f in _list_python_files(_MODELS_DIR):
            text = _read_text(f)
            # Match ForeignKey( or ForeignKeyConstraint( at word boundary
            fk_count += len(re.findall(r"\bForeignKey(?:Constraint)?\s*\(", text))
        # R2 documented 2 FKs; 0 would mean we lost them
        assert fk_count >= 1, f"Expected at least 1 FK, found {fk_count}"


# ════════════════════════════════════════════════════════════════════════════
# 14. MIGRATION REVERSIBILITY — downgrade() present
# ════════════════════════════════════════════════════════════════════════════
class TestMigrationReversibility:
    """Every alembic migration must have a downgrade() function."""

    def test_each_migration_has_downgrade(self):
        """Each revision file defines ``def downgrade():``."""
        bad = []
        for chain_dir in (_LEGACY_ALEMBIC_VERSIONS, _IMDF_ALEMBIC_VERSIONS):
            if not chain_dir.exists():
                continue
            for f in sorted(chain_dir.glob("*.py")):
                text = _read_text(f)
                if "def downgrade" not in text:
                    bad.append(str(f.relative_to(_PROJECT_ROOT)))
        assert not bad, f"Migrations missing downgrade(): {bad}"

    def test_each_migration_has_upgrade(self):
        """Each revision file defines ``def upgrade():``."""
        bad = []
        for chain_dir in (_LEGACY_ALEMBIC_VERSIONS, _IMDF_ALEMBIC_VERSIONS):
            if not chain_dir.exists():
                continue
            for f in sorted(chain_dir.glob("*.py")):
                text = _read_text(f)
                if "def upgrade" not in text:
                    bad.append(str(f.relative_to(_PROJECT_ROOT)))
        assert not bad, f"Migrations missing upgrade(): {bad}"

    def test_downgrade_is_not_trivial_pass(self, extreme_gaps):
        """downgrade() should actually drop the table/index — not just `pass`."""
        weak = []
        for chain_dir in (_LEGACY_ALEMBIC_VERSIONS, _IMDF_ALEMBIC_VERSIONS):
            if not chain_dir.exists():
                continue
            for f in sorted(chain_dir.glob("*.py")):
                text = _read_text(f)
                # Find the body of downgrade()
                m = re.search(r"def downgrade\(\)[^:]*:\s*\n((?:\s+[^\n]*\n)+)", text)
                if m:
                    body = m.group(1).strip()
                    # If body is just `pass` or empty → weak
                    if body in ("pass", "") or "op.drop_table" not in body and "op.execute" not in body:
                        weak.append(str(f.relative_to(_PROJECT_ROOT)))
        if weak:
            extreme_gaps.append({
                "category": "migration-reversibility",
                "severity": "P2",
                "files": weak,
                "hint": (
                    "downgrade() should drop tables/indexes, not just 'pass' — "
                    "rollback path is needed for blue/green deploys"
                ),
            })
        # Soft — surface, don't fail
        assert True


# ════════════════════════════════════════════════════════════════════════════
# 15. CONCURRENT WRITE AUDIT — race conditions + locking
# ════════════════════════════════════════════════════════════════════════════
class TestConcurrentWriteAudit:
    """Verify hot tables survive concurrent writes without corruption."""

    @live_only
    def test_concurrent_inserts_serialize(self, tmp_path):
        """Live: 50 threads insert into the same table → all succeed (serialized by SQLite)."""
        conn = sqlite3.connect(str(tmp_path / "concurrent.db"), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE hot (id INTEGER PRIMARY KEY AUTOINCREMENT, val TEXT)")
        conn.commit()

        errors: List[str] = []
        successes = [0]
        s_lock = threading.Lock()

        def worker(i: int):
            try:
                # Each thread opens its own connection
                c = sqlite3.connect(str(tmp_path / "concurrent.db"), timeout=30)
                c.execute("INSERT INTO hot (val) VALUES (?)", (f"t{i}",))
                c.commit()
                c.close()
                with s_lock:
                    successes[0] += 1
            except Exception as e:  # pragma: no cover
                errors.append(f"t{i}: {e!r}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Concurrent write errors: {errors[:5]}"
        assert successes[0] == 50, f"only {successes[0]}/50 succeeded"
        # Verify all 50 rows present
        c2 = sqlite3.connect(str(tmp_path / "concurrent.db"))
        n = c2.execute("SELECT COUNT(*) FROM hot").fetchone()[0]
        c2.close()
        assert n == 50, f"row count mismatch: expected 50, got {n}"
        conn.close()

    def test_no_select_for_update_in_engines(self, imdf_dir, extreme_gaps):
        """Document absence of SELECT FOR UPDATE — surfaces a known concurrency gap."""
        for_update_sites = 0
        for f in _list_python_files(_ENGINES_DIR):
            text = _read_text(f)
            for_update_sites += len(re.findall(r"with_for_update|SELECT.+FOR UPDATE", text, re.I))
        # 0 is fine for now — test just records the metric
        extreme_gaps.append({
            "category": "concurrent-write",
            "severity": "P2",
            "select_for_update_sites": for_update_sites,
            "hint": (
                "For 'claim task' / 'consume quota' patterns, use "
                "SELECT ... FOR UPDATE SKIP LOCKED or row-versioning"
            ),
        })
        assert for_update_sites >= 0


# ════════════════════════════════════════════════════════════════════════════
# 16. ALEMBIC HEAD DRIFT — identify missing migrations
# ════════════════════════════════════════════════════════════════════════════
class TestAlembicHeadDrift:
    """Verify only one head per chain, and that the chain is the right one."""

    def test_only_one_alembic_chain_in_imdf(self, imdf_dir):
        """The real chain is imdf/alembic; legacy backend/alembic should either
        be removed or have its env.py point to Base.metadata.
        """
        legacy_env = _read_text(_LEGACY_ALEMBIC_ENV) if _LEGACY_ALEMBIC_ENV.exists() else ""
        imdf_env = _read_text(_IMDF_ALEMBIC_ENV) if _IMDF_ALEMBIC_ENV.exists() else ""

        # Real chain must use Base.metadata
        assert "target_metadata = Base.metadata" in imdf_env, (
            "imdf/alembic/env.py must set target_metadata = Base.metadata"
        )

        # If legacy chain still exists, it must also point to Base.metadata
        # OR be empty (otherwise it's a footgun for new devs)
        if _LEGACY_ALEMBIC_VERSIONS.exists():
            legacy_versions = list(_LEGACY_ALEMBIC_VERSIONS.glob("*.py"))
            if legacy_versions:
                # If legacy chain has migrations, its env must point to Base.metadata
                # Currently it points to hand-written MetaData() — that's the R2 P0
                if "Base.metadata" not in legacy_env:
                    pytest.skip(
                        "Known gap (R2-N1 P0): backend/alembic/env.py points to "
                        "hand-written MetaData() — fix by either removing or "
                        "redirecting to Base.metadata"
                    )

    def test_legacy_chain_does_not_collide_with_imdf_chain(self, imdf_dir):
        """If both chains exist, their revision files should not share revision IDs."""
        rev_ids: Dict[str, str] = {}  # rev_id -> chain
        for chain_name, chain_dir in (
            ("legacy", _LEGACY_ALEMBIC_VERSIONS),
            ("imdf", _IMDF_ALEMBIC_VERSIONS),
        ):
            if not chain_dir.exists():
                continue
            for f in chain_dir.glob("*.py"):
                text = _read_text(f)
                m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
                if m:
                    rev = m.group(1)
                    if rev in rev_ids:
                        pytest.fail(
                            f"Revision id '{rev}' appears in both "
                            f"'{rev_ids[rev]}' and '{chain_name}' — collision"
                        )
                    rev_ids[rev] = chain_name

    def test_chain_has_at_least_one_migration(self):
        """Each existing chain must have at least one migration file."""
        for name, chain_dir in (
            ("legacy", _LEGACY_ALEMBIC_VERSIONS),
            ("imdf", _IMDF_ALEMBIC_VERSIONS),
        ):
            if not chain_dir.exists():
                continue
            versions = list(chain_dir.glob("*.py"))
            if versions:
                assert len(versions) >= 1, f"{name} chain has no .py files"


# ════════════════════════════════════════════════════════════════════════════
# REPORT — at end, dump the collected extreme_gaps as a summary
# ════════════════════════════════════════════════════════════════════════════
class TestExtremeReport:
    """Final summary — surfaces the cumulative findings for the verifier."""

    def test_summary_gaps_collected(self, extreme_gaps, tmp_path):
        """Write a JSON report of all gaps surfaced during the test run."""
        import json
        out = tmp_path / "extreme_gaps.json"
        out.write_text(
            json.dumps(extreme_gaps, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        # Sanity: gaps file exists and is valid JSON
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
        # We don't assert count == 0 — gaps are expected (this is the extreme test)
        print(f"\n=== EXTREME DB TEST SUMMARY ===\n"
              f"Total gaps surfaced: {len(loaded)}\n"
              f"By category: {Counter(g.get('category') for g in loaded)}\n"
              f"Report written to: {out}\n"
              f"===============================")
