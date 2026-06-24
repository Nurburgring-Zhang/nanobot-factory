"""数据血缘追踪——记录数据行级来源和变换"""
import uuid, logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class LineageNode:
    """血缘节点——代表一次数据变换操作"""
    def __init__(self, source_id: str, target_id: str, operation: str, 
                 params: dict = None, pipeline_id: str = ""):
        self.edge_id = f"le_{uuid.uuid4().hex[:12]}"
        self.source_id = source_id
        self.target_id = target_id
        self.operation = operation
        self.params = params or {}
        self.pipeline_id = pipeline_id
        self.created_at = datetime.now().isoformat()

class LineageManager:
    _edges: List[LineageNode] = []
    
    @classmethod
    def record(cls, source_id: str, target_id: str, operation: str,
               params: dict = None, pipeline_id: str = "") -> str:
        edge = LineageNode(source_id, target_id, operation, params, pipeline_id)
        cls._edges.append(edge)
        return edge.edge_id
    
    @classmethod
    def get_upstream(cls, target_id: str) -> List[dict]:
        """获取目标数据的所有上游来源"""
        return [{"edge_id": e.edge_id, "source_id": e.source_id, "operation": e.operation,
                 "pipeline_id": e.pipeline_id, "created_at": e.created_at}
                for e in cls._edges if e.target_id == target_id]
    
    @classmethod
    def get_downstream(cls, source_id: str) -> List[dict]:
        """获取源数据的所有下游去向"""
        return [{"edge_id": e.edge_id, "target_id": e.target_id, "operation": e.operation,
                 "pipeline_id": e.pipeline_id, "created_at": e.created_at}
                for e in cls._edges if e.source_id == source_id]
    
    @classmethod
    def get_lineage_graph(cls, asset_id: str, depth: int = 3) -> dict:
        """获取完整血缘图（上下游递归depth层）"""
        graph = {"nodes": {}, "edges": []}
        
        def traverse(current_id: str, current_depth: int, direction: str):
            if current_depth > depth:
                return
            graph["nodes"][current_id] = {"id": current_id, "depth": current_depth}
            
            if direction in ("up", "both"):
                for e in cls._edges:
                    if e.target_id == current_id:
                        graph["edges"].append({"from": e.source_id, "to": e.target_id, 
                                              "operation": e.operation})
                        traverse(e.source_id, current_depth + 1, "up")
            
            if direction in ("down", "both"):
                for e in cls._edges:
                    if e.source_id == current_id:
                        graph["edges"].append({"from": e.source_id, "to": e.target_id,
                                              "operation": e.operation})
                        traverse(e.target_id, current_depth + 1, "down")
        
        traverse(asset_id, 0, "both")
        return graph

lineage = LineageManager()
