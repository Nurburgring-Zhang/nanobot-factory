"""P4-4-W1 metadata package — OpenMetadata-inspired metadata platform.

This package turns ``dataset_service`` into a full metadata service with:

  * **10 ORM tables** — Database / DatabaseSchema / Table / Column /
    Dataset / Tag / TagAssignment / Glossary / GlossaryTerm / TermRelation.
  * **discovery** — PostgreSQL/filesystem/LLM-driven auto-discovery.
  * **tags** — auto-PII + manual + propagation.
  * **glossary** — business terms with synonyms / antonyms / hierarchy.
  * **search** — full-text + tag filter + recommendations.
  * **routes** — ``/api/v1/metadata/*`` CRUD surface.

Module map (intentionally flat to keep imports trivial)::

    metadata/
      __init__.py    ← public surface (re-exports + init_db)
      models.py      ← 10 SQLAlchemy ORM classes + 10 Pydantic schemas
      discovery.py   ← PG introspection + file schema inference + LLM descriptions
      tags.py        ← PII detector + auto-tag + propagation
      glossary.py    ← terms + relations + column linking
      search.py      ← fulltext + tag filter + rec
      routes.py      ← FastAPI router (mounted by services/dataset_service/main.py)
"""
from __future__ import annotations

from .models import (
    Base,
    ColumnORM,
    DatabaseORM,
    DatabaseSchemaORM,
    DatasetORM,
    GlossaryORM,
    GlossaryTermORM,
    TableORM,
    TagORM,
    TagAssignmentORM,
    TermRelationORM,
    init_metadata_db,
)

__all__ = [
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
    "init_metadata_db",
]
