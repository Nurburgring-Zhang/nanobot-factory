"""P4-6-W1 Effect Engine — 16 视觉效果/美学/实用效果.

8 visual:   color_grade, blur, sharpen, denoise, stabilize,
            slow_motion, speed_ramp, lens_correction
4 aesthetic: vignette, grain, LUT_preset, film_look
4 utility:   subtitle_burn, watermark, chromakey, background_blur

Each effect emits an FFmpeg filter chain fragment so the render
engine can stitch it onto a per-clip filter graph.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

EFFECT_CATALOG: Dict[str, Dict[str, Any]] = {
    # ---- 8 visual ----
    "color_grade": {
        "category": "visual", "default": {"intensity": 0.6},
        "ffmpeg": "eq=brightness=0.05:saturation={intensity}:contrast=1.1",
    },
    "blur": {
        "category": "visual", "default": {"intensity": 5.0},
        "ffmpeg": "boxblur={intensity}:1",
    },
    "sharpen": {
        "category": "visual", "default": {"intensity": 1.0},
        "ffmpeg": "unsharp=5:5:{intensity}:5:5:0",
    },
    "denoise": {
        "category": "visual", "default": {"intensity": 0.5},
        "ffmpeg": "hqdn3d={intensity}:{intensity}:6:6",
    },
    "stabilize": {
        "category": "visual", "default": {"smoothing": 10},
        "ffmpeg": "vidstabdetect=shakiness=8:accuracy=9,"
                   "vidstabtransform=smoothing={smoothing}",
    },
    "slow_motion": {
        "category": "visual", "default": {"speed": 0.5},
        "ffmpeg": "setpts=PTS/{speed}",
    },
    "speed_ramp": {
        "category": "visual", "default": {"start_speed": 1.0, "end_speed": 0.5},
        "ffmpeg": "setpts='PTS/(1.0+({end_speed}-{start_speed})*(t/DR))'",
    },
    "lens_correction": {
        "category": "visual", "default": {"strength": 0.05},
        "ffmpeg": "lenscorrection=k1={strength}:k2={strength}",
    },
    # ---- 4 aesthetic ----
    "vignette": {
        "category": "aesthetic", "default": {"intensity": 0.5},
        "ffmpeg": "vignette=PI/{intensity}",
    },
    "grain": {
        "category": "aesthetic", "default": {"intensity": 0.1},
        "ffmpeg": "noise=alls={intensity}:allf=t",
    },
    "LUT_preset": {
        "category": "aesthetic",
        "default": {"preset": "cinematic", "path": ""},
        "ffmpeg": "lut3d={path}",
    },
    "film_look": {
        "category": "aesthetic",
        "default": {"preset": "kodak_2383"},
        "ffmpeg": "curves=preset={preset}",
    },
    # ---- 4 utility ----
    "subtitle_burn": {
        "category": "utility",
        "default": {"text": "", "position": "bottom", "fontsize": 24},
        "ffmpeg": "drawtext=text='{text}':fontsize={fontsize}:"
                   "x=(w-text_w)/2:y=h-th-10",
    },
    "watermark": {
        "category": "utility",
        "default": {"path": "logo.png", "position": "topright", "opacity": 0.7},
        "ffmpeg": "overlay=W-w-10:10:format=auto,colorchannelmixer="
                   "aa={opacity}",
    },
    "chromakey": {
        "category": "utility",
        "default": {"color": "0x00FF00", "similarity": 0.3},
        "ffmpeg": "chromakey=color={color}:similarity={similarity}",
    },
    "background_blur": {
        "category": "utility", "default": {"intensity": 15.0},
        "ffmpeg": "split[orig][bg],"
                   "[bg]boxblur={intensity}:1[bgblur],"
                   "[orig][bgblur]overlay",
    },
}


def list_effects() -> List[Dict[str, Any]]:
    return [
        {"id": k, "category": v["category"],
         "default_params": v["default"]}
        for k, v in EFFECT_CATALOG.items()
    ]


@dataclass
class Effect:
    type: str
    clip_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    start: float = 0.0
    end: float = -1.0         # -1 = entire clip

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "clip_id": self.clip_id,
            "params": self.params,
            "start": self.start,
            "end": self.end,
        }


class EffectEngine:
    """Validate + emit FFmpeg filter fragments for effects."""

    @staticmethod
    def _id(prefix: str) -> str:
        h = hashlib.sha1(prefix.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}-{h}"

    def validate(self, eff: Effect) -> None:
        if eff.type not in EFFECT_CATALOG:
            raise ValueError(f"unknown effect: {eff.type!r}")
        spec = EFFECT_CATALOG[eff.type]
        # Coerce missing defaults in
        merged = dict(spec["default"])
        merged.update(eff.params)
        eff.params = merged
        # Range check
        if "intensity" in merged:
            iv = float(merged["intensity"])
            if eff.type == "blur" and not (1.0 <= iv <= 30.0):
                raise ValueError(f"blur.intensity must be in [1, 30], got {iv}")
            if eff.type in ("sharpen", "vignette", "grain",
                            "denoise") and not (0.0 <= iv <= 1.0):
                raise ValueError(
                    f"{eff.type}.intensity must be in [0, 1], got {iv}")
        if eff.start < 0:
            raise ValueError("start must be >= 0")
        if eff.end != -1 and eff.end <= eff.start:
            raise ValueError("end must be > start (or -1 for full)")

    def build_filter(self, eff: Effect) -> Dict[str, Any]:
        self.validate(eff)
        spec = EFFECT_CATALOG[eff.type]
        # Format the FFmpeg expression with merged params
        expr = spec["ffmpeg"]
        try:
            rendered = expr.format(**eff.params)
        except KeyError as exc:
            raise ValueError(
                f"effect {eff.type!r} missing param: {exc}") from exc
        return {
            "id": self._id(f"{eff.clip_id}-{eff.type}"),
            "type": eff.type,
            "clip_id": eff.clip_id,
            "category": spec["category"],
            "params": eff.params,
            "start": eff.start,
            "end": eff.end,
            "ffmpeg_filter": rendered,
        }

    def apply(self, timeline: Dict[str, Any], clip_id: str,
              type: str, **kwargs: Any) -> Dict[str, Any]:
        eff = Effect(type=type, clip_id=clip_id, params=kwargs)
        built = self.build_filter(eff)
        effects: List[Dict[str, Any]] = list(
            timeline.get("effects") or [])
        effects.append(built)
        timeline["effects"] = effects
        return built
