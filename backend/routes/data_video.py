"""视频Caption与视频数据生产管线路由"""
from fastapi import APIRouter, Request, HTTPException
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data/video/caption")
async def data_video_caption(request: Request):
    """视频Caption — 全局叙事/逐帧描述/分段描述"""
    body = await request.json()
    video_path = body.get("video_path", "")
    mode = body.get("mode", "full")  # full / narrative / segments / opensora
    output_dir = body.get("output_dir", "./data/video_caption")
    interval = body.get("frame_interval", 30)

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Video not found")

    from data_video_caption import VideoCaptionGenerator
    gen = VideoCaptionGenerator(work_dir=output_dir)

    if mode == "narrative":
        caption = gen.generate_narrative_caption(video_path)
        return {"success": True, "mode": "narrative", "caption": caption}
    elif mode == "segments":
        segments = gen.generate_segment_captions(video_path)
        return {"success": True, "mode": "segments", "segments": segments}
    elif mode == "opensora":
        out = gen.save_open_sora_format(video_path, output_dir=output_dir)
        return {"success": True, "mode": "opensora", "output_dir": out}
    else:
        # full
        result = gen.run_pipeline(video_path, output_dir=output_dir,
                                  extract_interval=interval)
        return {
            "success": True,
            "mode": "full",
            "narrative_caption": result.narrative_caption,
            "num_frames": result.num_frames,
            "num_segments": len(result.segment_captions),
            "output_dir": result.output_dir,
        }


@router.post("/api/data/video/pipeline")
async def data_video_pipeline(request: Request):
    """运行视频数据生产管线"""
    body = await request.json()

    input_video = body.get("input_video", "")
    input_dir = body.get("input_dir", "")
    output_dir = body.get("output_dir", "./data/video_output")

    from data_video_pipeline import VideoPipeline, VideoPipelineConfig

    config = VideoPipelineConfig(
        output_dir=output_dir,
        frame_interval=body.get("frame_interval", 30),
        scene_threshold=body.get("scene_threshold", 30),
        dedup_threshold=body.get("dedup_threshold", 10),
        quality_threshold=body.get("quality_threshold", 0.4),
        extract_frames=body.get("extract_frames", True),
        detect_scenes=body.get("detect_scenes", True),
        extract_keyframes=body.get("extract_keyframes", True),
        deduplicate=body.get("deduplicate", True),
        quality_filter=body.get("quality_filter", True)
    )

    pipeline = VideoPipeline(config)

    if input_video and os.path.exists(input_video):
        result = pipeline.run_pipeline(input_video)
    elif input_dir and os.path.exists(input_dir):
        result = pipeline.run_batch_pipeline(input_dir)
    else:
        raise HTTPException(status_code=400, detail="Provide input_video or input_dir")

    return {"success": True, "result": result}
