"""PE系统路由 v4 — 预设+自适应生成+自定义管理

R2-Worker-5: /stats 加入 ``DateRangeParams`` / ``Granularity`` / dimension 白名单校验。
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension
# R2-3: 路径 ID 校验
from api._common.validators import validate_id

router = APIRouter(prefix="/api/pe", tags=["prompt_engineering"])

# PE 模块允许的聚合维度
PE_ALLOWED_DIMENSIONS = ("modality", "stage", "subtype", "date")

class GeneratePERequest(BaseModel):
    modality: str  # image/video/audio/text
    stage: str     # pretrain/post_train/sft/rlhf/dpo
    subtype: str   # 子类型
    custom_notes: str = ""  # 自定义额外要求

class CustomPEAdd(BaseModel):
    pe_id: str
    system_prompt: str
    few_shot: List[dict] = []

@router.get("/modalities")
async def list_modalities(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    from engines.pe_system import MODALITIES
    modalities = {
        mod: {"name": info["name"], "stages": info["stages"], "subtypes": info["subtypes"]}
        for mod, info in MODALITIES.items()
    }
    if q:
        modalities = {k: v for k, v in modalities.items() if q.lower() in str(k).lower() or q.lower() in v.get("name", "").lower()}
    total = len(modalities)
    page = dict(list(modalities.items())[offset: offset + limit])
    return {
        "success": True,
        "modalities": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.get("/templates")
async def list_templates(
    modality: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模态过滤 (白名单字符)",
    ),
    stage: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="阶段过滤 (白名单字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    from engines.pe_system import get_pe_v4
    mgr = get_pe_v4()
    templates = mgr.list_by_modality(modality or "image", stage)
    if q:
        templates = [t for t in templates if q.lower() in str(t).lower()]
    total = len(templates)
    page = templates[offset: offset + limit]
    return {
        "success": True,
        "templates": page,
        "total": total,
        "modality": modality,
        "stage": stage,
        "limit": limit,
        "offset": offset,
    }

@router.get("/templates/{pe_id}")
async def get_template(
    pe_id: str,
    custom_version: Optional[int] = Query(None, ge=0, le=10000, description="自定义版本号"),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    validate_id(pe_id, "pe_id")
    from engines.pe_system import get_pe_v4
    mgr = get_pe_v4()
    pe = mgr.get_pe(pe_id, custom_version)
    if not pe:
        return {"success": False, "error": f"模板 {pe_id} 不存在"}
    return {
        "success": True,
        "limit": limit,
        "offset": offset,
        **pe,
    }

@router.post("/generate")
async def generate_pe(req: GeneratePERequest):
    """自适应生成PE — 覆盖任意模态×阶段×子类型组合"""
    from engines.pe_system import get_pe_v4, MODALITIES
    
    if req.modality not in MODALITIES:
        return {"success": False, "error": f"未知模态: {req.modality}"}
    
    info = MODALITIES[req.modality]
    if req.stage not in info["stages"]:
        return {"success": False, "error": f"未知阶段: {req.stage}"}
    
    subtype_name = info["subtypes"].get(req.subtype, req.subtype)
    
    # 尝试从预置PE中匹配
    mgr = get_pe_v4()
    for pid, pe in mgr.db.items():
        if pe["modality"]==req.modality and pe["stage"]==req.stage and pe["subtype"]==req.subtype:
            return {"success": True, "source": "preset", "pe_id": pid, **pe}
    
    # 自适应生成
    pe = _generate_adaptive_pe(req.modality, req.stage, req.subtype, subtype_name, req.custom_notes)
    return {"success": True, "source": "generated", "pe": pe}

def _generate_adaptive_pe(modality: str, stage: str, subtype: str, name: str, notes: str) -> dict:
    """自适应PE生成器 — 基于模态+阶段+子类型模板生成"""
    
    stage_guidance = {
        "pretrain": "大规模数据质量筛选,关注格式标准化、内容合规、粗粒度质量分级",
        "post_train": "增强特定能力的数据补充,关注编辑指令清晰度、参考图/视频质量",
        "sft": "指令跟随精细化,关注指令多样性、回答准确性、格式规范(ShareGPT/ChatML)",
        "rlhf": "偏好对比,关注chosen>rejected的明显差距,多维评分(有用性/诚实性/安全性)",
        "dpo": "直接偏好优化对,关注单一变量的对比,c..."
    }
    
    modality_guidance = {
        "image": {"format":"图片(支持jpg/png/webp)","metrics":"CLIP score, aesthetic score, resolution"},
        "video": {"format":"视频(支持mp4/webm)","metrics":"motion score, temporal consistency, FPS"},
        "audio": {"format":"音频(支持wav/mp3/flac)","metrics":"MOS, SNR, duration"},
        "text": {"format":"文本(支持json/markdown)","metrics":"perplexity, quality score, tokens"}
    }
    
    g = modality_guidance.get(modality, {})
    sg = stage_guidance.get(stage, "通用数据生产标准")
    
    system_prompt = f"""你是{name}数据标注专家。为{stage}阶段生产高质量训练数据。

## 数据规范
- 格式: {g.get('format','')}
- 质量指标: {g.get('metrics','')}
- 阶段重点: {sg}

## 标注要求(自动生成)
1. 确保数据格式符合标准schema
2. 标注内容准确、完整、一致
3. 标记所有质量问题(模糊/损坏/违规)
4. 输出结构化JSON,便于自动化处理
{notes}

## 输出schema
根据{modality}/{stage}/{subtype}自动适配,参考同模态同阶段的其他PE模板格式。
"""
    return {
        "modality": modality, "stage": stage, "subtype": subtype,
        "system_prompt": system_prompt,
        "few_shot": [],
        "generated": True
    }

@router.post("/templates/{pe_id}/custom")
async def add_custom(pe_id: str, req: CustomPEAdd):
    validate_id(pe_id, "pe_id")
    from engines.pe_system import get_pe_v4
    mgr = get_pe_v4()
    version = mgr.add_custom(pe_id, req.system_prompt, req.few_shot)
    if version < 0:
        return {"success": False, "error": "模板不存在"}
    return {"success": True, "version": version, "message": f"自定义PE已添加(v{version})"}

@router.get("/stats")
async def pe_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "modality",
        description=f"聚合维度, 允许: {list(PE_ALLOWED_DIMENSIONS)}",
    ),
):
    """PE 统计 — R2-Worker-5: DateRangeParams + granularity 枚举 + dimension 白名单"""
    if not is_valid_dimension(dimension, scope="pe"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(PE_ALLOWED_DIMENSIONS)}",
        )
    from engines.pe_system import get_pe_v4
    return {
        "success": True,
        "stats": get_pe_v4().stats(),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }
