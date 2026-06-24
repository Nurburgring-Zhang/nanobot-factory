"""本地模型管理器 — 支持本地/云端双模式切换"""
import os, json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

class ModelBackend(str, Enum):
    LOCAL = "local"
    API = "api"
    AUTO = "auto"  # 优先本地,fallback API

@dataclass
class ModelInfo:
    name: str
    backend: ModelBackend
    path: str = ""  # 本地路径
    api_endpoint: str = ""  # API端点
    installed: bool = False

class LocalModelManager:
    """本地模型管理器 — 管理所有可本地运行的模型"""
    
    MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "local_models")
    
    # 轻量本地模型清单
    REGISTRY = {
        "auto_tag": ModelInfo(
            name="bge-m3 (MTEB #1中文)",
            backend=ModelBackend.AUTO,
            path="BAAI/bge-m3",  # 2.2GB,中文最优
            api_endpoint="/api/chat"
        ),
        "aesthetic": ModelInfo(
            name="LAION-AI aesthetic-predictor-v2",
            backend=ModelBackend.AUTO,
            path="LAION-AI/aesthetic-predictor-v2",  # 890MB
            api_endpoint="/api/aesthetic/score"
        ),
        "image_quality": ModelInfo(
            name="google/musiq (NR-IQA SOTA)",
            backend=ModelBackend.LOCAL,
            path="google/musiq",  # 100MB
        ),
        "text_embed": ModelInfo(
            name="bge-m3 multilingual",
            backend=ModelBackend.AUTO,
            path="BAAI/bge-m3",
            api_endpoint="/api/chat"
        ),
        "image_embed": ModelInfo(
            name="CLIP ViT-Base (语义特征)",
            backend=ModelBackend.AUTO,
            path="openai/clip-vit-base-patch32",  # 600MB
            api_endpoint="/api/chat"
        ),
    }
    
    def __init__(self):
        os.makedirs(self.MODELS_DIR, exist_ok=True)
        self._check_installed()
    
    def _check_installed(self):
        """检查哪些本地模型可用"""
        # auto_tag: 检查 sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            self.REGISTRY["auto_tag"].installed = True
        except ImportError:
            pass
        
        # aesthetic: 检查clip-interrogator
        try:
            import clip_interrogator
            self.REGISTRY["aesthetic"].installed = True
        except ImportError:
            pass
        
        # Pillow-based: 永远可用
        try:
            from PIL import Image
            self.REGISTRY["image_quality"].installed = True
            self.REGISTRY["image_embed"].installed = True
        except ImportError:
            pass
        
        # text_embed: 同auto_tag
        self.REGISTRY["text_embed"].installed = self.REGISTRY["auto_tag"].installed
    
    def is_local_available(self, model_id: str) -> bool:
        return model_id in self.REGISTRY and self.REGISTRY[model_id].installed
    
    def get_backend(self, model_id: str, prefer_local: bool = True) -> ModelBackend:
        """自动选择后端"""
        info = self.REGISTRY.get(model_id)
        if not info:
            return ModelBackend.API
        
        if info.backend == ModelBackend.LOCAL:
            return ModelBackend.LOCAL
        if info.backend == ModelBackend.API:
            return ModelBackend.API
        
        # AUTO模式
        if prefer_local and info.installed:
            return ModelBackend.LOCAL
        return ModelBackend.API
    
    def list_models(self) -> List[Dict]:
        return [
            {"id": mid, "name": info.name, "backend": info.backend.value,
             "installed": info.installed, "local_path": info.path if info.installed else None}
            for mid, info in self.REGISTRY.items()
        ]
    
    # === 本地推理方法 ===
    
    def auto_tag_local(self, text: str, candidate_labels: List[str]) -> Dict:
        """本地自动打标 — 使用sentence-transformers零样本分类"""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            # 零样本: 计算text与每个label的相似度
            from sklearn.metrics.pairwise import cosine_similarity
            text_emb = model.encode([text])
            label_embs = model.encode(candidate_labels)
            scores = cosine_similarity(text_emb, label_embs)[0]
            # 归一化
            results = sorted(
                [{"label": l, "score": float(s)} for l, s in zip(candidate_labels, scores)],
                key=lambda x: -x["score"]
            )
            return {"success": True, "tags": results[:5], "backend": "local"}
        except Exception as e:
            return {"success": False, "error": str(e), "backend": "local"}
    
    def aesthetic_score_local(self, image_path: str) -> Dict:
        """本地审美评分 — Pillow分析"""
        try:
            from PIL import Image
            import numpy as np
            
            img = Image.open(image_path).convert("RGB")
            arr = np.array(img)
            
            # 6维度评分
            h, w = arr.shape[:2]
            
            # 构图: 三分法则
            thirds_h, thirds_w = h//3, w//3
            center = arr[thirds_h:2*thirds_h, thirds_w:2*thirds_w]
            edge = np.concatenate([arr[:thirds_h].ravel(), arr[2*thirds_h:].ravel(),
                                    arr[:,:thirds_w].ravel(), arr[:,2*thirds_w:].ravel()])
            composition = 50 + min(50, abs(float(np.mean(center)) - float(np.mean(edge))) / 5)
            
            # 色彩: HSV饱和度
            from PIL import ImageStat
            hsv = img.convert("HSV")
            stat = ImageStat.Stat(hsv)
            saturation = stat.mean[1]
            color = min(100, float(saturation) * 1.5)
            
            # 光影: 亮度均衡
            gray = img.convert("L")
            stat_l = ImageStat.Stat(gray)
            lighting = 100 - abs(float(stat_l.mean[0]) - 128) / 1.28
            
            # 清晰度: Laplacian方差
            from PIL import ImageFilter
            lap = np.array(img.filter(ImageFilter.LAPLACIAN))
            sharpness = min(100, float(np.var(lap)) * 0.5)
            
            # 内容: 复杂度(edge ratio)
            edges = np.array(img.filter(ImageFilter.FIND_EDGES))
            content = min(100, float(np.mean(edges)) * 2)
            
            # 创意: 颜色多样性
            colors = len(set(tuple(p) for p in arr[::4,::4].reshape(-1, 3)))
            creativity = min(100, float(colors) / 2)
            
            return {
                "success": True,
                "scores": {
                    "composition": round(composition, 1),
                    "color": round(color, 1),
                    "lighting": round(lighting, 1),
                    "sharpness": round(sharpness, 1),
                    "content": round(content, 1),
                    "creativity": round(creativity, 1)
                },
                "overall": round((composition+color+lighting+sharpness+content+creativity)/6, 1),
                "backend": "local"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# 单例
_local_mgr: LocalModelManager = None
def get_local_models():
    global _local_mgr
    if not _local_mgr:
        _local_mgr = LocalModelManager()
    return _local_mgr
