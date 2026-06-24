"""ML Backend 主动学习引擎

对标 Label Studio ML Backend + Scale AI Model Foundry
实现：模型注册 → 预标注 → 主动学习采样 → 效果跟踪
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MLModelStatus(str, Enum):
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    TRAINING = "training"
    READY = "ready"
    ERROR = "error"


class MLModelType(str, Enum):
    OBJECT_DETECTION = "object_detection"
    IMAGE_CLASSIFICATION = "image_classification"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    CAPTION = "caption"
    TAG = "tag"


class MLModel(BaseModel):
    """注册的ML模型"""
    id: str
    name: str
    model_type: MLModelType
    status: MLModelStatus = MLModelStatus.REGISTERED
    endpoint: str = ""  # 模型API端点
    api_key: str = ""
    description: str = ""
    accuracy: float = 0.0  # 最近评估准确率
    total_predictions: int = 0
    created_at: str = ""
    updated_at: str = ""


class PredictionResult(BaseModel):
    """预标注结果"""
    task_id: str
    model_id: str
    predictions: List[Dict] = []
    confidence: float = 0.0
    latency_ms: float = 0.0
    created_at: str = ""


class MLBackend:
    """ML Backend管理器"""

    _models: Dict[str, MLModel] = {}
    _predictions: List[PredictionResult] = []

    @classmethod
    def register_model(cls, name: str, model_type: MLModelType,
                       endpoint: str = "", api_key: str = "") -> MLModel:
        model_id = f"ml_{uuid.uuid4().hex[:12]}"
        model = MLModel(
            id=model_id, name=name, model_type=model_type,
            endpoint=endpoint, api_key=api_key,
            status=MLModelStatus.REGISTERED,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        cls._models[model_id] = model
        logger.info(f"ML model registered: {model_id} ({name}, {model_type.value})")
        return model

    @classmethod
    def list_models(cls, model_type: Optional[MLModelType] = None) -> List[MLModel]:
        if model_type:
            return [m for m in cls._models.values() if m.model_type == model_type]
        return list(cls._models.values())

    @classmethod
    def get_model(cls, model_id: str) -> Optional[MLModel]:
        return cls._models.get(model_id)

    @classmethod
    def remove_model(cls, model_id: str) -> bool:
        if model_id in cls._models:
            del cls._models[model_id]
            logger.info(f"ML model removed: {model_id}")
            return True
        return False

    @classmethod
    async def predict(cls, model_id: str, task_data: Dict) -> PredictionResult:
        """调用ML模型做预标注（支持HTTP调用和本地模型）"""
        model = cls._models.get(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        start = datetime.now()

        # 如果有HTTP端点，调用远程模型
        if model.endpoint:
            import aiohttp
            try:
                headers = {}
                if model.api_key:
                    headers["Authorization"] = f"Bearer {model.api_key}"
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        model.endpoint, json=task_data, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                        else:
                            result = {"error": f"HTTP {resp.status}"}
            except Exception as e:
                result = {"error": str(e)}
        else:
            # 本地模型回退
            result = cls._local_predict(model, task_data)

        latency = (datetime.now() - start).total_seconds() * 1000

        prediction = PredictionResult(
            task_id=task_data.get("task_id", ""),
            model_id=model_id,
            predictions=result.get("predictions", [result]),
            confidence=result.get("confidence", 0.5),
            latency_ms=latency,
            created_at=datetime.now().isoformat()
        )
        cls._predictions.append(prediction)
        model.total_predictions += 1
        model.updated_at = datetime.now().isoformat()
        return prediction

    @classmethod
    def _local_predict(cls, model: MLModel, task_data: Dict) -> Dict:
        """本地模型推理——使用现有的ai_models模块"""
        from core.ai_models import get_clip, get_blip
        image_url = task_data.get("image_url",
                                  task_data.get("data", {}).get("image", ""))

        if model.model_type == MLModelType.CAPTION and image_url:
            try:
                blip = get_blip()
                caption = blip.caption_image(image_url)
                return {"predictions": [{"caption": caption}], "confidence": 0.8}
            except Exception:
                pass
        elif model.model_type == MLModelType.TAG and image_url:
            try:
                clip = get_clip()
                tags = clip.tag_image(image_url)
                return {"predictions": [{"tags": tags}], "confidence": 0.7}
            except Exception:
                pass

        return {"predictions": [{"label": "unknown"}], "confidence": 0.1}

    @classmethod
    def get_active_learning_samples(cls, strategy: str = "uncertainty",
                                    count: int = 10) -> List[Dict]:
        """主动学习采样——选择最需要人工标注的样本

        基于置信度排序（越低越需要标注），支持多种采样策略。
        """
        if strategy == "uncertainty":
            # 低置信度采样
            samples = []
            for p in cls._predictions:
                if p.confidence < 0.7:
                    samples.append({
                        "task_id": p.task_id,
                        "confidence": p.confidence,
                        "model_id": p.model_id,
                        "predictions": p.predictions[:3]
                    })
            samples.sort(key=lambda x: x["confidence"])
            return samples[:count]
        elif strategy == "random":
            import random
            all_samples = []
            for p in cls._predictions:
                all_samples.append({
                    "task_id": p.task_id,
                    "confidence": p.confidence,
                    "model_id": p.model_id,
                    "predictions": p.predictions[:3]
                })
            random.shuffle(all_samples)
            return all_samples[:count]
        else:
            return []

    @classmethod
    def update_model_accuracy(cls, model_id: str, accuracy: float) -> bool:
        """更新模型准确率（基于人工审核反馈）"""
        model = cls._models.get(model_id)
        if not model:
            return False
        model.accuracy = accuracy
        model.updated_at = datetime.now().isoformat()
        logger.info(f"ML model accuracy updated: {model_id} -> {accuracy:.4f}")
        return True


# 全局单例
_ml_backend = None


def get_ml_backend() -> MLBackend:
    global _ml_backend
    if _ml_backend is None:
        _ml_backend = MLBackend()
    return _ml_backend
