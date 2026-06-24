"""P4-4-W2 lineage collector.

Four collection paths, all returning a uniform :class:`LineageCollectResult`:

  1. **SQL**         — sqlglot parses SELECT/JOIN/CTE/INSERT…SELECT
                       → table-level + column-level edges
  2. **AST**         — Python ``ast`` parses pandas/polars-style DataFrame
                       ops (read_csv / read_parquet / merge / join / assign)
  3. **Operator**    — explicitly invoked after cleaning/scoring/... op
                       execution: ``record_operator(operator_id, in, out)``
  4. **Manual**      — user-declared: ``record_manual(from, to, edge_type)``

A fifth, **scan** mode is supported by the API: re-scan a known source
(e.g. registered dataset → re-parse its declared SQL view definition).

Each call returns a :class:`LineageCollectResult` with the edges added,
the run id, and a flag indicating success. Persistence goes through
the SQLAlchemy engine wired by :mod:`models`.
"""
from __future__ import annotations

import ast
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from .models import (
    COLLECT_SOURCES,
    EDGE_TYPES,
    ENTITY_TYPES,
    AssetORM,
    EdgeORM,
    RunORM,
    _dumps,
    _loads,
    _new_id,
    _now,
    get_lineage_session,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Result object
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class LineageCollectResult:
    """Outcome of a single collection call.

    Attributes
    ----------
    ok               : bool — did the parse succeed + persist
    source           : one of COLLECT_SOURCES
    edges_added      : number of new edges written
    edges_skipped    : number of edges already present (deduped)
    assets_added     : number of new assets auto-registered
    run_id           : id of the lin_runs audit row
    message          : human-readable summary / error
    edges            : full list of edge dicts that were added
    """

    ok: bool
    source: str
    edges_added: int = 0
    edges_skipped: int = 0
    assets_added: int = 0
    run_id: str = ""
    message: str = ""
    edges: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "source": self.source,
            "edges_added": self.edges_added,
            "edges_skipped": self.edges_skipped,
            "assets_added": self.assets_added,
            "run_id": self.run_id,
            "message": self.message,
            "edges": list(self.edges),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Asset registration helper
# ═════════════════════════════════════════════════════════════════════════════
def _split_qualified_name(qn: str) -> Tuple[str, str]:
    """``pg.public.users`` → (``table``, ``users``); default entity_type is 'table'.

    Heuristic — any qualified name with ≥2 dots is treated as ``table``
    (db.schema.table). Names like ``ds.coco_v1`` are also ``dataset``.
    """
    if not qn:
        return "table", ""
    parts = qn.split(".")
    if len(parts) >= 3:
        return "table", parts[-1]
    if qn.startswith("ds."):
        return "dataset", parts[-1]
    if qn.startswith("col."):
        return "column", parts[-1]
    if qn.startswith("model."):
        return "model", parts[-1]
    if qn.startswith("pipe.") or qn.startswith("pipeline."):
        return "pipeline", parts[-1]
    if qn.startswith("job."):
        return "job", parts[-1]
    return "table", parts[-1]


def _ensure_asset(
    db: Session,
    qualified_name: str,
    entity_type: Optional[str] = None,
    name: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[AssetORM, bool]:
    """Get-or-create the asset row. Returns ``(asset, created)``."""
    if entity_type is None or name is None:
        et, n = _split_qualified_name(qualified_name)
        entity_type = entity_type or et
        name = name or n
    existing = (
        db.query(AssetORM)
        .filter(AssetORM.qualified_name == qualified_name)
        .one_or_none()
    )
    if existing is not None:
        return existing, False
    asset = AssetORM(
        id=_new_id(),
        qualified_name=qualified_name,
        entity_type=entity_type,
        name=name or qualified_name,
        extra=_dumps(extra or {}),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(asset)
    db.flush()
    return asset, True


def _upsert_edge(
    db: Session,
    *,
    from_entity: str,
    from_type: str,
    to_entity: str,
    to_type: str,
    edge_type: str,
    pipeline_id: str = "",
    sql: str = "",
    script: str = "",
    source: str = "manual",
    columns: Optional[List[Dict[str, Any]]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[EdgeORM, bool]:
    """Idempotent edge insert. Returns ``(edge, created)``."""
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"invalid edge_type: {edge_type}")
    existing = (
        db.query(EdgeORM)
        .filter(
            EdgeORM.from_entity == from_entity,
            EdgeORM.to_entity == to_entity,
            EdgeORM.edge_type == edge_type,
            EdgeORM.pipeline_id == pipeline_id,
            EdgeORM.source == source,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing, False
    edge = EdgeORM(
        id=_new_id(),
        from_entity=from_entity,
        from_type=from_type,
        to_entity=to_entity,
        to_type=to_type,
        edge_type=edge_type,
        pipeline_id=pipeline_id or "",
        sql=sql or "",
        script=script or "",
        source=source,
        columns_json=_dumps(columns or []),
        extra=_dumps(extra or {}),
        created_at=_now(),
    )
    db.add(edge)
    db.flush()
    return edge, True


# ═════════════════════════════════════════════════════════════════════════════
# SQL parser (sqlglot)
# ═════════════════════════════════════════════════════════════════════════════
def parse_sql_lineage(
    sql: str,
    *,
    target_entity: Optional[str] = None,
    pipeline_id: str = "",
) -> Dict[str, Any]:
    """Parse a SQL string and return a structured lineage skeleton.

    Returns
    -------
    {
        "ok": bool,
        "source_tables": ["public.user", "public.order", ...],
        "target_table":  "public.user_order_join",
        "column_edges":  [{"from": "user.id", "to": "user_order_join.user_id"}, ...],
        "ctes":           ["public.user_stats"],
        "message":        "...",
    }
    """
    out: Dict[str, Any] = {
        "ok": False,
        "source_tables": [],
        "target_table": target_entity or "",
        "column_edges": [],
        "ctes": [],
        "message": "",
    }
    if not sql or not sql.strip():
        out["message"] = "empty sql"
        return out
    try:
        import sqlglot
        from sqlglot import exp
    except Exception as exc:  # pragma: no cover
        out["message"] = f"sqlglot_unavailable: {exc}"
        return out

    try:
        stmts = sqlglot.parse(sql, read=None)
    except Exception as exc:
        out["message"] = f"parse_error: {exc}"
        return out

    if not stmts:
        out["message"] = "no statements"
        return out

    sources: List[str] = []
    targets: List[str] = []
    column_edges: List[Dict[str, str]] = []
    ctes: List[str] = []

    for stmt in stmts:
        if stmt is None:
            continue
        # CTEs
        for cte in stmt.find_all(exp.CTE):
            alias = cte.alias_or_name
            if alias:
                ctes.append(_qn("public", alias))
        # Source tables (FROM / JOIN)
        for tbl in stmt.find_all(exp.Table):
            qn = ".".join(
                p for p in (tbl.catalog, tbl.db, tbl.name) if p
            )
            if qn and qn not in sources:
                sources.append(qn)
        # Target table — INSERT / CREATE / UPDATE
        if isinstance(stmt, exp.Insert):
            target = stmt.this
            if isinstance(target, exp.Schema):
                target = target.this
            if isinstance(target, exp.Table):
                targets.append(".".join(p for p in (target.catalog, target.db, target.name) if p))
        elif isinstance(stmt, exp.Create):
            target = stmt.this
            if isinstance(target, exp.Schema):
                target = target.this
            if isinstance(target, exp.Table):
                targets.append(".".join(p for p in (target.catalog, target.db, target.name) if p))
        elif isinstance(stmt, exp.Update):
            target = stmt.this
            if isinstance(target, exp.Table):
                targets.append(".".join(p for p in (target.catalog, target.db, target.name) if p))
        # Column lineage: SELECT projections referencing source columns
        for select in stmt.find_all(exp.Select):
            tgt = target_entity or (targets[0] if targets else "public.derived")
            for proj in select.expressions:
                # An AS alias wraps the column — unwrap it
                if isinstance(proj, exp.Alias):
                    target_col = proj.alias_or_name
                    inner = proj.this
                else:
                    target_col = None
                    inner = proj
                if not isinstance(inner, exp.Column):
                    continue
                col_name = inner.name
                if not col_name:
                    continue
                src_table = inner.table
                if not src_table:
                    continue
                column_edges.append(
                    {
                        "from": f"{src_table}.{col_name}",
                        "to": f"{tgt}.{target_col or col_name}",
                    }
                )

    if not target_entity and targets:
        out["target_table"] = targets[0]
    out["source_tables"] = sources
    out["ctes"] = ctes
    out["column_edges"] = column_edges
    out["ok"] = True
    out["message"] = (
        f"parsed {len(stmts)} stmt(s); "
        f"{len(sources)} source(s), {len(column_edges)} column edge(s)"
    )
    return out


def _qn(*parts: str) -> str:
    return ".".join(p for p in parts if p)


# ═════════════════════════════════════════════════════════════════════════════
# Python AST parser (pandas / polars style)
# ═════════════════════════════════════════════════════════════════════════════
_AST_READ_FUNCS = {
    "read_csv", "read_parquet", "read_json", "read_table",
    "read_excel", "read_pickle", "read_sql", "read_sql_query", "read_sql_table",
    "scan_csv", "scan_parquet", "scan_json",
}
_AST_WRITE_FUNCS = {
    "to_csv", "to_parquet", "to_json", "to_pickle", "to_sql", "to_excel",
    "to_dict", "to_records",
}
_AST_DERIVE_METHODS = {
    "merge", "join", "concat", "assign", "with_columns", "select",
    "filter", "groupby", "agg", "transform", "pivot", "melt",
    "rename", "drop", "dropna", "fillna",
}


def _literal_str(node: ast.AST) -> Optional[str]:
    """Return the string value of a literal or constant node, if any."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Str):  # py<3.8
        return node.s
    return None


def _literal_call_name(node: ast.Call) -> Tuple[Optional[str], Optional[str]]:
    """Return (module, attr) of a Call, e.g. ``pd.read_csv`` → ('pd', 'read_csv')."""
    func = node.func
    if isinstance(func, ast.Attribute):
        # pd.read_csv
        if isinstance(func.value, ast.Name):
            return func.value.id, func.attr
        # df.merge(...)
        return None, func.attr
    if isinstance(func, ast.Name):
        return None, func.id
    return None, None


def parse_python_lineage(
    script: str,
    *,
    target_entity: Optional[str] = None,
    pipeline_id: str = "",
) -> Dict[str, Any]:
    """Parse a Python script and extract DataFrame read/write/derive ops.

    Returns
    -------
    {
        "ok": bool,
        "reads":   ["data/raw.csv", "data/aux.parquet"],
        "writes":  ["data/out.parquet"],
        "derives": ["df2"],      # intermediate var names that are derived
        "column_edges": [{"from": "raw.user_id", "to": "df2.user_id"}],
        "message": "...",
    }
    """
    out: Dict[str, Any] = {
        "ok": False,
        "reads": [],
        "writes": [],
        "derives": [],
        "column_edges": [],
        "message": "",
    }
    if not script or not script.strip():
        out["message"] = "empty script"
        return out
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        out["message"] = f"syntax_error: {exc}"
        return out

    reads: List[str] = []
    writes: List[str] = []
    derives: List[str] = []
    derived_assigns: Dict[str, List[str]] = {}  # var → list of source vars

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        mod, attr = _literal_call_name(node)
        # pd.read_csv('x.csv')
        if attr in _AST_READ_FUNCS and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                reads.append(arg.value)
            elif isinstance(arg, ast.Str):
                reads.append(arg.s)
            elif isinstance(arg, ast.Name):
                # read_csv(df) — record the var name as a derive hint
                derives.append(arg.id)
        # df.to_csv('x.csv')
        elif attr in _AST_WRITE_FUNCS and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                writes.append(arg.value)
            elif isinstance(arg, ast.Str):
                writes.append(arg.s)
        # df.merge(other, on='user_id')
        elif attr in {"merge", "join"} and node.args:
            other = node.args[0]
            if isinstance(other, ast.Name):
                # Record "left ⊕ right" provenance in the caller
                caller = _enclosing_assign_target(node, tree)
                if caller:
                    derived_assigns.setdefault(caller, []).append(other)
        # df.assign(...) or pl.with_columns(...)
        elif attr in {"assign", "with_columns", "select", "transform"}:
            caller = _enclosing_assign_target(node, tree)
            if caller:
                derives.append(caller)

    # Resolve top-level assignments: which variables are derived from which reads
    top_assigns: Dict[str, ast.AST] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name):
                    top_assigns[tgt.id] = stmt.value

    # Walk the assignment graph to find each derived var's "base" reads
    for var, src_list in derived_assigns.items():
        for src in src_list:
            edge = _resolve_chain(src, top_assigns, seen=set())
            for e in edge:
                if e not in reads:
                    reads.append(e)

    # Build column-level hints from ``on=`` kwargs (rough)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if attr not in {"merge", "join"}:
            continue
        on = None
        for kw in node.keywords:
            if kw.arg == "on" or kw.arg == "left_on" or kw.arg == "right_on":
                v = _literal_str(kw.value) if isinstance(kw.value, ast.Constant) else None
                if v and (kw.arg == "on" or kw.arg == "left_on"):
                    on = v
                    break
        if not on or not node.args:
            continue
        other = node.args[0]
        if isinstance(other, ast.Name):
            edge = _resolve_chain(other.id, top_assigns, set())
            base = edge[0] if edge else other.id
            for e in (edge or [other.id]):
                out["column_edges"].append(
                    {"from": f"{base}.{on}", "to": f"{other.id}.{on}"}
                )

    out["reads"] = reads
    out["writes"] = writes
    out["derives"] = list(set(derives))
    out["ok"] = True
    out["message"] = (
        f"parsed {len(reads)} read(s), {len(writes)} write(s), "
        f"{len(derives)} derive(s)"
    )
    return out


def _enclosing_assign_target(node: ast.AST, tree: ast.AST) -> Optional[str]:
    """Find the name on the LHS of the assignment that contains *node*."""
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.Assign):
            continue
        for child in ast.walk(parent):
            if child is node:
                for tgt in parent.targets:
                    if isinstance(tgt, ast.Name):
                        return tgt.id
    return None


def _resolve_chain(
    var: Any, assigns: Dict[str, ast.AST], seen: set
) -> List[str]:
    """Resolve a variable back to its base file reads (BFS through assigns).

    ``var`` may be either a string (variable name) or an :class:`ast.Name`
    node — we coerce to a string id first.
    """
    # Coerce Name → id; skip other AST nodes (they're not a path we can use)
    if isinstance(var, ast.Name):
        key = var.id
    elif isinstance(var, ast.Constant) and isinstance(var.value, str):
        return [var.value]
    elif isinstance(var, ast.Str):  # py<3.8
        return [var.s]
    elif isinstance(var, str):
        key = var
    else:
        return []
    if key in seen or not assigns:
        return []
    seen.add(key)
    if key not in assigns:
        return [key]
    val = assigns[key]
    if isinstance(val, ast.Call):
        attr = val.func.attr if isinstance(val.func, ast.Attribute) else None
        if attr in _AST_READ_FUNCS and val.args:
            a0 = val.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                return [a0.value]
            if isinstance(a0, ast.Str):
                return [a0.s]
        if attr in {"merge", "join"} and val.args:
            a0 = val.args[0]
            # Both LHS (caller of merge) and RHS (arg) are sources
            sources: List[Any] = []
            if isinstance(val.func, ast.Attribute) and isinstance(
                val.func.value, ast.Name
            ):
                sources.append(val.func.value)
            if isinstance(a0, ast.Name):
                sources.append(a0)
            out_paths: List[str] = []
            for s in sources:
                out_paths.extend(_resolve_chain(s, assigns, seen))
            return out_paths
    return [key]


# ═════════════════════════════════════════════════════════════════════════════
# Operator hook
# ═════════════════════════════════════════════════════════════════════════════
def record_operator(
    operator_id: str,
    inputs: Sequence[str],
    outputs: Sequence[str],
    *,
    edge_type: str = "cleaned_by",
    pipeline_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> LineageCollectResult:
    """Record the input → output mapping of a cleaning/scoring/... op.

    Default ``edge_type='cleaned_by'``; pass ``'scored_by'`` for scoring,
    ``'trained_by'`` for model training, etc.

    Each (input, output) pair becomes one edge; the operator itself is
    *not* a node in the graph (the edge type encodes the relationship).
    """
    close_db = False
    if db is None:
        db = get_lineage_session()
        close_db = True
    added = 0
    skipped = 0
    edges_out: List[Dict[str, Any]] = []
    assets_added = 0
    try:
        for inp in inputs or []:
            in_t, in_n = _split_qualified_name(inp)
            _, was_new = _ensure_asset(db, inp, entity_type=in_t, name=in_n)
            if was_new:
                assets_added += 1
        for outp in outputs or []:
            out_t, out_n = _split_qualified_name(outp)
            _, was_new = _ensure_asset(db, outp, entity_type=out_t, name=out_n)
            if was_new:
                assets_added += 1
        for inp in inputs or []:
            in_t, _ = _split_qualified_name(inp)
            for outp in outputs or []:
                out_t, _ = _split_qualified_name(outp)
                edge, created = _upsert_edge(
                    db,
                    from_entity=inp,
                    from_type=in_t,
                    to_entity=outp,
                    to_type=out_t,
                    edge_type=edge_type,
                    pipeline_id=pipeline_id,
                    source="operator",
                    extra={"operator_id": operator_id, **(extra or {})},
                )
                if created:
                    added += 1
                    edges_out.append(_edge_to_public(edge))
                else:
                    skipped += 1
        run = RunORM(
            id=_new_id(),
            source="operator",
            pipeline_id=pipeline_id or "",
            operator_id=operator_id or "",
            inputs_json=_dumps(list(inputs or [])),
            outputs_json=_dumps(list(outputs or [])),
            edges_added=str(added),
            ok="true",
            message=f"operator={operator_id} edge_type={edge_type}",
            created_at=_now(),
        )
        db.add(run)
        db.commit()
        return LineageCollectResult(
            ok=True,
            source="operator",
            edges_added=added,
            edges_skipped=skipped,
            assets_added=assets_added,
            run_id=run.id,
            message=f"recorded {added} edge(s) for op={operator_id}",
            edges=edges_out,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("record_operator failed")
        try:
            db.rollback()
        except Exception:
            pass
        return LineageCollectResult(
            ok=False,
            source="operator",
            edges_added=added,
            edges_skipped=skipped,
            assets_added=assets_added,
            message=f"operator_record_failed: {exc}",
        )
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
# Manual entry
# ═════════════════════════════════════════════════════════════════════════════
def record_manual(
    from_entity: str,
    to_entity: str,
    edge_type: str = "manual",
    *,
    pipeline_id: str = "",
    note: str = "",
    db: Optional[Session] = None,
) -> LineageCollectResult:
    """Record a single user-declared edge."""
    close_db = False
    if db is None:
        db = get_lineage_session()
        close_db = True
    try:
        from_t, from_n = _split_qualified_name(from_entity)
        to_t, to_n = _split_qualified_name(to_entity)
        _, a1 = _ensure_asset(db, from_entity, entity_type=from_t, name=from_n)
        _, a2 = _ensure_asset(db, to_entity, entity_type=to_t, name=to_n)
        edge, created = _upsert_edge(
            db,
            from_entity=from_entity,
            from_type=from_t,
            to_entity=to_entity,
            to_type=to_t,
            edge_type=edge_type,
            pipeline_id=pipeline_id,
            source="manual",
            extra={"note": note} if note else {},
        )
        run = RunORM(
            id=_new_id(),
            source="manual",
            pipeline_id=pipeline_id or "",
            operator_id="",
            inputs_json=_dumps([from_entity]),
            outputs_json=_dumps([to_entity]),
            edges_added="1" if created else "0",
            ok="true",
            message=note or f"manual edge {from_entity} → {to_entity}",
            created_at=_now(),
        )
        db.add(run)
        db.commit()
        return LineageCollectResult(
            ok=True,
            source="manual",
            edges_added=1 if created else 0,
            edges_skipped=0 if created else 1,
            assets_added=int(a1) + int(a2),
            run_id=run.id,
            message="ok" if created else "duplicate",
            edges=[_edge_to_public(edge)] if created else [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("record_manual failed")
        try:
            db.rollback()
        except Exception:
            pass
        return LineageCollectResult(
            ok=False,
            source="manual",
            message=f"manual_failed: {exc}",
        )
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
# SQL collect (one-shot)
# ═════════════════════════════════════════════════════════════════════════════
def collect_from_sql(
    sql: str,
    *,
    target_entity: Optional[str] = None,
    pipeline_id: str = "",
    db: Optional[Session] = None,
) -> LineageCollectResult:
    """Parse SQL and persist one edge per source → target pair."""
    close_db = False
    if db is None:
        db = get_lineage_session()
        close_db = True
    parsed = parse_sql_lineage(sql, target_entity=target_entity, pipeline_id=pipeline_id)
    if not parsed.get("ok"):
        return LineageCollectResult(
            ok=False,
            source="sql",
            message=parsed.get("message", "parse_failed"),
        )
    srcs = parsed["source_tables"]
    target = parsed.get("target_table") or target_entity
    if not target:
        target = "public.derived"
    assets_added = 0
    added = 0
    skipped = 0
    edges_out: List[Dict[str, Any]] = []
    try:
        for s in srcs:
            _, was_new = _ensure_asset(db, s)
            if was_new:
                assets_added += 1
        _, was_new = _ensure_asset(db, target)
        if was_new:
            assets_added += 1
        for s in srcs:
            in_t, _ = _split_qualified_name(s)
            out_t, _ = _split_qualified_name(target)
            edge, created = _upsert_edge(
                db,
                from_entity=s,
                from_type=in_t,
                to_entity=target,
                to_type=out_t,
                edge_type="derived_from",
                pipeline_id=pipeline_id,
                sql=sql,
                source="sql",
                columns=parsed.get("column_edges", []),
            )
            if created:
                added += 1
                edges_out.append(_edge_to_public(edge))
            else:
                skipped += 1
        run = RunORM(
            id=_new_id(),
            source="sql",
            pipeline_id=pipeline_id or "",
            operator_id="",
            inputs_json=_dumps(srcs),
            outputs_json=_dumps([target]),
            edges_added=str(added),
            ok="true",
            message=parsed.get("message", ""),
            created_at=_now(),
        )
        db.add(run)
        db.commit()
        return LineageCollectResult(
            ok=True,
            source="sql",
            edges_added=added,
            edges_skipped=skipped,
            assets_added=assets_added,
            run_id=run.id,
            message=parsed.get("message", ""),
            edges=edges_out,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_from_sql failed")
        try:
            db.rollback()
        except Exception:
            pass
        return LineageCollectResult(
            ok=False,
            source="sql",
            message=f"sql_collect_failed: {exc}",
        )
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
# Python AST collect
# ═════════════════════════════════════════════════════════════════════════════
def collect_from_python(
    script: str,
    *,
    target_entity: Optional[str] = None,
    pipeline_id: str = "",
    db: Optional[Session] = None,
) -> LineageCollectResult:
    close_db = False
    if db is None:
        db = get_lineage_session()
        close_db = True
    parsed = parse_python_lineage(script, target_entity=target_entity)
    if not parsed.get("ok"):
        return LineageCollectResult(
            ok=False,
            source="ast",
            message=parsed.get("message", "parse_failed"),
        )
    reads = parsed["reads"]
    writes = parsed["writes"] or ([target_entity] if target_entity else [])
    if not writes:
        return LineageCollectResult(
            ok=False,
            source="ast",
            message="no write/target detected; pass target_entity",
        )
    assets_added = 0
    added = 0
    skipped = 0
    edges_out: List[Dict[str, Any]] = []
    try:
        for r in reads:
            _, was_new = _ensure_asset(db, r, entity_type="dataset", name=r.split("/")[-1])
            if was_new:
                assets_added += 1
        for w in writes:
            _, was_new = _ensure_asset(db, w, entity_type="dataset", name=w.split("/")[-1])
            if was_new:
                assets_added += 1
        for r in reads:
            r_t, _ = _split_qualified_name(r)
            for w in writes:
                w_t, _ = _split_qualified_name(w)
                edge, created = _upsert_edge(
                    db,
                    from_entity=r,
                    from_type="dataset" if not r_t or r_t == "table" else r_t,
                    to_entity=w,
                    to_type="dataset",
                    edge_type="derived_from",
                    pipeline_id=pipeline_id,
                    script=script,
                    source="ast",
                    columns=parsed.get("column_edges", []),
                )
                if created:
                    added += 1
                    edges_out.append(_edge_to_public(edge))
                else:
                    skipped += 1
        run = RunORM(
            id=_new_id(),
            source="ast",
            pipeline_id=pipeline_id or "",
            operator_id="",
            inputs_json=_dumps(reads),
            outputs_json=_dumps(writes),
            edges_added=str(added),
            ok="true",
            message=parsed.get("message", ""),
            created_at=_now(),
        )
        db.add(run)
        db.commit()
        return LineageCollectResult(
            ok=True,
            source="ast",
            edges_added=added,
            edges_skipped=skipped,
            assets_added=assets_added,
            run_id=run.id,
            message=parsed.get("message", ""),
            edges=edges_out,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_from_python failed")
        try:
            db.rollback()
        except Exception:
            pass
        return LineageCollectResult(
            ok=False,
            source="ast",
            message=f"ast_collect_failed: {exc}",
        )
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════
def _edge_to_public(edge: EdgeORM) -> Dict[str, Any]:
    return {
        "id": edge.id,
        "from_entity": edge.from_entity,
        "from_type": edge.from_type,
        "to_entity": edge.to_entity,
        "to_type": edge.to_type,
        "edge_type": edge.edge_type,
        "pipeline_id": edge.pipeline_id,
        "source": edge.source,
        "columns": _loads(edge.columns_json, []),
        "created_at": edge.created_at,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline run hook (called by P3-6 template runtime)
# ═════════════════════════════════════════════════════════════════════════════
def record_pipeline_step(
    pipeline_id: str,
    step_index: int,
    inputs: Sequence[str],
    outputs: Sequence[str],
    *,
    operator_id: str = "",
    edge_type: str = "generated_by",
    db: Optional[Session] = None,
) -> LineageCollectResult:
    """Record one step in a P3-6 template / pipeline run."""
    close_db = False
    if db is None:
        db = get_lineage_session()
        close_db = True
    try:
        if operator_id:
            res = record_operator(
                operator_id=operator_id,
                inputs=inputs,
                outputs=outputs,
                edge_type=edge_type,
                pipeline_id=f"{pipeline_id}:{step_index}",
                db=db,
            )
        else:
            assets_added = 0
            added = 0
            edges_out: List[Dict[str, Any]] = []
            for x in list(inputs or []) + list(outputs or []):
                _, was_new = _ensure_asset(db, x)
                if was_new:
                    assets_added += 1
            for i in inputs or []:
                for o in outputs or []:
                    in_t, _ = _split_qualified_name(i)
                    out_t, _ = _split_qualified_name(o)
                    edge, created = _upsert_edge(
                        db,
                        from_entity=i,
                        from_type=in_t,
                        to_entity=o,
                        to_type=out_t,
                        edge_type=edge_type,
                        pipeline_id=f"{pipeline_id}:{step_index}",
                        source="manual",
                    )
                    if created:
                        added += 1
                        edges_out.append(_edge_to_public(edge))
            run = RunORM(
                id=_new_id(),
                source="manual",
                pipeline_id=f"{pipeline_id}:{step_index}",
                operator_id=operator_id or "",
                inputs_json=_dumps(list(inputs or [])),
                outputs_json=_dumps(list(outputs or [])),
                edges_added=str(added),
                ok="true",
                message=f"pipeline step {step_index}",
                created_at=_now(),
            )
            db.add(run)
            db.commit()
            res = LineageCollectResult(
                ok=True,
                source="manual",
                edges_added=added,
                assets_added=assets_added,
                run_id=run.id,
                message=f"pipeline step {step_index}",
                edges=edges_out,
            )
        return res
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:
            pass
        return LineageCollectResult(
            ok=False, source="manual", message=f"pipeline_step_failed: {exc}"
        )
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


__all__ = [
    "LineageCollectResult",
    "parse_sql_lineage",
    "parse_python_lineage",
    "collect_from_sql",
    "collect_from_python",
    "record_operator",
    "record_manual",
    "record_pipeline_step",
    "_ensure_asset",
    "_upsert_edge",
    "_split_qualified_name",
]
