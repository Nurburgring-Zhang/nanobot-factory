"""P4-6-W1 Transition Engine — 12 转场 + 缓动函数.

12 types:
  fade, dissolve, wipe, slide, zoom, blur, glitch,
  match_cut, j_cut, l_cut, cross_dissolve, dip_to_color

Duration: 0.3 - 2.0 s, validated.
Easing: linear / ease-in / ease-out / ease-in-out / cubic-bezier(...)

Each transition emits an FFmpeg filter-graph fragment so the render
engine can compose the timeline into a single ``-filter_complex``
expression.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TRANSITION_TYPES: Tuple[str, ...] = (
    "fade", "dissolve", "wipe", "slide", "zoom", "blur", "glitch",
    "match_cut", "j_cut", "l_cut", "cross_dissolve", "dip_to_color",
)

# Per-type defaults: min/max duration + a default color (for dip_to_color)
_TRANSITION_META: Dict[str, Dict[str, Any]] = {
    "fade":            {"min": 0.3, "max": 2.0, "default": 0.5},
    "dissolve":        {"min": 0.3, "max": 2.0, "default": 0.7},
    "wipe":            {"min": 0.3, "max": 1.5, "default": 0.6},
    "slide":           {"min": 0.3, "max": 1.5, "default": 0.5},
    "zoom":            {"min": 0.3, "max": 1.5, "default": 0.5},
    "blur":            {"min": 0.3, "max": 1.5, "default": 0.6},
    "glitch":          {"min": 0.2, "max": 1.0, "default": 0.3},
    "match_cut":       {"min": 0.0, "max": 0.3, "default": 0.1},
    "j_cut":           {"min": 0.3, "max": 2.0, "default": 0.8},
    "l_cut":           {"min": 0.3, "max": 2.0, "default": 0.8},
    "cross_dissolve":  {"min": 0.3, "max": 2.0, "default": 0.7},
    "dip_to_color":    {"min": 0.3, "max": 2.0, "default": 0.6,
                        "color": "black"},
}

EASING_FUNCTIONS: Tuple[str, ...] = (
    "linear", "ease-in", "ease-out", "ease-in-out",
    "cubic-bezier(0.4,0,0.2,1)", "cubic-bezier(0.68,-0.55,0.27,1.55)",
)


def list_easing_functions() -> List[Dict[str, str]]:
    return [
        {"id": "linear", "name": "Linear", "desc": "匀速"},
        {"id": "ease-in", "name": "Ease In", "desc": "缓入"},
        {"id": "ease-out", "name": "Ease Out", "desc": "缓出"},
        {"id": "ease-in-out", "name": "Ease In-Out", "desc": "缓入缓出"},
        {"id": "cubic-bezier(0.4,0,0.2,1)",
         "name": "Material Standard",
         "desc": "Material Design 标准曲线"},
        {"id": "cubic-bezier(0.68,-0.55,0.27,1.55)",
         "name": "Back Out", "desc": "带回弹"},
    ]


def list_transitions() -> List[Dict[str, Any]]:
    return [
        {"id": t,
         "min_duration": _TRANSITION_META[t]["min"],
         "max_duration": _TRANSITION_META[t]["max"],
         "default_duration": _TRANSITION_META[t]["default"]}
        for t in TRANSITION_TYPES
    ]


# ---------------------------------------------------------------------
# Easing evaluation — used by the renderer to map t∈[0,1] → opacity
# ---------------------------------------------------------------------

def apply_easing(t: float, easing: str) -> float:
    """Map normalized time t∈[0,1] through the named easing curve.

    Returns a value in [0, 1] (overshoots clipped to 0..1.05).
    """
    t = max(0.0, min(1.0, float(t)))
    if easing == "linear":
        return t
    if easing == "ease-in":
        return t * t
    if easing == "ease-out":
        return 1 - (1 - t) * (1 - t)
    if easing == "ease-in-out":
        return 3 * t * t - 2 * t * t * t
    if easing.startswith("cubic-bezier"):
        # parse (x1,y1,x2,y2)
        try:
            inside = easing[easing.index("(") + 1:easing.index(")")]
            parts = [float(p.strip()) for p in inside.split(",")]
            x1, y1, x2, y2 = parts
        except (ValueError, IndexError) as exc:
            raise ValueError(f"bad cubic-bezier: {easing}") from exc
        return _cubic_bezier(t, x1, y1, x2, y2)
    raise ValueError(f"unknown easing: {easing!r}")


def _cubic_bezier(t: float, x1: float, y1: float,
                  x2: float, y2: float) -> float:
    """Compute y(t) for a 2D cubic-bezier with implicit control points
    (0,0) and (1,1) — Newton-Raphson 6 iterations to invert x.
    """
    # Sample x at parameter u in [0, 1] (curve parametric over u, not t)
    def _bx(u: float) -> float:
        return 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3

    def _by(u: float) -> float:
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3

    # Newton-Raphson: solve x(u) - t = 0
    u = t
    for _ in range(8):
        x = _bx(u)
        if abs(x - t) < 1e-5:
            break
        # derivative dx/du ≈ 3(1-u)^2 x1 + 6u(1-u)(x2-x1) + 3u^2(1-x2)
        dx = (3 * (1 - u) ** 2 * x1
              + 6 * u * (1 - u) * (x2 - x1)
              + 3 * u ** 2 * (1 - x2))
        if abs(dx) < 1e-6:
            break
        u = u - (x - t) / dx
    return max(0.0, min(1.05, _by(u)))


# ---------------------------------------------------------------------
# Transition building
# ---------------------------------------------------------------------

@dataclass
class Transition:
    type: str
    duration: float
    from_clip: str
    to_clip: str
    easing: str = "ease-in-out"
    color: str = "black"
    direction: str = "left"        # wipe / slide direction
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "duration": self.duration,
            "from_clip": self.from_clip,
            "to_clip": self.to_clip,
            "easing": self.easing,
            "color": self.color,
            "direction": self.direction,
            "params": self.params,
        }


class TransitionEngine:
    """Builds FFmpeg filter-graph fragments for each transition type."""

    @staticmethod
    def _id(prefix: str) -> str:
        h = hashlib.sha1(prefix.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}-{h}"

    def validate(self, trans: Transition) -> None:
        if trans.type not in TRANSITION_TYPES:
            raise ValueError(f"unknown transition type: {trans.type!r}")
        meta = _TRANSITION_META[trans.type]
        if not (meta["min"] <= trans.duration <= meta["max"]):
            raise ValueError(
                f"transition {trans.type!r} duration "
                f"{trans.duration} out of range "
                f"[{meta['min']}, {meta['max']}]")
        if trans.easing not in EASING_FUNCTIONS:
            raise ValueError(f"unknown easing: {trans.easing!r}")

    def build_filter(self, trans: Transition) -> Dict[str, Any]:
        """Build the FFmpeg filter fragment for a transition."""
        self.validate(trans)
        d = trans.duration
        keyframes: List[Dict[str, Any]] = []
        # Sample 5 keyframes for preview
        for k in (0.0, 0.25, 0.5, 0.75, 1.0):
            eased = apply_easing(k, trans.easing)
            keyframes.append({"t": round(k * d, 3),
                              "eased": round(eased, 4)})
        if trans.type in ("fade", "dissolve", "cross_dissolve"):
            expr = (f"xfade=transition=fade:duration={d}:"
                    f"offset=0")
        elif trans.type == "wipe":
            direction = trans.direction
            expr = (f"xfade=transition=wipe{direction}:duration={d}:"
                    f"offset=0")
        elif trans.type == "slide":
            direction = trans.direction
            expr = (
                f"xfade=transition=slide{direction}:"
                f"duration={d}:offset=0"
            )
        elif trans.type == "zoom":
            expr = f"xfade=transition=zoomin:duration={d}:offset=0"
        elif trans.type == "blur":
            expr = (f"xfade=transition=fadeblack:duration={d}:offset=0,"
                    f"boxblur=10:enable='between(t,0,{d})'")
        elif trans.type == "glitch":
            expr = (f"xfade=transition=pixelize:duration={d}:offset=0")
        elif trans.type == "match_cut":
            # 几乎零时长,仅裁切对齐
            expr = f"xfade=transition=fade:duration={d}:offset=0"
        elif trans.type == "j_cut":
            # J-cut: 下一段音频先入 (audio offset negative)
            expr = (f"xfade=transition=fade:duration={d}:offset=0,"
                    f"adelay=delays=-{int(d*1000)}:all=1")
        elif trans.type == "l_cut":
            # L-cut: 当前段音频延后 (audio offset positive)
            expr = (f"xfade=transition=fade:duration={d}:offset=0,"
                    f"adelay=delays={int(d*1000)}:all=1")
        elif trans.type == "dip_to_color":
            color = trans.color or "black"
            expr = (f"xfade=transition=fadeblack:duration={d}:offset=0,"
                    f"drawbox=color={color}:t=fill")
        else:
            raise ValueError(f"unsupported: {trans.type}")
        return {
            "id": self._id(f"{trans.from_clip}-{trans.to_clip}"),
            "type": trans.type,
            "duration": d,
            "easing": trans.easing,
            "color": trans.color,
            "direction": trans.direction,
            "keyframes": keyframes,
            "ffmpeg_filter": expr,
        }

    def apply(self, timeline: Dict[str, Any],
              from_clip: str, to_clip: str,
              type: str = "fade",
              duration: float = 0.5,
              easing: str = "ease-in-out",
              **kwargs: Any) -> Dict[str, Any]:
        if from_clip == to_clip:
            raise ValueError("from_clip and to_clip must differ")
        trans = Transition(
            type=type, duration=duration, from_clip=from_clip,
            to_clip=to_clip, easing=easing, **kwargs)
        built = self.build_filter(trans)
        transitions: List[Dict[str, Any]] = list(
            timeline.get("transitions") or [])
        transitions.append(built)
        timeline["transitions"] = transitions
        return built
