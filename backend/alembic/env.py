"""
Alembic migrations environment configuration for Nanobot Factory.

Supports both SQLite (default) and PostgreSQL via DATABASE_URL env variable.
"""

import logging
import os
import re
from logging.config import fileConfig

from alembic import context

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ---- Database URL resolution ------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgresql://") if DATABASE_URL else False
SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "nanobot.db"),
)

if USE_POSTGRES:
    database_url = DATABASE_URL
    logger.info("Alembic targeting PostgreSQL: %s", database_url[:40] + "...")
else:
    # Convert absolute/relative SQLite path to sqlalchemy URL
    db_path = SQLITE_PATH
    # Make path absolute relative to this file's directory if relative
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(__file__), "..", db_path)
    database_url = f"sqlite:///{db_path}"
    logger.info("Alembic targeting SQLite: %s", database_url)

# Override sqlalchemy.url in config
config.set_main_option("sqlalchemy.url", database_url)

# ---- Metadata ---------------------------------------------------------------
# Import the metadata from your application models.
# For Nanobot Factory, the schema is defined in database.py directly.
# We construct a MetaData object reflecting the current schema.

from sqlalchemy import (
    Column, Integer, String, Float, Text, MetaData, Table,
    ForeignKey, PrimaryKeyConstraint, Index,
)

target_metadata = MetaData()

# ---- Reflect or define schema -----------------------------------------------
# Define tables matching the schema in database.py so Alembic can detect changes.

Table(
    "assets",
    target_metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("type", String, nullable=False),
    Column("path", String, nullable=False),
    Column("size", Integer, nullable=False),
    Column("hash", String, nullable=False),
    Column("tags", Text, default="[]"),
    Column("metadata", Text, default="{}"),
    Column("quality_score", Float, default=0.0),
    Column("aesthetic_score", Float, default=0.0),
    Column("nsfw_score", Float, default=0.0),
    Column("clip_score", Float, default=0.0),
    Column("rating", Integer, default=0),
    Column("color", String, default=""),
    Column("palette", Text, default=""),
    Column("primary_color", String, default=""),
    Column("annotation", Text, default=""),
    Column("folder_id", String, default=""),
    Column("favorite", Integer, default=0),
    Column("width", Integer, default=0),
    Column("height", Integer, default=0),
    Column("duration", Integer, default=0),
    Column("format", String, default=""),
    Column("mime_type", String, default=""),
    Column("orientation", Integer, default=1),
    Column("source_url", String, default=""),
    Column("author", String, default=""),
    Column("copyright", String, default=""),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("thumbnail_path", String, default=""),
    Column("import_source", String, default=""),
)

Table(
    "folders",
    target_metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("parent_id", String, default=""),
    Column("is_smart", Integer, default=0),
    Column("smart_rules", Text, default="{}"),
    Column("color", String, default=""),
    Column("icon", String, default=""),
    Column("sort_order", Integer, default=0),
    Column("is_system", Integer, default=0),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

Table(
    "tag_groups",
    target_metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("color", String, default=""),
    Column("sort_order", Integer, default=0),
    Column("created_at", String, nullable=False),
)

Table(
    "tags",
    target_metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("group_id", String, default=""),
    Column("parent_id", String, default=""),
    Column("color", String, default=""),
    Column("count", Integer, default=0),
    Column("created_at", String, nullable=False),
)

Table(
    "asset_folders",
    target_metadata,
    Column("asset_id", String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("folder_id", String, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("asset_id", "folder_id"),
)

Table(
    "asset_tags",
    target_metadata,
    Column("asset_id", String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("tag_id", String, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("asset_id", "tag_id"),
)

Table(
    "metadata",
    target_metadata,
    Column("asset_id", String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("key", String, nullable=False),
    Column("value", Text),
    PrimaryKeyConstraint("asset_id", "key"),
)

Table(
    "datasets",
    target_metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("description", Text),
    Column("asset_count", Integer, default=0),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

Table(
    "smart_folders",
    target_metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("conditions", Text, nullable=False),
    Column("sort_by", String, default="created_at"),
    Column("sort_order", String, default="desc"),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

Table(
    "dataset_assets",
    target_metadata,
    Column("dataset_id", String, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
    Column("asset_id", String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("dataset_id", "asset_id"),
)


# ---- Migration functions ----------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to the actual database)."""
    from sqlalchemy import create_engine

    connectable = create_engine(config.get_main_option("sqlalchemy.url"))

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
