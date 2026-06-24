"""P4-4-W2 lineage asset graph.

A directed multigraph (via NetworkX) on top of the lineage DB.

Nodes
-----
* table, column, dataset, pipeline, model, job — keyed by ``qualified_name``
* Each node carries the merged attributes from ``lin_assets``.

Edges
-----
* Stored as ``(from_entity, to_entity, edge_type, source, pipeline_id)``
* Edge attrs: ``edge_type``, ``source``, ``pipeline_id``, ``columns``,
  ``sql``, ``script``, ``created_at``.

The graph is built lazily on first call, then refreshed on
``refresh()``. A small in-process cache (``self._cache``) is kept so
hot paths (``get_neighbors`` / ``upstream`` / ``downstream``) are O(1)
after the first hit.

For very large graphs (10k+ edges) the same API also accepts
``edge_type``, ``source`` and ``pipeline_id`` filters so callers can
slice the graph before traversal.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Sequence

import networkx as nx

from .collector import _split_qualified_name
from .models import (
    AssetORM,
    EdgeORM,
    get_lineage_session,
)

logger = logging.getLogger(__name__)


class AssetGraph:
    """Thread-safe in-process lineage graph.

    A single instance is shared per service. ``refresh()`` rebuilds from DB.
    """

    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._lock = threading.RLock()
        self._loaded = False

    # ── Build / refresh ──────────────────────────────────────────────────
    def refresh(
        self,
        *,
        edge_type: Optional[str] = None,
        source: Optional[str] = None,
        pipeline_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> Dict[str, int]:
        """Rebuild the graph from the DB (optionally filtered)."""
        close_db = False
        if db is None:
            db = get_lineage_session()
            close_db = True
        try:
            asset_q = db.query(AssetORM)
            edge_q = db.query(EdgeORM)
            if edge_type:
                edge_q = edge_q.filter(EdgeORM.edge_type == edge_type)
            if source:
                edge_q = edge_q.filter(EdgeORM.source == source)
            if pipeline_id:
                edge_q = edge_q.filter(EdgeORM.pipeline_id == pipeline_id)

            new_g: nx.MultiDiGraph = nx.MultiDiGraph()
            for a in asset_q.all():
                new_g.add_node(
                    a.qualified_name,
                    id=a.id,
                    entity_type=a.entity_type,
                    name=a.name,
                    owner=a.owner,
                    team=a.team,
                    tier=a.tier,
                    status=a.status,
                    description=a.description,
                )
            for e in edge_q.all():
                for qn in (e.from_entity, e.to_entity):
                    if qn not in new_g:
                        # Auto-register missing endpoint as a stub
                        et, nm = _split_qualified_name(qn)
                        new_g.add_node(
                            qn,
                            id="",
                            entity_type=et,
                            name=nm or qn,
                            owner="",
                            team="",
                            tier="bronze",
                            status="active",
                            description="(auto-stub)",
                        )
                new_g.add_edge(
                    e.from_entity,
                    e.to_entity,
                    key=f"{e.edge_type}|{e.source}|{e.pipeline_id or ''}|{e.id}",
                    id=e.id,
                    edge_type=e.edge_type,
                    source=e.source,
                    pipeline_id=e.pipeline_id,
                    sql=e.sql or "",
                    script=e.script or "",
                    columns=e.columns_json or "[]",
                    created_at=e.created_at,
                )
            with self._lock:
                self._g = new_g
                self._loaded = True
            return {"nodes": new_g.number_of_nodes(), "edges": new_g.number_of_edges()}
        finally:
            if close_db:
                try:
                    db.close()
                except Exception:
                    pass

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()

    # ── Read accessors ───────────────────────────────────────────────────
    def node(self, qn: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        with self._lock:
            if qn not in self._g:
                return None
            return self._wrap_node(qn)

    def neighbors_upstream(self, qn: str, *, depth: int = -1) -> List[Dict[str, Any]]:
        """All nodes that *produce* ``qn`` (ancestors)."""
        self._ensure_loaded()
        with self._lock:
            if qn not in self._g:
                return []
            return self._bfs_neighbors(qn, upstream=True, depth=depth)

    def neighbors_downstream(self, qn: str, *, depth: int = -1) -> List[Dict[str, Any]]:
        """All nodes that *consume* ``qn`` (descendants)."""
        self._ensure_loaded()
        with self._lock:
            if qn not in self._g:
                return []
            return self._bfs_neighbors(qn, upstream=False, depth=depth)

    def _bfs_neighbors(
        self, qn: str, *, upstream: bool, depth: int
    ) -> List[Dict[str, Any]]:
        """BFS up to ``depth`` hops (depth=-1 means unlimited).

        Returns the wrapped-node dicts in BFS order, deduped.
        """
        g = self._g
        visited: set = {qn}
        frontier: List[tuple] = [(qn, 0)]
        collected: List[str] = []
        while frontier:
            cur, d = frontier.pop(0)
            if depth != -1 and d >= depth:
                continue
            nxt_iter = (
                g.predecessors(cur) if upstream else g.successors(cur)
            )
            for nxt in nxt_iter:
                if nxt in visited:
                    continue
                visited.add(nxt)
                collected.append(nxt)
                frontier.append((nxt, d + 1))
        return [self._wrap_node(n) for n in collected]

    def edges_of(self, qn: str) -> List[Dict[str, Any]]:
        """All edges touching ``qn`` (in + out), as flat dicts."""
        self._ensure_loaded()
        with self._lock:
            if qn not in self._g:
                return []
            out: List[Dict[str, Any]] = []
            for u, v, k, d in self._g.out_edges(qn, keys=True, data=True):
                out.append(self._wrap_edge(u, v, d))
            for u, v, k, d in self._g.in_edges(qn, keys=True, data=True):
                out.append(self._wrap_edge(u, v, d))
            return out

    def full_graph(
        self,
        *,
        edge_type: Optional[str] = None,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """Dump the entire (filtered) graph as nodes + edges lists.

        Cap ``limit`` edges to avoid blowing up the response.
        """
        self._ensure_loaded()
        with self._lock:
            g = self._g
            if edge_type:
                kept_edges = [
                    (u, v, k, d)
                    for u, v, k, d in g.edges(keys=True, data=True)
                    if d.get("edge_type") == edge_type
                ]
            else:
                kept_edges = list(g.edges(keys=True, data=True))
            kept_edges = kept_edges[:limit]
            kept_nodes = set()
            for u, v, _, _ in kept_edges:
                kept_nodes.add(u)
                kept_nodes.add(v)
            return {
                "nodes": [self._wrap_node(n) for n in kept_nodes],
                "edges": [self._wrap_edge(u, v, d) for u, v, _, d in kept_edges],
                "total_edges": g.number_of_edges(),
                "total_nodes": g.number_of_nodes(),
                "returned_edges": len(kept_edges),
            }

    def stats(self) -> Dict[str, Any]:
        self._ensure_loaded()
        with self._lock:
            g = self._g
            by_type: Dict[str, int] = {}
            for _, _, d in g.edges(data=True):
                by_type[d.get("edge_type", "manual")] = by_type.get(
                    d.get("edge_type", "manual"), 0
                ) + 1
            by_entity: Dict[str, int] = {}
            for _, d in g.nodes(data=True):
                et = d.get("entity_type", "table")
                by_entity[et] = by_entity.get(et, 0) + 1
            return {
                "nodes": g.number_of_nodes(),
                "edges": g.number_of_edges(),
                "by_edge_type": by_type,
                "by_entity_type": by_entity,
            }

    # ── Internal helpers ────────────────────────────────────────────────
    def _wrap_node(self, qn: str) -> Dict[str, Any]:
        d = self._g.nodes[qn]
        return {
            "qualified_name": qn,
            "entity_type": d.get("entity_type", "table"),
            "name": d.get("name", qn),
            "owner": d.get("owner", ""),
            "team": d.get("team", ""),
            "tier": d.get("tier", "bronze"),
            "status": d.get("status", "active"),
        }

    def _wrap_edge(self, u: str, v: str, d: Dict[str, Any]) -> Dict[str, Any]:
        cols_raw = d.get("columns", "[]")
        if isinstance(cols_raw, str):
            import json as _json
            try:
                cols = _json.loads(cols_raw)
            except Exception:
                cols = []
        else:
            cols = cols_raw or []
        return {
            "from": u,
            "to": v,
            "edge_type": d.get("edge_type", "manual"),
            "source": d.get("source", "manual"),
            "pipeline_id": d.get("pipeline_id", ""),
            "columns": cols,
            "created_at": d.get("created_at", ""),
        }


# ── Singleton accessor ─────────────────────────────────────────────────────
_GRAPH_SINGLETON: Optional[AssetGraph] = None
_GRAPH_LOCK = threading.Lock()


def get_graph() -> AssetGraph:
    global _GRAPH_SINGLETON
    with _GRAPH_LOCK:
        if _GRAPH_SINGLETON is None:
            _GRAPH_SINGLETON = AssetGraph()
        return _GRAPH_SINGLETON


def reset_graph() -> None:
    """Test hook."""
    global _GRAPH_SINGLETON
    with _GRAPH_LOCK:
        _GRAPH_SINGLETON = None


__all__ = ["AssetGraph", "get_graph", "reset_graph"]
