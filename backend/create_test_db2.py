import sqlite3
import os

db_path = 'data/nanobot_test2.db'
if os.path.exists(db_path):
    os.remove(db_path)
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS assets (id VARCHAR(32) PRIMARY KEY, name VARCHAR(255), type VARCHAR(255), path VARCHAR(255), size INTEGER, hash VARCHAR(255), created_at VARCHAR(32), updated_at VARCHAR(32))')
c.execute('CREATE TABLE IF NOT EXISTS md_databases (id VARCHAR(32) PRIMARY KEY, name VARCHAR(128), service VARCHAR(64), created_at VARCHAR(32), updated_at VARCHAR(32))')
c.execute('CREATE TABLE IF NOT EXISTS folders (id VARCHAR(32) PRIMARY KEY, name VARCHAR(128), parent_id VARCHAR(32), created_at VARCHAR(32), updated_at VARCHAR(32))')
c.execute('CREATE TABLE IF NOT EXISTS agent_tasks (id VARCHAR(64) PRIMARY KEY, agent_type VARCHAR(40), status VARCHAR(20), priority INTEGER, payload TEXT, result TEXT, error TEXT, meta TEXT, queued_at TIMESTAMP)')
c.execute('CREATE TABLE IF NOT EXISTS usage_logs (id INTEGER PRIMARY KEY, provider_id VARCHAR(64), kind VARCHAR(40), created_at TIMESTAMP, extra TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS workflows (id VARCHAR(64) PRIMARY KEY, name VARCHAR(200), owner VARCHAR(64), status VARCHAR(20), dag_json TEXT, updated_at TIMESTAMP)')
c.execute('CREATE TABLE IF NOT EXISTS embeddings (id VARCHAR(64) PRIMARY KEY, entity_type VARCHAR(40), entity_id VARCHAR(64), vector TEXT, meta TEXT, created_at TIMESTAMP)')
c.execute('CREATE TABLE IF NOT EXISTS audit_chain_entries (id INTEGER PRIMARY KEY, seq BIGINT, method VARCHAR(10), path VARCHAR(500), timestamp VARCHAR(40), occurred_at TIMESTAMP, extra TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)')
c.execute("INSERT OR REPLACE INTO alembic_version VALUES ('p4_4_w1_metadata')")
conn.commit()
conn.close()
print(f'Created fresh DB at {db_path} with all tables')