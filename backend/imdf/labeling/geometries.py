"""P19 v5.5: V5 §十 几何标注 schema — Pydantic v2.

10 几何类型状态 (V5 §十):
  - 6 base (本模块新增, P21 P2 P2 修复 R1-#7):
      * Rect         — 2D axis-aligned bounding box (x, y, w, h)
      * Polygon      — 2D polygon (≥3 points)
      * Point        — single 2D point (x, y)
      * Keypoint     — single skeleton keypoint (x, y, visible, skeleton_id)
      * OBB          — oriented bounding box (cx, cy, w, h, angle)
      * Mask         — segmentation mask (RLE-encoded)
  - 4 3D/segmentation (本模块):
      * Cuboid3D            — 3D cuboid (8 corners + center + dims + rotation)
      * PointCloudLiDAR     — LiDAR point cloud (x,y,z,intensity per point)
      * BBox3D              — axis-aligned 3D bounding box
      * PanopticSegmentation — panoptic seg mask + class labels

每个模型独立 class, 不互相依赖; 支持 JSON 序列化 / 反序列化.
GEOMETRY_REGISTRY maps kebab-case type name -> Pydantic class for downstream
dispatch (e.g. :func:`imdf.skills.registry._register_labeling_skill`).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────────────
# Reusable sub-schemas
# ──────────────────────────────────────────────────────────────────────────────
class Vec3(BaseModel):
    """3D vector (x, y, z)."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


class Quaternion(BaseModel):
    """Unit quaternion (x, y, z, w) — rotation in 3D space.

    On validation, normalizes to unit length (warns via |q| ≈ 1).
    """

    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @field_validator("x", "y", "z", "w")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("quaternion component must be finite")
        return v

    @model_validator(mode="after")
    def _normalize(self) -> "Quaternion":
        norm = math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2 + self.w ** 2)
        if norm == 0:
            raise ValueError("quaternion zero vector is not a valid rotation")
        # Re-normalize to unit length; keep sign convention (w > 0)
        self.x /= norm
        self.y /= norm
        self.z /= norm
        if self.w < 0:
            self.x = -self.x
            self.y = -self.y
            self.z = -self.z
            self.w = -self.w
        self.w /= norm
        return self


class Dimensions3D(BaseModel):
    """3D dimensions (length / width / height). All values must be > 0."""

    model_config = ConfigDict(extra="forbid")

    length: float = Field(..., gt=0, description="Length along X (meters)")
    width: float = Field(..., gt=0, description="Width along Y (meters)")
    height: float = Field(..., gt=0, description="Height along Z (meters)")

    def volume(self) -> float:
        return self.length * self.width * self.height


# ──────────────────────────────────────────────────────────────────────────────
# Cuboid3D — 8 corners + center + dimensions + rotation
# ──────────────────────────────────────────────────────────────────────────────
class Cuboid3D(BaseModel):
    """3D cuboid annotation — 8 corner points + center + dimensions + rotation.

    The 8 corners are in canonical order (right-handed, starting from
    bottom-back-left, going clockwise around the bottom face then the top).
    Optional rotation rotates the local frame from the canonical frame.

    V5 §十: 3d_cuboid — used for object pose / bounding cuboid in 3D space.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="object", min_length=1)
    center: Vec3
    dimensions: Dimensions3D
    rotation: Quaternion = Field(default_factory=Quaternion)
    corners: List[Vec3] = Field(default_factory=list,
                                 description="8 corner points in world frame")

    @field_validator("corners")
    @classmethod
    def _corners_length(cls, v: List[Vec3]) -> List[Vec3]:
        if v and len(v) != 8:
            raise ValueError(f"Cuboid3D must have exactly 8 corners, got {len(v)}")
        return v

    def volume(self) -> float:
        return self.dimensions.volume()


# ──────────────────────────────────────────────────────────────────────────────
# PointCloudLiDAR — LiDAR point cloud
# ──────────────────────────────────────────────────────────────────────────────
class LiDARPoint(BaseModel):
    """Single LiDAR return — 3D position + intensity."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float
    intensity: float = Field(default=0.0, ge=0.0, le=1.0,
                              description="Normalized intensity [0,1]")


class PointCloudLiDAR(BaseModel):
    """LiDAR point cloud — sequence of LiDARPoint + frame metadata.

    V5 §十: lidar_pointcloud — single-frame 3D scan.
    """

    model_config = ConfigDict(extra="forbid")

    frame_id: str = Field(default="frame_0000", min_length=1)
    points: List[LiDARPoint] = Field(default_factory=list)
    sensor_id: Optional[str] = None
    timestamp: Optional[float] = Field(default=None, description="Unix timestamp")

    def n_points(self) -> int:
        return len(self.points)


