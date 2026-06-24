"""Final DB state summary."""
import sys
sys.path.insert(0, r"D:\Hermes\生产平台\nanobot-factory\backend\imdf")
from sqlalchemy import text
from db import engine

with engine.connect() as c:
    ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"alembic_version = {ver}")
    tables = c.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%' ORDER BY name")
    ).fetchall()
    print(f"tables ({len(tables)}): {[r[0] for r in tables]}")
    for (name,) in tables:
        n = c.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
        # count indexes for this table
        idx = c.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name=:t AND name NOT LIKE 'sqlite_%'"),
            {"t": name},
        ).scalar()
        print(f"  {name}: {n} rows, {idx} indexes")
