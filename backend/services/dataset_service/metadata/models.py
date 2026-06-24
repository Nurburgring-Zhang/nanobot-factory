"""P4-4-W1 metadata ORM models + Pydantic schemas.

10 SQLAlchemy ORM tables, modeled after OpenMetadata's metadata spine::

    md_databases           (Database)            — physical or logical database
    md_schemas             (DatabaseSchema)      — namespace inside a database
    md_tables              (Table)               — table inside a schema
    md_columns             (Column)              — column inside a table
    md_datasets            (Dataset)             — logical dataset (file/folder/PG view)
    md_tags                (Tag)                 — taxonomy tag (PII / sensitivity / business)
    md_tag_assignments     (TagAssignment)       — M:N: tag → resource (table/column/dataset/glossary_term)
    md_glossaries          (Glossary)            — business glossary
    md_glossary_terms      (GlossaryTerm)        — single business term (user_id / email / 性别 ...)
    md_term_relations      (TermRelation)        — synonym / antonym / parent / derives_from / maps_to

Why 10? The minimum viable OpenMetadata spine requires:
  - 4 hierarchy tables (database/schema/table/column)
  - 1 dataset table (for files / data products)
  - 3 taxonomy tables (tag / assignment / glossary)
  - 2 term-relation tables (term + relation)

Schema choices:
  - All ids are 32-char hex strings (uuid4.hex) — portable across PG / SQLite.
  - ``created_at`` / ``updated_at`` stored as ISO-8601 strings (UTC) so SQLite tests
    don't depend on tzdata.
  - JSON / list columns stored as ``Text`` with JSON serialization helpers
    (``json.dumps`` / ``json.loads``) so SQLite and PG share the same path.
  - Indices on FK columns + natural keys (``name``).

The file also exposes the matching **Pydantic** schemas (one ORM table ↔ one Pydantic
model) so routes can return typed JSON envelopes without re-parsing dicts.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column as SAColumn,
    ForeignKey,
    Index,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_id() -> str:
    return uuid.uuid4().hex


def _loads(s: Optional[str], default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ── SQLAlchemy base ───────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Declarative base for all 10 metadata ORM tables."""


