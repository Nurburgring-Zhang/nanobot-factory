"""video_frames — 视频抽帧导出器 (manifest + frame list).

op_id: export.video_frames
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict

OP_ID = "export.video_frames"
NAME = "视频抽帧导出"
CATEGORY = "video"
DESCRIPTION = "导出 video metadata 为帧列表 + manifest (无 ffmpeg 时降级 mock)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True,
     "description": "Output directory"},
    {"name": "fps", "type": "float", "default": 1.0, "required": False},
    {"name": "video_field", "type": "str", "default": "video", "required": False},
    {"name": "duration_field", "type": "str", "default": "duration_sec", "required": False},
]


def _probe_with_opencv(video_path: str) -> Dict[str, Any]:
    try:
        import cv2  # type: ignore
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {"ok": False, "error": "cannot_open"}
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (frame_count / fps) if fps else 0
        cap.release()
        return {
            "ok": True,
            "fps": round(fps, 3),
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration_sec": round(duration, 3),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _mock_probe(video_path: str) -> Dict[str, Any]:
    h = int(hashlib.md5(video_path.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    fps = 24.0
    duration = 5 + (h % 60)  # 5-65 sec
    return {
        "ok": True,
        "mode": "mock",
        "fps": fps,
        "frame_count": int(fps * duration),
        "width": 1280,
        "height": 720,
        "duration_sec": float(duration),
    }


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    base = str(params.get("path") or params.get("dir") or "").strip()
    if not base:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(base, exist_ok=True)
    fps_target = float(params.get("fps", 1.0))
    video_field = str(params.get("video_field", "video"))
    duration_field = str(params.get("duration_field", "duration_sec"))
    items = list(data) if isinstance(data, list) else [data]
    manifest = []
    for idx, x in enumerate(items):
        if isinstance(x, dict):
            video_path = str(x.get(video_field, x.get("path", "")))
        else:
            video_path = str(x)
        if video_path and os.path.exists(video_path):
            info = _probe_with_opencv(video_path)
            if not info["ok"]:
                info = _mock_probe(video_path)
        else:
            info = _mock_probe(video_path)
        duration = info.get("duration_sec") or float(x.get(duration_field, 0) if isinstance(x, dict) else 0)
        info_fps = info.get("fps") or 24.0
        frame_count_target = int(duration * fps_target)
        frames = [
            {"frame_id": i, "timestamp_sec": round(i / fps_target, 3),
             "video_fps": info_fps, "video_frame_index": int(round(i / fps_target * info_fps))}
            for i in range(frame_count_target)
        ]
        rec = {
            "index": idx,
            "video_path": video_path,
            "video_info": info,
            "fps_target": fps_target,
            "frame_count": len(frames),
            "frames": frames[:50],  # truncate for manifest sanity
            "frame_count_total": len(frames),
        }
        manifest.append(rec)
    manifest_path = os.path.join(base, "frames_manifest.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as fp:
        for rec in manifest:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "format": "video_frames",
        "manifest_path": os.path.abspath(manifest_path),
        "video_count": len(manifest),
    }
