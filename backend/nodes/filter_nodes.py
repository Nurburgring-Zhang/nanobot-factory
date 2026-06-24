"""
过滤节点 — 封装 operators_lib 中的 filter 算子为 Node。

每个节点包装对应的 core.operators_lib 类，将 process() 调用转为
async execute()。
"""
import logging
from typing import Any, Dict, List

from .base import BaseNode, NodeDefinition, NodePort, NodeParam
from .registry import registry

logger = logging.getLogger(__name__)


# =============================================================================
# Filter: Blur
# =============================================================================

class FilterBlurNode(BaseNode):
    definition = NodeDefinition(
        node_id="filter.blur",
        name="模糊检测过滤",
        category="filter",
        description="检测并过滤模糊图片",
        inputs=[NodePort(name="images", type="image[]")],
        outputs=[
            NodePort(name="filtered_images", type="image[]"),
            NodePort(name="blur_scores", type="metadata"),
        ],
        params=[NodeParam(name="threshold", type="float", default=0.5, min=0, max=1)],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import FilterBlur
            op = FilterBlur()
            result = op.process(inputs.get("images", []), params)
            return {
                "filtered_images": result.data if result.success else [],
                "blur_scores": result.metrics if result.success else {},
            }
        except Exception as e:
            logger.error(f"FilterBlurNode failed: {e}")
            return {"filtered_images": [], "blur_scores": {}}


class FilterResolutionNode(BaseNode):
    definition = NodeDefinition(
        node_id="filter.resolution",
        name="分辨率过滤",
        category="filter",
        description="按分辨率过滤图片",
        inputs=[NodePort(name="images", type="image[]")],
        outputs=[NodePort(name="filtered_images", type="image[]")],
        params=[
            NodeParam(name="min", type="int", default=512, min=0),
            NodeParam(name="max", type="int", default=4096, min=0),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import FilterResolution
            op = FilterResolution()
            result = op.process(inputs.get("images", []), params)
            return {"filtered_images": result.data if result.success else []}
        except Exception as e:
            logger.error(f"FilterResolutionNode failed: {e}")
            return {"filtered_images": []}


class FilterDedupMD5Node(BaseNode):
    definition = NodeDefinition(
        node_id="filter.dedup.md5",
        name="MD5精确去重",
        category="filter",
        description="基于MD5哈希的精确去重",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[NodePort(name="deduped", type="any")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import FilterDedupMD5
            op = FilterDedupMD5()
            result = op.process(inputs.get("items", []), params)
            return {"deduped": result.data if result.success else []}
        except Exception as e:
            logger.error(f"FilterDedupMD5Node failed: {e}")
            return {"deduped": []}


class FilterDedupPhashNode(BaseNode):
    definition = NodeDefinition(
        node_id="filter.dedup.phash",
        name="感知哈希去重",
        category="filter",
        description="基于感知哈希（pHash）的相似去重",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[NodePort(name="deduped", type="any")],
        params=[NodeParam(name="threshold", type="float", default=0.95, min=0, max=1)],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import FilterDedupPhash
            op = FilterDedupPhash()
            result = op.process(inputs.get("items", []), params)
            return {"deduped": result.data if result.success else []}
        except Exception as e:
            logger.error(f"FilterDedupPhashNode failed: {e}")
            return {"deduped": []}


class FilterNSFWNode(BaseNode):
    definition = NodeDefinition(
        node_id="filter.nsfw",
        name="NSFW过滤",
        category="filter",
        description="检测并过滤NSFW内容",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[NodePort(name="filtered", type="any")],
        params=[NodeParam(name="threshold", type="float", default=0.8, min=0, max=1)],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import FilterNSFW
            op = FilterNSFW()
            result = op.process(inputs.get("items", []), params)
            return {"filtered": result.data if result.success else []}
        except Exception as e:
            logger.error(f"FilterNSFWNode failed: {e}")
            return {"filtered": []}


class FilterNoiseNode(BaseNode):
    definition = NodeDefinition(
        node_id="filter.noise",
        name="噪声检测过滤",
        category="filter",
        description="检测并过滤高噪声图片",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[NodePort(name="filtered", type="any")],
        params=[NodeParam(name="threshold", type="float", default=0.05, min=0, max=1)],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.operators_lib import FilterNoise
            op = FilterNoise()
            result = op.process(inputs.get("items", []), params)
            return {"filtered": result.data if result.success else []}
        except Exception as e:
            logger.error(f"FilterNoiseNode failed: {e}")
            return {"filtered": []}


# ---- 注册 ----
registry.register(FilterBlurNode)
registry.register(FilterResolutionNode)
registry.register(FilterDedupMD5Node)
registry.register(FilterDedupPhashNode)
registry.register(FilterNSFWNode)
registry.register(FilterNoiseNode)
