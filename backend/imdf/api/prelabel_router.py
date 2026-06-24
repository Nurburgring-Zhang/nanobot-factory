"""AI预标注路由 — 利用DeepSeek API自动生成标注"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import json
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["prelabel"])


class PrelabelRequest(BaseModel):
    image_url: str = ""
    image_desc: str = ""
    task_type: str = "detection"  # detection | classification | tagging


class BBoxResult(BaseModel):
    x: float
    y: float
    w: float
    h: float
    label: str
    confidence: float


class PrelabelResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: str = ""


@router.post("/prelabel", response_model=PrelabelResponse)
async def prelabel(req: PrelabelRequest):
    from api.nanobot_adapter import NanobotAdapter

    adapter = NanobotAdapter()

    # 根据task_type构造不同prompt
    if req.task_type == "detection":
        prompt = f"""分析以下图片描述,返回图片中的物体检测框(Bounding Box)。
图片描述: {req.image_desc or req.image_url}
请返回JSON格式: {{"bboxes":[{{"x":左上角X,"y":左上角Y,"w":宽度,"h":高度,"label":"类别","confidence":0.95}}]}}
只返回JSON,不要其他文字。每个框的坐标在0-1000范围内。"""
    elif req.task_type == "classification":
        prompt = f"""分析以下图片描述,返回图片分类结果。
图片描述: {req.image_desc or req.image_url}
请返回JSON格式: {{"classification":"类别","confidence":0.95,"tags":["标签1","标签2"]}}
只返回JSON,不要其他文字。"""
    else:  # tagging
        prompt = f"""分析以下图片描述,返回图片标签。
图片描述: {req.image_desc or req.image_url}
请返回JSON格式: {{"tags":[{{"tag":"标签","confidence":0.95}}],"summary":"一句话总结"}}
只返回JSON,不要其他文字。"""

    try:
        result = await adapter.chat(prompt)
        if not result:
            return PrelabelResponse(success=False, error="AI服务无响应")

        if isinstance(result, dict) and not result.get("success"):
            return PrelabelResponse(success=False, error=result.get("error", "AI调用失败"))

        message = ""
        if isinstance(result, str):
            message = result
        elif isinstance(result, dict):
            message = result.get("message", str(result))

        if not message:
            return PrelabelResponse(success=False, error="AI返回内容为空")

        # 尝试解析JSON(LLM可能返回markdown代码块)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', message)
        if json_match:
            message = json_match.group(1).strip()

        # 清理可能的非JSON前导/后缀
        message = message.strip()
        # 查找第一个{和最后一个}
        first_brace = message.find("{")
        last_brace = message.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            message = message[first_brace : last_brace + 1]

        data = json.loads(message)
        return PrelabelResponse(success=True, data=data)
    except json.JSONDecodeError:
        return PrelabelResponse(success=False, error=f"AI返回格式异常: {message[:300]}")
    except Exception as e:
        return PrelabelResponse(success=False, error=str(e))
