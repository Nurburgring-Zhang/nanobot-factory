"""annot.video — re-exports for 5 video annotation operators."""
from services._none_safety import safe_dict_run  # P6-Fix-P0-1: NoneType guard

from . import (
    tracking,
    action_recognition,
    temporal_seg,
    shot_detection,
    video_caption,
)

# P6-Fix-P0-1: wrap each module's run() with None-safety guard.
for _mod in (tracking, action_recognition, temporal_seg, shot_detection, video_caption):
    _mod.run = safe_dict_run(_mod.run)  # type: ignore[attr-defined]

__all__ = [
    "tracking",
    "action_recognition",
    "temporal_seg",
    "shot_detection",
    "video_caption",
]