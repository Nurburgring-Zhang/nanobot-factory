"""本地模型管理路由 — 支持本地/云端双模式切换"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/local-models", tags=["local_models"])

class AutoTagRequest(BaseModel):
    text: str
    candidate_labels: List[str]
    prefer_local: bool = True

class ScoreRequest(BaseModel):
    image_path: str
    prefer_local: bool = True

@router.get("/list")
async def list_local_models():
    from engines.local_models import get_local_models
    mgr = get_local_models()
    return {"success": True, "models": mgr.list_models()}

@router.get("/backend/{model_id}")
async def get_backend(model_id: str, prefer_local: bool = True):
    from engines.local_models import get_local_models
    mgr = get_local_models()
    backend = mgr.get_backend(model_id, prefer_local)
    local_ok = mgr.is_local_available(model_id)
    return {"success": True, "model_id": model_id, "backend": backend.value, "local_available": local_ok}

@router.post("/auto-tag")
async def auto_tag(req: AutoTagRequest):
    from engines.local_models import get_local_models, ModelBackend
    mgr = get_local_models()
    backend = mgr.get_backend("auto_tag", req.prefer_local)
    
    if backend == ModelBackend.LOCAL:
        result = mgr.auto_tag_local(req.text, req.candidate_labels)
        if result.get("success"):
            return result
        # fallback to API
    # 云端
    try:
        from engines.model_gateway import get_gateway
        gw = get_gateway()
        labels_str = ", ".join(req.candidate_labels)
        resp = gw.chat([{"role":"user","content":f"为以下文本选择最合适的标签(可多选):\n文本: {req.text}\n可选标签: {labels_str}\n\n只返回标签名,逗号分隔。"}], model="auto")
        tags = resp.content.split(",") if resp.content else []
        return {"success": True, "tags": [{"label": t.strip(), "score": 0.9} for t in tags], "backend": "api"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/aesthetic-score")
async def aesthetic_score(req: ScoreRequest):
    from engines.local_models import get_local_models, ModelBackend
    mgr = get_local_models()
    backend = mgr.get_backend("aesthetic", req.prefer_local)
    
    if backend == ModelBackend.LOCAL:
        result = mgr.aesthetic_score_local(req.image_path)
        if result.get("success"):
            return result
    # fallback to API
    try:
        from engines.aesthetic_engine import get_aesthetic_engine
        ae = get_aesthetic_engine()
        return ae.score_image(req.image_path)
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/install-guide")
async def install_guide():
    return {
        "success": True,
        "guides": {
            "auto_tag": {
                "description": "零样本分类模型(132MB)",
                "install": "pip install sentence-transformers",
                "model": "all-MiniLM-L6-v2 (自动下载)"
            },
            "aesthetic": {
                "description": "AI审美评分(50MB)", 
                "install": "pip install clip-interrogator",
                "model": "CLIP ViT-L/14 (自动下载)"
            },
            "text_embed": {
                "description": "多语言文本嵌入(420MB)",
                "install": "pip install sentence-transformers",
                "model": "paraphrase-multilingual-MiniLM-L12-v2"
            },
            "image_quality": {
                "description": "图像质量分析(无需额外安装)",
                "install": "pip install Pillow (已安装)",
                "model": "纯算法,无模型文件"
            },
            "image_embed": {
                "description": "图像特征指纹(无需额外安装)",
                "install": "pip install Pillow imagehash",
                "model": "pHash + 主色提取"
            }
        }
    }
