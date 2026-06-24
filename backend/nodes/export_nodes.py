"""
导出节点 — 封装 operators_lib 的 export 算子为 Node。
"""
import logging
from typing import Any, Dict

from .base import BaseNode, NodeDefinition, NodePort, NodeParam
from .registry import registry

logger = logging.getLogger(__name__)


class ExportJSONLNode(BaseNode):
    definition = NodeDefinition(
        node_id="export.jsonl",
        name="导出JSONL",
        category="export",
        description="将数据导出为 JSONL 格式文件",
        inputs=[NodePort(name="data", type="any", required=True)],
        outputs=[NodePort(name="path", type="text")],
        params=[NodeParam(name="output_path", type="string", default="/tmp/export.jsonl")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import ExportJSONL
            op = ExportJSONL()
            result = op.process(inputs.get("data", []), params)
            return {"path": result.data if result.success else ""}
        except Exception as e:
            logger.error(f"ExportJSONLNode failed: {e}")
            return {"path": ""}


class ExportCSVNode(BaseNode):
    definition = NodeDefinition(
        node_id="export.csv",
        name="导出CSV",
        category="export",
        description="将数据导出为 CSV 格式文件",
        inputs=[NodePort(name="data", type="any", required=True)],
        outputs=[NodePort(name="path", type="text")],
        params=[NodeParam(name="output_path", type="string", default="/tmp/export.csv")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import ExportCSV
            op = ExportCSV()
            result = op.process(inputs.get("data", []), params)
            return {"path": result.data if result.success else ""}
        except Exception as e:
            logger.error(f"ExportCSVNode failed: {e}")
            return {"path": ""}


class ExportParquetNode(BaseNode):
    definition = NodeDefinition(
        node_id="export.parquet",
        name="导出Parquet",
        category="export",
        description="将数据导出为 Parquet 格式文件",
        inputs=[NodePort(name="data", type="any", required=True)],
        outputs=[NodePort(name="path", type="text")],
        params=[NodeParam(name="output_path", type="string", default="/tmp/export.parquet")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import ExportParquet
            op = ExportParquet()
            result = op.process(inputs.get("data", []), params)
            return {"path": result.data if result.success else ""}
        except Exception as e:
            logger.error(f"ExportParquetNode failed: {e}")
            return {"path": ""}


class ExportLLaVANode(BaseNode):
    definition = NodeDefinition(
        node_id="export.llava",
        name="导出LLaVA格式",
        category="export",
        description="将数据导出为 LLaVA 微调格式",
        inputs=[NodePort(name="data", type="any", required=True)],
        outputs=[NodePort(name="path", type="text")],
        params=[NodeParam(name="output_path", type="string", default="/tmp/llava.json")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import ExportLLaVA
            op = ExportLLaVA()
            result = op.process(inputs.get("data", []), params)
            return {"path": result.data if result.success else ""}
        except Exception as e:
            logger.error(f"ExportLLaVANode failed: {e}")
            return {"path": ""}


class ExportCOCONode(BaseNode):
    definition = NodeDefinition(
        node_id="export.coco",
        name="导出COCO格式",
        category="export",
        description="将数据导出为 COCO 标注格式",
        inputs=[NodePort(name="data", type="any", required=True)],
        outputs=[NodePort(name="path", type="text")],
        params=[NodeParam(name="output_path", type="string", default="/tmp/coco.json")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import ExportCOCO
            op = ExportCOCO()
            result = op.process(inputs.get("data", []), params)
            return {"path": result.data if result.success else ""}
        except Exception as e:
            logger.error(f"ExportCOCONode failed: {e}")
            return {"path": ""}


class ExportLocalNode(BaseNode):
    definition = NodeDefinition(
        node_id="export.local",
        name="导出到本地",
        category="export",
        description="将数据文件复制到本地目录",
        inputs=[NodePort(name="data", type="any", required=True)],
        outputs=[NodePort(name="path", type="text")],
        params=[NodeParam(name="target_dir", type="string", default="/tmp/export")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import ExportLocal
            op = ExportLocal()
            result = op.process(inputs.get("data", []), params)
            return {"path": result.data if result.success else ""}
        except Exception as e:
            logger.error(f"ExportLocalNode failed: {e}")
            return {"path": ""}


# ---- 注册 ----
registry.register(ExportJSONLNode)
registry.register(ExportCSVNode)
registry.register(ExportParquetNode)
registry.register(ExportLLaVANode)
registry.register(ExportCOCONode)
registry.register(ExportLocalNode)
