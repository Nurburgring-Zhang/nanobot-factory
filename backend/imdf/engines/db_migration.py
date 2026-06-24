"""数据库迁移管理器(轻量版Alembic接口)"""
import os, json, hashlib
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path("data/migrations")
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = MIGRATIONS_DIR / "state.json"

class MigrationManager:
    def __init__(self):
        self._state = self._load_state()
    
    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception as e: logger.error(f"Operation failed: {e}")
        return {"version": 0, "applied": []}
    
    def _save_state(self):
        STATE_FILE.write_text(json.dumps(self._state, indent=2))
    
    @property
    def current_version(self) -> int:
        return self._state.get("version", 0)
    
    def register_migration(self, version: int, name: str, sql: str):
        """注册迁移"""
        migration_file = MIGRATIONS_DIR / f"v{version:04d}_{name}.sql"
        migration_file.write_text(sql)
        return migration_file
    
    def apply_pending(self, db_path: str = "data/imdf.db"):
        """应用未执行的迁移"""
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
        applied = 0
        
        for mf in migrations:
            # 解析版本号
            parts = mf.stem.split("_", 1)
            ver = int(parts[0][1:])  # v0001 -> 1
            
            if ver <= self.current_version:
                continue
            
            sql = mf.read_text()
            try:
                cursor.executescript(sql)
                conn.commit()
                self._state["version"] = ver
                self._state["applied"].append(mf.stem)
                self._save_state()
                applied += 1
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"迁移 v{ver} 失败: {e}")
        
        conn.close()
        return applied
    
    def get_status(self) -> dict:
        migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
        return {
            "current_version": self.current_version,
            "total_migrations": len(migrations),
            "pending": len(migrations) - len(self._state.get("applied", [])),
            "applied": self._state.get("applied", []),
        }
