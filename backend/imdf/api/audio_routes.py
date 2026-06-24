"""音频能力路由 — F4.4"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from engines.audio_engine import get_audio

router = APIRouter(prefix="/api/audio", tags=["audio"])

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"
    speed: float = 1.0

class MusicRequest(BaseModel):
    prompt: str
    duration: float = 30
    style: str = "ambient"

class ASRRequest(BaseModel):
    file_path: str

@router.post("/tts")
async def text_to_speech(req: TTSRequest):
    from engines.audio_engine import get_audio
    job = get_audio().text_to_speech(req.text, req.voice, req.speed)
    return {"success": True, "job": {"id":job.id,"status":job.status,"output":job.output_path,"duration":job.duration}}

@router.post("/asr")
async def transcribe(req: ASRRequest):
    from engines.audio_engine import get_audio
    result = get_audio().asr_transcribe(req.file_path)
    return {"success": True, "text": result["text"], "confidence": result["confidence"]}

@router.post("/music")
async def generate_music(req: MusicRequest):
    from engines.audio_engine import get_audio
    job = get_audio().generate_music(req.prompt, req.duration, req.style)
    return {"success": True, "job": {"id":job.id,"status":job.status,"output":job.output_path}}

@router.post("/sfx")
async def sound_effect(description: str = Query(...)):
    from engines.audio_engine import get_audio
    job = get_audio().generate_sound_effect(description)
    return {"success": True, "job": {"id":job.id,"status":job.status}}

@router.get("/jobs")
async def list_jobs(
    type: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$",
        description="任务类型 (白名单字符, ≤64 字符)",
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
    """List audio jobs (R2.5-W1: Pydantic Query 验证)"""
    jobs = get_audio().list_jobs(type)
    if q:
        ql = q.lower()
        jobs = [j for j in jobs if ql in str(j).lower()]
    total = len(jobs)
    if sort_by:
        jobs.sort(
            key=lambda j: j.get(sort_by, "") if isinstance(j, dict) else "",
            reverse=(order == "desc"),
        )
    page = jobs[offset: offset + limit]
    return {"success": True, "jobs": page, "total": total, "limit": limit, "offset": offset}
