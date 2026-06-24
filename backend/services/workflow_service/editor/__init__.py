"""P4-6-W1 Video Editor — 视频编辑核心 (借鉴 OpenMontage + Remotion 思路).

Public surface:
  - ``editor.cut``         Cut/trim/split/merge/reorder/loop + cut-point detection
  - ``editor.transition``  12 transition types + ease/cubic-bezier
  - ``editor.effect``      16 effects (color / aesthetic / utility)
  - ``editor.montage``     5 montages + BPM sync
  - ``editor.render``      Final FFmpeg render with progress
  - ``editor.project``     Project / version snapshot / collaboration

The editor operates on an in-memory timeline JSON
(``Timeline -> Clips[] -> Cuts[]/Transitions[]/Effects[]``) and never
touches the real video bytes directly.  The render step funnels the
timeline into a single FFmpeg filter graph.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .cut import (
    CUT_OPERATIONS,
    CutEngine,
    detect_cut_points,
    detect_silence_segments,
    extract_keyframes,
    list_cut_operations,
)
from .effect import (
    EFFECT_CATALOG,
    EffectEngine,
    list_effects,
)
from .montage import (
    MONTAGE_TYPES,
    MONTAGE_TIME_MODES,
    MontageEngine,
    bpm_to_cut_points,
    list_montage_types,
    list_time_modes,
)
from .project import (
    EditorProject,
    ProjectStore,
    get_project_store,
)
from .render import (
    RENDER_CODECS,
    RENDER_RESOLUTIONS,
    RenderEngine,
    get_render_engine,
)
from .transition import (
    TRANSITION_TYPES,
    TransitionEngine,
    EASING_FUNCTIONS,
    list_easing_functions,
    list_transitions,
)


__all__ = [
    # cut
    "CUT_OPERATIONS", "CutEngine", "detect_cut_points",
    "detect_silence_segments", "extract_keyframes", "list_cut_operations",
    # transition
    "TRANSITION_TYPES", "TransitionEngine", "EASING_FUNCTIONS",
    "list_easing_functions", "list_transitions",
    # effect
    "EFFECT_CATALOG", "EffectEngine", "list_effects",
    # montage
    "MONTAGE_TYPES", "MONTAGE_TIME_MODES", "MontageEngine",
    "bpm_to_cut_points", "list_montage_types", "list_time_modes",
    # project
    "EditorProject", "ProjectStore", "get_project_store",
    # render
    "RENDER_CODECS", "RENDER_RESOLUTIONS", "RenderEngine",
    "get_render_engine",
]


def get_timeline_summary(timeline: Dict[str, Any]) -> Dict[str, Any]:
    """Helper for routes: summarise a timeline JSON.

    Expected shape (all keys optional, defaults applied):
        {
          "clips": [{"id","src","start","end","duration"}, ...],
          "cuts":  [{"at", "type"}, ...],
          "transitions": [{"type","from_clip","to_clip","duration"}],
          "effects":     [{"clip_id","type","params"}],
        }
    """
    clips = timeline.get("clips") or []
    cuts = timeline.get("cuts") or []
    transitions = timeline.get("transitions") or []
    effects = timeline.get("effects") or []
    total_dur = sum(
        float(c.get("duration") or 0.0)
        for c in clips
    )
    return {
        "clips": len(clips),
        "cuts": len(cuts),
        "transitions": len(transitions),
        "effects": len(effects),
        "total_duration_sec": round(total_dur, 3),
    }
