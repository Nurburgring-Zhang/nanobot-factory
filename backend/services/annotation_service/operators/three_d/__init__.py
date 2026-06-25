"""annot.three_d — re-exports for 3 3D annotation operators."""
from services._none_safety import safe_dict_run  # P6-Fix-P0-1: NoneType guard

from . import (
    depth_map,
    lidar_box,
    three_d_mesh,
)

# P6-Fix-P0-1: wrap each module's run() with None-safety guard.
for _mod in (depth_map, lidar_box, three_d_mesh):
    _mod.run = safe_dict_run(_mod.run)  # type: ignore[attr-defined]

__all__ = [
    "depth_map",
    "lidar_box",
    "three_d_mesh",
]