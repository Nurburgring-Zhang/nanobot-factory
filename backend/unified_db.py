#!/usr/bin/env python3
"""
NanoBot Factory - Unified Database Interface
Unified API for PostgreSQL, SQLite, MySQL, MongoDB

@author Matrix Agent
@date 2026-04-23
"""

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UnifiedDB")


class DatabaseType(Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"


class DatabaseConfig:
    """Database configuration"""
    
    def __init__(
        self,
        db_type: DatabaseType = DatabaseType.SQLITE,
        host: str = "localhost",
        port: int = 5432,
        user: str = "",
        password: str = "",
        database: str = "nanobot_db",
        pool_size: int = 10,
        db_path: str = "./data/nanobot.db",
    ):
        self.db_type = db_type
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.db_path = db_path
    
    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        db_type_str = os.getenv("DB_TYPE", "sqlite")
        try:
            db_type = DatabaseType(db_type_str.lower())
        except ValueError:
            db_type = DatabaseType.SQLITE
        
        cfg = cls(db_type=db_type)
        
        if db_type == DatabaseType.MYSQL:
            cfg.host = os.getenv("MYSQL_HOST", "localhost")
            cfg.port = int(os.getenv("MYSQL_PORT", "3306"))
            cfg.user = os.getenv("MYSQL_USER", "root")
            cfg.password = os.getenv("MYSQL_PASSWORD", "")
            cfg.database = os.getenv("MYSQL_DATABASE", "nanobot_db")
        elif db_type == DatabaseType.MONGODB:
            cfg.host = os.getenv("MONGODB_HOST", "localhost")
            cfg.port = int(os.getenv("MONGODB_PORT", "27017"))
            cfg.user = os.getenv("MONGODB_USER", "")
            cfg.password = os.getenv("MONGODB_PASSWORD", "")
            cfg.database = os.getenv("MONGODB_DATABASE", "nanobot_db")
        elif db_type == DatabaseType.POSTGRESQL:
            cfg.host = os.getenv("POSTGRES_HOST", "localhost")
            cfg.port = int(os.getenv("POSTGRES_PORT", "5432"))
            cfg.user = os.getenv("POSTGRES_USER", "")
            cfg.password = os.getenv("POSTGRES_PASSWORD", "")
            cfg.database = os.getenv("POSTGRES_DB", "nanobot_db")
        elif db_type == DatabaseType.SQLITE:
            cfg.db_path = os.getenv("SQLITE_PATH", "./data/nanobot.db")
        
        return cfg


class UnifiedDatabase:
    """Unified database interface"""
    
    _instance = None
    
    def __new__(cls, config: DatabaseConfig = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: DatabaseConfig = None):
        if self._initialized:
            return
        self._initialized = True
        self.config = config or DatabaseConfig.from_env()
        self._db = None
        self._db_type = self.config.db_type
        self._connect()
    
    def _connect(self):
        if self._db_type == DatabaseType.MYSQL:
            self._connect_mysql()
        elif self._db_type == DatabaseType.MONGODB:
            self._connect_mongodb()
        elif self._db_type == DatabaseType.POSTGRESQL:
            self._connect_postgresql()
        else:
            self._connect_sqlite()
    
    def _connect_sqlite(self):
        import sqlite3
        from pathlib import Path
        Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.config.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        logger.info(f"[UnifiedDB] SQLite: {self.config.db_path}")
    
    def _connect_mysql(self):
        try:
            from mysql_manager import MySQLManager, MySQLConfig
            cfg = MySQLConfig(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                pool_size=self.config.pool_size,
            )
            self._db = MySQLManager(cfg)
            logger.info(f"[UnifiedDB] MySQL: {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.warning(f"MySQL unavailable, using SQLite: {e}")
            self._db_type = DatabaseType.SQLITE
            self._connect_sqlite()
    
    def _connect_mongodb(self):
        try:
            from mongodb_manager import MongoDBManager, MongoDBConfig
            cfg = MongoDBConfig(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                max_pool_size=self.config.pool_size,
            )
            self._db = MongoDBManager(cfg)
            logger.info(f"[UnifiedDB] MongoDB: {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.warning(f"MongoDB unavailable, using SQLite: {e}")
            self._db_type = DatabaseType.SQLITE
            self._connect_sqlite()
    
    def _connect_postgresql(self):
        try:
            from postgres_manager import PostgreSQLManager, PostgresConfig
            cfg = PostgresConfig(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                username=self.config.user,
                password=self.config.password,
                pool_size=self.config.pool_size,
            )
            self._db = PostgreSQLManager(cfg)
            logger.info(f"[UnifiedDB] PostgreSQL: {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable, using SQLite: {e}")
            self._db_type = DatabaseType.SQLITE
            self._connect_sqlite()
    
    @property
    def db_type(self) -> DatabaseType:
        return self._db_type
    
    def insert(self, table: str, data: Dict[str, Any]) -> Optional[str]:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.insert_one(table, data)
        return self._db.insert(table, data)
    
    def get(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.find_by_id(table, record_id)
        return self._db.get(table, record_id)
    
    def find_one(self, table: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.find_one(table, query)
        results, _ = self._db.query(table, query, limit=1)
        return results[0] if results else None
    
    def find(
        self,
        table: str,
        query: Dict[str, Any] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> List[Dict[str, Any]]:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.find(table, query, limit=limit, skip=offset)
        results, _ = self._db.query(table, query or {}, order_by=order_by, order_desc=order_desc, limit=limit, offset=offset)
        return results
    
    def update(self, table: str, record_id: str, data: Dict[str, Any]) -> bool:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.update_by_id(table, record_id, data)
        return self._db.update(table, record_id, data)
    
    def delete(self, table: str, record_id: str, soft: bool = True) -> bool:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.delete_by_id(table, record_id)
        return self._db.delete(table, record_id, soft)
    
    def count(self, table: str, query: Dict[str, Any] = None) -> int:
        if self._db_type == DatabaseType.MONGODB:
            return self._db.count(table, query)
        return self._db.count(table, query)
    
    def query(
        self,
        table: str,
        filters: Dict[str, Any] = None,
        order_by: str = "created_at",
        order_desc: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        if self._db_type == DatabaseType.MONGODB:
            results = self._db.find(table, filters, limit=limit, skip=offset)
            total = self._db.count(table, filters)
            return results, total
        return self._db.query(table, filters or {}, order_by=order_by, order_desc=order_desc, limit=limit, offset=offset)
    
    def health_check(self) -> Dict[str, Any]:
        if hasattr(self._db, 'health_check'):
            return self._db.health_check()
        return {"status": "healthy", "type": self._db_type.value}
    
    def close(self):
        if hasattr(self._db, 'close'):
            self._db.close()
        UnifiedDatabase._instance = None
        self._initialized = False


def get_unified_db(config: DatabaseConfig = None) -> UnifiedDatabase:
    """Get unified database singleton"""
    if UnifiedDatabase._instance is None:
        UnifiedDatabase._instance = UnifiedDatabase(config)
    return UnifiedDatabase._instance


def init_unified_db(config: DatabaseConfig) -> UnifiedDatabase:
    """Initialize unified database"""
    if UnifiedDatabase._instance:
        UnifiedDatabase._instance.close()
    UnifiedDatabase._instance = UnifiedDatabase(config)
    return UnifiedDatabase._instance


def close_unified_db():
    """Close unified database"""
    if UnifiedDatabase._instance:
        UnifiedDatabase._instance.close()
        UnifiedDatabase._instance = None


if __name__ == "__main__":
    print("=== Unified Database Test ===")
    db = get_unified_db()
    print(f"Type: {db.db_type.value}")
    print(f"Health: {db.health_check()}")
    
    uid = db.insert("users", {
        "username": "test",
        "email": "test@example.com",
    })
    print(f"Inserted: {uid}")
    
    user = db.get("users", uid)
    print(f"Retrieved: {user}")
    
    db.update("users", uid, {"display_name": "Test User"})
    
    users, total = db.query("users", {})
    print(f"Total: {total}")
    
    db.delete("users", uid)
    db.close()
    print("Done")
