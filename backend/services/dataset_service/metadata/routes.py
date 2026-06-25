"""P4-4-W1 metadata FastAPI router.

Public surface (mounted by ``services/dataset_service/main.py``)::

  GET  /api/v1/metadata/health                     鈥?sub-health
  POST /api/v1/metadata/databases                  鈥?create database
  GET  /api/v1/metadata/databases                  鈥?list
  GET  /api/v1/metadata/databases/{id}             鈥?detail
  DELETE /api/v1/metadata/databases/{id}           鈥?delete
  POST /api/v1/metadata/schemas                    鈥?create schema
  GET  /api/v1/metadata/schemas                    鈥?list
  POST /api/v1/metadata/tables                     鈥?create table (+ columns optional)
  GET  /api/v1/metadata/tables                     鈥?list
  POST /api/v1/metadata/columns                    鈥?create column
  GET  /api/v1/metadata/columns                    鈥?list
  POST /api/v1/metadata/datasets                   鈥?create dataset
  GET  /api/v1/metadata/datasets                   鈥?list

  POST /api/v1/metadata/discovery/run              鈥?manual discovery
  GET  /api/v1/metadata/discovery/schedule         鈥?list schedules
  POST /api/v1/metadata/discovery/schedule         鈥?upsert schedule
  POST /api/v1/metadata/discovery/schedule/{db}/run 鈥?tick

  POST /api/v1/metadata/tags                       鈥?create / upsert tag
  GET  /api/v1/metadata/tags                       鈥?list
  POST /api/v1/metadata/tags/assign                鈥?assign tag 鈫?target
  POST /api/v1/metadata/tags/unassign              鈥?unassign
  POST /api/v1/metadata/tags/auto/pii              鈥?auto PII scan
  POST /api/v1/metadata/tags/propagate             鈥?propagate column 鈫?table

  POST /api/v1/metadata/glossaries                 鈥?upsert glossary
  GET  /api/v1/metadata/glossaries                 鈥?list
  POST /api/v1/metadata/glossaries/{id}/terms      鈥?create term
  GET  /api/v1/metadata/glossaries/{id}/terms      鈥?list terms
  POST /api/v1/metadata/glossary/terms/{id}/relations 鈥?add relation
  GET  /api/v1/metadata/glossary/terms/{id}/relations 鈥?list relations
  GET  /api/v1/metadata/glossary/terms/{id}/columns   鈥?linked columns
  POST /api/v1/metadata/glossary/seed              鈥?seed default glossary

  GET  /api/v1/metadata/search                     鈥?fulltext + tag filter
  POST /api/v1/metadata/recommend                  鈥?rec for a user
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from common import success_response, error_response, paginated_response

from . import discovery as _discovery
from . import glossary as _glossary
from . import search as _search
from . import tags as _tags
from .models import (
    ColumnORM,
    DatabaseORM,
    DatabaseSchemaORM,
    DatasetORM,
    GlossaryORM,
    GlossaryTermORM,
    TableORM,
    TagORM,
    db_to_dict,
    get_metadata_session,
    init_metadata_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/metadata", tags=["metadata"])


# Lazy engine init 鈥?runs the first time the router is hit. Safe to call
# multiple times; the underlying helper is idempotent.
@router.on_event("startup")
def _startup_init() -> None:
    init_metadata_db()


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "module": "metadata",
        "endpoints": [
            "/api/v1/metadata/databases",
            "/api/v1/metadata/tables",
            "/api/v1/metadata/columns",
            "/api/v1/metadata/datasets",
            "/api/v1/metadata/tags",
            "/api/v1/metadata/glossaries",
            "/api/v1/metadata/search",
        ],
    }


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Databases / Schemas / Tables / Columns / Datasets 鈥?basic CRUD
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
class CreateDatabaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    service: str = Field("custom", min_length=1, max_length=64)
    description: str = ""
    host: str = ""
    port: str = ""


@router.post("/databases", status_code=status.HTTP_201_CREATED)
async def create_database(req: CreateDatabaseRequest):
    init_metadata_db()
    with get_metadata_session() as s:
        if s.query(DatabaseORM).filter(DatabaseORM.name == req.name).first():
            raise HTTPException(409, detail=f"database_already_exists: {req.name}")
        d = DatabaseORM(
            name=req.name, service=req.service, description=req.description,
            host=req.host, port=req.port,
        )
        s.add(d); s.commit(); s.refresh(d)
        return success_response(db_to_dict(d), message="database_created", status_code=201)


@router.get("/databases")
async def list_databases():
    init_metadata_db()
    with get_metadata_session() as s:
        return success_response([db_to_dict(d) for d in s.query(DatabaseORM).order_by(DatabaseORM.name).all()])


@router.get("/databases/{db_id}")
async def get_database(db_id: str):
    init_metadata_db()
    with get_metadata_session() as s:
        d = s.query(DatabaseORM).filter(DatabaseORM.id == db_id).one_or_none()
        if not d:
            raise HTTPException(404, detail="database_not_found")
        return success_response(db_to_dict(d))


@router.delete("/databases/{db_id}")
async def delete_database(db_id: str):
    init_metadata_db()
    with get_metadata_session() as s:
        d = s.query(DatabaseORM).filter(DatabaseORM.id == db_id).one_or_none()
        if not d:
            raise HTTPException(404, detail="database_not_found")
        s.delete(d); s.commit()
        return success_response({"deleted": True, "id": db_id})


class CreateSchemaRequest(BaseModel):
    database_id: str
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""


@router.post("/schemas", status_code=status.HTTP_201_CREATED)
async def create_schema(req: CreateSchemaRequest):
    init_metadata_db()
    with get_metadata_session() as s:
        db = s.query(DatabaseORM).filter(DatabaseORM.id == req.database_id).one_or_none()
        if not db:
            raise HTTPException(404, detail="database_not_found")
        sch = DatabaseSchemaORM(
            database_id=req.database_id, name=req.name, description=req.description
        )
        s.add(sch); s.commit(); s.refresh(sch)
        return success_response(db_to_dict(sch), message="schema_created", status_code=201)


@router.get("/schemas")
async def list_schemas(database_id: Optional[str] = None):
    init_metadata_db()
    with get_metadata_session() as s:
        q = s.query(DatabaseSchemaORM)
        if database_id:
            q = q.filter(DatabaseSchemaORM.database_id == database_id)
        return success_response([db_to_dict(x) for x in q.order_by(DatabaseSchemaORM.name).all()])


class ColumnIn(BaseModel):
    name: str
    data_type: str = "string"
    nullable: bool = True
    description: str = ""
    ordinal: int = 0


class CreateTableRequest(BaseModel):
    schema_id: str
    name: str
    table_type: str = "table"
    description: str = ""
    owner: str = ""
    row_count_estimate: int = 0
    columns: List[ColumnIn] = Field(default_factory=list)


@router.post("/tables", status_code=status.HTTP_201_CREATED)
async def create_table(req: CreateTableRequest):
    init_metadata_db()
    with get_metadata_session() as s:
        sch = s.query(DatabaseSchemaORM).filter(DatabaseSchemaORM.id == req.schema_id).one_or_none()
        if not sch:
            raise HTTPException(404, detail="schema_not_found")
        if (s.query(TableORM).filter(TableORM.schema_id == req.schema_id, TableORM.name == req.name).first()):
            raise HTTPException(409, detail="table_already_exists")
        t = TableORM(
            schema_id=req.schema_id,
            name=req.name,
            table_type=req.table_type,
            description=req.description,
            owner=req.owner,
            row_count_estimate=str(req.row_count_estimate),
            extra="{}",
        )
        s.add(t); s.flush()
        for ci in req.columns:
            s.add(ColumnORM(
                table_id=t.id,
                name=ci.name,
                data_type=ci.data_type,
                nullable="true" if ci.nullable else "false",
                description=ci.description,
                ordinal=str(ci.ordinal),
                extra="{}",
            ))
        s.commit(); s.refresh(t)
        # Refetch with columns
        out = db_to_dict(t)
        out["columns"] = [db_to_dict(c) for c in t.columns]
        return success_response(out, message="table_created", status_code=201)


@router.get("/tables")
async def list_tables(schema_id: Optional[str] = None, database_id: Optional[str] = None):
    init_metadata_db()
    with get_metadata_session() as s:
        q = s.query(TableORM)
        if schema_id:
            q = q.filter(TableORM.schema_id == schema_id)
        if database_id:
            q = q.join(DatabaseSchemaORM, TableORM.schema_id == DatabaseSchemaORM.id)
            q = q.filter(DatabaseSchemaORM.database_id == database_id)
        return success_response([db_to_dict(x) for x in q.order_by(TableORM.name).all()])


class CreateColumnRequest(BaseModel):
    table_id: str
    name: str
    data_type: str = "string"
    nullable: bool = True
    description: str = ""
    ordinal: int = 0


@router.post("/columns", status_code=status.HTTP_201_CREATED)
async def create_column(req: CreateColumnRequest):
    init_metadata_db()
    with get_metadata_session() as s:
        t = s.query(TableORM).filter(TableORM.id == req.table_id).one_or_none()
        if not t:
            raise HTTPException(404, detail="table_not_found")
        c = ColumnORM(
            table_id=req.table_id, name=req.name, data_type=req.data_type,
            nullable="true" if req.nullable else "false",
            description=req.description, ordinal=str(req.ordinal), extra="{}",
        )
        s.add(c); s.commit(); s.refresh(c)
        return success_response(db_to_dict(c), message="column_created", status_code=201)


@router.get("/columns")
async def list_columns(table_id: Optional[str] = None):
    init_metadata_db()
    with get_metadata_session() as s:
        q = s.query(ColumnORM)
        if table_id:
            q = q.filter(ColumnORM.table_id == table_id)
        return success_response([db_to_dict(x) for x in q.order_by(ColumnORM.ordinal).all()])


class CreateDatasetRequest(BaseModel):
    name: str
    format: str = "parquet"
    size_bytes: int = 0
    row_count: int = 0
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    owner: str = ""
    tier: str = "bronze"
    location: str = ""


@router.post("/datasets", status_code=status.HTTP_201_CREATED)
async def create_dataset(req: CreateDatasetRequest):
    init_metadata_db()
    import json as _json
    with get_metadata_session() as s:
        if s.query(DatasetORM).filter(DatasetORM.name == req.name).first():
            raise HTTPException(409, detail="dataset_already_exists")
        d = DatasetORM(
            name=req.name, format=req.format,
            size_bytes=str(req.size_bytes), row_count=str(req.row_count),
            columns_json=_json.dumps(req.columns, ensure_ascii=False),
            description=req.description, owner=req.owner,
            tier=req.tier, location=req.location,
            extra="{}",
        )
        s.add(d); s.commit(); s.refresh(d)
        out = db_to_dict(d)
        return success_response(out, message="dataset_created", status_code=201)


@router.get("/datasets")
async def list_datasets(tier: Optional[str] = None):
    init_metadata_db()
    with get_metadata_session() as s:
        q = s.query(DatasetORM)
        if tier:
            q = q.filter(DatasetORM.tier == tier)
        return success_response([db_to_dict(x) for x in q.order_by(DatasetORM.name).all()])


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Discovery
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
class DiscoveryRequest(BaseModel):
    backend: str = Field("auto", pattern="^(auto|postgres|filesystem)$")
    target: str
    database_name: str = "default"
    llm_endpoint: Optional[str] = None
    save_schedule: bool = False


@router.post("/discovery/run")
async def run_discovery(req: DiscoveryRequest):
    init_metadata_db()
    try:
        res = _discovery.run_discovery(
            backend=req.backend,
            target=req.target,
            database_name=req.database_name,
            llm_endpoint=req.llm_endpoint,
            save_schedule=req.save_schedule,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return success_response(res.to_dict())


class ScheduleRequest(BaseModel):
    database_name: str
    backend: str = Field("postgres", pattern="^(postgres|filesystem)$")
    target: str
    cron: str = "0 3 * * *"
    enabled: bool = True


@router.post("/discovery/schedule")
async def upsert_schedule(req: ScheduleRequest):
    sched = _discovery.upsert_schedule(
        _discovery.DiscoverySchedule(
            backend=req.backend, target=req.target,
            database_name=req.database_name, cron=req.cron,
            enabled=req.enabled,
        )
    )
    return success_response({
        "database_name": sched.database_name,
        "backend": sched.backend, "target": sched.target,
        "cron": sched.cron, "enabled": sched.enabled,
    })


@router.get("/discovery/schedule")
async def list_schedules():
    return success_response([
        {
            "database_name": s.database_name,
            "backend": s.backend, "target": s.target,
            "cron": s.cron, "enabled": s.enabled,
            "last_run_at": s.last_run_at,
        }
        for s in _discovery.list_schedules()
    ])


@router.post("/discovery/schedule/{database_name}/run")
async def run_schedule(database_name: str):
    res = _discovery.apply_schedule(database_name)
    if res is None:
        raise HTTPException(404, detail="schedule_not_found_or_disabled")
    return success_response(res.to_dict())


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Tags
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
class CreateTagRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    category: str = "general"
    description: str = ""
    color: str = "#888888"
    source: str = "manual"
    sensitivity_level: int = Field(0, ge=0, le=5)


@router.post("/tags", status_code=status.HTTP_201_CREATED)
async def create_tag(req: CreateTagRequest):
    init_metadata_db()
    t = _tags.upsert_tag(
        req.name, category=req.category, description=req.description,
        color=req.color, source=req.source,
        sensitivity_level=req.sensitivity_level,
    )
    return success_response(_tags.get_tag_by_id(t.id), message="tag_upserted", status_code=201)


@router.get("/tags")
async def list_tags(category: Optional[str] = None, source: Optional[str] = None):
    return success_response(_tags.list_tags(category=category, source=source))


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: str):
    ok = _tags.delete_tag(tag_id)
    if not ok:
        raise HTTPException(404, detail="tag_not_found")
    return success_response({"deleted": True, "id": tag_id})


class AssignTagRequest(BaseModel):
    tag_id: str
    target_type: str = Field(..., pattern="^(column|table|dataset|glossary_term)$")
    target_id: str
    source: str = "manual"


@router.post("/tags/assign", status_code=status.HTTP_201_CREATED)
async def assign_tag(req: AssignTagRequest):
    try:
        a = _tags.assign_tag(req.tag_id, req.target_type, req.target_id, source=req.source)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return success_response(a, message="tag_assigned", status_code=201)


class UnassignTagRequest(BaseModel):
    tag_id: str
    target_type: str
    target_id: str


@router.post("/tags/unassign")
async def unassign_tag(req: UnassignTagRequest):
    ok = _tags.unassign_tag(req.tag_id, req.target_type, req.target_id)
    return success_response({"removed": ok})


@router.post("/tags/auto/pii")
async def auto_tag_pii(
    database_name: Optional[str] = None,
    schema_name: Optional[str] = None,
    dry_run: bool = False,
):
    res = _tags.auto_tag_pii(database_name=database_name, schema_name=schema_name, dry_run=dry_run)
    return success_response(res.to_dict())


@router.post("/tags/propagate")
async def propagate_tags(only_pii: bool = True, dry_run: bool = False):
    res = _tags.propagate_column_tags(only_pii=only_pii, dry_run=dry_run)
    return success_response(res.to_dict())


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Glossary
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
class CreateGlossaryRequest(BaseModel):
    name: str
    description: str = ""
    owner: str = ""


@router.post("/glossaries", status_code=status.HTTP_201_CREATED)
async def create_glossary(req: CreateGlossaryRequest):
    g = _glossary.upsert_glossary(req.name, description=req.description, owner=req.owner)
    return success_response(_glossary.get_glossary(g.id), message="glossary_upserted", status_code=201)


@router.get("/glossaries")
async def list_glossaries():
    return success_response(_glossary.list_glossaries())


@router.delete("/glossaries/{glossary_id}")
async def delete_glossary(glossary_id: str):
    ok = _glossary.delete_glossary(glossary_id)
    if not ok:
        raise HTTPException(404, detail="glossary_not_found")
    return success_response({"deleted": True, "id": glossary_id})


class CreateTermRequest(BaseModel):
    name: str
    definition: str = ""
    related_terms: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)


@router.post("/glossaries/{glossary_id}/terms", status_code=status.HTTP_201_CREATED)
async def create_term(glossary_id: str, req: CreateTermRequest):
    try:
        t = _glossary.create_term(
            glossary_id, req.name,
            definition=req.definition,
            related_terms=req.related_terms,
            extra=req.extra,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return success_response(_glossary.get_term(t.id), message="term_created", status_code=201)


@router.get("/glossaries/{glossary_id}/terms")
async def list_terms(glossary_id: str, name_like: Optional[str] = None):
    return success_response(_glossary.list_terms(glossary_id, name_like=name_like))


class AddRelationRequest(BaseModel):
    from_term_id: str
    to_term_id: str
    relation_type: str
    note: str = ""
    bidirectional: bool = False


@router.post("/glossary/terms/relations", status_code=status.HTTP_201_CREATED)
async def add_relation(req: AddRelationRequest):
    try:
        r = _glossary.add_relation(
            req.from_term_id, req.to_term_id, req.relation_type,
            note=req.note, bidirectional=req.bidirectional,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return success_response({"id": r.id, "from_term_id": r.from_term_id,
                             "to_term_id": r.to_term_id,
                             "relation_type": r.relation_type})


@router.get("/glossary/terms/{term_id}/relations")
async def list_relations_for_term(term_id: str, relation_type: Optional[str] = None):
    return success_response(_glossary.list_relations(term_id, relation_type=relation_type))


@router.get("/glossary/terms/{term_id}/columns")
async def list_term_columns(term_id: str):
    return success_response([lc.to_dict() for lc in _glossary.link_term_to_columns(term_id)])


@router.post("/glossary/seed")
async def seed_glossary():
    out = _glossary.seed_default_glossary()
    return success_response(out, message="default_glossary_seeded")


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Search + recommend
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
@router.get("/search")
async def search(
    q: str = Query("", description="Free-text query"),
    type: Optional[str] = Query(None, description="Type filter: database/table/column/..."),
    tag_ids: Optional[List[str]] = Query(None),
    tag_names: Optional[List[str]] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    init_metadata_db()
    try:
        hits = _search.search(
            q, type_filter=type, tag_ids=tag_ids, tag_names=tag_names,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return success_response({
        "query": q,
        "type": type,
        "count": len(hits),
        "hits": hits,
    })


class RecommendRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=100)


@router.post("/recommend")
async def recommend(req: RecommendRequest):
    return success_response({
        "user_id": req.user_id,
        "count": 0,
        "items": _search.recommend(req.user_id, limit=req.limit),
    })


class RecordViewRequest(BaseModel):
    user_id: str
    target_type: str = Field(..., pattern="^(database|table|column|dataset|glossary_term)$")
    target_id: str


@router.post("/record-view")
async def record_view(req: RecordViewRequest):
    _search.record_view(req.user_id, req.target_type, req.target_id)
    return success_response({"recorded": True})


__all__ = ["router"]