# ── ORM classes ──────────────────────────────────────────────────────────────
class DatabaseORM(Base):
    """A database instance — PG / MySQL / SQLite / etc.

    Inspired by OpenMetadata's ``Database`` entity.
    """

    __tablename__ = "md_databases"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    name = SAColumn(String(128), nullable=False, unique=True)
    service = SAColumn(String(64), nullable=False, default="custom")  # postgres / mysql / sqlite / duckdb / file
    description = SAColumn(Text, default="")
    host = SAColumn(String(256), default="")
    port = SAColumn(String(8), default="")
    created_at = SAColumn(String(32), default=_now, nullable=False)
    updated_at = SAColumn(String(32), default=_now, nullable=False)

    schemas = relationship(
        "DatabaseSchemaORM", back_populates="database", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_md_databases_service", "service"),)


class DatabaseSchemaORM(Base):
    """A namespace/schema inside a database (``public`` / ``analytics`` / ...)."""

    __tablename__ = "md_schemas"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    database_id = SAColumn(
        String(32), ForeignKey("md_databases.id", ondelete="CASCADE"), nullable=False
    )
    name = SAColumn(String(128), nullable=False)
    description = SAColumn(Text, default="")
    created_at = SAColumn(String(32), default=_now, nullable=False)

    database = relationship("DatabaseORM", back_populates="schemas")
    tables = relationship(
        "TableORM", back_populates="schema", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_md_schemas_database", "database_id"),
        Index("uq_md_schemas_db_name", "database_id", "name", unique=True),
    )


class TableORM(Base):
    """A physical or virtual table inside a schema."""

    __tablename__ = "md_tables"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    schema_id = SAColumn(
        String(32), ForeignKey("md_schemas.id", ondelete="CASCADE"), nullable=False
    )
    name = SAColumn(String(256), nullable=False)
    table_type = SAColumn(String(32), default="table")  # table / view / materialized_view
    description = SAColumn(Text, default="")
    owner = SAColumn(String(128), default="")
    row_count_estimate = SAColumn(String(32), default="0")
    extra = SAColumn(Text, default="{}")  # JSON: indexes, constraints
    created_at = SAColumn(String(32), default=_now, nullable=False)
    updated_at = SAColumn(String(32), default=_now, nullable=False)

    schema = relationship("DatabaseSchemaORM", back_populates="tables")
    columns = relationship(
        "ColumnORM", back_populates="table", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_md_tables_schema", "schema_id"),
        Index("uq_md_tables_schema_name", "schema_id", "name", unique=True),
    )


class ColumnORM(Base):
    """A single column inside a table."""

    __tablename__ = "md_columns"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    table_id = SAColumn(
        String(32), ForeignKey("md_tables.id", ondelete="CASCADE"), nullable=False
    )
    name = SAColumn(String(256), nullable=False)
    data_type = SAColumn(String(64), default="string")
    nullable = SAColumn(String(8), default="true")  # "true" / "false"
    description = SAColumn(Text, default="")
    ordinal = SAColumn(String(16), default="0")
    extra = SAColumn(Text, default="{}")  # JSON: default, length, precision, is_pk
    created_at = SAColumn(String(32), default=_now, nullable=False)

    table = relationship("TableORM", back_populates="columns")

    __table_args__ = (
        Index("ix_md_columns_table", "table_id"),
        Index("uq_md_columns_table_name", "table_id", "name", unique=True),
    )


class DatasetORM(Base):
    """A logical dataset — file/folder/PG view/data product.

    OpenMetadata also calls this ``Dataset``; we treat it as the unit of
    consumption (vs. ``Table`` which is a physical unit of storage).
    """

    __tablename__ = "md_datasets"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    name = SAColumn(String(256), nullable=False, unique=True)
    format = SAColumn(String(32), default="parquet")  # parquet / csv / json / jsonl / avro / tfrecord
    size_bytes = SAColumn(String(32), default="0")
    row_count = SAColumn(String(32), default="0")
    columns_json = SAColumn(Text, default="[]")  # [{name,type,description},...]
    description = SAColumn(Text, default="")
    owner = SAColumn(String(128), default="")
    tier = SAColumn(String(16), default="bronze")  # bronze / silver / gold
    location = SAColumn(String(512), default="")
    extra = SAColumn(Text, default="{}")
    created_at = SAColumn(String(32), default=_now, nullable=False)
    updated_at = SAColumn(String(32), default=_now, nullable=False)

    __table_args__ = (Index("ix_md_datasets_tier", "tier"),)


class TagORM(Base):
    """A taxonomy tag — PII / sensitivity / business classification."""

    __tablename__ = "md_tags"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    name = SAColumn(String(128), nullable=False, unique=True)
    category = SAColumn(String(64), default="general")  # pii / sensitivity / business / technical
    description = SAColumn(Text, default="")
    color = SAColumn(String(16), default="#888888")
    source = SAColumn(String(32), default="manual")  # manual / auto_pii / auto_business
    sensitivity_level = SAColumn(String(8), default="0")  # 0=none, 1=public, 2=internal, 3=confidential, 4=restricted, 5=secret
    created_at = SAColumn(String(32), default=_now, nullable=False)

    __table_args__ = (
        Index("ix_md_tags_category", "category"),
        Index("ix_md_tags_source", "source"),
    )


class TagAssignmentORM(Base):
    """M:N between tags and resource (column/table/dataset/glossary_term)."""

    __tablename__ = "md_tag_assignments"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    tag_id = SAColumn(
        String(32), ForeignKey("md_tags.id", ondelete="CASCADE"), nullable=False
    )
    target_type = SAColumn(String(32), nullable=False)  # column / table / dataset / glossary_term
    target_id = SAColumn(String(32), nullable=False)
    source = SAColumn(String(32), default="manual")  # manual / auto / propagation
    created_at = SAColumn(String(32), default=_now, nullable=False)

    tag = relationship("TagORM")

    __table_args__ = (
        Index("ix_md_tag_assignments_tag", "tag_id"),
        Index("ix_md_tag_assignments_target", "target_type", "target_id"),
        Index(
            "uq_md_tag_assignments",
            "tag_id",
            "target_type",
            "target_id",
            unique=True,
        ),
    )


class GlossaryORM(Base):
    """A business glossary — a curated vocabulary for a domain."""

    __tablename__ = "md_glossaries"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    name = SAColumn(String(128), nullable=False, unique=True)
    description = SAColumn(Text, default="")
    owner = SAColumn(String(128), default="")
    created_at = SAColumn(String(32), default=_now, nullable=False)

    terms = relationship(
        "GlossaryTermORM", back_populates="glossary", cascade="all, delete-orphan"
    )


class GlossaryTermORM(Base):
    """A single business term — ``user_id`` / ``email`` / ``真实姓名`` / ``性别``."""

    __tablename__ = "md_glossary_terms"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    glossary_id = SAColumn(
        String(32), ForeignKey("md_glossaries.id", ondelete="CASCADE"), nullable=False
    )
    name = SAColumn(String(256), nullable=False)
    definition = SAColumn(Text, default="")
    related_terms_json = SAColumn(Text, default="[]")  # [term_id, ...] — quick refs
    extra = SAColumn(Text, default="{}")  # JSON: examples / references
    created_at = SAColumn(String(32), default=_now, nullable=False)
    updated_at = SAColumn(String(32), default=_now, nullable=False)

    glossary = relationship("GlossaryORM", back_populates="terms")
    relations = relationship(
        "TermRelationORM",
        primaryjoin="or_(GlossaryTermORM.id==TermRelationORM.from_term_id, "
        "GlossaryTermORM.id==TermRelationORM.to_term_id)",
        viewonly=True,
    )

    __table_args__ = (
        Index("ix_md_glossary_terms_glossary", "glossary_id"),
        Index("uq_md_glossary_terms_glossary_name", "glossary_id", "name", unique=True),
    )


class TermRelationORM(Base):
    """Directed relation between two glossary terms.

    Types follow OpenMetadata conventions plus our own:
      * ``synonym``      — interchangeable names (e.g. ``user_id`` ⇄ ``uid``)
      * ``antonym``      — opposite meanings (e.g. ``active`` vs ``disabled``)
      * ``parent``       — ``to_term`` is the parent of ``from_term``
      * ``derives_from`` — ``from_term`` is derived from ``to_term``
      * ``maps_to``      — ``from_term`` corresponds to ``to_term`` (cross-domain)
    """

    __tablename__ = "md_term_relations"

    id = SAColumn(String(32), primary_key=True, default=_new_id)
    from_term_id = SAColumn(
        String(32), ForeignKey("md_glossary_terms.id", ondelete="CASCADE"), nullable=False
    )
    to_term_id = SAColumn(
        String(32), ForeignKey("md_glossary_terms.id", ondelete="CASCADE"), nullable=False
    )
    relation_type = SAColumn(String(32), nullable=False)
    note = SAColumn(Text, default="")
    created_at = SAColumn(String(32), default=_now, nullable=False)

    __table_args__ = (
        Index("ix_md_term_relations_from", "from_term_id"),
        Index("ix_md_term_relations_to", "to_term_id"),
        Index(
            "uq_md_term_relations",
            "from_term_id",
            "to_term_id",
            "relation_type",
            unique=True,
        ),
    )


# ── Pydantic schemas ─────────────────────────────────────────────────────────
class _Base(BaseModel):
    model_config = {"from_attributes": True}


class Database(_Base):
    id: str
    name: str
    service: str = "custom"
    description: str = ""
    host: str = ""
    port: str = ""
    created_at: str = ""
    updated_at: str = ""


class DatabaseSchema(_Base):
    id: str
    database_id: str
    name: str
    description: str = ""
    created_at: str = ""


class Table(_Base):
    id: str
    schema_id: str
    name: str
    table_type: str = "table"
    description: str = ""
    owner: str = ""
    row_count_estimate: str = "0"
    extra: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class Column(_Base):
    id: str
    table_id: str
    name: str
    data_type: str = "string"
    nullable: str = "true"
    description: str = ""
    ordinal: str = "0"
    extra: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class Dataset(_Base):
    id: str
    name: str
    format: str = "parquet"
    size_bytes: str = "0"
    row_count: str = "0"
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    owner: str = ""
    tier: str = "bronze"
    location: str = ""
    extra: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class Tag(_Base):
    id: str
    name: str
    category: str = "general"
    description: str = ""
    color: str = "#888888"
    source: str = "manual"
    sensitivity_level: int = 0
    created_at: str = ""


class TagAssignment(_Base):
    id: str
    tag_id: str
    target_type: str
    target_id: str
    source: str = "manual"
    created_at: str = ""


class Glossary(_Base):
    id: str
    name: str
    description: str = ""
    owner: str = ""
    created_at: str = ""
    term_count: int = 0  # derived


class GlossaryTerm(_Base):
    id: str
    glossary_id: str
    name: str
    definition: str = ""
    related_terms: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class TermRelation(_Base):
    id: str
    from_term_id: str
    to_term_id: str
    relation_type: str
    note: str = ""
    created_at: str = ""


# ── Engine bootstrap (mirrors backend.common.db) ─────────────────────────────
_metadata_engine: Optional[Engine] = None
_metadata_session_factory: Optional[sessionmaker] = None


def _build_metadata_engine(url: str) -> Engine:
    """Build a SQLAlchemy engine compatible with both SQLite + PG.

    SQLite gets PRAGMA foreign_keys=ON + WAL; PG gets pool_pre_ping.
    """
    if url.startswith("sqlite"):
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
            try:
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
            except Exception:
                pass
        return eng
    return create_engine(url, pool_pre_ping=True)


def init_metadata_db(
    db_url: Optional[str] = None,
    *,
    auto_create: bool = True,
) -> Engine:
    """Initialise the metadata engine + (optionally) ``create_all`` tables.

    Resolution order:
      1. ``db_url`` arg
      2. ``IMDF_P2_DB_URL`` env
      3. ``METADATA_DB_URL`` env
      4. SQLite under ``backend/data/metadata.db``

    Safe to call multiple times — only the first call wires the engine;
    later calls return the cached engine.
    """
    global _metadata_engine, _metadata_session_factory

    if _metadata_engine is not None:
        if auto_create:
            try:
                Base.metadata.create_all(bind=_metadata_engine)
            except Exception:
                pass
        return _metadata_engine

    import os
    from pathlib import Path

    if not db_url:
        db_url = (
            os.environ.get("IMDF_P2_DB_URL", "").strip()
            or os.environ.get("METADATA_DB_URL", "").strip()
        )
    if not db_url:
        # Default: SQLite under backend/data/metadata.db
        here = Path(__file__).resolve().parents[3]  # backend/
        data_dir = here / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{(data_dir / 'metadata.db').as_posix()}"

    _metadata_engine = _build_metadata_engine(db_url)
    _metadata_session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=_metadata_engine, expire_on_commit=False
    )
    if auto_create:
        Base.metadata.create_all(bind=_metadata_engine)
    return _metadata_engine


