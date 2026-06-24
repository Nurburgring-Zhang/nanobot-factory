"""Verify migration: list tables, count rows."""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Hermes\生产平台\nanobot-factory\backend\imdf")
from sqlalchemy import text
from db import engine

with engine.connect() as conn:
    rows = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ).fetchall()
    print("TABLES in imdf_p2.db:")
    for (name,) in rows:
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM \"{name}\"")).scalar()
        print(f"  - {name}: {cnt} rows")
    print()
    print("alembic_version:")
    ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"  -> {ver}")
