"""Check what indexes are in test3 DB."""
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
c = conn.cursor()

print(f'=== Tables in {db_path} ===')
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for t in c.fetchall():
    print(f'  {t[0]}')

print()
print('=== Indexes ===')
c.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name, name")
for r in c.fetchall():
    print(f'  {r[0]} ON {r[1]}')

print()
print('=== alembic_version ===')
c.execute("SELECT * FROM alembic_version")
for r in c.fetchall():
    print(f'  {r}')

conn.close()