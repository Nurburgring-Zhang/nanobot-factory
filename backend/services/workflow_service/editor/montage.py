"""P4-6-W1 Montage Engine — 5 蒙太奇 + 3 时间模式 + BPM sync.

5 montages:
  parallel      — 多视频同步播放 (split screen / PiP)
  cross         — 主题交叉切换
  sequential    — 顺序连接
  thematic      — 按主题分组
  contrast      — 反差对比 (快 vs 慢, 大 vs 小)

3 time modes:
  linear              — 正常时间线
  flashback           — 倒叙
  flashforward        — 闪前
  parallel_timeline   — 多线并行

Layouts:
  split_screen / picture_in_picture / collage

BPM sync:
  - 输入: BPM (int) + clip 数
  - 输出: cut points (sec)  — 0, 60/bpm, 2*60/bpm, ...
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def _NOW() -> float:
    """Local time helper so tests can monkey-patch the timestamp."""
    return time.time()

MONTAGE_TYPES: Tuple[str, ...] = (
    "parallel", "cross", "sequential", "thematic", "contrast",
)

MONTAGE_TIME_MODES: Tuple[str, ...] = (
    "linear", "flashback", "flashforward", "parallel_timeline",
)

# Layout matrix
LAYOUTS: Tuple[str, ...] = (
    "split_screen", "picture_in_picture", "collage",
)


def list_montage_types() -> List[Dict[str, str]]:
    return [
        {"id": "parallel", "name": "Parallel",
         "desc": "多视频同框同步播放"},
        {"id": "cross", "name": "Cross",
         "desc": "主题交叉切换"},
        {"id": "sequential", "name": "Sequential",
         "desc": "顺序连接"},
        {"id": "thematic", "name": "Thematic",
         "desc": "按主题分组"},
        {"id": "contrast", "name": "Contrast",
         "desc": "反差对比 (快/慢/大/小)"},
    ]


def list_time_modes() -> List[Dict[str, str]]:
    return [
        {"id": "linear", "name": "Linear", "desc": "正常时间线"},
        {"id": "flashback", "name": "Flashback", "desc": "倒叙"},
        {"id": "flashforward", "name": "Flashforward", "desc": "闪前"},
        {"id": "parallel_timeline", "name": "Parallel",
         "desc": "多线并行"},
    ]


def bpm_to_cut_points(bpm: int, clip_count: int,
                       offset: float = 0.0) -> List[float]:
    """Given a BPM, return cut points (sec) on a beat grid.

    Each beat = 60 / bpm seconds.  We return ``clip_count`` cut
    points starting from ``offset``.
    """
    if bpm <= 0:
        raise ValueError("bpm must be > 0")
    if clip_count <= 0:
        raise ValueError("clip_count must be > 0")
    beat_sec = 60.0 / bpm
    return [round(offset + i * beat_sec, 3) for i in range(clip_count)]


# ---------------------------------------------------------------------
# Montage plan building
# ---------------------------------------------------------------------

@dataclass
class MontagePlan:
    type: str
    time_mode: str
    layout: str
    clips: List[str] = field(default_factory=list)
    cut_points: List[float] = field(default_factory=list)
    bpm: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "time_mode": self.time_mode,
            "layout": self.layout,
            "clips": self.clips,
            "cut_points": self.cut_points,
            "bpm": self.bpm,
            "params": self.params,
        }


class MontageEngine:

    @staticmethod
    def _id(prefix: str) -> str:
        h = hashlib.sha1(prefix.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}-{h}"

    # ----- plan validation -----
    def validate_plan(self, plan: MontagePlan) -> None:
        if plan.type not in MONTAGE_TYPES:
            raise ValueError(f"unknown montage type: {plan.type!r}")
        if plan.time_mode not in MONTAGE_TIME_MODES:
            raise ValueError(f"unknown time mode: {plan.time_mode!r}")
        if plan.layout not in LAYOUTS:
            raise ValueError(f"unknown layout: {plan.layout!r}")
        if plan.type in ("parallel", "cross", "contrast") \
                and len(plan.clips) < 2:
            raise ValueError(
                f"montage {plan.type!r} requires >= 2 clips")
        if plan.bpm is not None and not (40 <= plan.bpm <= 240):
            raise ValueError(
                f"bpm out of reasonable range [40, 240]: {plan.bpm}")

    # ----- plan building -----
    def build_plan(self, clips: List[str],
                   type: str = "sequential",
                   time_mode: str = "linear",
                   layout: str = "split_screen",
                   bpm: Optional[int] = None,
                   params: Optional[Dict[str, Any]] = None
                   ) -> MontagePlan:
        if type not in MONTAGE_TYPES:
            raise ValueError(f"unknown type: {type!r}")
        plan = MontagePlan(
            type=type, time_mode=time_mode, layout=layout,
            clips=list(clips), bpm=bpm,
            params=params or {},
        )
        # Compute cut points
        if bpm is not None:
            # Use BPM grid
            plan.cut_points = bpm_to_cut_points(bpm, len(clips))
        elif type == "sequential":
            # Equal length: 0, dur, 2*dur, ...
            per = float((params or {}).get("per_clip_sec", 2.0))
            plan.cut_points = [round(i * per, 3) for i in range(len(clips))]
        elif type == "cross":
            per = float((params or {}).get("per_clip_sec", 1.5))
            plan.cut_points = [round(i * per, 3) for i in range(len(clips))]
        elif type == "thematic":
            # 2 segments per group: 0, d, 0+d+d, ...
            per = float((params or {}).get("per_clip_sec", 1.0))
            plan.cut_points = [round(i * per, 3) for i in range(len(clips))]
        elif type == "parallel":
            per = float((params or {}).get("per_clip_sec", 3.0))
            plan.cut_points = [round(i * per, 3) for i in range(len(clips))]
        elif type == "contrast":
            # 快 vs 慢
            per = float((params or {}).get("per_clip_sec", 2.0))
            plan.cut_points = [round(i * per, 3) for i in range(len(clips))]
        self.validate_plan(plan)
        return plan

    # ----- apply (mutates timeline) -----
    def apply(self, timeline: Dict[str, Any],
              clips: List[str],
              type: str = "sequential",
              time_mode: str = "linear",
              layout: str = "split_screen",
              bpm: Optional[int] = None,
              params: Optional[Dict[str, Any]] = None
              ) -> Dict[str, Any]:
        plan = self.build_plan(
            clips=clips, type=type, time_mode=time_mode,
            layout=layout, bpm=bpm, params=params)
        # Re-order clips on the timeline based on time_mode
        if time_mode == "flashback":
            timeline_clips = list(timeline.get("clips") or [])
            # Find and reverse
            sub = [c for c in timeline_clips if c.get("id") in clips]
            sub_idx = [timeline_clips.index(c) for c in sub]
            sub.reverse()
            for idx, c in zip(sub_idx, sub):
                timeline_clips[idx] = c
            timeline["clips"] = timeline_clips
        elif time_mode == "flashforward":
            # Mark each clip with a flashforward tag and record them in a
            # dedicated list on the timeline.  The renderer reads this list to
            # splice a "preview" cut at the head of the montage.
            timeline_clips = list(timeline.get("clips") or [])
            preview_id = self._id(f"flashforward-preview-{type}")
            for c in timeline_clips:
                if c.get("id") in clips:
                    c["flashforward"] = True
                    c.setdefault("tags", []).append("flashforward")
            previews: List[Dict[str, Any]] = list(
                timeline.get("flashforward_previews") or [])
            previews.append({
                "id": preview_id,
                "montage_type": type,
                "montage_layout": layout,
                "clip_ids": list(clips),
                "created_at": _NOW(),
            })
            timeline["clips"] = timeline_clips
            timeline["flashforward_previews"] = previews
        elif time_mode == "parallel_timeline":
            # Mark each clip with a parallel-track id
            track_id = self._id(f"track-{type}")
            for c in list(timeline.get("clips") or []):
                if c.get("id") in clips:
                    c["parallel_track"] = track_id
            timeline["clips"] = list(timeline.get("clips") or [])
        # Insert cuts
        cuts: List[Dict[str, Any]] = list(timeline.get("cuts") or [])
        for cp in plan.cut_points:
            cuts.append({
                "id": self._id(f"montage-cut-{cp}"),
                "at": cp,
                "type": f"montage_{type}",
                "from_clip": "",
                "to_clip": "",
            })
        timeline["cuts"] = cuts
        # Store plan
        montages: List[Dict[str, Any]] = list(
            timeline.get("montages") or [])
        montages.append(plan.to_dict())
        timeline["montages"] = montages
        return plan.to_dict()
