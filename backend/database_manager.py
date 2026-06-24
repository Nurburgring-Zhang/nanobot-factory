#!/usr/bin/env python3
"""
NanoBot Factory 数据库管理系统
Database Management System

功能:
- 多数据库连接管理 (PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch)
- 数据分析引擎
- 数据安全审计
- 数据质量管理
- 数据分类管理

@author Matrix Agent
@date 2026-04-21
@version 2.0.0
"""

import os
import sys
import json
import asyncio
import logging
import sqlite3
import hashlib
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import queue
import statistics
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DatabaseManager")


# ==================== 枚举类型定义 ====================

class DatabaseType(Enum):
    """支持的数据库类型"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"
    ELASTICSEARCH = "elasticsearch"
    VECTOR_DB = "vector_db"


class DataCategory(Enum):
    """数据分类"""
    USER_DATA = "user_data"
    CONVERSATION = "conversation"
    AGENT_MEMORY = "agent_memory"
    SYSTEM_LOG = "system_log"
    SECURITY_AUDIT = "security_audit"
    BUSINESS_DATA = "business_data"
    ANALYTICS = "analytics"
    ANNOTATION = "annotation"
    ANNOTATION_PROJECT = "annotation_project"
    ANNOTATION_IMAGE = "annotation_image"
    ANNOTATION_LABEL = "annotation_label"
    ANNOTATION_QUALITY = "annotation_quality"
    DATASET = "dataset"


class DataQualityLevel(Enum):
    """数据质量等级"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CORRUPTED = "corrupted"


class SensitiveLevel(Enum):
    """敏感等级"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class AuditAction(Enum):
    """审计动作"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    QUERY = "query"


# ==================== 数据类定义 ====================

@dataclass
class ConnectionConfig:
    """数据库连接配置"""
    db_type: DatabaseType
    host: str = "localhost"
    port: int = 5432
    database: str = "nanobot"
    username: str = ""
    password: str = ""
    ssl_enabled: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    # SQLite专用
    db_path: Optional[str] = None
    # MongoDB专用
    auth_source: str = "admin"
    max_pool_size: int = 100
    # Redis专用
    db_index: int = 0
    # Elasticsearch专用
    timeout: int = 30
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "db_type": self.db_type.value,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "pool_size": self.pool_size,
        }


@dataclass
class DataRecord:
    """数据记录"""
    record_id: str
    data_type: DataCategory
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[str] = None
    sensitive_level: SensitiveLevel = SensitiveLevel.INTERNAL
    quality_level: DataQualityLevel = DataQualityLevel.GOOD
    tags: List[str] = field(default_factory=list)
    version: int = 1
    is_deleted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "data_type": self.data_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "sensitive_level": self.sensitive_level.value,
            "quality_level": self.quality_level.value,
            "tags": self.tags,
            "version": self.version,
            "is_deleted": self.is_deleted,
        }


@dataclass
class QueryFilter:
    """查询过滤器"""
    data_category: Optional[DataCategory] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    created_by: Optional[str] = None
    tags: Optional[List[str]] = None
    sensitive_level: Optional[SensitiveLevel] = None
    quality_level: Optional[DataQualityLevel] = None
    search_text: Optional[str] = None
    limit: int = 100
    offset: int = 0
    order_by: str = "created_at"
    order_desc: bool = True


@dataclass
class DataQualityReport:
    """数据质量报告"""
    total_records: int
    valid_records: int
    invalid_records: int
    missing_fields: Dict[str, int]
    duplicate_records: int
    quality_distribution: Dict[str, int]
    recommendations: List[str]
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SecurityAuditRecord:
    """安全审计记录"""
    audit_id: str
    operation_type: str
    user_id: Optional[str]
    ip_address: Optional[str]
    resource_type: str
    resource_id: str
    action: AuditAction
    result: str  # success, failed, denied
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "operation_type": self.operation_type,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action.value,
            "result": self.result,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class AnalyticsMetrics:
    """分析指标"""
    total_records: int
    records_by_category: Dict[str, int]
    records_by_date: Dict[str, int]
    average_quality_score: float
    quality_distribution: Dict[str, int]
    top_tags: List[Tuple[str, int]]
    data_growth_rate: float  # 百分比
    active_users: int
    storage_size_mb: float


# ==================== SQLite实现 (核心存储) ====================