# ──────────────────────────────────────────────────────────────────────────────
# BBox3D — axis-aligned 3D bounding box
# ──────────────────────────────────────────────────────────────────────────────
class BBox3D(BaseModel):
    """Axis-aligned 3D bounding box — center + size + rotation.

    When ``rotation`` is identity (default), the box is axis-aligned.
    Non-zero rotation is allowed (yaw-only) for nuScenes-style annotations.

    V5 §十: 3d_bbox — axis-aligned 3D box for autonomous driving / robotics.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="object", min_length=1)
    center: Vec3
    x_size: float = Field(..., gt=0, description="Size along X")
    y_size: float = Field(..., gt=0, description="Size along Y")
    z_size: float = Field(..., gt=0, description="Size along Z")
    rotation: Quaternion = Field(default_factory=Quaternion)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    def volume(self) -> float:
        return self.x_size * self.y_size * self.z_size


# ──────────────────────────────────────────────────────────────────────────────
# PanopticSegmentation — instance_id + class_id + mask
# ──────────────────────────────────────────────────────────────────────────────
class PanopticSegmentation(BaseModel):
    """Panoptic segmentation annotation — instance + class IDs + 2D mask.

    ``mask`` is a 2D matrix represented as list of rows (each row is a
    list of integers). Stored as a nested-list to keep the model JSON-
    serializable without requiring numpy at import time. When constructed
    from a numpy array, callers should pass ``mask.tolist()``.

    V5 §十: panoptic — used for Cityscapes / COCO Panoptic-style annotations.
    """

    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(default="image_0000", min_length=1)
    instance_id: int = Field(default=0, ge=0)
    class_id: int = Field(default=0, ge=0)
    class_name: str = Field(default="background", min_length=1)
    is_thing: bool = Field(default=False,
                           description="True for countable objects, False for stuff")
    mask: List[List[int]] = Field(default_factory=list,
                                  description="2D mask as list-of-rows of ints")

    @field_validator("mask")
    @classmethod
    def _mask_rows_consistent(cls, v: List[List[int]]) -> List[List[int]]:
        if v:
            row_len = len(v[0])
            for i, row in enumerate(v):
                if len(row) != row_len:
                    raise ValueError(
                        f"mask rows inconsistent: row 0 has {row_len} cols, "
                        f"row {i} has {len(row)}"
                    )
        return v

    @property
    def height(self) -> int:
        return len(self.mask)

    @property
    def width(self) -> int:
        return len(self.mask[0]) if self.mask else 0

    @property
    def n_pixels(self) -> int:
        return sum(sum(1 for v in row if v > 0) for row in self.mask)


# ──────────────────────────────────────────────────────────────────────────────
# Rect — 2D axis-aligned bounding box (P21 P2 P2: R1-#7 fix)
# ──────────────────────────────────────────────────────────────────────────────
class Rect(BaseModel):
    """2D axis-aligned bounding box — (x, y, w, h) in image coords.

    V5 §十: rect — most common 2D detection annotation.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="object", min_length=1)
    x: float = Field(..., ge=0, description="Top-left x in image pixels")
    y: float = Field(..., ge=0, description="Top-left y in image pixels")
    w: float = Field(..., gt=0, description="Box width (must be > 0)")
    h: float = Field(..., gt=0, description="Box height (must be > 0)")

    def area(self) -> float:
        return self.w * self.h

    def iou(self, other: "Rect") -> float:
        """Intersection-over-Union with another Rect. Returns 0 when disjoint."""
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.w, other.x + other.w)
        y2 = min(self.y + self.h, other.y + other.h)
        inter_w = max(0.0, x2 - x1)
        inter_h = max(0.0, y2 - y1)
        inter = inter_w * inter_h
        union = self.area() + other.area() - inter
        return inter / union if union > 0 else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Polygon — 2D arbitrary polygon (P21 P2 P2: R1-#7 fix)
# ──────────────────────────────────────────────────────────────────────────────
class Polygon(BaseModel):
    """2D polygon — ordered list of (x, y) vertices.

    V5 §十: polygon — instance segmentation, lane markings, region-of-interest.
    At least 3 points required (a polygon needs ≥3 vertices).
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="object", min_length=1)
    points: List[Tuple[float, float]] = Field(..., min_length=3,
                                               description="Ordered vertices (x, y)")

    @field_validator("points")
    @classmethod
    def _finite_points(cls, v: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        for i, p in enumerate(v):
            if len(p) != 2:
                raise ValueError(f"polygon point {i} must be (x, y), got {len(p)}-tuple")
            if not (math.isfinite(p[0]) and math.isfinite(p[1])):
                raise ValueError(f"polygon point {i} has non-finite coords: {p}")
        return v

    def n_points(self) -> int:
        return len(self.points)


# ──────────────────────────────────────────────────────────────────────────────
# Point — single 2D point (P21 P2 P2: R1-#7 fix)
# ──────────────────────────────────────────────────────────────────────────────
class Point(BaseModel):
    """Single 2D point — used for landmark / dot annotation.

    V5 §十: point — sparse detection / landmark labels.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="point", min_length=1)
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")


