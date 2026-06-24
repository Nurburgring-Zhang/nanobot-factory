"""向量语义搜索——基于CLIP embedding的语义检索"""
import logging, json, numpy as np
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class VectorSearch:
    """向量搜索引擎——用CLIP embedding做语义搜索"""
    
    _index: Dict[str, np.ndarray] = {}  # asset_id -> embedding
    _metadata: Dict[str, dict] = {}     # asset_id -> metadata
    
    @classmethod
    def index_asset(cls, asset_id: str, embedding: List[float], metadata: dict = None):
        """索引一个资产（向量+元数据）"""
        cls._index[asset_id] = np.array(embedding, dtype=np.float32)
        if metadata:
            cls._metadata[asset_id] = metadata
    
    @classmethod
    def remove_asset(cls, asset_id: str):
        cls._index.pop(asset_id, None)
        cls._metadata.pop(asset_id, None)
    
    @classmethod
    def search(cls, query_embedding: List[float], top_k: int = 20, 
               filter_type: str = "", min_score: float = 0.0) -> List[dict]:
        """语义搜索——余弦相似度排序"""
        if not cls._index:
            return []
        
        q = np.array(query_embedding, dtype=np.float32)
        results = []
        
        for asset_id, emb in cls._index.items():
            meta = cls._metadata.get(asset_id, {})
            
            # 类型过滤
            if filter_type and meta.get("type") != filter_type:
                continue
            
            # 余弦相似度
            sim = float(np.dot(q, emb) / (np.linalg.norm(q) * np.linalg.norm(emb) + 1e-8))
            if sim < min_score:
                continue
            
            results.append({
                "asset_id": asset_id,
                "score": round(float(sim), 4),
                "metadata": meta
            })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    @classmethod
    def get_embedding_from_text(cls, text: str) -> List[float]:
        """用CLIP模型从文本生成embedding"""
        try:
            from core.ai_models import get_clip
            clip = get_clip()
            if clip and clip.processor and clip.model:
                import torch
                inputs = clip.processor(text=[text], return_tensors="pt", padding=True)
                with torch.no_grad():
                    outputs = clip.model.get_text_features(**inputs)
                return outputs[0].cpu().numpy().tolist()
        except Exception as e:
            logger.warning(f"CLIP embedding failed: {e}")
        # fallback: 随机向量（仅开发用）
        return list(np.random.rand(512).astype(np.float32))
    
    @classmethod
    def get_embedding_from_image(cls, image_path: str) -> List[float]:
        """用CLIP模型从图片生成embedding"""
        try:
            from core.ai_models import get_clip
            from PIL import Image
            clip = get_clip()
            if clip and clip.processor and clip.model:
                img = Image.open(image_path).convert("RGB")
                import torch
                inputs = clip.processor(images=img, return_tensors="pt")
                with torch.no_grad():
                    outputs = clip.model.get_image_features(**inputs)
                return outputs[0].cpu().numpy().tolist()
        except Exception as e:
            logger.warning(f"CLIP image embedding failed: {e}")
        return list(np.random.rand(512).astype(np.float32))

vs = VectorSearch()