def get_metadata_session() -> Session:
    """Yield a metadata Session (caller closes)."""
    if _metadata_session_factory is None:
        init_metadata_db()
    assert _metadata_session_factory is not None
    return _metadata_session_factory()


def reset_metadata_engine() -> None:
    """Test hook: drop the cached engine so tests can re-init with a tmp DB."""
    global _metadata_engine, _metadata_session_factory
    if _metadata_engine is not None:
        try:
            _metadata_engine.dispose()
        except Exception:
            pass
    _metadata_engine = None
    _metadata_session_factory = None


# ── ORM → dict helpers (used by routes / tests) ──────────────────────────────
def db_to_dict(obj) -> Dict[str, Any]:
    """Serialise an ORM instance to a dict; decode JSON/list fields."""
    if obj is None:
        return {}
    d: Dict[str, Any] = {}
    for col in obj.__table__.columns:
        v = getattr(obj, col.name)
        d[col.name] = v
    # Decode JSON fields
    if isinstance(obj, DatasetORM):
        d["columns"] = _loads(d.get("columns_json"), [])
        d["extra"] = _loads(d.get("extra"), {})
    elif isinstance(obj, TableORM):
        d["extra"] = _loads(d.get("extra"), {})
    elif isinstance(obj, ColumnORM):
        d["extra"] = _loads(d.get("extra"), {})
    elif isinstance(obj, GlossaryTermORM):
        d["related_terms"] = _loads(d.get("related_terms_json"), [])
        d["extra"] = _loads(d.get("extra"), {})
    return d


__all__ = [
    # ORM
    "Base",
    "DatabaseORM",
    "DatabaseSchemaORM",
    "TableORM",
    "ColumnORM",
    "DatasetORM",
    "TagORM",
    "TagAssignmentORM",
    "GlossaryORM",
    "GlossaryTermORM",
    "TermRelationORM",
    # Pydantic
    "Database",
    "DatabaseSchema",
    "Table",
    "Column",
    "Dataset",
    "Tag",
    "TagAssignment",
    "Glossary",
    "GlossaryTerm",
    "TermRelation",
    # Engine bootstrap
    "init_metadata_db",
    "get_metadata_session",
    "reset_metadata_engine",
    # Helpers
    "db_to_dict",
    "_new_id",
    "_now",
]
