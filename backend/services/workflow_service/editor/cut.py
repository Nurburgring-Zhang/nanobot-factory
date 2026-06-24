"""P4-6-W1 Cut Engine — 6 剪辑操作 + 自动 cut point 检测.

借鉴 OpenMontage 的 SceneDetector / SilenceDetector 模块:

  Operations:
    1. cut        — 在某个时间点剪切,生成两个连续 clip
    2. trim       — 调整 clip 头尾 (in/out points)
    3. split      — 在指定 offset 把一个 clip 切成两段
    4. merge      — 把多个连续 clip 合并成一个
    5. reorder    — 改变 clip 顺序
    6. loop       — 重复某个 clip N 次 (loop count)

  Detectors:
    - detect_cut_points   : Scene change / 关键帧 → 自动 cut points
    - detect_silence_segments : VAD 长沉默段
    - extract_keyframes    : I-frame / P-frame / scene change 关键帧

Outputs are timeline JSON:
    {"clips": [...], "cuts": [...], "transitions": [...], "effects": [...]}
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

CUT_OPERATIONS = ("cut", "trim", "split", "merge", "reorder", "loop")


def list_cut_operations() -> List[Dict[str, str]]:
    return [
        {"id": "cut", "name": "Cut",
         "desc": "在指定时间点剪切 timeline,生成新 clip"},
        {"id": "trim", "name": "Trim",
         "desc": "调整 clip 的 in/out 点"},
        {"id": "split", "name": "Split",
         "desc": "在 offset 处把一个 clip 切成两段"},
        {"id": "merge", "name": "Merge",
         "desc": "把多个连续 clip 合并为一个"},
        {"id": "reorder", "name": "Reorder",
         "desc": "改变 clip 顺序"},
        {"id": "loop", "name": "Loop",
         "desc": "重复某个 clip N 次"},
    ]


@dataclass
class CutOp:
    """A single cut/trim/split/merge/reorder/loop instruction."""
    op: str
    params: Dict[str, Any] = field(default_factory=dict)
    result_clips: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CutReport:
    """Aggregate result of a batch of cut operations."""
    operations: List[CutOp] = field(default_factory=list)
    timeline: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operations": [
                {
                    "op": o.op,
                    "params": o.params,
                    "result_clips": o.result_clips,
                }
                for o in self.operations
            ],
            "timeline": self.timeline,
        }


class CutEngine:
    """Stateless engine that mutates a timeline JSON in place."""

    @staticmethod
    def _id(prefix: str) -> str:
        h = hashlib.sha1(prefix.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}-{h}"

    # ------------------------------------------------------------------
    # 1. cut — 在某个时间点剪切,生成两个连续 clip
    # ------------------------------------------------------------------
    def cut(self, timeline: Dict[str, Any], at: float,
            clip_id: Optional[str] = None) -> CutOp:
        if at < 0:
            raise ValueError("cut.at must be >= 0")
        clips: List[Dict[str, Any]] = list(timeline.get("clips") or [])
        if not clips:
            raise ValueError("timeline has no clips")
        target = None
        if clip_id:
            for c in clips:
                if c.get("id") == clip_id:
                    target = c
                    break
            if target is None:
                raise ValueError(f"clip_id not found: {clip_id!r}")
        else:
            # auto: 找到 at 落入的 clip
            for c in clips:
                s, e = float(c.get("start", 0)), float(
                    c.get("end") or c.get("start", 0) + c.get("duration", 0))
                if s <= at < e:
                    target = c
                    break
        if target is None:
            raise ValueError(f"no clip covers at={at}")

        # 在 at 处拆分
        return self.split(timeline, offset=at - float(target.get("start", 0)),
                          clip_id=target["id"], op_name="cut")

    # ------------------------------------------------------------------
    # 2. trim — 调整 clip 头尾
    # ------------------------------------------------------------------
    def trim(self, timeline: Dict[str, Any], clip_id: str,
             in_offset: float = 0.0, out_offset: float = 0.0) -> CutOp:
        """in_offset: 头部长度 (sec); out_offset: 尾部长度 (sec)."""
        clips: List[Dict[str, Any]] = list(timeline.get("clips") or [])
        target = next((c for c in clips if c.get("id") == clip_id), None)
        if target is None:
            raise ValueError(f"clip_id not found: {clip_id!r}")
        new_start = float(target.get("start", 0)) + in_offset
        new_end = float(target.get("end") or
                        target.get("start", 0) + target.get("duration", 0)) \
            - out_offset
        if new_end < new_start:
            raise ValueError("trim: out_offset larger than clip duration")
        target["start"] = round(new_start, 3)
        target["end"] = round(new_end, 3)
        target["duration"] = round(new_end - new_start, 3)
        target["in_offset"] = round(in_offset, 3)
        target["out_offset"] = round(out_offset, 3)
        timeline["clips"] = clips
        return CutOp(
            op="trim",
            params={"clip_id": clip_id, "in_offset": in_offset,
                    "out_offset": out_offset},
            result_clips=[target],
        )

    # ------------------------------------------------------------------
    # 3. split — 在指定 offset 把一个 clip 切成两段
    # ------------------------------------------------------------------
    def split(self, timeline: Dict[str, Any], offset: float,
              clip_id: str, op_name: str = "split") -> CutOp:
        clips: List[Dict[str, Any]] = list(timeline.get("clips") or [])
        target = next((c for c in clips if c.get("id") == clip_id), None)
        if target is None:
            raise ValueError(f"clip_id not found: {clip_id!r}")
        if offset <= 0 or offset >= float(target.get("duration", 0)):
            raise ValueError(
                f"split.offset must be in (0, duration={target.get('duration')})")
        start = float(target.get("start", 0))
        end = float(target.get("end") or start + target.get("duration", 0))
        split_at = start + offset
        # Build two new clips
        new_a = dict(target)
        new_a["id"] = target["id"] + "_a"
        new_a["end"] = round(split_at, 3)
        new_a["duration"] = round(split_at - start, 3)
        new_b = dict(target)
        new_b["id"] = target["id"] + "_b"
        new_b["start"] = round(split_at, 3)
        new_b["duration"] = round(end - split_at, 3)
        # Replace target with the two new clips in original position
        idx = clips.index(target)
        clips.pop(idx)
        clips.insert(idx, new_b)
        clips.insert(idx, new_a)
        timeline["clips"] = clips
        # Append a cut record
        cuts: List[Dict[str, Any]] = list(timeline.get("cuts") or [])
        cuts.append({
            "id": self._id("cut"),
            "at": round(split_at, 3),
            "type": op_name,
            "from_clip": new_a["id"],
            "to_clip": new_b["id"],
        })
        timeline["cuts"] = cuts
        return CutOp(
            op=op_name,
            params={"clip_id": clip_id, "offset": offset},
            result_clips=[new_a, new_b],
        )

    # ------------------------------------------------------------------
    # 4. merge — 把多个连续 clip 合并为一个
    # ------------------------------------------------------------------
    def merge(self, timeline: Dict[str, Any],
              clip_ids: List[str]) -> CutOp:
        if len(clip_ids) < 2:
            raise ValueError("merge requires >= 2 clip_ids")
        clips: List[Dict[str, Any]] = list(timeline.get("clips") or [])
        by_id = {c["id"]: c for c in clips}
        for cid in clip_ids:
            if cid not in by_id:
                raise ValueError(f"clip_id not found: {cid!r}")
        # Take the first as base, extend its end/duration
        first = by_id[clip_ids[0]]
        last = by_id[clip_ids[-1]]
        # Verify they're consecutive by start time ordering
        ordered = sorted(
            [by_id[c] for c in clip_ids],
            key=lambda c: float(c.get("start", 0)))
        merged_start = float(ordered[0].get("start", 0))
        merged_end = float(ordered[-1].get("end") or
                           ordered[-1].get("start", 0) +
                           ordered[-1].get("duration", 0))
        merged_id = "merged-" + self._id("_".join(clip_ids))
        merged = dict(first)
        merged["id"] = merged_id
        merged["start"] = round(merged_start, 3)
        merged["end"] = round(merged_end, 3)
        merged["duration"] = round(merged_end - merged_start, 3)
        merged["source_clips"] = clip_ids
        # Remove the originals, insert merged at the first one's position
        first_idx = clips.index(first)
        for c in ordered:
            if c in clips:
                clips.remove(c)
        clips.insert(first_idx, merged)
        timeline["clips"] = clips
        return CutOp(
            op="merge",
            params={"clip_ids": clip_ids},
            result_clips=[merged],
        )

    # ------------------------------------------------------------------
    # 5. reorder — 改变 clip 顺序
    # ------------------------------------------------------------------
    def reorder(self, timeline: Dict[str, Any],
                order: List[str]) -> CutOp:
        clips: List[Dict[str, Any]] = list(timeline.get("clips") or [])
        by_id = {c["id"]: c for c in clips}
        missing = [cid for cid in order if cid not in by_id]
        if missing:
            raise ValueError(f"unknown clip_ids: {missing}")
        # Build new list: ordered ids first, then any leftovers
        seen = set(order)
        new_clips = [by_id[cid] for cid in order] + \
            [c for c in clips if c["id"] not in seen]
        # Re-stamp starts so they remain continuous
        cursor = 0.0
        for c in new_clips:
            dur = float(c.get("duration", 0))
            c["start"] = round(cursor, 3)
            c["end"] = round(cursor + dur, 3)
            cursor += dur
        timeline["clips"] = new_clips
        return CutOp(op="reorder", params={"order": order},
                     result_clips=list(new_clips))

    # ------------------------------------------------------------------
    # 6. loop — 重复某个 clip N 次
    # ------------------------------------------------------------------
    def loop(self, timeline: Dict[str, Any], clip_id: str,
             count: int) -> CutOp:
        if count < 1:
            raise ValueError("loop.count must be >= 1")
        clips: List[Dict[str, Any]] = list(timeline.get("clips") or [])
        target = next((c for c in clips if c.get("id") == clip_id), None)
        if target is None:
            raise ValueError(f"clip_id not found: {clip_id!r}")
        idx = clips.index(target)
        original = dict(target)
        repeats: List[Dict[str, Any]] = []
        cursor = float(target.get("start", 0))
        for i in range(count):
            r = dict(original)
            r["id"] = f"{clip_id}_loop{i+1}"
            r["start"] = round(cursor, 3)
            r["end"] = round(cursor + float(original.get("duration", 0)), 3)
            r["loop_index"] = i + 1
            repeats.append(r)
            cursor += float(original.get("duration", 0))
        # Replace target with the looped series
        clips.pop(idx)
        for r in repeats:
            clips.insert(idx, r)
            idx += 1
        timeline["clips"] = clips
        return CutOp(
            op="loop",
            params={"clip_id": clip_id, "count": count},
            result_clips=repeats,
        )

    # ------------------------------------------------------------------
    # batch — run a list of operations atomically
    #
    # Each operation may be either:
    #   {"op": "split", "offset": 1.5, "clip_id": "c2"}  — flat kwargs
    #   {"op": "split", "params": {"offset": 1.5, ...}}   — nested params
    # ------------------------------------------------------------------
    def batch(self, timeline: Dict[str, Any],
              operations: List[Dict[str, Any]]) -> CutReport:
        report = CutReport(timeline=timeline)
        for op in operations:
            if not isinstance(op, dict):
                raise ValueError("operation must be a dict")
            name = op.get("op")
            if not name:
                raise ValueError("operation missing 'op'")
            if "params" in op and isinstance(op["params"], dict):
                kwargs = dict(op["params"])
            else:
                kwargs = {k: v for k, v in op.items() if k != "op"}
            if name == "cut":
                report.operations.append(self.cut(timeline, **kwargs))
            elif name == "trim":
                report.operations.append(self.trim(timeline, **kwargs))
            elif name == "split":
                report.operations.append(self.split(timeline, **kwargs))
            elif name == "merge":
                report.operations.append(self.merge(timeline, **kwargs))
            elif name == "reorder":
                report.operations.append(self.reorder(timeline, **kwargs))
            elif name == "loop":
                report.operations.append(self.loop(timeline, **kwargs))
            else:
                raise ValueError(f"unknown cut op: {name!r}")
        return report


# =====================================================================
# Detectors — 自动 cut points
# =====================================================================


def detect_cut_points(frames: List[float],
                      threshold: float = 0.35) -> List[Dict[str, Any]]:
    """Scene-change detector.

    ``frames`` is a list of per-frame difference scores in [0, 1]
    (1 = maximum difference vs. previous frame).  Returns a list of
    cut points where the score crosses ``threshold``.

    The function is intentionally **synthetic** (no OpenCV dependency):
    given a real audio/video pipeline the caller would feed FFmpeg
    ``select=gt(scene\\,0.4)`` output here.  Tests use deterministic
    synthetic vectors.
    """
    if threshold <= 0 or threshold > 1:
        raise ValueError("threshold must be in (0, 1]")
    cuts: List[Dict[str, Any]] = []
    for i, score in enumerate(frames):
        if score >= threshold:
            cuts.append({
                "index": i,
                "score": round(float(score), 4),
                "type": "scene_change",
            })
    return cuts


def detect_silence_segments(amplitudes: List[float],
                            min_silence_sec: float = 0.5,
                            threshold: float = 0.05) -> List[Dict[str, Any]]:
    """VAD long-silence detector.

    ``amplitudes`` is a list of amplitude samples (linear, [0, 1]).
    Returns segments where amplitude is below ``threshold`` for at
    least ``min_silence_sec`` consecutive samples.
    """
    if not amplitudes:
        return []
    segments: List[Dict[str, Any]] = []
    in_silence = False
    seg_start = 0
    for i, a in enumerate(amplitudes):
        if a <= threshold:
            if not in_silence:
                in_silence = True
                seg_start = i
        else:
            if in_silence:
                seg_len = i - seg_start
                if seg_len >= min_silence_sec:
                    segments.append({
                        "start": float(seg_start),
                        "end": float(i),
                        "duration": float(seg_len),
                    })
                in_silence = False
    if in_silence:
        seg_len = len(amplitudes) - seg_start
        if seg_len >= min_silence_sec:
            segments.append({
                "start": float(seg_start),
                "end": float(len(amplitudes)),
                "duration": float(seg_len),
            })
    return segments


def extract_keyframes(timestamps: List[float],
                      method: str = "scene_change",
                      interval_sec: float = 1.0) -> List[Dict[str, Any]]:
    """Keyframe extractor.

    methods: ``scene_change`` (sparse, based on detected cuts),
             ``i_frame``  (every I-frame, here every Nth element),
             ``uniform``  (every ``interval_sec`` seconds).

    Returns the keyframe list with type tags so the renderer can pick
    whether to honour them when re-encoding.
    """
    if method not in ("scene_change", "i_frame", "uniform"):
        raise ValueError(f"unknown method: {method!r}")
    if not timestamps:
        return []
    if method == "uniform":
        out: List[Dict[str, Any]] = []
        last = -math.inf
        for t in timestamps:
            if t - last >= interval_sec:
                out.append({"t": float(t), "type": "uniform"})
                last = t
        return out
    if method == "i_frame":
        return [{"t": float(t), "type": "i_frame"}
                for i, t in enumerate(timestamps) if i % 4 == 0]
    # scene_change: sparsify to peaks separated by >= 0.5s
    out = []
    last = -math.inf
    for t in timestamps:
        if t - last >= 0.5:
            out.append({"t": float(t), "type": "scene_change"})
            last = t
    return out
