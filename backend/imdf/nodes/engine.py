"""
IMDF DAG Engine — build, validate, and execute node workflows
==============================================================
Topological-sort based execution engine for the node-based workflow
system. Supports both sequential and parallel execution modes.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import deque

from nodes.registry import NodeRegistry, NodeDef, PortDef

logger = logging.getLogger(__name__)


# ─── Data structures ─────────────────────────────────────────────────────────

class DAGNode:
    """A node instance inside a DAG."""
    def __init__(self, node_id: str, node_type: str, data: Dict[str, Any] = None):
        self.id = node_id
        self.type = node_type
        self.data = data or {}
        self.definition: Optional[NodeDef] = NodeRegistry.get(node_type)
        self.inputs: Dict[str, Any] = {}      # port_name -> received value
        self.outputs: Dict[str, Any] = {}     # port_name -> produced value
        self.status: str = "pending"          # pending / running / completed / failed
        self.error: Optional[str] = None


class Connection:
    """A connection (edge) between two DAG nodes."""
    def __init__(self, from_id: str, from_port: str, to_id: str, to_port: str):
        self.from_id = from_id
        self.from_port = from_port
        self.to_id = to_id
        self.to_port = to_port


class DAG:
    """A directed acyclic graph of workflow nodes."""
    def __init__(self):
        self.nodes: Dict[str, DAGNode] = {}
        self.connections: List[Connection] = []
        self.topological_order: List[str] = []   # node IDs in execution order


class ExecutionContext:
    """Execution context for a workflow run."""
    def __init__(self, dag: DAG):
        self.dag = dag
        self.results: Dict[str, Dict[str, Any]] = {}  # node_id -> {port: value}
        self.global_vars: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}


# ─── DAG Engine ──────────────────────────────────────────────────────────────

class DAGEngine:
    """
    DAG Execution Engine.
    
    Builds a DAG from workflow state (nodes + connections), validates it,
    and executes nodes in topological order.
    """

    @staticmethod
    def build_dag(nodes: Dict[str, Dict], connections: List[Dict]) -> DAG:
        """
        Build a DAG from raw workflow data (as received from the frontend).
        
        Args:
            nodes: {node_id: {id, type, data, ...}, ...}
            connections: [{from, fromP, to, toP}, ...]
        
        Returns:
            DAG instance ready for validation/execution.
        """
        dag = DAG()
        
        # Create DAGNode instances
        for node_id, node_data in nodes.items():
            dag_node = DAGNode(
                node_id=node_id,
                node_type=node_data.get("type", ""),
                data=node_data.get("data", {}),
            )
            dag.nodes[node_id] = dag_node
        
        # Create Connection instances
        for conn in connections:
            c = Connection(
                from_id=str(conn.get("from", "")),
                from_port=f"out_{conn.get('fromP', 0)}",
                to_id=str(conn.get("to", "")),
                to_port=f"in_{conn.get('toP', 0)}",
            )
            dag.connections.append(c)
        
        return dag

    @staticmethod
    def validate(dag: DAG) -> Dict[str, Any]:
        """
        Validate a DAG: cycle detection + type checking + port matching.
        
        Returns:
            {"valid": bool, "errors": [str], "warnings": [str]}
        """
        errors = []
        warnings = []

        if not dag.nodes:
            return {"valid": True, "errors": [], "warnings": ["DAG is empty — no nodes"]}

        # ── 1. Build adjacency list and in-degree map ──────────────────
        adj: Dict[str, List[str]] = {nid: [] for nid in dag.nodes}
        in_degree: Dict[str, int] = {nid: 0 for nid in dag.nodes}
        edge_map: Dict[Tuple[str, str, str], str] = {}  # (from, from_port, to) -> to_port

        for conn in dag.connections:
            if conn.from_id not in dag.nodes:
                errors.append(f"Connection references unknown source node '{conn.from_id}'")
                continue
            if conn.to_id not in dag.nodes:
                errors.append(f"Connection references unknown target node '{conn.to_id}'")
                continue
            adj[conn.from_id].append(conn.to_id)
            in_degree[conn.to_id] += 1
            edge_map[(conn.from_id, conn.from_port, conn.to_id)] = conn.to_port

        # ── 2. Topological sort (Kahn's algorithm) — cycle detection ───
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        topo_order = []
        visited_count = 0

        while queue:
            nid = queue.popleft()
            topo_order.append(nid)
            visited_count += 1
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(dag.nodes):
            cycle_nodes = [nid for nid in dag.nodes if in_degree[nid] > 0]
            errors.append(f"Cycle detected involving nodes: {cycle_nodes}")
            return {"valid": False, "errors": errors, "warnings": warnings}

        dag.topological_order = topo_order

        # ── 3. Port matching / type checking ──────────────────────────
        for conn in dag.connections:
            from_node = dag.nodes.get(conn.from_id)
            to_node = dag.nodes.get(conn.to_id)
            if not from_node or not to_node:
                continue

            from_def = from_node.definition
            to_def = to_node.definition

            if from_def:
                # Check that the output port exists
                valid_out_port = any(p.name == conn.from_port for p in from_def.outputs)
                if not valid_out_port:
                    warnings.append(
                        f"Node '{from_node.id}' ({from_def.label}) has no output port '{conn.from_port}'. "
                        f"Available: {[p.name for p in from_def.outputs]}"
                    )

            if to_def:
                # Check that the input port exists
                valid_in_port = any(p.name == conn.to_port for p in to_def.inputs)
                if not valid_in_port:
                    warnings.append(
                        f"Node '{to_node.id}' ({to_def.label}) has no input port '{conn.to_port}'. "
                        f"Available: {[p.name for p in to_def.inputs]}"
                    )

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    # ── Execution ──────────────────────────────────────────────────────

    @staticmethod
    async def execute(dag: DAG, context: Optional[ExecutionContext] = None) -> ExecutionContext:
        """
        Execute a DAG in topological order. Nodes run sequentially.
        
        Data is routed between nodes via port bindings.
        
        Args:
            dag: A validated DAG.
            context: Optional existing context (creates new one if None).
        
        Returns:
            ExecutionContext with results filled in.
        """
        ctx = context or ExecutionContext(dag)

        # Run validation first if not already done
        if not dag.topological_order:
            validation = DAGEngine.validate(dag)
            if not validation["valid"]:
                raise ValueError(f"DAG validation failed: {validation['errors']}")

        # Build connection map: (to_id, to_port) -> (from_id, from_port)
        input_map: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for conn in dag.connections:
            input_map[(conn.to_id, conn.to_port)] = (conn.from_id, conn.from_port)

        for node_id in dag.topological_order:
            dag_node = dag.nodes[node_id]
            dag_node.status = "running"

            # ── Collect inputs from upstream nodes ──
            for input_port_name in [p.name for p in (dag_node.definition.inputs if dag_node.definition else [])]:
                key = (node_id, input_port_name)
                if key in input_map:
                    from_id, from_port = input_map[key]
                    upstream_node = dag.nodes.get(from_id)
                    if upstream_node and from_port in upstream_node.outputs:
                        dag_node.inputs[input_port_name] = upstream_node.outputs[from_port]

            # ── Execute the node ──
            try:
                outputs = await DAGEngine._execute_node(dag_node, ctx)
                dag_node.outputs = outputs
                dag_node.status = "completed"

                # Store in context
                ctx.results[node_id] = dict(outputs)

            except Exception as e:
                dag_node.status = "failed"
                dag_node.error = str(e)
                logger.error(f"Node '{node_id}' ({dag_node.type}) failed: {e}")
                raise

        return ctx

    @staticmethod
    async def execute_parallel(dag: DAG, context: Optional[ExecutionContext] = None) -> ExecutionContext:
        """
        Execute a DAG with parallel execution for independent branches.
        
        Uses topological layering: nodes at the same depth (same max distance
        from any root) can run concurrently if they have no interdependencies.
        
        Args:
            dag: A validated DAG.
            context: Optional existing context.
        
        Returns:
            ExecutionContext with results filled in.
        """
        ctx = context or ExecutionContext(dag)

        if not dag.topological_order:
            validation = DAGEngine.validate(dag)
            if not validation["valid"]:
                raise ValueError(f"DAG validation failed: {validation['errors']}")

        # Build reverse adjacency for layer computation
        rev_adj: Dict[str, List[str]] = {nid: [] for nid in dag.nodes}
        for conn in dag.connections:
            rev_adj[conn.to_id].append(conn.from_id)

        # Compute layer (longest path from any root)
        layer: Dict[str, int] = {}
        
        def compute_layer(nid: str) -> int:
            if nid in layer:
                return layer[nid]
            if not rev_adj[nid]:
                layer[nid] = 0
                return 0
            max_depth = 0
            for upstream in rev_adj[nid]:
                max_depth = max(max_depth, compute_layer(upstream) + 1)
            layer[nid] = max_depth
            return max_depth

        for nid in dag.nodes:
            compute_layer(nid)

        # Group nodes by layer
        max_layer = max(layer.values()) if layer else 0
        layers: List[List[str]] = [[] for _ in range(max_layer + 1)]
        for nid, l in layer.items():
            layers[l].append(nid)

        # Build input map
        input_map: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for conn in dag.connections:
            input_map[(conn.to_id, conn.to_port)] = (conn.from_id, conn.from_port)

        # Execute layer by layer, nodes within a layer in parallel
        for layer_nodes in layers:
            async def run_node(nid: str):
                dag_node = dag.nodes[nid]
                dag_node.status = "running"

                for input_port_name in [p.name for p in (dag_node.definition.inputs if dag_node.definition else [])]:
                    key = (nid, input_port_name)
                    if key in input_map:
                        from_id, from_port = input_map[key]
                        upstream_node = dag.nodes.get(from_id)
                        if upstream_node and from_port in upstream_node.outputs:
                            dag_node.inputs[input_port_name] = upstream_node.outputs[from_port]

                try:
                    outputs = await DAGEngine._execute_node(dag_node, ctx)
                    dag_node.outputs = outputs
                    dag_node.status = "completed"
                    ctx.results[nid] = dict(outputs)
                except Exception as e:
                    dag_node.status = "failed"
                    dag_node.error = str(e)
                    raise

            tasks = [run_node(nid) for nid in layer_nodes]
            if tasks:
                await asyncio.gather(*tasks)

        return ctx

    # ── Internal execution ─────────────────────────────────────────────

    @staticmethod
    async def _execute_node(node: DAGNode, ctx: ExecutionContext) -> Dict[str, Any]:
        """
        Execute a single node. This is the core execution logic.
        
        For now, provides a basic execution that:
        - For dimension nodes: passes data through
        - For capability/function nodes: runs the node's 'execute' function
          if defined in the node data, otherwise returns the data as-is.
        """
        node_type = node.type
        node_data = node.data

        # If the node has a custom 'execute' function in its data, call it
        if "execute" in node_data and callable(node_data["execute"]):
            result = node_data["execute"](node.inputs, ctx.global_vars)
            if isinstance(result, dict):
                return result
            return {"out_0": result}

        # ── Type-specific execution logic ──
        outputs = {}

        if node_type == "output":
            # Output node: collect all inputs and store
            outputs["out_0"] = dict(node.inputs)

        elif node_type == "text":
            # Text node: return content
            content = node_data.get("content", "")
            if node.inputs:
                content = str(list(node.inputs.values())[0])
            outputs["out_0"] = content

        elif node_type == "llm":
            # LLM node: combine prompts and return
            prompt = node_data.get("prompt", "")
            if "in_0" in node.inputs:
                prompt = str(node.inputs["in_0"])
            outputs["out_0"] = f"[LLM模拟] {prompt}"

        elif node_type == "image":
            src = node_data.get("src", "")
            if node.inputs:
                src = str(list(node.inputs.values())[0])
            outputs["out_0"] = {"src": src, "type": "image"}

        elif node_type == "video":
            src = node_data.get("src", "")
            if node.inputs:
                src = str(list(node.inputs.values())[0])
            outputs["out_0"] = {"src": src, "type": "video"}

        elif node_type == "script":
            code = node_data.get("code", "return input;")
            outputs["out_0"] = f"[Script executed] {code[:80]}..."

        elif node_type in ("aggregate", "combine"):
            # Combine/aggregate: merge multiple inputs
            merged = {}
            for k, v in node.inputs.items():
                if isinstance(v, dict):
                    merged.update(v)
                else:
                    merged[k] = v
            outputs["out_0"] = merged

        elif node_type == "ppt":
            title = node_data.get("title", "PPT")
            outputs["out_0"] = {"title": title, "slides": node_data.get("slides", 5), "type": "ppt"}

        elif node_type == "prelabel":
            outputs["out_0"] = {"status": "annotated", "bboxes": [], "tags": []}
            outputs["out_1"] = "Annotation complete (simulated)"

        elif node_type in ("seedance", "runninghub", "portrait", "falbox", "rhtools", "grok"):
            outputs["out_0"] = {"status": "submitted", "type": node_type}

        else:
            # Generic: pass through inputs as outputs
            if node.inputs:
                outputs["out_0"] = list(node.inputs.values())[0] if len(node.inputs) == 1 else dict(node.inputs)
            else:
                outputs["out_0"] = node_data

        return outputs
