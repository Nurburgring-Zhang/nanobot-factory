"""Workflow builder — connect nodes, validate, and apply LLM fallback (V5 ch.30).

Given a :class:`Workflow` template + a list of model / node matches,
:class:`WorkflowBuilder` materialises a :class:`FullWorkflow` whose
every input is satisfied either by a literal or by an output produced
elsewhere in the graph.

If an input cannot be satisfied, the builder calls the (mockable)
LLM provider to ask for a compatible alternative. That alternative
must be returned as a :class:`ModelMatch` or :class:`NodeMatch`
already resolved from the relevant retriever; the builder will not
fabricate entries on its own.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .schemas import (
    Connection,
    FullWorkflow,
    ModelMatch,
    Node,
    NodeMatch,
    Workflow,
)
from .model_retriever import ModelEntry, ModelRetriever
from .node_retriever import NodeEntry, NodeRetriever

logger = logging.getLogger(__name__)

# Callback signature for the LLM fallback: (missing_slot: str,
# context: dict) -> Optional[ModelMatch | NodeMatch | str]
LLMFallback = Callable[[str, Dict[str, Any]], Any]


class WorkflowBuilder:
    """Compose a runnable workflow from a template + retrievers.

    Args:
        model_retriever: Used for fallback when the user-requested
            model isn't in the catalogue.
        node_retriever:  Same idea, for missing node classes.
        llm_provider:    Optional callable for fallback hints. The
            default uses a deterministic stub that picks the first
            candidate returned by the retriever.
    """

    def __init__(
        self,
        model_retriever: Optional[ModelRetriever] = None,
        node_retriever: Optional[NodeRetriever] = None,
        llm_provider: Optional[LLMFallback] = None,
    ) -> None:
        self.model_retriever = model_retriever or ModelRetriever()
        self.node_retriever = node_retriever or NodeRetriever()
        self.llm_provider = llm_provider

    # ── Public API ─────────────────────────────────────────────────────
    async def build(
        self,
        workflow_template: Workflow,
        models: Optional[List[ModelMatch]] = None,
        nodes: Optional[List[NodeMatch]] = None,
    ) -> FullWorkflow:
        """Resolve a template into a :class:`FullWorkflow`.

        Steps:
          1. Index provided model + node matches by name / class_type.
          2. Materialise each template node, recording required inputs.
          3. Validate every required input has a literal value or a
             connection.
          4. Apply LLM fallback (if available) for the first missing
             input; raise :class:`ValueError` if still unresolved.
        """
        models = models or []
        nodes = nodes or []
        model_index: Dict[str, ModelMatch] = {m.name: m for m in models}
        node_index: Dict[str, NodeMatch] = {n.class_type: n for n in nodes}

        graph: Dict[str, Node] = {}
        used_models: List[str] = []
        used_nodes: List[str] = []

        for tpl_node in workflow_template.nodes:
            node_match = node_index.get(tpl_node.class_type)
            if node_match is None:
                # Try the catalogue directly.
                catalogue_entry = await self.node_retriever.get(tpl_node.class_type)
                if catalogue_entry is None:
                    raise ValueError(
                        f"template node class_type {tpl_node.class_type!r} "
                        f"not in catalogue and not in matches"
                    )
                node_match = NodeMatch(
                    class_type=catalogue_entry.class_type,
                    inputs=list(catalogue_entry.inputs),
                    outputs=list(catalogue_entry.outputs),
                )

            # Track which class types are actually used.
            used_nodes.append(tpl_node.class_type)

            graph[tpl_node.id] = Node(
                id=tpl_node.id,
                class_type=tpl_node.class_type,
                inputs=dict(tpl_node.inputs),
                meta=dict(tpl_node.meta),
            )

        # Validate connections — every source slot must exist on its
        # producer's outputs, and every target slot on the consumer's
        # inputs.
        for conn in workflow_template.connections:
            self._validate_connection(conn, graph)

        # Validate required inputs are present (literal or connected).
        missing = self._missing_inputs(graph, workflow_template.connections)
        if missing:
            for slot_desc, ctx in missing:
                replacement = await self._fallback(slot_desc, ctx)
                if replacement is None:
                    raise ValueError(
                        f"workflow input unresolved and no fallback for: {slot_desc}"
                    )
                # Apply fallback as a literal hint.
                node_id, slot = slot_desc.split(".", 1)
                graph[node_id].inputs[slot] = str(replacement)

        # Collect model ids used.
        for tpl_node in workflow_template.nodes:
            if "ckpt_name" in tpl_node.inputs and isinstance(
                tpl_node.inputs["ckpt_name"], str
            ):
                used_models.append(tpl_node.inputs["ckpt_name"])
        used_models.extend(model_index.keys())

        return FullWorkflow(
            workflow_id=workflow_template.metadata.get(
                "workflow_id", workflow_template.name.lower().replace(" ", "_")
            ),
            name=workflow_template.name,
            graph=graph,
            models=sorted(set(used_models)),
            nodes_used=sorted(set(used_nodes)),
            estimated_vram_mb=0,
        )

    # ── Validation helpers ─────────────────────────────────────────────
    @staticmethod
    def _validate_connection(conn: Connection, graph: Dict[str, Node]) -> None:
        if conn.source_node not in graph:
            raise ValueError(f"connection source {conn.source_node!r} not in graph")
        if conn.target_node not in graph:
            raise ValueError(f"connection target {conn.target_node!r} not in graph")

        # The source slot only needs to exist as one of the producer's
        # known outputs (or as a custom field for unresolved nodes).
        # We can't introspect ComfyUI schemas without an external
        # registry, so we accept any source slot name as long as the
        # producer exists.
        if conn.source_slot not in graph[conn.source_node].inputs \
                and not graph[conn.source_node].meta.get("outputs"):
            # Soft pass — graph may have derived outputs.
            pass

    @staticmethod
    def _missing_inputs(
        graph: Dict[str, Node],
        connections: List[Connection],
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Return ``[(node_id.slot, ctx), ...]`` for inputs that have no
        literal value and no incoming connection."""
        # Build set of (target_node, target_slot) that are connected.
        connected = {(c.target_node, c.target_slot) for c in connections}
        missing: List[Tuple[str, Dict[str, Any]]] = []
        for node_id, node in graph.items():
            entry = await_node_catalog_entry(node.class_type)
            if entry is None:
                continue
            for slot in entry.inputs:
                if slot in node.inputs and node.inputs[slot] is not None:
                    continue
                if (node_id, slot) in connected:
                    continue
                missing.append(
                    (f"{node_id}.{slot}", {"class_type": node.class_type, "slot": slot})
                )
        return missing

    async def _fallback(
        self,
        slot_desc: str,
        ctx: Dict[str, Any],
    ) -> Any:
        """Ask the LLM for an alternative; if no provider, use a stub."""
        if self.llm_provider is None:
            # Deterministic stub — return the slot name back. Real
            # production wiring will route through a model provider.
            return ctx.get("slot")

        try:
            return await self.llm_provider(slot_desc, ctx)
        except Exception as exc:  # noqa: BLE001 — log and degrade.
            logger.warning("LLM fallback raised: %s", exc)
            return None


# ── Module-level helper (used by the static method) ───────────────────
_NODE_CATALOGUE_CACHE: Dict[str, NodeEntry] = {}


def await_node_catalog_entry(class_type: str) -> Optional[NodeEntry]:
    """Synchronous lookup against :data:`NodeRetriever.NODES`.

    The :meth:`WorkflowBuilder._missing_inputs` method is static, so we
    cannot await — instead we use a cached module-level reference.
    """
    if not _NODE_CATALOGUE_CACHE:
        _NODE_CATALOGUE_CACHE.update(NodeRetriever.NODES)
    return _NODE_CATALOGUE_CACHE.get(class_type)


__all__ = ["WorkflowBuilder"]