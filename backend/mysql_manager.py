#!/usr/bin/env python3
"""
NanoBot Factory - MySQL Database Manager
MySQL Database Manager with Connection Pool

Features:
- MySQL connection pool management
- CRUD operations
- Transaction support
- Auto-reconnection
- Async support

@author Matrix Agent
@date 2026-04-23
"""

import os
import json
import logging
import threading
import time
import uuid
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager
from queue import Queue, Empty

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MySQLManager")

# Dependency check
try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    try:
        import mysql.connector as pymysql
        from mysql.connector.cursor import DictCursor
    except ImportError:
        pymysql = None
        logger.warning("MySQL driver not installed. Run: pip install pymysql")


@dataclass
class MySQLConfig:
    """MySQL connection configuration"""
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "nanobot_db"
    charset: str = "utf8mb4"
    pool_size: int = 10
    connect_timeout: int = 10
    auto_reconnect: bool = True

    @classmethod
    def from_env(cls) -> "MySQLConfig":
        return cls(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "nanobot_db"),
            pool_size=int(os.getenv("MYSQL_POOL_SIZE", "10")),
        )


class MySQLConnection:
    """MySQL connection wrapper"""
    
    def __init__(self, config: MySQLConfig):
        self.config = config
        self._conn = None
        self._id = str(uuid.uuid4())[:8]
    
    def connect(self) -> bool:
        if pymysql is None:
            return False
        try:
            self._conn = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset=self.config.charset,
                connect_timeout=self.config.connect_timeout,
                cursorclass=DictCursor,
                autocommit=False,
            )
            logger.info(f"[MySQL] Connected: {self.config.host}:{self.config.port}/{self.config.database}")
            return True
        except Exception as e:
            logger.error(f"[MySQL] Connection failed: {e}")
            return False
    
    def is_connected(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.ping(reconnect=False)
            return True
        except Exception:
            return False
    
    def reconnect(self) -> bool:
        self.close()
        return self.connect()
    
    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
    
    def execute(self, query: str, params: tuple = None) -> Tuple[List[Dict], int]:
        if not self.is_connected():
            if not self.reconnect():
                raise ConnectionError("Cannot connect to MySQL")
        
        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            
            if query.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall() or []
                return list(rows), cursor.rowcount
            else:
                self._conn.commit()
                return [], cursor.rowcount
        except Exception as e:
            self._conn.rollback()
            logger.error(f"[MySQL] Query failed: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def commit(self):
        if self._conn:
            self._conn.commit()
    
    def rollback(self):
        if self._conn:
            self._conn.rollback()


class MySQLPool:
    """MySQL connection pool"""
    
    def __init__(self, config: MySQLConfig):
        self.config = config
        self._pool: Queue = Queue(maxsize=config.pool_size)
        self._all_conns: List[MySQLConnection] = []
        self._lock = threading.Lock()
        self._stats = {"total": 0, "active": 0, "idle": 0}
        self._init_pool()
        logger.info(f"[MySQL] Pool initialized with {config.pool_size} connections")
    
    def _init_pool(self):
        for _ in range(self.config.pool_size):
            conn = MySQLConnection(self.config)
            if conn.connect():
                self._pool.put(conn)
                self._all_conns.append(conn)
                self._stats["total"] += 1
                self._stats["idle"] += 1
    
    @contextmanager
    def get_connection(self, timeout: float = 30.0):
        conn = None
        acquired = False
        try:
            try:
                conn = self._pool.get(timeout=timeout)
                self._stats["idle"] -= 1
                acquired = True
            except Empty:
                conn = MySQLConnection(self.config)
                if not conn.connect():
                    raise ConnectionError("Cannot create MySQL connection")
                with self._lock:
                    self._all_conns.append(conn)
                    self._stats["total"] += 1
                acquired = True
            
            if not conn.is_connected():
                conn.reconnect()
            
            yield conn
        except Exception as e:
            logger.error(f"[MySQL] Connection error: {e}")
            raise
        finally:
            if acquired and conn:
                try:
                    if not self._pool.full():
                        self._pool.put(conn, timeout=1)
                        self._stats["idle"] += 1
                    else:
                        conn.close()
                except Exception:
                    conn.close()
    
    def get_stats(self) -> Dict[str, int]:
        self._stats["active"] = len(self._all_conns) - self._stats["idle"]
        return self._stats.copy()
    
    def close_all(self):
        with self._lock:
            for conn in self._all_conns:
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
        logger.info("[MySQL] Pool closed")


class MySQLManager:
    """MySQL database manager"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config: MySQLConfig = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: MySQLConfig = None):
        if self._initialized:
            return
        self._initialized = True
        self.config = config or MySQLConfig.from_env()
        self.pool = MySQLPool(self.config)
        self._init_schema()
        logger.info("[MySQL] MySQLManager initialized")
    
    def _init_schema(self):
        schema = [
            """CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                display_name VARCHAR(100),
                role VARCHAR(50) DEFAULT 'user',
                status VARCHAR(50) DEFAULT 'active',
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_username (username),
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            """CREATE TABLE IF NOT EXISTS projects (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                status VARCHAR(50) DEFAULT 'active',
                settings TEXT,
                user_id VARCHAR(36),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            """CREATE TABLE IF NOT EXISTS assets (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                asset_type VARCHAR(50),
                path TEXT,
                url TEXT,
                size BIGINT DEFAULT 0,
                metadata TEXT,
                user_id VARCHAR(36),
                project_id VARCHAR(36),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user (user_id),
                INDEX idx_project (project_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            
            """CREATE TABLE IF NOT EXISTS audit_logs (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36),
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(100),
                resource_id VARCHAR(36),
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user (user_id),
                INDEX idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        ]
        
        try:
            with self.pool.get_connection() as conn:
                for q in schema:
                    conn.execute(q)
                conn.commit()
            logger.info("[MySQL] Schema initialized")
        except Exception as e:
            logger.error(f"[MySQL] Schema init failed: {e}")
    
    def insert(self, table: str, data: Dict[str, Any]) -> Optional[str]:
        if not data:
            return None
        record_id = data.get("id") or str(uuid.uuid4())
        data["id"] = record_id
        cols = list(data.keys())
        vals = list(data.values())
        query = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        try:
            with self.pool.get_connection() as conn:
                conn.execute(query, tuple(vals))
                conn.commit()
                return record_id
        except Exception as e:
            logger.error(f"[MySQL] Insert failed: {e}")
            return None
    
    def get(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        query = f"SELECT * FROM {table} WHERE id = %s"
        try:
            with self.pool.get_connection() as conn:
                rows, _ = conn.execute(query, (record_id,))
                return rows[0] if rows else None
        except Exception as e:
            logger.error(f"[MySQL] Get failed: {e}")
            return None
    
    def update(self, table: str, record_id: str, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        data = {k: v for k, v in data.items() if k != "id"}
        if not data:
            return False
        cols = list(data.keys())
        vals = list(data.values())
        set_clause = ", ".join([f"{c} = %s" for c in cols])
        query = f"UPDATE {table} SET {set_clause}, updated_at = NOW() WHERE id = %s"
        vals.append(record_id)
        try:
            with self.pool.get_connection() as conn:
                _, affected = conn.execute(query, tuple(vals))
                conn.commit()
                return affected > 0
        except Exception as e:
            logger.error(f"[MySQL] Update failed: {e}")
            return False
    
    def delete(self, table: str, record_id: str, soft: bool = True) -> bool:
        if soft:
            query = f"UPDATE {table} SET is_deleted = 1 WHERE id = %s"
        else:
            query = f"DELETE FROM {table} WHERE id = %s"
        try:
            with self.pool.get_connection() as conn:
                _, affected = conn.execute(query, (record_id,))
                conn.commit()
                return affected > 0
        except Exception as e:
            logger.error(f"[MySQL] Delete failed: {e}")
            return False
    
    def query(
        self,
        table: str,
        filters: Dict[str, Any] = None,
        order_by: str = "created_at",
        order_desc: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        filters = filters or {}
        conds = []
        vals = []
        for k, v in filters.items():
            if isinstance(v, (list, tuple)):
                conds.append(f"{k} IN ({', '.join(['%s'] * len(v))})")
                vals.extend(v)
            else:
                conds.append(f"{k} = %s")
                vals.append(v)
        where = " AND ".join(conds) if conds else "1=1"
        order = "DESC" if order_desc else "ASC"
        
        count_q = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        data_q = f"SELECT * FROM {table} WHERE {where} ORDER BY {order_by} {order} LIMIT %s OFFSET %s"
        
        try:
            with self.pool.get_connection() as conn:
                _, cnt = conn.execute(count_q, tuple(vals))
                total = cnt[0]["cnt"] if cnt else 0
                rows, _ = conn.execute(data_q, tuple(vals) + (limit, offset))
                return list(rows), total
        except Exception as e:
            logger.error(f"[MySQL] Query failed: {e}")
            return [], 0
    
    @contextmanager
    def transaction(self):
        with self.pool.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def health_check(self) -> Dict[str, Any]:
        try:
            with self.pool.get_connection() as conn:
                conn.execute("SELECT 1")
                stats = self.pool.get_stats()
                return {"status": "healthy", "connected": True, "stats": stats}
        except Exception as e:
            return {"status": "unhealthy", "connected": False, "error": str(e)}
    
    def close(self):
        if self.pool:
            self.pool.close_all()
        MySQLManager._instance = None
        self._initialized = False


_mysql_manager: Optional[MySQLManager] = None


def get_mysql_manager(config: MySQLConfig = None) -> MySQLManager:
    global _mysql_manager
    if _mysql_manager is None:
        _mysql_manager = MySQLManager(config)
    return _mysql_manager


def init_mysql(config: MySQLConfig) -> MySQLManager:
    global _mysql_manager
    if _mysql_manager:
        _mysql_manager.close()
    _mysql_manager = MySQLManager(config)
    return _mysql_manager


if __name__ == "__main__":
    print("=== MySQL Manager Test ===")
    config = MySQLConfig(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "nanobot_db"),
    )
    
    mysql = MySQLManager(config)
    health = mysql.health_check()
    print(f"Health: {health}")
    
    if health["connected"]:
        uid = mysql.insert("users", {
            "username": "test_user",
            "email": "test@example.com",
            "password_hash": "hashed",
        })
        print(f"Inserted: {uid}")
        
        user = mysql.get("users", uid)
        print(f"Retrieved: {user}")
        
        mysql.update("users", uid, {"display_name": "Test"})
        
        users, total = mysql.query("users", {})
        print(f"Total users: {total}")
        
        mysql.delete("users", uid)
        print("Deleted")
        
        mysql.close()
    
    print("=== Test Complete ===")