class SQLiteDataStore:
    """
    SQLite数据存储 - 作为核心元数据存储
    支持表: data_records, audit_logs, quality_reports, connections
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认使用项目数据目录
            project_dir = Path(__file__).parent.parent / "data"
            project_dir.mkdir(exist_ok=True)
            db_path = str(project_dir / "nanobot_data.db")

        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()
        logger.info(f"SQLiteDataStore initialized at: {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 数据记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_records (
                record_id TEXT PRIMARY KEY,
                data_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT,
                sensitive_level TEXT DEFAULT 'internal',
                quality_level TEXT DEFAULT 'good',
                tags TEXT DEFAULT '[]',
                version INTEGER DEFAULT 1,
                is_deleted INTEGER DEFAULT 0,
                checksum TEXT
            )
        """)

        # 安全审计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                audit_id TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                user_id TEXT,
                ip_address TEXT,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT DEFAULT '{}'
            )
        """)

        # 数据质量报告表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_reports (
                report_id TEXT PRIMARY KEY,
                data_category TEXT,
                total_records INTEGER,
                valid_records INTEGER,
                invalid_records INTEGER,
                quality_distribution TEXT,
                recommendations TEXT,
                generated_at TEXT NOT NULL
            )
        """)

        # 数据库连接配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS db_connections (
                connection_id TEXT PRIMARY KEY,
                db_type TEXT NOT NULL,
                name TEXT NOT NULL,
                config TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_type ON data_records(data_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_created ON data_records(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_deleted ON data_records(is_deleted)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)")

        conn.commit()
        conn.close()
        logger.info("Database tables initialized")

    def create_record(self, record: DataRecord) -> bool:
        """创建数据记录"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                # 计算校验和
                content_str = json.dumps(record.content, sort_keys=True, ensure_ascii=False)
                checksum = hashlib.md5(content_str.encode()).hexdigest()

                cursor.execute("""
                    INSERT INTO data_records 
                    (record_id, data_type, content, metadata, created_at, updated_at,
                     created_by, sensitive_level, quality_level, tags, version, is_deleted, checksum)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.record_id,
                    record.data_type.value,
                    json.dumps(record.content, ensure_ascii=False),
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.created_by,
                    record.sensitive_level.value,
                    record.quality_level.value,
                    json.dumps(record.tags, ensure_ascii=False),
                    record.version,
                    1 if record.is_deleted else 0,
                    checksum
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to create record: {e}")
                return False
            finally:
                conn.close()

    def get_record(self, record_id: str, include_deleted: bool = False) -> Optional[DataRecord]:
        """获取单条记录"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            query = "SELECT * FROM data_records WHERE record_id = ?"
            if not include_deleted:
                query += " AND is_deleted = 0"

            cursor.execute(query, (record_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                return self._row_to_record(row)
            return None

    def update_record(self, record_id: str, updates: Dict[str, Any]) -> bool:
        """更新记录"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                update_fields = []
                values = []

                if "content" in updates:
                    update_fields.append("content = ?")
                    values.append(json.dumps(updates["content"], ensure_ascii=False))
                    # 重新计算校验和
                    content_str = json.dumps(updates["content"], sort_keys=True, ensure_ascii=False)
                    checksum = hashlib.md5(content_str.encode()).hexdigest()
                    update_fields.append("checksum = ?")
                    values.append(checksum)

                if "metadata" in updates:
                    update_fields.append("metadata = ?")
                    values.append(json.dumps(updates["metadata"], ensure_ascii=False))

                if "quality_level" in updates:
                    update_fields.append("quality_level = ?")
                    values.append(updates["quality_level"])

                if "tags" in updates:
                    update_fields.append("tags = ?")
                    values.append(json.dumps(updates["tags"], ensure_ascii=False))

                if "sensitive_level" in updates:
                    update_fields.append("sensitive_level = ?")
                    values.append(updates["sensitive_level"])

                update_fields.append("updated_at = ?")
                values.append(datetime.now().isoformat())

                update_fields.append("version = version + 1")

                values.append(record_id)

                query = f"UPDATE data_records SET {', '.join(update_fields)} WHERE record_id = ?"
                cursor.execute(query, values)
                conn.commit()

                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to update record: {e}")
                return False
            finally:
                conn.close()

    def delete_record(self, record_id: str, soft: bool = True) -> bool:
        """删除记录"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                if soft:
                    cursor.execute(
                        "UPDATE data_records SET is_deleted = 1, updated_at = ? WHERE record_id = ?",
                        (datetime.now().isoformat(), record_id)
                    )
                else:
                    cursor.execute("DELETE FROM data_records WHERE record_id = ?", (record_id,))

                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def query_records(self, query_filter: QueryFilter) -> Tuple[List[DataRecord], int]:
        """查询记录"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 构建查询
            conditions = ["is_deleted = 0"]
            values = []

            if query_filter.data_category:
                conditions.append("data_type = ?")
                values.append(query_filter.data_category.value)

            if query_filter.date_from:
                conditions.append("created_at >= ?")
                values.append(query_filter.date_from.isoformat())

            if query_filter.date_to:
                conditions.append("created_at <= ?")
                values.append(query_filter.date_to.isoformat())

            if query_filter.created_by:
                conditions.append("created_by = ?")
                values.append(query_filter.created_by)

            if query_filter.search_text:
                conditions.append("(content LIKE ? OR metadata LIKE ?)")
                search_pattern = f"%{query_filter.search_text}%"
                values.extend([search_pattern, search_pattern])

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 获取总数
            count_query = f"SELECT COUNT(*) as count FROM data_records WHERE {where_clause}"
            cursor.execute(count_query, values)
            total = cursor.fetchone()["count"]

            # 获取数据
            order = "DESC" if query_filter.order_desc else "ASC"
            limit = min(query_filter.limit, 1000)  # 最多1000条
            offset = query_filter.offset

            data_query = f"""
                SELECT * FROM data_records 
                WHERE {where_clause}
                ORDER BY {query_filter.order_by} {order}
                LIMIT ? OFFSET ?
            """
            values.extend([limit, offset])

            cursor.execute(data_query, values)
            rows = cursor.fetchall()
            conn.close()

            records = [self._row_to_record(row) for row in rows]
            return records, total

    def _row_to_record(self, row: sqlite3.Row) -> DataRecord:
        """将数据库行转换为DataRecord"""
        return DataRecord(
            record_id=row["record_id"],
            data_type=DataCategory(row["data_type"]),
            content=json.loads(row["content"]),
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            created_by=row["created_by"],
            sensitive_level=SensitiveLevel(row["sensitive_level"]),
            quality_level=DataQualityLevel(row["quality_level"]),
            tags=json.loads(row["tags"]),
            version=row["version"],
            is_deleted=bool(row["is_deleted"]),
        )

    # ==================== 审计日志 ====================

    def create_audit_log(self, record: SecurityAuditRecord) -> bool:
        """创建审计日志"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO audit_logs 
                    (audit_id, operation_type, user_id, ip_address, resource_type,
                     resource_id, action, result, timestamp, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.audit_id,
                    record.operation_type,
                    record.user_id,
                    record.ip_address,
                    record.resource_type,
                    record.resource_id,
                    record.action.value,
                    record.result,
                    record.timestamp.isoformat(),
                    json.dumps(record.details, ensure_ascii=False),
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to create audit log: {e}")
                return False
            finally:
                conn.close()

    def query_audit_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SecurityAuditRecord]:
        """查询审计日志"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            conditions = []
            values = []

            if user_id:
                conditions.append("user_id = ?")
                values.append(user_id)

            if action:
                conditions.append("action = ?")
                values.append(action.value)

            if date_from:
                conditions.append("timestamp >= ?")
                values.append(date_from.isoformat())

            if date_to:
                conditions.append("timestamp <= ?")
                values.append(date_to.isoformat())

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            values.append(limit)

            cursor.execute(f"""
                SELECT * FROM audit_logs 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """, values)

            rows = cursor.fetchall()
            conn.close()

            return [
                SecurityAuditRecord(
                    audit_id=row["audit_id"],
                    operation_type=row["operation_type"],
                    user_id=row["user_id"],
                    ip_address=row["ip_address"],
                    resource_type=row["resource_type"],
                    resource_id=row["resource_id"],
                    action=AuditAction(row["action"]),
                    result=row["result"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    details=json.loads(row["details"]),
                )
                for row in rows
            ]

    # ==================== 统计分析 ====================

    def get_analytics(self, days: int = 30) -> AnalyticsMetrics:
        """获取分析指标"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 总记录数
            cursor.execute("SELECT COUNT(*) as count FROM data_records WHERE is_deleted = 0")
            total_records = cursor.fetchone()["count"]

            # 按分类统计
            cursor.execute("""
                SELECT data_type, COUNT(*) as count 
                FROM data_records WHERE is_deleted = 0
                GROUP BY data_type
            """)
            records_by_category = {row["data_type"]: row["count"] for row in cursor.fetchall()}

            # 按日期统计 (最近N天)
            cursor.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM data_records 
                WHERE is_deleted = 0 AND created_at >= date('now', ?)
                GROUP BY DATE(created_at)
                ORDER BY date
            """, (f"-{days} days",))
            records_by_date = {row["date"]: row["count"] for row in cursor.fetchall()}

            # 质量分布
            cursor.execute("""
                SELECT quality_level, COUNT(*) as count 
                FROM data_records WHERE is_deleted = 0
                GROUP BY quality_level
            """)
            quality_distribution = {row["quality_level"]: row["count"] for row in cursor.fetchall()}

            # 活跃用户数
            cursor.execute("""
                SELECT COUNT(DISTINCT created_by) as count 
                FROM data_records 
                WHERE is_deleted = 0 AND created_at >= date('now', ?)
            """, (f"-{days} days",))
            active_users = cursor.fetchone()["count"]

            # 存储大小
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size_bytes = cursor.fetchone()["size"]
            storage_size_mb = size_bytes / (1024 * 1024)

            # 数据增长率
            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM data_records WHERE is_deleted = 0 AND created_at >= date('now', '-7 days')) as recent,
                    (SELECT COUNT(*) FROM data_records WHERE is_deleted = 0 AND created_at >= date('now', '-14 days') AND created_at < date('now', '-7 days')) as previous
            """)
            row = cursor.fetchone()
            if row["previous"] > 0:
                growth_rate = ((row["recent"] - row["previous"]) / row["previous"]) * 100
            else:
                growth_rate = 0.0

            conn.close()

            return AnalyticsMetrics(
                total_records=total_records,
                records_by_category=records_by_category,
                records_by_date=records_by_date,
                average_quality_score=self._calculate_avg_quality(),
                quality_distribution=quality_distribution,
                top_tags=self._get_top_tags(10),
                data_growth_rate=growth_rate,
                active_users=active_users,
                storage_size_mb=round(storage_size_mb, 2),
            )

    def _calculate_avg_quality(self) -> float:
        """计算平均质量分数"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            quality_scores = {"excellent": 100, "good": 80, "fair": 60, "poor": 40, "corrupted": 10}

            cursor.execute("""
                SELECT quality_level, COUNT(*) as count 
                FROM data_records WHERE is_deleted = 0
                GROUP BY quality_level
            """)

            total_count = 0
            weighted_sum = 0

            for row in cursor.fetchall():
                score = quality_scores.get(row["quality_level"], 50)
                weighted_sum += score * row["count"]
                total_count += row["count"]

            conn.close()

            return round(weighted_sum / total_count, 2) if total_count > 0 else 0.0

    def _get_top_tags(self, limit: int = 10) -> List[Tuple[str, int]]:
        """获取热门标签"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT tags FROM data_records 
                WHERE is_deleted = 0 AND tags != '[]'
            """)

            tag_counts = defaultdict(int)
            for row in cursor.fetchall():
                tags = json.loads(row["tags"])
                for tag in tags:
                    tag_counts[tag] += 1

            conn.close()

            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            return sorted_tags[:limit]

    # ==================== 数据质量管理 ====================

    def generate_quality_report(self, data_category: Optional[DataCategory] = None) -> DataQualityReport:
        """生成数据质量报告"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            conditions = ["is_deleted = 0"]
            values = []

            if data_category:
                conditions.append("data_type = ?")
                values.append(data_category.value)

            where_clause = " AND ".join(conditions)

            # 总记录数
            cursor.execute(f"SELECT COUNT(*) as count FROM data_records WHERE {where_clause}", values)
            total_records = cursor.fetchone()["count"]

            # 有效记录数 (有content且非空)
            cursor.execute(f"""
                SELECT COUNT(*) as count FROM data_records 
                WHERE {where_clause} AND content != 'null' AND content != '[]' AND content != 'None'
            """, values)
            valid_records = cursor.fetchone()["count"]

            # 缺失字段统计
            cursor.execute(f"""
                SELECT COUNT(*) as count FROM data_records 
                WHERE {where_clause} AND (metadata = 'None' OR created_by IS NULL)
            """, values)
            missing_metadata = cursor.fetchone()["count"]

            # 重复记录检测 (基于内容校验和)
            cursor.execute(f"""
                SELECT checksum, COUNT(*) as count 
                FROM data_records WHERE {where_clause} AND checksum IS NOT NULL
                GROUP BY checksum HAVING count > 1
            """, values)
            duplicates = sum(row["count"] - 1 for row in cursor.fetchall())

            # 质量分布
            cursor.execute(f"""
                SELECT quality_level, COUNT(*) as count 
                FROM data_records WHERE {where_clause}
                GROUP BY quality_level
            """, values)
            quality_distribution = {row["quality_level"]: row["count"] for row in cursor.fetchall()}

            conn.close()

            # 生成建议
            recommendations = []
            if missing_metadata > total_records * 0.1:
                recommendations.append(f"警告: {missing_metadata}条记录缺少元数据或创建者信息")
            if duplicates > 0:
                recommendations.append(f"发现{duplicates}条重复记录,建议进行去重处理")
            if quality_distribution.get("poor", 0) > total_records * 0.05:
                recommendations.append("部分数据质量较差,建议优先整改")
            if total_records == 0:
                recommendations.append("当前无数据记录")

            return DataQualityReport(
                total_records=total_records,
                valid_records=valid_records,
                invalid_records=total_records - valid_records,
                missing_fields={"metadata": missing_metadata},
                duplicate_records=duplicates,
                quality_distribution=quality_distribution,
                recommendations=recommendations,
            )

    # ==================== 连接管理 ====================

    def save_connection_config(self, connection_id: str, name: str, config: ConnectionConfig) -> bool:
        """保存数据库连接配置"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                # 密码不存储,只存储配置
                config_dict = config.to_dict()
                config_dict.pop("password", None)

                cursor.execute("""
                    INSERT OR REPLACE INTO db_connections 
                    (connection_id, db_type, name, config, created_at, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (
                    connection_id,
                    config.db_type.value,
                    name,
                    json.dumps(config_dict, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))
                conn.commit()
                return True
            finally:
                conn.close()

    def list_connections(self) -> List[Dict[str, Any]]:
        """列出所有连接配置"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT connection_id, db_type, name, created_at, last_used_at, is_active
                FROM db_connections WHERE is_active = 1
                ORDER BY last_used_at DESC
            """)

            connections = []
            for row in cursor.fetchall():
                connections.append({
                    "connection_id": row["connection_id"],
                    "db_type": row["db_type"],
                    "name": row["name"],
                    "created_at": row["created_at"],
                })

            conn.close()
            return connections


# ==================== 数据库管理器主类 ====================

class DatabaseManager:
    """
    数据库管理器 - 统一管理多种数据库
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.data_store = SQLiteDataStore()
            self._audit_enabled = True
            logger.info("DatabaseManager initialized")

    # ==================== 审计功能 ====================

    def enable_audit(self, enabled: bool = True):
        """启用/禁用审计"""
        self._audit_enabled = enabled

    def audit_log(
        self,
        operation_type: str,
        resource_type: str,
        resource_id: str,
        action: AuditAction,
        result: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """记录审计日志"""
        if not self._audit_enabled:
            return True

        record = SecurityAuditRecord(
            audit_id=f"audit_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.md5(str(resource_id).encode()).hexdigest()[:8]}",
            operation_type=operation_type,
            user_id=user_id,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            result=result,
            details=details or {},
        )

        return self.data_store.create_audit_log(record)

# ==================== 数据记录操作 ====================

    def create(
        self,
        data_type: DataCategory,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: Optional[str] = None,
        sensitive_level: SensitiveLevel = SensitiveLevel.INTERNAL,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """创建数据记录"""
        record = DataRecord(
            record_id=f"rec_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            data_type=data_type,
            content=content,
            metadata=metadata or {},
            created_by=created_by,
            sensitive_level=sensitive_level,
            tags=tags or [],
        )

        if self.data_store.create_record(record):
            self.audit_log(
                operation_type="create",
                resource_type=data_type.value,
                resource_id=record.record_id,
                action=AuditAction.CREATE,
                result="success",
                user_id=created_by,
                details={"data_type": data_type.value},
            )
            return record.record_id
        return None

    def read(self, record_id: str, include_deleted: bool = False) -> Optional[DataRecord]:
        """读取数据记录"""
        record = self.data_store.get_record(record_id, include_deleted)
        if record:
            self.audit_log(
                operation_type="read",
                resource_type=record.data_type.value,
                resource_id=record_id,
                action=AuditAction.READ,
                result="success",
            )
        return record

    def update(
        self,
        record_id: str,
        updates: Dict[str, Any],
        updated_by: Optional[str] = None,
    ) -> bool:
        """更新数据记录"""
        result = self.data_store.update_record(record_id, updates)
        if result:
            self.audit_log(
                operation_type="update",
                resource_type="data_record",
                resource_id=record_id,
                action=AuditAction.UPDATE,
                result="success",
                user_id=updated_by,
                details=updates,
            )
        return result

    def delete(self, record_id: str, soft: bool = True, deleted_by: Optional[str] = None) -> bool:
        """删除数据记录"""
        result = self.data_store.delete_record(record_id, soft)
        if result:
            self.audit_log(
                operation_type="delete",
                resource_type="data_record",
                resource_id=record_id,
                action=AuditAction.DELETE,
                result="success",
                user_id=deleted_by,
            )
        return result

    def query(self, query_filter: QueryFilter) -> Tuple[List[DataRecord], int]:
        """查询数据记录"""
        return self.data_store.query_records(query_filter)

    # ==================== 分析与报告 ====================

    def get_analytics(self, days: int = 30) -> AnalyticsMetrics:
        """获取分析指标"""
        return self.data_store.get_analytics(days)

    def get_quality_report(self, data_category: Optional[DataCategory] = None) -> DataQualityReport:
        """获取质量报告"""
        return self.data_store.generate_quality_report(data_category)

    def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SecurityAuditRecord]:
        """获取审计日志"""
        return self.data_store.query_audit_logs(user_id, action, date_from, date_to, limit)

    # ==================== 批量操作 ====================

    def batch_create(
        self,
        records: List[Dict[str, Any]],
        data_type: DataCategory,
        created_by: Optional[str] = None,
    ) -> Tuple[int, int]:
        """批量创建记录"""
        success_count = 0
        fail_count = 0

        for record_data in records:
            record = DataRecord(
                record_id=f"rec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{success_count}",
                data_type=data_type,
                content=record_data.get("content", {}),
                metadata=record_data.get("metadata", {}),
                created_by=created_by,
                tags=record_data.get("tags", []),
            )

            if self.data_store.create_record(record):
                success_count += 1
            else:
                fail_count += 1

        return success_count, fail_count

    def batch_update(
        self,
        record_ids: List[str],
        updates: Dict[str, Any],
        updated_by: Optional[str] = None,
    ) -> Tuple[int, int]:
        """批量更新记录"""
        success_count = 0
        fail_count = 0

        for record_id in record_ids:
            if self.data_store.update_record(record_id, updates):
                success_count += 1
            else:
                fail_count += 1

        return success_count, fail_count

    # ==================== 统计汇总 ====================

    def get_summary(self) -> Dict[str, Any]:
        """获取系统摘要"""
        analytics = self.data_store.get_analytics(30)
        quality_report = self.data_store.generate_quality_report()

        return {
            "total_records": analytics.total_records,
            "records_by_category": analytics.records_by_category,
            "active_users_30d": analytics.active_users,
            "data_growth_rate": analytics.data_growth_rate,
            "storage_size_mb": analytics.storage_size_mb,
            "quality_excellent": quality_report.quality_distribution.get("excellent", 0),
            "quality_good": quality_report.quality_distribution.get("good", 0),
            "quality_fair": quality_report.quality_distribution.get("fair", 0),
            "quality_poor": quality_report.quality_distribution.get("poor", 0),
            "duplicate_records": quality_report.duplicate_records,
            "generated_at": datetime.now().isoformat(),
        }


# ==================== 全局实例 ====================

_db_manager = None


def get_db_manager() -> DatabaseManager:
    """获取数据库管理器全局实例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


# ==================== 标注系统集成 ====================
# 导入增强版标注系统
import importlib.util
import sys

# 动态导入标注系统
annotation_system_path = Path(__file__).parent / "annotation_system_enhanced.py"
if annotation_system_path.exists():
    spec = importlib.util.spec_from_file_location("annotation_system_enhanced", annotation_system_path)
    annotation_module = importlib.util.module_from_spec(spec)
    sys.modules["annotation_system_enhanced"] = annotation_module
    spec.loader.exec_module(annotation_module)
    
    # 从标注系统导入核心类型
    EnhancedAnnotationManager = annotation_module.EnhancedAnnotationManager
    ImageDataType = annotation_module.ImageDataType
    DataOperation = annotation_module.DataOperation
    AnnotationType = annotation_module.AnnotationType
    QualityDefectType = annotation_module.QualityDefectType
    QualitySeverity = annotation_module.QualitySeverity
    AnnotationStatus = annotation_module.AnnotationStatus
    AnnotationStatus = annotation_module.AnnotationStatus
    ImageData = annotation_module.ImageRecord  # ImageRecord是实际类名
    AnnotationData = annotation_module.AnnotationObject
    ImageGroup = annotation_module.ImageGroup
    QualityInspection = annotation_module.QualityInspection
    QualityDefect = annotation_module.QualityDefect
    AnnotationComment = annotation_module.Comment  # Comment是实际类名
    ImageTag = annotation_module.TagRecord  # TagRecord是实际类名
    AnnotationProject = annotation_module.AnnotationProject
    DataSource = annotation_module.DataSource
    OperationType = annotation_module.OperationType
    ReviewStatus = annotation_module.ReviewStatus
    
    ANNOTATION_SYSTEM_AVAILABLE = True
    logger.info("增强版标注系统已加载")
else:
    ANNOTATION_SYSTEM_AVAILABLE = False
    logger.warning("annotation_system_enhanced.py 未找到")


class AnnotationManager:
    """
    标注管理器 - 整合增强版标注系统到数据库管理
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            if ANNOTATION_SYSTEM_AVAILABLE:
                # 初始化增强版标注管理器
                db_path = Path(__file__).parent.parent / "data" / "annotations.db"
                self.annotation_manager = EnhancedAnnotationManager(str(db_path))
                logger.info("AnnotationManager initialized with EnhancedAnnotationManager")
            else:
                self.annotation_manager = None
                logger.warning("AnnotationManager initialized without annotation system")

    # ==================== 图片数据管理 ====================

    def add_image(
        self,
        image_path: str,
        image_type: str = "single_image",
        source: str = "user_upload",
        project_id: Optional[str] = None,
        created_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        parent_image_id: Optional[str] = None,
    ) -> Optional[str]:
        """添加图片数据"""
        if not self.annotation_manager:
            logger.error("标注系统不可用")
            return None
        
        try:
            from annotation_system_enhanced import DataSource, ImageDataType, OperationType
            
            # 映射数据源
            source_map = {
                "ai_generation": DataSource.AI_GENERATION,
                "manual_capture": DataSource.MANUAL_CAPTURE,
                "web_scraping": DataSource.WEB_SCRAPING,
                "dataset_import": DataSource.DATASET_IMPORT,
                "user_upload": DataSource.USER_UPLOAD,
            }
            data_source = source_map.get(source, DataSource.USER_UPLOAD)
            
            # 映射图片类型
            type_map = {
                "single_image": ImageDataType.SINGLE_IMAGE,
                "image_group": ImageDataType.IMAGE_GROUP,
                "multi_group": ImageDataType.MULTI_GROUP,
                "multi_turn": ImageDataType.MULTI_TURN,
                "multi_turn_group": ImageDataType.MULTI_TURN_GROUP,
                "multi_turn_multi_group": ImageDataType.MULTI_TURN_MULTI_GROUP,
            }
            img_type = type_map.get(image_type, ImageDataType.SINGLE_IMAGE)
            
            # 获取图片尺寸
            width, height = self.annotation_manager._get_image_size(image_path)
            
            # 创建单张图片
            asset_id = f"asset_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            image = self.annotation_manager.create_single_image(
                asset_id=asset_id,
                image_path=image_path,
                width=width,
                height=height,
                source=data_source,
                operation_type=OperationType.IMAGE_COLLECTION,
                created_by=created_by or "system",
                metadata=metadata or {},
            )
            
            # 设置图片类型
            image.data_type = img_type
            
            # 如果有父图片ID，设置版本链
            if parent_image_id:
                image.parent_id = parent_image_id
                parent_image = self.annotation_manager.get_image(parent_image_id)
                if parent_image:
                    image.lineage = parent_image.lineage.copy()
                    image.lineage.append(parent_image_id)
                image.version = 1
                if parent_image:
                    image.version = parent_image.version + 1
            
            # 保存到内存
            self.annotation_manager.images[image.data_id] = image
            self.annotation_manager._index_by_status[image.status].append(image.data_id)
            self.annotation_manager._save_image_to_db(image)
            
            logger.info(f"Created image: {image.data_id}")
            return image.data_id
            
        except Exception as e:
            logger.error(f"添加图片失败: {e}")
            return None

    def get_image(self, image_id: str) -> Optional[ImageData]:
        """获取图片数据"""
        if self.annotation_manager:
            return self.annotation_manager.get_image(image_id)
        return None

    def list_images(
        self,
        project_id: Optional[str] = None,
        image_type: Optional[str] = None,
        status: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ImageData]:
        """列出图片"""
        if self.annotation_manager:
            from annotation_system_enhanced import ImageDataType, AnnotationStatus, DataSource
            
            # 映射参数
            data_types = None
            if image_type:
                type_map = {
                    "single_image": ImageDataType.SINGLE_IMAGE,
                    "image_group": ImageDataType.IMAGE_GROUP,
                    "multi_group": ImageDataType.MULTI_GROUP,
                    "multi_turn": ImageDataType.MULTI_TURN,
                    "multi_turn_group": ImageDataType.MULTI_TURN_GROUP,
                    "multi_turn_multi_group": ImageDataType.MULTI_TURN_MULTI_GROUP,
                }
                img_type = type_map.get(image_type, ImageDataType.SINGLE_IMAGE)
                data_types = [img_type]
            
            statuses = None
            if status:
                status_map = {
                    "draft": AnnotationStatus.DRAFT,
                    "in_progress": AnnotationStatus.IN_PROGRESS,
                    "completed": AnnotationStatus.COMPLETED,
                    "reviewed": AnnotationStatus.REVIEWED,
                    "approved": AnnotationStatus.APPROVED,
                    "rejected": AnnotationStatus.REJECTED,
                }
                s = status_map.get(status, AnnotationStatus.DRAFT)
                statuses = [s]
            
            return self.annotation_manager.filter_images(
                data_types=data_types,
                statuses=statuses,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            )
        return []

    def filter_images(
        self,
        project_id: Optional[str] = None,
        image_type: Optional[str] = None,
        status: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ImageData]:
        """筛选图片 (list_images的别名)"""
        return self.list_images(project_id, image_type, status, include_deleted, limit, offset)

    def update_image_status(self, image_id: str, status: str) -> bool:
        """更新图片状态"""
        if self.annotation_manager:
            return self.annotation_manager.update_image_status(image_id, status)
        return False

    def soft_delete_image(self, image_id: str) -> bool:
        """软删除图片"""
        if self.annotation_manager:
            return self.annotation_manager.soft_delete_image(image_id)
        return False

    def restore_image(self, image_id: str) -> bool:
        """恢复已删除图片"""
        if self.annotation_manager:
            return self.annotation_manager.restore_image(image_id)
        return False

    # ==================== 标注管理 ====================

    def add_annotation(
        self,
        image_id: str,
        annotation_type: str,
        label: str,
        coordinates: List[Any],
        annotator: str,
        category_id: Optional[str] = None,
        confidence: Optional[float] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """添加标注"""
        if self.annotation_manager:
            # 创建AnnotationObject
            from annotation_system_enhanced import AnnotationObject, AnnotationType, BoundingBox, AnnotationLabel, Point
            import uuid
            
            anno_type = AnnotationType(annotation_type) if annotation_type else AnnotationType.NORMAL_BOX
            
            # 创建标签
            lbl = AnnotationLabel(id=str(uuid.uuid4())[:8], name=label, color="#FF0000")
            
            # 根据坐标类型创建标注对象
            if len(coordinates) >= 4:
                bbox = BoundingBox(x=coordinates[0], y=coordinates[1], width=coordinates[2], height=coordinates[3])
            else:
                bbox = BoundingBox(x=0, y=0, width=100, height=100)
            
            annotation = AnnotationObject(
                id=str(uuid.uuid4())[:12],
                annotation_type=anno_type,
                label=lbl,
                bbox=bbox,
                created_by=annotator,
                confidence=confidence or 1.0,
                attributes=attributes or {},
            )
            
            success = self.annotation_manager.add_annotation(image_id, annotation)
            if success:
                # 返回最后一个标注的ID
                image = self.annotation_manager.get_image(image_id)
                if image and image.annotations:
                    return image.annotations[-1].id
            return None
        return None

    def get_annotations(self, image_id: str) -> List[AnnotationData]:
        """获取图片的所有标注"""
        if self.annotation_manager:
            image = self.annotation_manager.get_image(image_id)
            if image:
                return image.annotations
        return []

    def update_annotation(
        self,
        annotation_id: str,
        coordinates: Optional[List[Any]] = None,
        label: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """更新标注"""
        if self.annotation_manager:
            # 需要找到图片ID
            for img_id, image in self.annotation_manager.images.items():
                for ann in image.annotations:
                    if ann.id == annotation_id:
                        updates = {}
                        if attributes:
                            updates["attributes"] = attributes
                        if label:
                            updates["attributes"] = {**(attributes or {}), "label_name": label}
                        return self.annotation_manager.update_annotation(img_id, annotation_id, updates)
        return False

    def delete_annotation(self, annotation_id: str) -> bool:
        """删除标注"""
        if self.annotation_manager:
            # 需要找到图片ID
            for img_id, image in self.annotation_manager.images.items():
                for ann in image.annotations:
                    if ann.id == annotation_id:
                        return self.annotation_manager.delete_annotation(img_id, annotation_id)
        return False

    # ==================== 质量检查 ====================

    def add_quality_inspection(
        self,
        image_id: str,
        inspector: str,
        result: str,
        defects: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        """添加质量检查"""
        if self.annotation_manager:
            # 底层方法名是perform_quality_inspection
            from annotation_system_enhanced import QualityDefect, QualitySeverity, QualityDefectType
            import uuid
            
            defect_objects = []
            if defects:
                for d in defects:
                    defect_type = QualityDefectType(d.get('type', 'missing_label')) if d.get('type') else QualityDefectType.MISSING_LABEL
                    severity = QualitySeverity(d.get('severity', 'minor')) if d.get('severity') else QualitySeverity.MINOR
                    defect_obj = QualityDefect(
                        id=str(uuid.uuid4())[:8],
                        defect_type=defect_type,
                        severity=severity,
                        description=d.get('description', ''),
                    )
                    defect_objects.append(defect_obj)
            
            inspection = self.annotation_manager.perform_quality_inspection(
                data_id=image_id,
                inspector=inspector,
                result=result,
                score=1.0 if result == 'approved' else 0.0,
                defects=defect_objects,
                comments=notes or '',
            )
            return inspection.inspection_id if inspection else None
        return None

    def get_quality_inspections(self, image_id: str) -> List[QualityInspection]:
        """获取质量检查记录"""
        if self.annotation_manager:
            return self.annotation_manager.get_quality_inspections(image_id)
        return []

    def perform_quality_inspection(
        self,
        image_id: str,
        inspector: str,
        result: str,
        defects: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        """执行质量检查 (add_quality_inspection的别名)"""
        return self.add_quality_inspection(image_id, inspector, result, defects, notes)

    # ==================== 图片组管理 ====================

    def create_image_group(
        self,
        name: str,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Optional[str]:
        """创建图片组"""
        if self.annotation_manager:
            return self.annotation_manager.create_image_group(
                name=name,
                description=description,
                project_id=project_id,
                created_by=created_by,
            )
        return None

    def add_to_group(self, group_id: str, image_ids: List[str]) -> bool:
        """添加图片到组"""
        if self.annotation_manager:
            return self.annotation_manager.add_to_group(group_id, image_ids)
        return False

    def get_group_images(self, group_id: str) -> List[ImageData]:
        """获取组内所有图片"""
        if self.annotation_manager:
            return self.annotation_manager.get_group_images(group_id)
        return []

    # ==================== 标注项目 ====================

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        created_by: Optional[str] = None,
    ) -> Optional[str]:
        """创建标注项目"""
        if self.annotation_manager:
            project = self.annotation_manager.create_project(
                name=name,
                description=description or "",
                created_by=created_by or "system",
            )
            # 如果提供了categories，添加到项目中
            if project and categories:
                for cat in categories:
                    label = annotation_module.AnnotationLabel.create(
                        name=cat.get("name", ""),
                        category=cat.get("category", ""),
                        color=cat.get("color", "#000000"),
                    )
                    self.annotation_manager.add_label_to_project(project.project_id, label)
            return project.project_id if project else None
        return None

    def get_project(self, project_id: str) -> Optional[AnnotationProject]:
        """获取项目信息"""
        if self.annotation_manager:
            return self.annotation_manager.get_project(project_id)
        return None

    def list_projects(self, include_completed: bool = False) -> List[AnnotationProject]:
        """列出所有项目"""
        if self.annotation_manager:
            return self.annotation_manager.list_projects(include_completed)
        return []

    # ==================== 批处理操作 ====================

    def batch_add_images(
        self,
        image_paths: List[str],
        image_type: str = "single_image",
        source: str = "user_upload",
        project_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Tuple[int, List[str]]:
        """批量添加图片"""
        if not self.annotation_manager:
            return 0, []
        
        success_count = 0
        failed_ids = []
        
        for path in image_paths:
            img_id = self.add_image(
                image_path=path,
                image_type=image_type,
                source=source,
                project_id=project_id,
                created_by=created_by,
            )
            if img_id:
                success_count += 1
            else:
                failed_ids.append(path)
        
        return success_count, failed_ids

    def batch_update_status(self, image_ids: List[str], status: str) -> Tuple[int, int]:
        """批量更新状态"""
        if not self.annotation_manager:
            return 0, len(image_ids)
        
        success = 0
        failed = 0
        
        for img_id in image_ids:
            if self.update_image_status(img_id, status):
                success += 1
            else:
                failed += 1
        
        return success, failed

    # ==================== 搜索和过滤 ====================

    def search_images(
        self,
        keyword: Optional[str] = None,
        project_id: Optional[str] = None,
        image_type: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[ImageData]:
        """搜索图片"""
        if self.annotation_manager:
            return self.annotation_manager.search_images(
                keyword=keyword,
                project_id=project_id,
                image_type=image_type,
                status=status,
                tags=tags,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
            )
        return []

    def get_statistics(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """获取标注统计"""
        if self.annotation_manager:
            return self.annotation_manager.get_statistics(project_id)
        return {}

    # ==================== 导出功能 ====================

    def export_annotations(
        self,
        format_type: str,
        project_id: Optional[str] = None,
        image_ids: Optional[List[str]] = None,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """导出标注数据"""
        if self.annotation_manager:
            return self.annotation_manager.export_annotations(
                format_type=format_type,
                project_id=project_id,
                image_ids=image_ids,
                output_path=output_path,
            )
        return None

    # ==================== 评论和讨论 ====================

    def add_comment(
        self,
        image_id: str,
        content: str,
        user: str,
        parent_comment_id: Optional[str] = None,
    ) -> Optional[str]:
        """添加评论"""
        if self.annotation_manager:
            return self.annotation_manager.add_comment(
                image_id=image_id,
                content=content,
                user=user,
                parent_comment_id=parent_comment_id,
            )
        return None

    def get_comments(self, image_id: str) -> List[AnnotationComment]:
        """获取图片评论"""
        if self.annotation_manager:
            return self.annotation_manager.get_comments(image_id)
        return []

    # ==================== 标签管理 ====================

    def add_tag(self, image_id: str, tag_name: str, created_by: str) -> bool:
        """添加标签"""
        if self.annotation_manager:
            return self.annotation_manager.add_tag(image_id, tag_name, created_by)
        return False

    def get_tags(self, image_id: str) -> List[ImageTag]:
        """获取图片标签"""
        if self.annotation_manager:
            return self.annotation_manager.get_tags(image_id)
        return []

    def remove_tag(self, image_id: str, tag_name: str) -> bool:
        """移除标签"""
        if self.annotation_manager:
            return self.annotation_manager.remove_tag(image_id, tag_name)
        return False

    def batch_add_tag(self, image_ids: List[str], tag_name: str, created_by: str) -> Tuple[int, int]:
        """批量添加标签"""
        if not self.annotation_manager:
            return 0, len(image_ids)
        success = 0
        failed = 0
        for img_id in image_ids:
            if self.add_tag(img_id, tag_name, created_by):
                success += 1
            else:
                failed += 1
        return success, failed

    # ==================== 版本控制 ====================

    def get_deleted_items(self, project_id: Optional[str] = None) -> List[ImageData]:
        """获取已删除的项目"""
        if self.annotation_manager:
            return self.annotation_manager.get_deleted_items(project_id)
        return []

    def recall_deleted(self, image_ids: List[str]) -> Tuple[int, int]:
        """召回已删除的图片"""
        if not self.annotation_manager:
            return 0, len(image_ids)
        return self.annotation_manager.recall_deleted(image_ids)

    def resurrect_batch(self, image_ids: List[str]) -> Tuple[int, int]:
        """批量恢复图片 (recall_deleted的别名)"""
        return self.recall_deleted(image_ids)

    # ==================== 收藏和书签 ====================

    def star_image(self, image_id: str, user: str) -> bool:
        """收藏图片"""
        if self.annotation_manager:
            return self.annotation_manager.star_image(image_id, user)
        return False

    def unstar_image(self, image_id: str, user: str) -> bool:
        """取消收藏"""
        if self.annotation_manager:
            return self.annotation_manager.unstar_image(image_id, user)
        return False

    def bookmark_image(self, image_id: str, user: str) -> bool:
        """添加书签"""
        if self.annotation_manager:
            return self.annotation_manager.bookmark_image(image_id, user)
        return False

    # ==================== 比较和版本 ====================

    def compare_images(self, image_id_1: str, image_id_2: str) -> Dict[str, Any]:
        """比较两张图片"""
        if self.annotation_manager:
            return self.annotation_manager.compare_images(image_id_1, image_id_2)
        return {}

    def get_group(self, group_id: str) -> Any:
        """获取图片组"""
        if self.annotation_manager:
            return self.annotation_manager.get_group(group_id)
        return None

    def create_multi_turn_images(self, initial_image_id: str, turns: List[Dict]) -> List[str]:
        """创建多轮编辑图片"""
        if self.annotation_manager:
            return self.annotation_manager.create_multi_turn_images(initial_image_id, turns)
        return []

    # ==================== 缺陷管理 ====================

    def add_defect(self, image_id: str, defect_type: str, description: str, severity: str = "minor") -> bool:
        """添加缺陷记录"""
        if self.annotation_manager:
            return self.annotation_manager.add_defect(image_id, defect_type, description, severity)
        return False

    def fix_defect(self, image_id: str, defect_id: str) -> bool:
        """修复缺陷"""
        if self.annotation_manager:
            return self.annotation_manager.fix_defect(image_id, defect_id)
        return False

    def get_pending_review_items(self, project_id: Optional[str] = None) -> List[ImageData]:
        """获取待审核项目"""
        if self.annotation_manager:
            return self.annotation_manager.get_pending_review_items(project_id)
        return []

    def resolve_comment(self, comment_id: str) -> bool:
        """解决评论"""
        if self.annotation_manager:
            return self.annotation_manager.resolve_comment(comment_id)
        return False

    def get_recent_images(self, limit: int = 10) -> List[ImageData]:
        """获取最近的图片"""
        if self.annotation_manager:
            return self.annotation_manager.get_recent_images(limit)
        return []

    def get_image_by_asset_id(self, asset_id: str) -> Optional[ImageData]:
        """通过资产ID获取图片"""
        if self.annotation_manager:
            return self.annotation_manager.get_image_by_asset_id(asset_id)
        return None


# 全局标注管理器实例
_annotation_manager = None


def get_annotation_manager() -> AnnotationManager:
    """获取标注管理器全局实例"""
    global _annotation_manager
    if _annotation_manager is None:
        _annotation_manager = AnnotationManager()
    return _annotation_manager


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 测试数据库管理器
    db = get_db_manager()

    print("=== 数据库管理系统测试 ===")

    # 创建测试记录
    record_id = db.create(
        data_type=DataCategory.ANNOTATION,
        content={"image_id": "test_001", "annotations": []},
        metadata={"source": "test"},
        created_by="test_user",
        tags=["test", "demo"],
    )
    print(f"创建记录: {record_id}")

    # 读取记录
    record = db.read(record_id)
    print(f"读取记录: {record.record_id if record else 'None'}")

    # 查询记录
    records, total = db.query(QueryFilter(data_category=DataCategory.ANNOTATION))
    print(f"查询结果: {total}条记录")

    # 获取分析
    analytics = db.get_analytics(7)
    print(f"总记录数: {analytics.total_records}")
    print(f"活跃用户: {analytics.active_users}")

    # 获取质量报告
    quality = db.get_quality_report()
    print(f"数据质量: 有效{quality.valid_records}/{quality.total_records}")

    print("\n=== 标注系统测试 ===")
    
    # 测试标注管理器
    annotator = get_annotation_manager()
    
    if annotator.annotation_manager:
        # 创建测试项目
        project_id = annotator.create_project(
            name="测试项目",
            description="用于测试的标注项目",
            created_by="test_user",
        )
        print(f"创建项目: {project_id}")
        
        # 添加测试图片
        image_id = annotator.add_image(
            image_path="test/images/sample.jpg",
            image_type="single_image",
            source="manual_capture",
            project_id=project_id,
            created_by="test_user",
        )
        print(f"添加图片: {image_id}")
        
        if image_id:
            # 添加标注
            anno_id = annotator.add_annotation(
                image_id=image_id,
                annotation_type="bounding_box",
                label="person",
                coordinates=[100, 100, 200, 200],
                annotator="test_user",
                confidence=0.95,
            )
            print(f"添加标注: {anno_id}")
            
            # 添加质量检查
            inspect_id = annotator.add_quality_inspection(
                image_id=image_id,
                inspector="reviewer",
                result="approved",
                notes="标注质量良好",
            )
            print(f"添加质量检查: {inspect_id}")
            
            # 添加评论
            comment_id = annotator.add_comment(
                image_id=image_id,
                content="这是一个测试评论",
                user="test_user",
            )
            print(f"添加评论: {comment_id}")
            
            # 添加标签
            annotator.add_tag(image_id, "测试", "test_user")
            annotator.add_tag(image_id, "样本", "test_user")
            
            # 获取统计
            stats = annotator.get_statistics()
            print(f"统计信息: {stats}")
        
        # 列出所有项目
        projects = annotator.list_projects()
        print(f"项目数量: {len(projects)}")
        
        # 获取所有图片
        images = annotator.list_images(project_id=project_id)
        print(f"图片数量: {len(images)}")
    else:
        print("标注系统不可用")
    
    print("\n=== 测试完成 ===")
