"""R2 audit dry-run: connection pool + concurrent ops + migration gap + schema drift."""
import os
import sys
import time
import threading
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "imdf"))

# Use a SHARED file-based SQLite (in-memory :memory: is per-connection → pool gives each thread a new private DB)
import tempfile
TEST_DB = os.path.join(tempfile.gettempdir(), "p21_r2_dryrun.db")
if os.path.exists(TEST_DB):
    os.unlink(TEST_DB)
os.environ["IMDF_P2_DB_URL"] = f"sqlite:///{TEST_DB}"

from db import Base, engine, SessionLocal
from models import register_all

register_all()
Base.metadata.create_all(bind=engine)

from models import UsageLog, ProjectMember, RequirementRow, TaskRow
from datetime import datetime, timezone


def test_1_concurrent_inserts():
    """100 concurrent inserts. Detect pool exhaustion / serialization / errors."""
    errors = []
    inserts_ok = 0
    lock = threading.Lock()

    def worker(i):
        nonlocal inserts_ok
        try:
            s = SessionLocal()
            s.add(
                UsageLog(
                    id=f"ul_{i:012d}",
                    user_id=f"user_{i}",
                    provider_id="test",
                    protocol="openai",
                    kind="chat",
                    status="ok",
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            s.commit()
            s.close()
            with lock:
                inserts_ok += 1
        except Exception as e:
            errors.append(f"#{i}: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - t0
    print(f"\n=== Test 1: 100 concurrent UsageLog inserts ===")
    print(f"  elapsed:   {elapsed:.2f}s")
    print(f"  succeeded: {inserts_ok}/100")
    print(f"  errors:    {len(errors)}")
    if errors[:3]:
        for e in errors[:3]:
            print(f"  - {e[:200]}")
    pool = engine.pool
    print(f"  pool:      class={type(pool).__name__} size={pool._pool.maxsize if hasattr(pool._pool, 'maxsize') else 'n/a'} checkedout={len(pool._pool._holders) if hasattr(pool._pool, '_holders') else 'n/a'}")


def test_2_pool_under_load():
    """Force-checkout N connections simultaneously. Detect leak."""
    from sqlalchemy import text
    hold_time = 0.5
    errors = []
    n = 50

    def hold(i):
        try:
            s = SessionLocal()
            s.execute(text("SELECT 1"))
            time.sleep(hold_time)
            s.close()
        except Exception as e:
            errors.append(str(e))

    print(f"\n=== Test 2: {n} concurrent connection holds ({hold_time}s each) ===")
    threads = [threading.Thread(target=hold, args=(i,)) for i in range(n)]
    t0 = time.time()
    for t in threads:
        t.start()
    time.sleep(0.1)  # let some connect
    pool = engine.pool
    print(f"  peak checkedout: {pool.checkedout()}, peak overflow: {pool.overflow()}, total size: {pool.size()}")
    for t in threads:
        t.join()
    print(f"  after drain:  checkedout={pool.checkedout()}, overflow={pool.overflow()}, size={pool.size()}")
    print(f"  errors: {len(errors)}")
    if errors[:3]:
        for e in errors[:3]:
            print(f"  - {e[:200]}")


def test_3_schema_drift():
    """Compare what Base.metadata has vs what imdf/alembic migrations create."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())

    expected_from_orm = set()
    for table_name, table in Base.metadata.tables.items():
        expected_from_orm.add(table_name)

    # What imdf/alembic/versions creates:
    # 0001: users, projects, tasks, assets, datasets
    # 0002: usage_logs
    # 0003: embeddings, workflows, agent_tasks, audit_chain_entries
    # 0004: billing_orders, billing_subscriptions, billing_usage_log
    # 0005: packs, pack_assets
    expected_from_migrations = {
        "users", "projects", "tasks", "assets", "datasets",
        "usage_logs",
        "embeddings", "workflows", "agent_tasks", "audit_chain_entries",
        "billing_orders", "billing_subscriptions", "billing_usage_log",
        "packs", "pack_assets",
    }

    orm_only = expected_from_orm - expected_from_migrations
    mig_only = expected_from_migrations - expected_from_orm
    both = expected_from_orm & expected_from_migrations
    print(f"\n=== Test 3: Schema drift ORM vs alembic ===")
    print(f"  ORM tables:        {len(expected_from_orm)}")
    print(f"  Migration tables:  {len(expected_from_migrations)}")
    print(f"  Both:              {len(both)}")
    print(f"  ORM-only (no migration): {orm_only}")
    print(f"  Migration-only (no ORM model): {mig_only}")


def test_4_bulk_ops():
    """Check if any model uses bulk_insert / insert().values() instead of per-row add()."""
    import subprocess
    # Use grep on imdf/
    root = os.path.join(os.path.dirname(__file__), "..", "backend", "imdf")
    print(f"\n=== Test 4: Bulk operation usage ===")
    for pat in ["bulk_insert_mappings", "bulk_save_objects", "session.bulk", "insert(.*).values", "executemany"]:
        result = subprocess.run(
            ["powershell", "-Command", f"Select-String -Path '{root}\\\\**\\\\*.py' -Pattern '{pat}' -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True
        )
        count = result.stdout.strip() or "0"
        print(f"  pattern={pat!r}: {count} matches")
    # Now show per-row db.add count
    result = subprocess.run(
        ["powershell", "-Command", f"Select-String -Path '{root}\\\\**\\\\*.py' -Pattern 'db\\.add\\(|session\\.add\\(' -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
        capture_output=True, text=True
    )
    print(f"  per-row db.add/session.add: {result.stdout.strip()}")


if __name__ == "__main__":
    test_1_concurrent_inserts()
    test_2_pool_under_load()
    test_3_schema_drift()
    test_4_bulk_ops()
    print("\n=== Done ===")
