"""P2 P2 fix: ModalKind 3D/LiDAR/Medical/Panoptic + 6 base geometry types.

R2 audit (reports/p21_r2_audit_data.md) found two P0 data-class gaps:

* **R1-#1** — ``ModalKind`` enum in
  ``backend/imdf/multimodal/types.py:19-26`` had only 5/9 spec modalities
  (IMAGE/VIDEO/AUDIO/DOCUMENT/TEXT). The 4 missing members — THREE_D, LIDAR,
  MEDICAL, PANOPTIC — were absent, which meant
  ``ModalKind("3d")`` raised ``ValueError`` and downstream
  :func:`parse_media_item` silently coerced anything (``.glb``/``.las``/``.dcm``
  /``.nii``) to ``ModalKind.IMAGE`` (R2-NEW-#10).

* **R1-#7** — ``GEOMETRY_REGISTRY`` in
  ``backend/imdf/labeling/geometries.py:233-238`` had only 4/10 spec types
  (the 4 3D / segmentation types: ``3d_cuboid``, ``lidar_pointcloud``,
  ``3d_bbox``, ``panoptic``). The 6 base 2D types — ``rect`` / ``polygon`` /
  ``point`` / ``keypoint`` / ``obb`` / ``mask`` — were not implemented in
  Pydantic at all, blocking the annotator workflow for > 90% of common 2D
  tasks.

P2 P2 fix (2026-07-11):

1. Added 4 enum members to ``ModalKind`` (3D/LIDAR/MEDICAL/PANOPTIC).
   Backward-compatible — existing string comparisons keep working.
2. Added 6 new Pydantic v2 ``BaseModel`` classes
   (``Rect``/``Polygon``/``Point``/``Keypoint``/``OBB``/``Mask``) and
   registered them in ``GEOMETRY_REGISTRY`` (now 10 keys).
3. Refactored ``GEOMETRY_REGISTRY`` from ``Dict[str, str]`` (class-name
   string) to ``Dict[str, Type[BaseModel]]`` (actual class) so downstream
   code can ``GEOMETRY_REGISTRY["rect"](**payload)`` directly. The only
   in-tree consumer
   (:func:`imdf.skills.registry._register_labeling_skill`) only inspects
   keys, so this is safe.

This test file pins:

* The 9 ModalKind members are present (5 original + 4 new).
* ``ModalKind("3d") == ModalKind.THREE_D`` etc. — string → enum lookup works
  for every new member.
* ``GEOMETRY_REGISTRY`` has all 10 keys.
* Each of the 6 new geometry classes can be constructed with valid args
  and round-trips through ``model_dump_json`` / ``model_validate_json``.
* Backward compat — the original 5 ModalKind strings still work; the
  original 4 registry keys still point to their classes.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

# ==== Path bootstrap (matches sibling p2_p2 tests) ==========================
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _PROJECT_ROOT / "backend"

# Make ``from backend.imdf.multimodal.types import ...`` work
for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ==== Imports under test ====================================================
try:
    from backend.imdf.multimodal.types import ModalKind  # type: ignore  # noqa: E402
except Exception:
    from imdf.multimodal.types import ModalKind  # type: ignore  # noqa: E402

try:
    from backend.imdf.labeling.geometries import (  # type: ignore  # noqa: E402
        GEOMETRY_REGISTRY,
        Rect,
        Polygon,
        Point,
        Keypoint,
        OBB,
        Mask,
        Cuboid3D,
        PointCloudLiDAR,
        BBox3D,
        PanopticSegmentation,
    )
except Exception:
    from imdf.labeling.geometries import (  # type: ignore  # noqa: E402
        GEOMETRY_REGISTRY,
        Rect,
        Polygon,
        Point,
        Keypoint,
        OBB,
        Mask,
        Cuboid3D,
        PointCloudLiDAR,
        BBox3D,
        PanopticSegmentation,
    )


# ===========================================================================
# Section 1 — ModalKind: 9 members, including 4 NEW (P21 P2 P2 R1-#1 fix)
# ===========================================================================
EXPECTED_MODALKIND = {
    # Original 5 (must keep working — backward compat)
    "image": "IMAGE",
    "video": "VIDEO",
    "audio": "AUDIO",
    "document": "DOCUMENT",
    "text": "TEXT",
    # 4 NEW (the fix)
    "3d": "THREE_D",
    "lidar": "LIDAR",
    "medical": "MEDICAL",
    "panoptic": "PANOPTIC",
}


def test_modalkind_has_all_9_members():
    """ModalKind must expose all 9 spec members (5 original + 4 NEW)."""
    actual = {m.name: m.value for m in ModalKind}
    # EXPECTED_MODALKIND is keyed by value (e.g. "3d") → name (e.g. "THREE_D").
    # Flip it to name → value for direct comparison.
    expected_by_name = {name: value for value, name in EXPECTED_MODALKIND.items()}
    assert len(actual) == 9, f"ModalKind has {len(actual)} members, expected 9: {actual}"
    assert actual == expected_by_name, (
        f"ModalKind mismatch — missing: {set(expected_by_name) - set(actual)}, "
        f"unexpected: {set(actual) - set(expected_by_name)}"
    )


@pytest.mark.parametrize("value,name", list(EXPECTED_MODALKIND.items()))
def test_modalkind_string_lookup(value, name):
    """``ModalKind(value)`` must equal ``getattr(ModalKind, name)`` for every spec."""
    assert ModalKind(value) == getattr(ModalKind, name), (
        f"ModalKind({value!r}) should equal ModalKind.{name}"
    )


def test_modalkind_new_members_distinct():
    """Each new enum member must be distinct (no value collisions)."""
    new_members = [ModalKind.THREE_D, ModalKind.LIDAR, ModalKind.MEDICAL, ModalKind.PANOPTIC]
    assert len(set(new_members)) == 4
    # Also check value distinctness
    assert len({m.value for m in new_members}) == 4


def test_modalkind_is_str_enum():
    """ModalKind must still be a str-Enum (so JSON-friendly + string-comparable).

    Note on ``str()``: Python's str-Enum ``str(ModalKind.THREE_D)`` returns
    the *name* ``"ModalKind.THREE_D"`` (because Enum.__str__ falls back to
    "ClassName.Name"), NOT the value. Use ``.value`` to get ``"3d"`` and
    use ``==`` to compare against plain strings.
    """
    assert ModalKind.IMAGE == "image"
    assert ModalKind.THREE_D == "3d"
    assert ModalKind.LIDAR == "lidar"
    # ``.value`` is the canonical way to get the underlying string
    assert ModalKind.THREE_D.value == "3d"
    assert ModalKind.PANOPTIC.value == "panoptic"
    # str-Enum equality with plain string (this is the Pydantic-friendly behavior)
    assert (ModalKind.THREE_D == "3d") is True
    assert (ModalKind.LIDAR == "lidar") is True


def test_modalkind_invalid_value_raises():
    """An unknown modality string must raise ValueError (not silently coerce)."""
    with pytest.raises(ValueError):
        ModalKind("not_a_real_modality")


def test_modalkind_string_equality_backward_compat():
    """Existing string comparisons (e.g. ``kind == 'image'``) must keep working."""
    # Original 5
    assert ModalKind.IMAGE == "image"
    assert ModalKind.VIDEO == "video"
    # New 4
    assert ModalKind.THREE_D == "3d"
    assert ModalKind.LIDAR == "lidar"
    assert ModalKind.MEDICAL == "medical"
    assert ModalKind.PANOPTIC == "panoptic"


# ===========================================================================
# Section 2 — GEOMETRY_REGISTRY: 10 keys, including 6 NEW (P21 P2 P2 R1-#7)
# ===========================================================================
EXPECTED_REGISTRY_KEYS = {
    # 6 NEW (the fix)
    "rect", "polygon", "point", "keypoint", "obb", "mask",
    # 4 existing (must keep working — backward compat)
    "3d_cuboid", "lidar_pointcloud", "3d_bbox", "panoptic",
}


def test_geometry_registry_has_all_10_keys():
    """GEOMETRY_REGISTRY must expose all 10 spec keys."""
    actual = set(GEOMETRY_REGISTRY.keys())
    assert len(actual) == 10, (
        f"GEOMETRY_REGISTRY has {len(actual)} keys, expected 10: {sorted(actual)}"
    )
    missing = EXPECTED_REGISTRY_KEYS - actual
    assert not missing, f"GEOMETRY_REGISTRY missing keys: {missing}"


def test_geometry_registry_values_are_classes():
    """Each value must be a Pydantic BaseModel class (so callers can instantiate)."""
    from pydantic import BaseModel
    for key, cls in GEOMETRY_REGISTRY.items():
        assert isinstance(cls, type), f"{key!r} maps to non-type: {cls!r}"
        assert issubclass(cls, BaseModel), (
            f"{key!r} maps to {cls.__name__} which is not a Pydantic BaseModel"
        )


def test_geometry_registry_existing_keys_preserved():
    """The original 4 3D / segmentation types must still point to the right classes."""
    assert GEOMETRY_REGISTRY["3d_cuboid"] is Cuboid3D
    assert GEOMETRY_REGISTRY["lidar_pointcloud"] is PointCloudLiDAR
    assert GEOMETRY_REGISTRY["3d_bbox"] is BBox3D
    assert GEOMETRY_REGISTRY["panoptic"] is PanopticSegmentation


def test_geometry_registry_new_keys_point_to_new_classes():
    """The 6 new keys must point to the 6 new Pydantic classes."""
    assert GEOMETRY_REGISTRY["rect"] is Rect
    assert GEOMETRY_REGISTRY["polygon"] is Polygon
    assert GEOMETRY_REGISTRY["point"] is Point
    assert GEOMETRY_REGISTRY["keypoint"] is Keypoint
    assert GEOMETRY_REGISTRY["obb"] is OBB
    assert GEOMETRY_REGISTRY["mask"] is Mask


# ===========================================================================
# Section 3 — 6 new geometry classes: construct + JSON roundtrip
# ===========================================================================
class TestRect:
    """Rect — 2D axis-aligned bounding box."""

    def test_construct_and_area(self):
        r = Rect(label="car", x=10.0, y=20.0, w=100.0, h=50.0)
        assert r.label == "car"
        assert r.x == 10.0
        assert r.w == 100.0
        assert r.area() == 5000.0

    def test_json_roundtrip(self):
        r = Rect(label="dog", x=0.0, y=0.0, w=50.0, h=80.0)
        s = r.model_dump_json()
        d = json.loads(s)
        assert d == {"label": "dog", "x": 0.0, "y": 0.0, "w": 50.0, "h": 80.0}
        r2 = Rect.model_validate_json(s)
        assert r == r2

    def test_zero_size_rejected(self):
        """w=0 must raise (Field gt=0)."""
        with pytest.raises(Exception):  # ValidationError
            Rect(label="x", x=0, y=0, w=0, h=10)

    def test_iou_self_is_one(self):
        r = Rect(label="x", x=0, y=0, w=10, h=10)
        assert r.iou(r) == 1.0

    def test_iou_disjoint_is_zero(self):
        a = Rect(label="x", x=0, y=0, w=10, h=10)
        b = Rect(label="y", x=100, y=100, w=10, h=10)
        assert a.iou(b) == 0.0


class TestPolygon:
    """Polygon — ordered list of (x, y) vertices."""

    def test_construct(self):
        p = Polygon(label="lane", points=[(0, 0), (10, 0), (10, 10), (0, 10)])
        assert p.label == "lane"
        assert p.n_points() == 4

    def test_json_roundtrip(self):
        p = Polygon(label="r", points=[(0.0, 0.0), (1.5, 0.0), (1.5, 1.5), (0.0, 1.5)])
        s = p.model_dump_json()
        d = json.loads(s)
        assert d["label"] == "r"
        assert d["points"] == [[0.0, 0.0], [1.5, 0.0], [1.5, 1.5], [0.0, 1.5]]
        p2 = Polygon.model_validate_json(s)
        assert p == p2

    def test_min_3_vertices_required(self):
        with pytest.raises(Exception):  # ValidationError (min_length=3)
            Polygon(label="x", points=[(0, 0), (1, 1)])

    def test_non_finite_coords_rejected(self):
        with pytest.raises(Exception):
            Polygon(label="x", points=[(0, 0), (math.inf, 0), (1, 1)])


class TestPoint:
    """Point — single 2D point."""

    def test_construct(self):
        p = Point(label="dot", x=3.5, y=-2.0)
        assert p.label == "dot"
        assert p.x == 3.5
        assert p.y == -2.0

    def test_json_roundtrip(self):
        p = Point(label="landmark", x=100.5, y=200.5)
        s = p.model_dump_json()
        d = json.loads(s)
        assert d == {"label": "landmark", "x": 100.5, "y": 200.5}
        p2 = Point.model_validate_json(s)
        assert p == p2


class TestKeypoint:
    """Keypoint — skeleton keypoint (x, y, visible, skeleton_id)."""

    def test_construct_defaults(self):
        kp = Keypoint(label="nose", x=1.0, y=2.0)
        assert kp.visible is True  # default
        assert kp.skeleton_id == 0  # default

    def test_construct_explicit(self):
        kp = Keypoint(label="left_eye", x=10.0, y=20.0,
                      visible=False, skeleton_id=1)
        assert kp.visible is False
        assert kp.skeleton_id == 1

    def test_json_roundtrip(self):
        kp = Keypoint(label="r_elbow", x=50.0, y=60.0,
                      visible=True, skeleton_id=2)
        s = kp.model_dump_json()
        d = json.loads(s)
        assert d == {"label": "r_elbow", "x": 50.0, "y": 60.0,
                     "visible": True, "skeleton_id": 2}
        kp2 = Keypoint.model_validate_json(s)
        assert kp == kp2

    def test_negative_skeleton_id_rejected(self):
        with pytest.raises(Exception):  # ge=0
            Keypoint(label="x", x=0, y=0, skeleton_id=-1)


class TestOBB:
    """OBB — oriented bounding box (cx, cy, w, h, angle)."""

    def test_construct(self):
        o = OBB(label="plane", cx=5.0, cy=5.0, w=3.0, h=4.0, angle=0.5)
        assert o.cx == 5.0
        assert o.area() == 12.0
        assert o.angle == 0.5

    def test_json_roundtrip(self):
        o = OBB(label="text", cx=100.0, cy=50.0, w=80.0, h=20.0, angle=1.57)
        s = o.model_dump_json()
        d = json.loads(s)
        assert d == {"label": "text", "cx": 100.0, "cy": 50.0,
                     "w": 80.0, "h": 20.0, "angle": 1.57}
        o2 = OBB.model_validate_json(s)
        assert o == o2

    def test_zero_width_rejected(self):
        with pytest.raises(Exception):  # gt=0
            OBB(label="x", cx=0, cy=0, w=0, h=1)

    def test_nan_angle_rejected(self):
        with pytest.raises(Exception):
            OBB(label="x", cx=0, cy=0, w=1, h=1, angle=math.nan)


class TestMask:
    """Mask — segmentation mask (RLE + canvas size)."""

    def test_construct(self):
        m = Mask(label="seg", mask_rle="abc123", width=640, height=480)
        assert m.label == "seg"
        assert m.mask_rle == "abc123"
        assert m.width == 640
        assert m.height == 480

    def test_json_roundtrip(self):
        m = Mask(label="seg", mask_rle="XYZ", width=100, height=200)
        s = m.model_dump_json()
        d = json.loads(s)
        assert d == {"label": "seg", "mask_rle": "XYZ",
                     "width": 100, "height": 200}
        m2 = Mask.model_validate_json(s)
        assert m == m2

    def test_empty_rle_rejected(self):
        with pytest.raises(Exception):  # min_length=1
            Mask(label="x", mask_rle="", width=1, height=1)

    def test_zero_dim_rejected(self):
        with pytest.raises(Exception):  # gt=0
            Mask(label="x", mask_rle="x", width=0, height=1)


# ===========================================================================
# Section 4 — Integration: GEOMETRY_REGISTRY[name](**payload) round-trip
# ===========================================================================
def test_registry_can_instantiate_all_10_types():
    """Every registry value must be instantiable with sensible defaults."""
    # Each entry is (class, valid_payload)
    cases = {
        "rect": {"label": "x", "x": 0, "y": 0, "w": 10, "h": 10},
        "polygon": {"label": "x", "points": [(0, 0), (1, 0), (1, 1)]},
        "point": {"label": "x", "x": 0, "y": 0},
        "keypoint": {"label": "x", "x": 0, "y": 0},
        "obb": {"label": "x", "cx": 0, "cy": 0, "w": 1, "h": 1},
        "mask": {"label": "x", "mask_rle": "a", "width": 1, "height": 1},
        "3d_cuboid": {
            "label": "x",
            "center": {"x": 0, "y": 0, "z": 0},
            "dimensions": {"length": 1, "width": 1, "height": 1},
        },
        "lidar_pointcloud": {"frame_id": "f0"},
        "3d_bbox": {
            "label": "x",
            "center": {"x": 0, "y": 0, "z": 0},
            "x_size": 1, "y_size": 1, "z_size": 1,
        },
        "panoptic": {"image_id": "img0"},
    }
    for gtype, payload in cases.items():
        cls = GEOMETRY_REGISTRY[gtype]
        inst = cls(**payload)
        # And it can serialize + re-parse
        s = inst.model_dump_json()
        re_inst = cls.model_validate_json(s)
        assert re_inst == inst, f"{gtype} roundtrip mismatch: {inst} vs {re_inst}"


# ===========================================================================
# Section 5 — R2 reproducer (before/after evidence)
# ===========================================================================
def test_r1_d1_reproducer_now_passes():
    """R1-#1 reproducer: list ModalKind values; 4 new ones must be present.

    Pre-fix: ``[m.value for m in ModalKind]`` returned
    ``['image','video','audio','document','text']`` (5 members).
    Post-fix: returns 9 members including ``'3d'``, ``'lidar'``,
    ``'medical'``, ``'panoptic'``.
    """
    actual = sorted(m.value for m in ModalKind)
    assert "3d" in actual
    assert "lidar" in actual
    assert "medical" in actual
    assert "panoptic" in actual
    assert len(actual) == 9


def test_r1_d7_reproducer_now_passes():
    """R1-#7 reproducer: list GEOMETRY_REGISTRY keys; 6 new ones must be present.

    Pre-fix: ``GEOMETRY_REGISTRY.keys()`` returned
    ``{'3d_cuboid', 'lidar_pointcloud', '3d_bbox', 'panoptic'}`` (4 keys).
    Post-fix: includes ``'rect'``, ``'polygon'``, ``'point'``, ``'keypoint'``,
    ``'obb'``, ``'mask'`` (10 keys total).
    """
    actual = set(GEOMETRY_REGISTRY.keys())
    for k in ("rect", "polygon", "point", "keypoint", "obb", "mask"):
        assert k in actual, f"R1-#7 NOT FIXED: {k!r} missing from GEOMETRY_REGISTRY"
    assert len(actual) == 10
