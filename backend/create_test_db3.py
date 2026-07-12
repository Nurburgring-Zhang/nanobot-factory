"""Create fresh DB with both main backend tables AND imdf tables, stamped to p4_4_w1_metadata.

Tests if p13_c1_p99_db migration works when all referenced tables exist.
"""
import sqlite3
import os

db_path = 'data/nanobot_test3.db'
if os.path.exists(db_path):
    os.remove(db_path)
conn = sqlite3.connect(db_path)
c = conn.cursor()

# ── main backend tables (would be created by p4_4_w1_metadata) ──
c.execute("""
CREATE TABLE md_databases (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    service VARCHAR(64) DEFAULT 'custom' NOT NULL,
    description TEXT DEFAULT '',
    host VARCHAR(256) DEFAULT '',
    port VARCHAR(8) DEFAULT '',
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL
)
""")
# Don't actually need to create all md_* tables; just enough for alembic_version to be happy

# ── imdf tables that p13_c1_p99_db needs ──
c.execute("""
CREATE TABLE agent_tasks (
    id VARCHAR(64) PRIMARY KEY,
    agent_type VARCHAR(40),
    status VARCHAR(20),
    priority INTEGER,
    payload TEXT,
    result TEXT,
    error TEXT,
    meta TEXT,
    queued_at TIMESTAMP
)
""")
c.execute("""
CREATE TABLE usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id VARCHAR(64),
    kind VARCHAR(40),
    created_at TIMESTAMP,
    extra TEXT
)
""")
c.execute("""
CREATE TABLE workflows (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200),
    owner VARCHAR(64),
    status VARCHAR(20),
    dag_json TEXT,
    updated_at TIMESTAMP
)
""")
c.execute("""
CREATE TABLE embeddings (
    id VARCHAR(64) PRIMARY KEY,
    entity_type VARCHAR(40),
    entity_id VARCHAR(64),
    vector TEXT,
    meta TEXT,
    created_at TIMESTAMP
)
""")
c.execute("""
CREATE TABLE audit_chain_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq BIGINT,
    method VARCHAR(10),
    path VARCHAR(500),
    timestamp VARCHAR(40),
    occurred_at TIMESTAMP,
    extra TEXT
)
""")
c.execute("""
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
)
""")
c.execute("INSERT INTO alembic_version VALUES ('p4_4_w1_metadata')")

conn.commit()
conn.close()
print(f'Created DB at {db_path}')
cur = sqlite3.connect(db_path).cursor()
names = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print(f'Tables: {names}')