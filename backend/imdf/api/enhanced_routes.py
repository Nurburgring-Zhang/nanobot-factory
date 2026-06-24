"""增强能力路由 — 去重/语音/视频分析"""
from fastapi import APIRouter, UploadFile, File, Query
from pydantic import BaseModel
from typing import List, Optional
import tempfile, os

# R2-3: 文件上传校验 (size + Content-Type)
from api._common.validators import check_upload, ALLOWED_AUDIO_TYPES, DEFAULT_MAX_SIZE

router = APIRouter(prefix="/api/enhanced", tags=["enhanced"])

# ===== 数据去重 =====
class DedupRequest(BaseModel):
    paths: List[str]
    level: str = "perceptual"  # exact/perceptual/semantic

@router.post("/dedup")
async def deduplicate(req: DedupRequest):
    from engines.enhanced_engines import get_dedup, DedupLevel
    level_map = {"exact": DedupLevel.EXACT, "perceptual": DedupLevel.PERCEPTUAL, "semantic": DedupLevel.SEMANTIC}
    result = get_dedup().deduplicate(req.paths, level_map.get(req.level, DedupLevel.PERCEPTUAL))
    return {"success": True, 
            "total": result.total,
            "exact_duplicates": result.exact_dups,
            "perceptual_duplicates": result.perceptual_dups,
            "semantic_duplicates": result.semantic_dups,
            "unique": result.unique,
            "dedup_rate": f"{(1 - result.unique/max(result.total,1))*100:.1f}%"}

# ===== 语音分析 =====
@router.post("/speech/transcribe")
async def transcribe_audio(file: UploadFile = File(...), language: str = "zh"):
    # R2-3: 校验文件 (100MB 上限 + 音频 Content-Type 白名单)
    file = await check_upload(
        file, max_size=DEFAULT_MAX_SIZE, allowed=ALLOWED_AUDIO_TYPES, field_name="file",
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(await file.read())
    tmp.close()
    from engines.enhanced_engines import get_speech
    result = get_speech().transcribe(tmp.name, language)
    os.unlink(tmp.name)
    return result

@router.post("/speech/diarization")
async def speaker_diarization(file: UploadFile = File(...)):
    # R2-3: 校验文件
    file = await check_upload(
        file, max_size=DEFAULT_MAX_SIZE, allowed=ALLOWED_AUDIO_TYPES, field_name="file",
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(await file.read())
    tmp.close()
    result = get_speech().speaker_diarization(tmp.name)
    os.unlink(tmp.name)
    return result

@router.post("/speech/emotion")
async def speech_emotion(file: UploadFile = File(...)):
    # R2-3: 校验文件
    file = await check_upload(
        file, max_size=DEFAULT_MAX_SIZE, allowed=ALLOWED_AUDIO_TYPES, field_name="file",
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(await file.read())
    tmp.close()
    from engines.enhanced_engines import get_speech
    result = get_speech().emotion_analysis(tmp.name)
    os.unlink(tmp.name)
    return result

# ===== 视频分析 =====
class VideoPathRequest(BaseModel):
    video_path: str

@router.post("/video/scenes")
async def detect_scenes(req: VideoPathRequest, threshold: float = 30.0):
    from engines.enhanced_engines import get_video
    return get_video().scene_detection(req.video_path, threshold)

@router.post("/video/keyframes")
async def extract_keyframes(req: VideoPathRequest, max_frames: int = 10):
    from engines.enhanced_engines import get_video
    return get_video().keyframe_extraction(req.video_path, max_frames)

@router.post("/video/actions")
async def recognize_actions(req: VideoPathRequest):
    from engines.enhanced_engines import get_video
    return get_video().action_recognition(req.video_path)

@router.get("/models")
async def list_enhanced_models():
    return {"success": True, "models": {
        "dedup": {"md5": "内置", "phash": "imagehash(pip)", "ssim": "Pillow", "clip": "CLIP-ViT-Base(600MB)"},
        "speech": {"asr": "Whisper-large-v3(1.5GB)", "asr_light": "Whisper-tiny(39MB)", 
                    "diarization": "pyannote-3.1(需HF Token)", "emotion": "wav2vec2-emotion(300MB)"},
        "video": {"scene": "PySceneDetect(算法)", "action": "VideoMAE-base(400MB)", 
                   "caption": "BLIP2-2.7B(5GB)"}
    }}
