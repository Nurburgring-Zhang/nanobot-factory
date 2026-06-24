"""Database Models for SQLite (SQLAlchemy)"""
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, JSON, create_engine,
    Table, MetaData, text as sa_text
)
from sqlalchemy.orm import sessionmaker, Session, declarative_base
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/imdf.db")
# SQLite needs check_same_thread=False for FastAPI
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- Models ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="viewer")
    tenant_id = Column(String(100), default="default")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    # Resource quotas
    max_datasets = Column(Integer, default=10)
    max_storage_mb = Column(Integer, default=1024)
    max_api_calls_per_day = Column(Integer, default=1000)

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    tenant_id = Column(String(100), default="default")
    quota = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    version = Column(String(50), default="1.0.0")
    files_count = Column(Integer, default=0)
    status = Column(String(20), default="draft")
    created_by = Column(String(100), nullable=False)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    requirement_id = Column(String(100), nullable=False)
    assignee = Column(String(100), default="")
    status = Column(String(20), default="pending")
    deadline = Column(DateTime, nullable=True)

class EvalRecord(Base):
    __tablename__ = "eval_records"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, nullable=False)
    model_name = Column(String(200), nullable=False)
    metrics = Column(JSON, default=dict)
    status = Column(String(20), default="pending")

class StatsSnapshot(Base):
    __tablename__ = "stats_snapshots"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    metrics_json = Column(JSON, default=dict)

class Delivery(Base):
    __tablename__ = "deliveries"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    dataset_version = Column(String(50), default="1.0.0")
    status = Column(String(20), default="pending")
    reviewer = Column(String(100), default="")
    comments = Column(String(500), default="")

# --- Dependency Injection ---

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a SQLite session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_async() -> AsyncGenerator:
    """Placeholder for async DB session (requires async engine)."""
    raise NotImplementedError("Async database not configured; use get_db() instead.")

# --- Initialization ---

def init_db():
    """Create all tables in the SQLite database and apply migrations."""
    # Ensure the data directory exists
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)

    # Apply quota column migration for existing databases
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info('users')"))
            existing_cols = [row[1] for row in result.fetchall()]
            quota_cols = {
                'max_datasets': 'INTEGER DEFAULT 10',
                'max_storage_mb': 'INTEGER DEFAULT 1024',
                'max_api_calls_per_day': 'INTEGER DEFAULT 1000',
            }
            for col_name, col_type in quota_cols.items():
                if col_name not in existing_cols:
                    conn.execute(text(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}'))
                    conn.commit()
    except Exception as e:
        logger.error(f"Operation failed: {e}")  # best-effort migration
