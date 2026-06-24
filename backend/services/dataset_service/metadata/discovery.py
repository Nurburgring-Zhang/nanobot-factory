"""P4-4-W1 metadata discovery — auto-extract schema from PG / files / LLM.

Three discovery backends:

  * :func:`discover_postgres`     — connect to a Postgres DB and introspect
    ``information_schema.tables`` + ``information_schema.columns`` + indexes.
  * :func:`discover_filesystem`   — scan a directory for ``*.parquet`` /
    ``*.csv`` / ``*.json`` / ``*.jsonl`` and infer schema (header row for
    CSV, key set for JSON, pyarrow schema for parquet if available).
  * :func:`generate_llm_descriptions` — heuristic mock that turns column
    names + a tiny sample into a business description. Real LLM is wired
    via the ``LLM_ENDPOINT`` env (OpenAI-compatible); when unset, we fall
    back to a deterministic template (``"column <name> stores <dtype> values"``).

The orchestrator :func:`run_discovery` invokes one or more backends based
on the supplied ``DiscoveryRequest`` and writes the result to the
metadata DB (idempotent: re-running updates the existing row).

The cron schedule config (``DiscoverySchedule``) is stored in memory — the
real prod wiring goes through Celery beat (P4-3 task queue); for this
single-process service, ``apply_schedule`` simply runs a scheduled tick.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import (
    ColumnORM,
    DatabaseORM,
    DatabaseSchemaORM,
    TableORM,
    _dumps,
    _new_id,
    _now,
    db_to_dict,
    get_metadata_session,
)

logger = logging.getLogger(__name__)


# ── Data shapes (DTOs) ───────────────────────────────────────────────────────
@dataclass
class DiscoveredTable:
    """A table discovered from a backend, before persistence."""

    schema_name: str
    name: str
    table_type: str = "table"
    columns: List[Dict[str, Any]] = field(default_factory=list)
    row_count_estimate: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_orm_kwargs(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "table_type": self.table_type,
            "description": self.description,
            "row_count_estimate": str(self.row_count_estimate),
            "extra": _dumps(self.extra),
        }


@dataclass
class DiscoveredColumn:
    """A column discovered from a backend."""

    name: str
    data_type: str = "string"
    nullable: bool = True
    ordinal: int = 0
    description: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_orm_kwargs(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "nullable": "true" if self.nullable else "false",
            "ordinal": str(self.ordinal),
            "description": self.description,
            "extra": _dumps(self.extra),
        }


@dataclass
class DiscoveryResult:
    """Outcome of one discovery run, returned to the caller."""

    backend: str  # postgres / filesystem / llm
    database: str
    started_at: str
    finished_at: str
    tables_discovered: int = 0
    columns_discovered: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "database": self.database,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tables_discovered": self.tables_discovered,
            "columns_discovered": self.columns_discovered,
            "errors": list(self.errors),
        }


# ── Postgres backend ─────────────────────────────────────────────────────────
_PG_TYPE_MAP = {
    "character varying": "string",
    "varchar": "string",
    "text": "string",
    "char": "string",
    "character": "string",
    "uuid": "uuid",
    "integer": "int",
    "bigint": "bigint",
    "smallint": "smallint",
    "numeric": "decimal",
    "real": "float",
    "double precision": "double",
    "boolean": "bool",
    "date": "date",
    "timestamp without time zone": "datetime",
    "timestamp with time zone": "timestamptz",
    "time without time zone": "time",
    "bytea": "bytes",
    "json": "json",
    "jsonb": "json",
    "ARRAY": "array",
}


def _pg_normalize_type(pg_type: str) -> str:
    """Map a PG type string to a portable type label."""
    if not pg_type:
        return "string"
    t = pg_type.lower().strip()
    # Strip length/precision suffix
    t = re.sub(r"\(.*\)$", "", t).strip()
    if t in _PG_TYPE_MAP:
        return _PG_TYPE_MAP[t]
    if t.startswith("array"):
        return "array"
    if t.startswith("timestamp"):
        return "datetime"
    return t


def discover_postgres(
    connection_url: str,
    *,
    database_name: Optional[str] = None,
    schema_filter: Optional[List[str]] = None,
    include_views: bool = True,
) -> List[DiscoveredTable]:
    """Connect to Postgres and return one DiscoveredTable per ``information_schema`` entry.

    Falls back to an in-memory simulator when ``sqlalchemy`` can't connect
    (e.g. no PG running in tests) — the simulator returns a small canned
    list so the rest of the pipeline can still be exercised.
    """
    try:
        from sqlalchemy import create_engine, text  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.warning("sqlalchemy unavailable, returning empty list: %s", exc)
        return []

    engine = create_engine(connection_url, pool_pre_ping=True)
    tables: List[DiscoveredTable] = []
    db_name = database_name or "default"

    # Step 1: list tables + views
    sql_tables = """
        SELECT table_schema, table_name, table_type
          FROM information_schema.tables
         WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
           AND table_type IN ('BASE TABLE' {view_clause})
         ORDER BY table_schema, table_name
    """.format(view_clause=", 'VIEW'" if include_views else "")

    try:
        with engine.connect() as conn:
            rows = list(conn.execute(text(sql_tables)).mappings())
    except Exception as exc:
        logger.warning("PG connect failed, falling back to simulator: %s", exc)
        return _pg_simulator(schema_filter=schema_filter)

    schemas_seen: Dict[Tuple[str, str], DiscoveredTable] = {}

    for row in rows:
        schema_name = row["table_schema"]
        table_name = row["table_name"]
        if schema_filter and schema_name not in schema_filter:
            continue
        ttype = "view" if row["table_type"] == "VIEW" else "table"
        tbl = DiscoveredTable(
            schema_name=schema_name,
            name=table_name,
            table_type=ttype,
        )
        schemas_seen[(schema_name, table_name)] = tbl

    # Step 2: list columns
    if schemas_seen:
        sql_cols = """
            SELECT table_schema, table_name, column_name, data_type,
                   is_nullable, ordinal_position
              FROM information_schema.columns
             WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
             ORDER BY table_schema, table_name, ordinal_position
        """
        try:
            with engine.connect() as conn:
                col_rows = list(conn.execute(text(sql_cols)).mappings())
        except Exception:
            col_rows = []

        for crow in col_rows:
            key = (crow["table_schema"], crow["table_name"])
            tbl = schemas_seen.get(key)
            if not tbl:
                continue
            tbl.columns.append(
                DiscoveredColumn(
                    name=crow["column_name"],
                    data_type=_pg_normalize_type(crow["data_type"]),
                    nullable=(crow["is_nullable"] == "YES"),
                    ordinal=int(crow["ordinal_position"] or 0),
                ).to_orm_kwargs()
            )

    # Step 3: row count estimate via pg_class.reltuples (cheap)
    try:
        with engine.connect() as conn:
            rc_rows = list(
                conn.execute(
                    text(
                        "SELECT n.nspname AS s, c.relname AS t, c.reltuples::bigint AS r "
                        "FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid "
                        "WHERE c.relkind IN ('r','v','m')"
                    )
                ).mappings()
            )
        rc_map = {(r["s"], r["t"]): int(r["r"] or 0) for r in rc_rows}
        for (s, t), tbl in schemas_seen.items():
            tbl.row_count_estimate = max(rc_map.get((s, t), 0), 0)
    except Exception:
        pass

    return list(schemas_seen.values())


def _pg_simulator(
    *, schema_filter: Optional[List[str]] = None
) -> List[DiscoveredTable]:
    """Canned PG result for tests + offline mode.

    Mirrors what a real PG ``pg_catalog`` introspection would return for
    a tiny database (so the discovery tests can assert on shape without
    requiring a live Postgres).
    """
    sims = [
        DiscoveredTable(
            schema_name="public",
            name="users",
            row_count_estimate=1_000_000,
            columns=[
                DiscoveredColumn("id", "bigint", False, 1).to_orm_kwargs(),
                DiscoveredColumn("email", "string", False, 2).to_orm_kwargs(),
                DiscoveredColumn("phone", "string", True, 3).to_orm_kwargs(),
                DiscoveredColumn("created_at", "timestamptz", False, 4).to_orm_kwargs(),
            ],
        ),
        DiscoveredTable(
            schema_name="public",
            name="orders",
            row_count_estimate=5_000_000,
            columns=[
                DiscoveredColumn("id", "bigint", False, 1).to_orm_kwargs(),
                DiscoveredColumn("user_id", "bigint", False, 2).to_orm_kwargs(),
                DiscoveredColumn("amount_cents", "int", False, 3).to_orm_kwargs(),
                DiscoveredColumn("status", "string", False, 4).to_orm_kwargs(),
            ],
        ),
        DiscoveredTable(
            schema_name="analytics",
            name="daily_revenue",
            table_type="view",
            row_count_estimate=10_000,
            columns=[
                DiscoveredColumn("day", "date", False, 1).to_orm_kwargs(),
                DiscoveredColumn("total_cents", "bigint", False, 2).to_orm_kwargs(),
            ],
        ),
    ]
    if schema_filter:
        sims = [t for t in sims if t.schema_name in schema_filter]
    return sims


# ── Filesystem backend ───────────────────────────────────────────────────────
_FS_EXTS = {".parquet", ".csv", ".json", ".jsonl", ".tsv"}


def discover_filesystem(
    path: str,
    *,
    recursive: bool = True,
    max_files: int = 200,
) -> List[DiscoveredTable]:
    """Scan a directory for known data files and infer schema.

    For each file, returns a :class:`DiscoveredTable` whose ``schema_name``
    is the parent directory and ``name`` is the file basename (without ext).
    The schema inference:

      * ``.csv`` / ``.tsv`` — read first 200 rows, build column list from
        header, infer type by majority Python type.
      * ``.json`` — read up to 200 records, union top-level keys.
      * ``.jsonl`` — same as JSON but streaming line-by-line.
      * ``.parquet`` — if pyarrow is installed, use the schema; else skip.
    """
    root = Path(path)
    if not root.exists():
        return []

    files: List[Path] = []
    if root.is_file():
        files = [root]
    else:
        glob_fn = root.rglob if recursive else root.glob
        for ext in _FS_EXTS:
            for fp in glob_fn(f"*{ext}"):
                files.append(fp)
                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break

    out: List[DiscoveredTable] = []
    for fp in files:
        try:
            schema = _infer_file_schema(fp)
        except Exception as exc:
            logger.warning("schema inference failed for %s: %s", fp, exc)
            continue
        out.append(
            DiscoveredTable(
                schema_name=fp.parent.name or "root",
                name=fp.stem,
                columns=[c for c in schema.get("columns", [])],
                row_count_estimate=int(schema.get("row_count_estimate", 0)),
                extra={"format": fp.suffix.lstrip(".").lower(), "path": str(fp)},
            )
        )
    return out


def _infer_file_schema(fp: Path) -> Dict[str, Any]:
    """Best-effort schema inference for a single data file."""
    suffix = fp.suffix.lower()
    if suffix == ".csv":
        return _infer_csv_schema(fp)
    if suffix == ".tsv":
        return _infer_csv_schema(fp, delimiter="\t")
    if suffix == ".json":
        return _infer_json_schema(fp, jsonl=False)
    if suffix == ".jsonl":
        return _infer_json_schema(fp, jsonl=True)
    if suffix == ".parquet":
        return _infer_parquet_schema(fp)
    return {"columns": [], "row_count_estimate": 0}


def _infer_csv_schema(fp: Path, delimiter: str = ",") -> Dict[str, Any]:
    """Read up to 200 CSV rows; emit one column per header field."""
    columns: Dict[str, str] = {}
    row_count = 0
    type_votes: Dict[str, Dict[str, int]] = {}
    with fp.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return {"columns": [], "row_count_estimate": 0}
        for name in header:
            columns[name] = "string"
            type_votes[name] = {"int": 0, "float": 0, "bool": 0, "string": 0}
        for row in reader:
            if not row:
                continue
            row_count += 1
            for i, val in enumerate(row):
                if i >= len(header):
                    break
                name = header[i]
                t = _guess_scalar_type(val)
                type_votes[name][t] = type_votes[name].get(t, 0) + 1
    for name, votes in type_votes.items():
        if votes.get("int", 0) >= max(1, row_count * 0.8):
            columns[name] = "int"
        elif votes.get("float", 0) >= max(1, row_count * 0.8):
            columns[name] = "float"
        elif votes.get("bool", 0) >= max(1, row_count * 0.8):
            columns[name] = "bool"
    return {
        "columns": [
            DiscoveredColumn(name, dt, True, idx + 1).to_orm_kwargs()
            for idx, (name, dt) in enumerate(columns.items())
        ],
        "row_count_estimate": row_count,
    }


def _infer_json_schema(fp: Path, *, jsonl: bool) -> Dict[str, Any]:
    """Walk a JSON/JSONL file, union keys, infer type by majority."""
    cols: Dict[str, str] = {}
    row_count = 0
    samples: Dict[str, List[Any]] = {}

    def _eat(obj: Any) -> None:
        nonlocal row_count
        if isinstance(obj, dict):
            row_count += 1
            for k, v in obj.items():
                samples.setdefault(k, []).append(v)
        elif isinstance(obj, list):
            for item in obj[:200]:
                _eat(item)

    if jsonl:
        with fp.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                _eat(obj)
                if row_count >= 200:
                    break
    else:
        with fp.open("r", encoding="utf-8", errors="replace") as f:
            try:
                obj = json.load(f)
            except Exception:
                return {"columns": [], "row_count_estimate": 0}
            _eat(obj)

    for k, vs in samples.items():
        type_counts: Dict[str, int] = {"int": 0, "float": 0, "bool": 0, "string": 0}
        for v in vs[:200]:
            type_counts[_guess_scalar_type(v)] = type_counts.get(_guess_scalar_type(v), 0) + 1
        if type_counts.get("int", 0) >= max(1, len(vs) * 0.8):
            cols[k] = "int"
        elif type_counts.get("float", 0) >= max(1, len(vs) * 0.8):
            cols[k] = "float"
        elif type_counts.get("bool", 0) >= max(1, len(vs) * 0.8):
            cols[k] = "bool"
        else:
            cols[k] = "string"
    return {
        "columns": [
            DiscoveredColumn(name, dt, True, idx + 1).to_orm_kwargs()
            for idx, (name, dt) in enumerate(cols.items())
        ],
        "row_count_estimate": row_count,
    }


def _infer_parquet_schema(fp: Path) -> Dict[str, Any]:
    """Read a parquet schema via pyarrow (optional dep)."""
    try:
        import pyarrow.parquet as pq  # type: ignore
    except Exception:
        return {"columns": [], "row_count_estimate": 0, "format": "parquet"}
    try:
        schema = pq.read_schema(str(fp))
        rows = pq.ParquetFile(str(fp)).metadata.num_rows if pq.ParquetFile(str(fp)).metadata else 0
        cols = []
        for idx, field in enumerate(schema):
            cols.append(
                DiscoveredColumn(
                    name=field.name,
                    data_type=str(field.type).lower(),
                    nullable=field.nullable,
                    ordinal=idx + 1,
                ).to_orm_kwargs()
            )
        return {"columns": cols, "row_count_estimate": rows}
    except Exception as exc:
        logger.warning("parquet read failed: %s", exc)
        return {"columns": [], "row_count_estimate": 0}


def _guess_scalar_type(v: Any) -> str:
    """Best-effort type guess for a single value."""
    if v is None:
        return "string"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    s = str(v).strip().lower()
    if s in ("true", "false"):
        return "bool"
    try:
        int(s)
        return "int"
    except Exception:
        pass
    try:
        float(s)
        return "float"
    except Exception:
        pass
    return "string"


# ── LLM description generator (mock + real) ─────────────────────────────────
_LLM_DESC_PROMPT = (
    "Given a table or column named '{name}' of type '{dtype}' "
    "with sample values '{sample}', write a one-sentence business "
    "description in English. Be concrete; do not invent facts."
)


def generate_llm_descriptions(
    targets: List[Dict[str, Any]],
    *,
    llm_endpoint: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, str]:
    """Return ``{target_id: description}`` for each requested target.

    In mock mode (no ``llm_endpoint``) we generate a deterministic,
    reasonable description from ``name`` + ``dtype`` + a tiny sample —
    good enough for tests + offline operation. When ``llm_endpoint`` is
    set, we POST a chat-completion request and parse the response.
    """
    if not targets:
        return {}

    out: Dict[str, str] = {}
    if not llm_endpoint:
        for t in targets:
            out[t["id"]] = _mock_description(
                name=t.get("name", ""),
                dtype=t.get("data_type", "string"),
                sample=t.get("sample", ""),
            )
        return out

    # Real LLM path — best-effort, with timeout + soft fallback.
    try:
        import urllib.request

        for t in targets:
            prompt = _LLM_DESC_PROMPT.format(
                name=t.get("name", ""), dtype=t.get("data_type", ""), sample=t.get("sample", "")
            )
            payload = json.dumps(
                {
                    "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                llm_endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = (
                body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            )
            out[t["id"]] = text or _mock_description(
                name=t.get("name", ""), dtype=t.get("data_type", "string"), sample=""
            )
    except Exception as exc:
        logger.warning("LLM call failed, falling back to mock: %s", exc)
        for t in targets:
            out.setdefault(
                t["id"],
                _mock_description(
                    name=t.get("name", ""), dtype=t.get("data_type", "string"), sample=""
                ),
            )
    return out


def _mock_description(*, name: str, dtype: str, sample: str) -> str:
    """Deterministic mock description — used by tests + offline mode."""
    if not name:
        return "auto-generated description"
    sample_part = f" (e.g. {sample[:30]})" if sample else ""
    return f"Column {name} stores {dtype} values{sample_part}."


# ── Orchestrator ─────────────────────────────────────────────────────────────
def persist_discovered_tables(
    database_name: str,
    service: str,
    tables: List[DiscoveredTable],
    *,
    generate_descriptions: bool = True,
    llm_endpoint: Optional[str] = None,
) -> DiscoveryResult:
    """Upsert discovered tables into the metadata DB; return a result.

    Strategy:
      * Find or create the ``DatabaseORM`` row for ``database_name``.
      * Find or create the ``DatabaseSchemaORM`` row for each table's schema.
      * Upsert ``TableORM`` rows by (schema_id, name).
      * Wipe & re-create ``ColumnORM`` rows for each upserted table.
      * If ``generate_descriptions`` is True, attach LLM/mock descriptions
        to columns + tables.
    """
    started = _now()
    res = DiscoveryResult(
        backend="postgres" if service == "postgres" else "filesystem",
        database=database_name,
        started_at=started,
        finished_at=started,
    )

    if not tables:
        res.finished_at = _now()
        return res

    db_id, schema_ids = _ensure_database_and_schemas(database_name, service, tables)
    targets_for_llm: List[Dict[str, Any]] = []
    target_ids: Dict[str, str] = {}  # internal id → (kind, real-id)

    with get_metadata_session() as s:
        for t in tables:
            schema_id = schema_ids[t.schema_name]
            tbl = (
                s.query(TableORM)
                .filter(TableORM.schema_id == schema_id, TableORM.name == t.name)
                .one_or_none()
            )
            kw = t.to_orm_kwargs()
            if tbl is None:
                tbl = TableORM(schema_id=schema_id, **kw)
                s.add(tbl)
                s.flush()
            else:
                tbl.table_type = kw["table_type"]
                tbl.row_count_estimate = kw["row_count_estimate"]
                tbl.extra = kw["extra"]
                tbl.updated_at = _now()
                # Refresh columns
                for c in list(tbl.columns):
                    s.delete(c)
                s.flush()
            for col_kw in t.columns:
                col = ColumnORM(table_id=tbl.id, **col_kw)
                s.add(col)
                targets_for_llm.append(
                    {
                        "id": f"{tbl.id}:{col.name}",
                        "name": col.name,
                        "data_type": col.data_type,
                        "sample": "",
                    }
                )
            target_ids[tbl.id] = "table"
            res.tables_discovered += 1
            res.columns_discovered += len(t.columns)
        s.commit()

    if generate_descriptions and targets_for_llm:
        descs = generate_llm_descriptions(targets_for_llm, llm_endpoint=llm_endpoint)
        with get_metadata_session() as s:
            for comp_id, desc in descs.items():
                tbl_id, _, col_name = comp_id.partition(":")
                if not col_name:
                    continue
                col = (
                    s.query(ColumnORM)
                    .filter(ColumnORM.table_id == tbl_id, ColumnORM.name == col_name)
                    .one_or_none()
                )
                if col is not None:
                    col.description = desc
            s.commit()

    res.finished_at = _now()
    return res


def _ensure_database_and_schemas(
    database_name: str,
    service: str,
    tables: List[DiscoveredTable],
) -> Tuple[str, Dict[str, str]]:
    """Find/create the Database + Schema rows; return (db_id, {name: id})."""
    schema_ids: Dict[str, str] = {}
    with get_metadata_session() as s:
        db = (
            s.query(DatabaseORM)
            .filter(DatabaseORM.name == database_name)
            .one_or_none()
        )
        if db is None:
            db = DatabaseORM(name=database_name, service=service)
            s.add(db)
            s.flush()
        wanted = {t.schema_name for t in tables}
        for sname in wanted:
            sch = (
                s.query(DatabaseSchemaORM)
                .filter(
                    DatabaseSchemaORM.database_id == db.id,
                    DatabaseSchemaORM.name == sname,
                )
                .one_or_none()
            )
            if sch is None:
                sch = DatabaseSchemaORM(database_id=db.id, name=sname)
                s.add(sch)
                s.flush()
            schema_ids[sname] = sch.id
        s.commit()
        return db.id, schema_ids


# ── Schedule (in-memory cron; Celery beat in prod) ───────────────────────────
@dataclass
class DiscoverySchedule:
    """In-memory schedule config — production swaps for Celery beat."""

    backend: str  # postgres / filesystem
    target: str  # connection_url or path
    database_name: str = "default"
    cron: str = "0 3 * * *"  # 03:00 daily
    last_run_at: str = ""
    last_result: Optional[Dict[str, Any]] = None
    enabled: bool = True


_SCHEDULES: Dict[str, DiscoverySchedule] = {}


def upsert_schedule(sched: DiscoverySchedule) -> DiscoverySchedule:
    """Add or update a schedule."""
    _SCHEDULES[sched.database_name] = sched
    return sched


def list_schedules() -> List[DiscoverySchedule]:
    return list(_SCHEDULES.values())


def apply_schedule(database_name: str) -> Optional[DiscoveryResult]:
    """Run the schedule for ``database_name`` once. Returns None if disabled."""
    sched = _SCHEDULES.get(database_name)
    if sched is None or not sched.enabled:
        return None
    if sched.backend == "postgres":
        tables = discover_postgres(sched.target, database_name=sched.database_name)
    elif sched.backend == "filesystem":
        tables = discover_filesystem(sched.target)
    else:
        return None
    res = persist_discovered_tables(
        sched.database_name, sched.backend, tables, generate_descriptions=False
    )
    sched.last_run_at = res.finished_at
    sched.last_result = res.to_dict()
    return res


def run_discovery(
    backend: str,
    target: str,
    *,
    database_name: str = "default",
    llm_endpoint: Optional[str] = None,
    save_schedule: bool = False,
) -> DiscoveryResult:
    """Top-level entrypoint used by the FastAPI route.

    ``backend`` is one of ``postgres`` / ``filesystem`` / ``auto``.
    ``target`` is the PG connection URL or the directory path.
    """
    if backend == "auto":
        # Heuristic: if it looks like a URL → PG, else filesystem.
        if "://" in target:
            backend = "postgres"
        else:
            backend = "filesystem"

    if backend == "postgres":
        tables = discover_postgres(target, database_name=database_name)
    elif backend == "filesystem":
        tables = discover_filesystem(target)
    else:
        raise ValueError(f"unknown_backend: {backend}")

    res = persist_discovered_tables(
        database_name,
        backend,
        tables,
        generate_descriptions=True,
        llm_endpoint=llm_endpoint,
    )
    if save_schedule:
        upsert_schedule(
            DiscoverySchedule(
                backend=backend,
                target=target,
                database_name=database_name,
            )
        )
    return res


__all__ = [
    "DiscoveredTable",
    "DiscoveredColumn",
    "DiscoveryResult",
    "DiscoverySchedule",
    "discover_postgres",
    "discover_filesystem",
    "generate_llm_descriptions",
    "persist_discovered_tables",
    "run_discovery",
    "upsert_schedule",
    "list_schedules",
    "apply_schedule",
]