# ──────────────────────────────────────────────────────────────────────────────
# Keypoint — skeleton keypoint (P21 P2 P2: R1-#7 fix)
# ──────────────────────────────────────────────────────────────────────────────
class Keypoint(BaseModel):
    """Single skeleton keypoint — (x, y) with visibility flag + skeleton id.

    V5 §十: keypoint — pose estimation / hand tracking. ``visible=False`` is
    used for occluded keypoints (COCO convention). ``skeleton_id`` is a small
    int that maps into a model-specific skeleton graph (e.g. COCO-17 has
    skeleton_ids 0..16, body-18 has 0..17).
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="keypoint", min_length=1)
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")
    visible: bool = Field(default=True,
                          description="False if occluded (COCO convention)")
    skeleton_id: int = Field(default=0, ge=0,
                             description="Index into the skeleton graph (e.g. COCO-17: 0..16)")


# ──────────────────────────────────────────────────────────────────────────────
# OBB — oriented bounding box (P21 P2 P2: R1-#7 fix)
# ──────────────────────────────────────────────────────────────────────────────
class OBB(BaseModel):
    """Oriented (rotated) 2D bounding box — center + size + rotation.

    V5 §十: obb — aerial / text-detection annotation where boxes are
    non-axis-aligned. ``angle`` is in radians, counter-clockwise (image-y down
    convention: positive angle = clockwise in image coords).
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="object", min_length=1)
    cx: float = Field(..., description="Center X")
    cy: float = Field(..., description="Center Y")
    w: float = Field(..., gt=0, description="Width (must be > 0)")
    h: float = Field(..., gt=0, description="Height (must be > 0)")
    angle: float = Field(default=0.0, description="Rotation angle in radians")

    @field_validator("angle")
    @classmethod
    def _angle_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("OBB angle must be finite")
        return v

    def area(self) -> float:
        return self.w * self.h


# ──────────────────────────────────────────────────────────────────────────────
# Mask — segmentation mask (P21 P2 P2: R1-#7 fix)
# ──────────────────────────────────────────────────────────────────────────────
class Mask(BaseModel):
    """Segmentation mask — RLE-encoded bytestring (COCO RLE convention).

    V5 §十: mask — dense per-pixel segmentation. Stored as RLE (run-length
    encoding) to keep JSON payloads small; ``width`` and ``height`` are kept
    alongside so the renderer / downstream consumers know the canvas size
    without re-decoding.

    The RLE string format is the COCO convention: a sequence of counts (one
    per row, starting with the first column) — but to keep this model
    dependency-free we accept any non-empty string and treat it as opaque
    RLE bytes. Decoding belongs to a downstream consumer (e.g. pycocotools
    or a custom decoder).
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="object", min_length=1)
    mask_rle: str = Field(..., min_length=1, description="RLE-encoded mask (opaque bytes)")
    width: int = Field(..., gt=0, description="Mask canvas width in pixels")
    height: int = Field(..., gt=0, description="Mask canvas height in pixels")


# ──────────────────────────────────────────────────────────────────────────────
# Helper — geometry registry (maps kebab-case name to Pydantic class)
# ──────────────────────────────────────────────────────────────────────────────
GEOMETRY_REGISTRY: Dict[str, Type[BaseModel]] = {
    # 6 base 2D types (P21 P2 P2 R1-#7 fix)
    "rect": Rect,
    "polygon": Polygon,
    "point": Point,
    "keypoint": Keypoint,
    "obb": OBB,
    "mask": Mask,
    # 4 3D / segmentation types (existing)
    "3d_cuboid": Cuboid3D,
    "lidar_pointcloud": PointCloudLiDAR,
    "3d_bbox": BBox3D,
    "panoptic": PanopticSegmentation,
}
"""V5 §十 all 10 geometry types — maps kebab-case name to Pydantic model class.

P21 P2 P2: changed from ``Dict[str, str]`` (class-name string) to
``Dict[str, Type[BaseModel]]`` (actual class) so downstream code can
``GEOMETRY_REGISTRY["rect"](**payload)`` instead of looking up by name.
Backward-compat: ``imdf.skills.registry._register_labeling_skill`` only
inspects keys (``gtype in GEOMETRY_REGISTRY``) and never reads the values
that the previous Dict[str, str] exposed, so this change is safe.
"""


__all__ = [
    "Vec3",
    "Quaternion",
    "Dimensions3D",
    # 6 base 2D types (P21 P2 P2)
    "Rect",
    "Polygon",
    "Point",
    "Keypoint",
    "OBB",
    "Mask",
    # 4 3D / segmentation types
    "Cuboid3D",
    "LiDARPoint",
    "PointCloudLiDAR",
    "BBox3D",
    "PanopticSegmentation",
    "GEOMETRY_REGISTRY",
]