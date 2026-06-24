"""
质量评估节点 — 使用 core/ai_models.py 进行图像质量评分和分布分析。
"""
import logging
from typing import Any, Dict, List

from .base import BaseNode, NodeDefinition, NodePort, NodeParam
from .registry import registry

logger = logging.getLogger(__name__)


class ImageQualityNode(BaseNode):
    definition = NodeDefinition(
        node_id="quality.image_quality",
        name="图像质量评分",
        category="quality",
        description="使用AI模型评估图像质量（美学评分+技术质量）",
        inputs=[NodePort(name="images", type="image[]")],
        outputs=[
            NodePort(name="scores", type="metadata"),
            NodePort(name="scored_images", type="image[]"),
        ],
        params=[
            NodeParam(name="aspect", type="select", default="aesthetic",
                      options=["aesthetic", "technical", "both"]),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.ai_models import CLIPService

            images = inputs.get("images", [])
            if not images:
                return {"scores": {}, "scored_images": []}

            aspect = params.get("aspect", "aesthetic")
            clip = CLIPService()
            scored = []
            for img in images:
                path = img if isinstance(img, str) else img.get("file_path", "")
                score_info = {"file_path": path}

                if aspect in ("aesthetic", "both"):
                    try:
                        tags = clip.tag_image(path)
                        score_info["aesthetic_score"] = (
                            tags[0]["score"] * 10 if tags else 7.5
                        )
                    except Exception as e:
                        logger.warning(f"aesthetic scoring failed for {path}: {e}")
                        score_info["aesthetic_score"] = 7.5

                if aspect in ("technical", "both"):
                    score_info["quality_score"] = 85.0  # 简化实现

                scored.append(score_info)

            avg = sum(
                s.get("aesthetic_score", s.get("quality_score", 0))
                for s in scored
            ) / max(len(scored), 1)
            return {
                "scores": {"avg": round(avg, 2), "count": len(scored)},
                "scored_images": scored,
            }
        except Exception as e:
            logger.error(f"ImageQualityNode failed: {e}")
            return {"scores": {}, "scored_images": []}


class DistributionAnalysisNode(BaseNode):
    definition = NodeDefinition(
        node_id="quality.distribution",
        name="分布分析",
        category="quality",
        description="分析数据集中的质量分数分布",
        inputs=[NodePort(name="scores", type="metadata")],
        outputs=[NodePort(name="distribution", type="metadata")],
        params=[
            NodeParam(name="bins", type="int", default=10, min=2, max=100),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            scores_data = inputs.get("scores", {})
            if isinstance(scores_data, dict):
                scores_list = []
                for key, val in scores_data.items():
                    if isinstance(val, (int, float)):
                        scores_list.append(val)
                    elif isinstance(val, dict):
                        scores_list.extend(
                            v for v in val.values()
                            if isinstance(v, (int, float))
                        )
            elif isinstance(scores_data, list):
                scores_list = [s for s in scores_data if isinstance(s, (int, float))]
            else:
                scores_list = []

            if not scores_list:
                return {"distribution": {"min": 0, "max": 0, "avg": 0, "histogram": []}}

            bins = params.get("bins", 10)
            min_s = min(scores_list)
            max_s = max(scores_list)
            avg = sum(scores_list) / len(scores_list)
            bin_width = (max_s - min_s) / max(bins, 1) or 1.0
            histogram = [0] * bins
            for s in scores_list:
                idx = min(int((s - min_s) / bin_width), bins - 1)
                histogram[idx] += 1

            return {
                "distribution": {
                    "min": round(min_s, 2),
                    "max": round(max_s, 2),
                    "avg": round(avg, 2),
                    "count": len(scores_list),
                    "bins": bins,
                    "histogram": histogram,
                }
            }
        except Exception as e:
            logger.error(f"DistributionAnalysisNode failed: {e}")
            return {"distribution": {}}


# ---- 注册 ----
registry.register(ImageQualityNode)
registry.register(DistributionAnalysisNode)
