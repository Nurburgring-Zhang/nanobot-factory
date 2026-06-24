"""P3-6-W1: business pipeline template — Short Drama SFT (10 步完整流).

Pipeline (混合业务:script -> storyboard -> shot video -> caption -> dialogue
  -> TTS -> compose -> audio mix -> ShareGPT export -> OSS upload):

  1.  script_parse    - 解析剧本 -> scene/character/dialogue 列表
  2.  storyboard       - 每个 scene 拆成 N 个 shot,生成 shot prompt
  3.  shot_video       - 每个 shot 跑 video model (cogvideox) 生成视频
  4.  shot_caption     - VLM 给每个 shot 生成描述
  5.  dialogue_tts     - 每个 dialogue 跑 TTS (cosyvoice)
  6.  lip_sync         - (可选) wav2lip 对齐嘴型
  7.  episode_compose  - 合成 episode (按 scene 顺序拼接视频+音频)
  8.  audio_mix        - 混合背景音乐 (music model + bgm)
  9.  sharegpt_export  - 输出 ShareGPT 训练数据 (conversation 多轮)
  10. oss_upload       - 上传到 drama-sft bucket

vs basic_templates/pipeline.py::tpl-biz-pipe-010 (8 步): 本模板细化到 10 步,
  加入 lip_sync + audio_mix + VLM shot caption,适合完整商业级短剧 SFT 数据。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-pipe-011",
    "name": "Short Drama SFT Full Pipeline (商业级)",
    "category": "pipeline",
    "description": (
        "完整商业级短剧 SFT 流:script -> storyboard -> shot video -> "
        "caption -> TTS -> lip-sync -> compose -> bgm -> ShareGPT 导出。"
    ),
    "tags": ["short-drama", "sft", "narrative", "video",
             "tts", "storyboard", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "script_source": {"type": "object", "required": True,
                           "description": "{path:'/x.txt', format:'txt'}"},
        "video_model": {"type": "string", "default": "cogvideox-5b"},
        "video_model_path": {"type": "string", "required": False,
                              "description": "本地路径或 HF repo"},
        "shot_duration_sec": {"type": "float", "default": 4.0},
        "fps": {"type": "int", "default": 24},
        "caption_model": {"type": "string", "default": "qwen-vl-max"},
        "tts_model": {"type": "string", "default": "cosyvoice-300m"},
        "enable_lip_sync": {"type": "boolean", "default": True},
        "lip_sync_model": {"type": "string", "default": "wav2lip"},
        "bgm_model": {"type": "string", "default": "musicgen-medium"},
        "bgm_prompt": {"type": "string", "default": "cinematic background"},
        "sharegpt_role_map": {"type": "object", "default": {
            "user": "user", "assistant": "assistant",
            "system": "system"}},
        "oss_bucket": {"type": "string", "default": "drama-sft"},
        "oss_key_prefix": {"type": "string", "default": "short_drama/"},
    },
    "outputs": [
        "sharegpt.json",
        "episodes/*.mp4",
        "audio/*.wav",
        "storyboard/*.json",
        "captions/*.json",
        "manifest.json",
        "stats.json",
    ],
    "steps": [
        {"id": "sc", "name": "Script Parse",
         "operator": "scripting.parse",
         "config": {"source": "$inputs.script_source"}},
        {"id": "sb", "name": "Storyboard (scene -> shots)",
         "operator": "preprocessing.storyboard",
         "config": {"shot_duration_sec": "$inputs.shot_duration_sec"}},
        {"id": "vs", "name": "Shot Video Generation",
         "operator": "video_generation.shot",
         "config": {"model": "$inputs.video_model",
                    "model_path": "$inputs.video_model_path",
                    "fps": "$inputs.fps"}},
        {"id": "cp", "name": "Per-shot VLM Caption",
         "operator": "annotation.vlm_shot_caption",
         "config": {"model": "$inputs.caption_model"}},
        {"id": "tt", "name": "Dialogue TTS",
         "operator": "audio.tts",
         "config": {"model": "$inputs.tts_model"}},
        {"id": "ls", "name": "Lip-sync (optional)",
         "operator": "video_generation.lip_sync",
         "config": {"enabled": "$inputs.enable_lip_sync",
                    "model": "$inputs.lip_sync_model"}},
        {"id": "ed", "name": "Episode Compose",
         "operator": "video_compose.episode"},
        {"id": "am", "name": "Background Music Mix",
         "operator": "audio.bgm_mix",
         "config": {"model": "$inputs.bgm_model",
                    "prompt": "$inputs.bgm_prompt",
                    "volume": 0.2}},
        {"id": "sg", "name": "ShareGPT Conversation Export",
         "operator": "format.sharegpt_export",
         "config": {"role_map": "$inputs.sharegpt_role_map",
                    "include_video_refs": True}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"},
         "retry_max": 2},
    ],
    "metrics": [
        "scripts_parsed", "scenes", "shots",
        "videos_generated", "captions",
        "tts_clips", "lip_synced", "bgm_mixed",
        "sharegpt_conversations", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]