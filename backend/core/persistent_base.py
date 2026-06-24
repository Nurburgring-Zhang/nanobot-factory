"""持久化基类 — 为所有Manager提供SQLite存储"""
import sqlite3
import json
import os
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List


class PersistentManager:
    """持久化管理器基类。子类设置_db_fields和_db_table即可自动持久化。"""

    _db_path: str = ""  # 子类可覆盖
    _db_table: str = ""
    _db_fields: List[str] = []
    _db_key_field: str = "id"

    def __init__(self):
        self._local_lock = threading.Lock()
        self._ensure_table()

    @classmethod
    def _get_db_path(cls) -> str:
        if cls._db_path:
            return cls._db_path
        base = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, f"{cls.__name__}.db")

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        conn = sqlite3.connect(cls._get_db_path())
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self, table: str = None, fields: list = None):
        table = table or self._db_table
        fields = fields or self._db_fields
        if not table or not fields:
            return
        # Validate table name against class constant (no user-provided table names)
        ALLOWED_TABLES = {self._db_table, getattr(self, '_project_db_table', None)}
        ALLOWED_TABLES.discard(None)
        if table not in ALLOWED_TABLES:
            table = self._db_table  # fallback to safe default
        fields_def = ", ".join(f + " TEXT" for f in fields)
        with self._local_lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS " + table + " (" + fields_def + ", "
                    "PRIMARY KEY (" + self._db_key_field + "))"
                )
                conn.commit()
            finally:
                conn.close()

    def _save(self, key: str, data: dict, table: str = None, fields: list = None):
        table = table or self._db_table
        if not table:
            return
        fields_list = fields or list(data.keys())
        # Whitelist validation: only allow fields from class _db_fields
        ALLOWED_FIELDS = set(self._db_fields)
        fields_list = [f for f in fields_list if f in ALLOWED_FIELDS]
        if not fields_list:
            return
        self._ensure_table(table, fields_list)
        placeholders = ", ".join("?" for _ in fields_list)
        col_names = ", ".join(fields_list)
        values = []
        for k in fields_list:
            v = data.get(k)
            if k == self._db_key_field:
                values.append(str(v) if not isinstance(v, str) else v)
            else:
                values.append(json.dumps(v, ensure_ascii=False))
        # Safe concatenation: table is class constant, fields are whitelist-validated
        sql = "INSERT OR REPLACE INTO " + table + " (" + col_names + ") VALUES (" + placeholders + ")"
        with self._local_lock:
            conn = self._get_conn()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def _load_all(self, table: str = None, fields: list = None) -> List[dict]:
        table = table or self._db_table
        if not table:
            return []
        # Validate table name against allowed tables
        ALLOWED_TABLES = {self._db_table, getattr(self, '_project_db_table', None)}
        ALLOWED_TABLES.discard(None)
        if table not in ALLOWED_TABLES:
            return []
        with self._local_lock:
            conn = self._get_conn()
            try:
                try:
                    # Safe concatenation: table is whitelist-validated
                    cursor = conn.execute("SELECT * FROM " + table)
                except sqlite3.OperationalError:
                    return []
                rows = [dict(row) for row in cursor.fetchall()]
                # 解析JSON字段
                result = []
                for row in rows:
                    parsed = {}
                    for k, v in row.items():
                        if v is None:
                            parsed[k] = None
                        else:
                            try:
                                parsed[k] = json.loads(v)
                            except (json.JSONDecodeError, TypeError):
                                parsed[k] = v
                    result.append(parsed)
                return result
            finally:
                conn.close()

    def _delete(self, key: str):
        if not self._db_table:
            return
        with self._local_lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    f"DELETE FROM {self._db_table} WHERE {self._db_key_field} = ?",
                    (key,),
                )
                conn.commit()
            finally:
                conn.close()

    def _load_one(self, key: str) -> Optional[dict]:
        if not self._db_table:
            return None
        with self._local_lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    f"SELECT * FROM {self._db_table} WHERE {self._db_key_field} = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                for k, v in d.items():
                    if v is not None:
                        try:
                            d[k] = json.loads(v)
                        except (json.JSONDecodeError, TypeError):
                            pass
                return d
            finally:
                conn.close()
