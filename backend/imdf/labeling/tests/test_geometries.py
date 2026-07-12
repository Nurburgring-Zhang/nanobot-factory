"""P19 v5.5: 4 几何标注 (Cuboid3D / PointCloudLiDAR / BBox3D / PanopticSegmentation) 测试.

覆盖:
  - 4 model instantiate + JSON serialize + deserialize
  - 4 renderer returns non-empty PNG-like bytes
  - BBox3D volume = x_size * y_size * z_size 精确计算
  - invalid input rejection (extra forbid, corners count, mask row consistency)
  - quaternion zero vector rejection
  - cuboid volume calculation

≥10 tests, 实际 14+ 测试覆盖.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# 允许独立运行此测试文件 — 不依赖 imdf.__init__.
_REPO_BACKEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_BACKEND not in sys.path:
    sys.path.insert(0, _REPO_BACKEND)

from labeling.geometries import (  # noqa: E402
    BBox3D,
    Cuboid3D,
    Dimensions3D,
    LiDARPoint,
    PanopticSegmentation,
    PointCloudLiDAR,
    Quaternion,
    Vec3,
)
from labeling.geometry_renderers import (  # noqa: E402
    BBox3DRenderer,
    Cuboid3DRenderer,
    PanopticRenderer,
    PointCloudLiDARRenderer,
    _make_png_bytes,
)


def _png_magic_ok(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers — model factories
# ──────────────────────────────────────────────────────────────────────────────
def make_cuboid() -> Cuboid3D:
    center = Vec3(x=1.0, y=2.0, z=3.0)
    dims = Dimensions3D(length=2.0, width=1.5, height=1.0)
    corners = [Vec3(x=i * 0.1, y=i * 0.1, z=i * 0.1) for i in range(8)]
    return Cuboid3D(
        label="car",
        center=center,
        dimensions=dims,
        rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
        corners=corners,
    )


def make_lidar(n: int = 100) -> PointCloudLiDAR:
    points = [
        LiDARPoint(
            x=float(i) * 0.1,
            y=float(i) * 0.05,
            z=float(i) * 0.02,
            intensity=(i % 100) / 100.0,
        )
        for i in range(n)
    ]
    return PointCloudLiDAR(frame_id="frame_0001", points=points, sensor_id="top_lidar")


def make_bbox3d() -> BBox3D:
    return BBox3D(
        label="vehicle",
        center=Vec3(x=10.0, y=5.0, z=0.0),
        x_size=4.5,
        y_size=2.0,
        z_size=1.5,
        confidence=0.95,
    )


def make_panoptic() -> PanopticSegmentation:
    mask = [
        [0, 0, 1, 1, 0],
        [0, 1, 1, 1, 0],
        [2, 2, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ]
    return PanopticSegmentation(
        image_id="img_001",
        instance_id=7,
        class_id=1,
        class_name="person",
        is_thing=True,
        mask=mask,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. Model instantiate
# ──────────────────────────────────────────────────────────────────────────────
class TestModelInstantiate(unittest.TestCase):

    def test_cuboid_instantiate(self):
        c = make_cuboid()
        self.assertEqual(c.label, "car")
        self.assertEqual(c.dimensions.length, 2.0)
        self.assertEqual(len(c.corners), 8)

    def test_lidar_instantiate(self):
        cloud = make_lidar(n=42)
        self.assertEqual(cloud.frame_id, "frame_0001")
        self.assertEqual(cloud.n_points(), 42)
        self.assertEqual(cloud.sensor_id, "top_lidar")

    def test_bbox3d_instantiate(self):
        b = make_bbox3d()
        self.assertEqual(b.x_size, 4.5)
        self.assertEqual(b.y_size, 2.0)
        self.assertEqual(b.z_size, 1.5)
        self.assertAlmostEqual(b.confidence, 0.95)

    def test_panoptic_instantiate(self):
        p = make_panoptic()
        self.assertEqual(p.width, 5)
        self.assertEqual(p.height, 4)
        self.assertEqual(p.class_name, "person")
        self.assertTrue(p.is_thing)

    def test_quaternion_normalized_to_unit(self):
        q = Quaternion(x=1.0, y=1.0, z=1.0, w=1.0)
        norm = (q.x ** 2 + q.y ** 2 + q.z ** 2 + q.w ** 2) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)


# ──────────────────────────────────────────────────────────────────────────────
# 2. JSON round-trip
# ──────────────────────────────────────────────────────────────────────────────
class TestModelJsonRoundTrip(unittest.TestCase):

    def test_cuboid_round_trip(self):
        c = make_cuboid()
        raw = c.model_dump_json()
        c2 = Cuboid3D.model_validate_json(raw)
        self.assertEqual(c2.label, c.label)
        self.assertEqual(c2.center.x, c.center.x)
        self.assertEqual(c2.dimensions.length, c.dimensions.length)
        self.assertEqual(len(c2.corners), 8)

    def test_lidar_round_trip(self):
        cloud = make_lidar(n=10)
        raw = cloud.model_dump_json()
        cloud2 = PointCloudLiDAR.model_validate_json(raw)
        self.assertEqual(cloud2.frame_id, cloud.frame_id)
        self.assertEqual(cloud2.n_points(), 10)
        self.assertAlmostEqual(cloud2.points[0].x, 0.0)
        self.assertAlmostEqual(cloud2.points[9].x, 0.9)

    def test_bbox3d_round_trip(self):
        b = make_bbox3d()
        raw = b.model_dump_json()
        b2 = BBox3D.model_validate_json(raw)
        self.assertEqual(b2.x_size, b.x_size)
        self.assertEqual(b2.y_size, b.y_size)
        self.assertEqual(b2.z_size, b.z_size)
        self.assertAlmostEqual(b2.confidence, b.confidence)

    def test_panoptic_round_trip(self):
        p = make_panoptic()
        raw = p.model_dump_json()
        p2 = PanopticSegmentation.model_validate_json(raw)
        self.assertEqual(p2.image_id, p.image_id)
        self.assertEqual(p2.class_name, p.class_name)
        self.assertEqual(p2.is_thing, p.is_thing)
        self.assertEqual(p2.width, 5)
        self.assertEqual(p2.height, 4)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Renderer returns non-empty PNG-like bytes
# ──────────────────────────────────────────────────────────────────────────────
class TestRenderers(unittest.TestCase):

    def test_cuboid_renderer(self):
        data = Cuboid3DRenderer().render(make_cuboid())
        self.assertGreater(len(data), 0)
        self.assertTrue(_png_magic_ok(data))

    def test_lidar_renderer(self):
        data = PointCloudLiDARRenderer().render(make_lidar(n=50))
        self.assertGreater(len(data), 0)
        self.assertTrue(_png_magic_ok(data))

    def test_bbox3d_renderer_3viewports(self):
        data, meta = BBox3DRenderer().render_to(make_bbox3d())
        self.assertGreater(len(data), 0)
        # First 4 bytes = panel count (=3)
        self.assertEqual(int.from_bytes(data[:4], "big"), 3)
        self.assertEqual(meta["viewports"], ["top", "front", "side"])

    def test_panoptic_renderer(self):
        data, meta = PanopticRenderer().render_to(make_panoptic())
        self.assertGreater(len(data), 0)
        self.assertEqual(meta["class_name"], "person")
        self.assertEqual(meta["width"], 5)
        self.assertEqual(meta["height"], 4)

    def test_empty_lidar_still_renders(self):
        data = PointCloudLiDARRenderer().render(
            PointCloudLiDAR(frame_id="empty", points=[])
        )
        self.assertGreater(len(data), 0)
        self.assertTrue(_png_magic_ok(data))

    def test_bbox3d_render_view_top(self):
        data = BBox3DRenderer().render_view(make_bbox3d(), "top")
        self.assertGreater(len(data), 0)
        self.assertTrue(_png_magic_ok(data))


# ──────────────────────────────────────────────────────────────────────────────
# 4. Volume / math correctness
# ──────────────────────────────────────────────────────────────────────────────
class TestVolumeCalculations(unittest.TestCase):

    def test_bbox3d_volume(self):
        b = BBox3D(
            label="x", center=Vec3(x=0, y=0, z=0),
            x_size=2.0, y_size=3.0, z_size=4.0,
        )
        self.assertAlmostEqual(b.volume(), 24.0, places=6)

    def test_cuboid_volume_via_dimensions(self):
        dims = Dimensions3D(length=2.0, width=3.0, height=4.0)
        self.assertAlmostEqual(dims.volume(), 24.0, places=6)

    def test_panoptic_n_pixels(self):
        p = PanopticSegmentation(
            image_id="x", class_id=1, class_name="c",
            mask=[
                [0, 1, 1],
                [0, 1, 0],
                [2, 2, 0],
            ],
        )
        # Foreground pixels (value > 0): 4 + 1 = 5
        self.assertEqual(p.n_pixels, 5)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Validation rejects invalid input
# ──────────────────────────────────────────────────────────────────────────────
class TestValidation(unittest.TestCase):

    def test_cuboid_rejects_wrong_corner_count(self):
        with self.assertRaises(Exception):
            Cuboid3D(
                label="x",
                center=Vec3(x=0, y=0, z=0),
                dimensions=Dimensions3D(length=1, width=1, height=1),
                corners=[Vec3(x=0, y=0, z=0) for _ in range(7)],  # only 7
            )

    def test_quaternion_zero_rejected(self):
        with self.assertRaises(Exception):
            Quaternion(x=0.0, y=0.0, z=0.0, w=0.0)

    def test_panoptic_rejects_inconsistent_mask_rows(self):
        with self.assertRaises(Exception):
            PanopticSegmentation(
                image_id="x", class_id=1, class_name="c",
                mask=[[0, 0], [0]],  # row 0 has 2 cols, row 1 has 1
            )

    def test_lidar_intensity_above_1_rejected(self):
        with self.assertRaises(Exception):
            LiDARPoint(x=0, y=0, z=0, intensity=2.0)

    def test_extra_forbid(self):
        # BBox3D has ConfigDict(extra="forbid") — unknown field must raise.
        with self.assertRaises(Exception):
            BBox3D.model_validate({
                "label": "x",
                "center": {"x": 0, "y": 0, "z": 0},
                "x_size": 1.0, "y_size": 1.0, "z_size": 1.0,
                "unknown_field": "bad",  # type: ignore
            })


# ──────────────────────────────────────────────────────────────────────────────
# 6. PNG helper sanity
# ──────────────────────────────────────────────────────────────────────────────
class TestPngHelper(unittest.TestCase):

    def test_make_png_bytes_returns_valid_png(self):
        data = _make_png_bytes(8, 8, b"seed1234")
        self.assertTrue(_png_magic_ok(data))
        # IHDR follows magic + 4 bytes length
        self.assertEqual(data[12:16], b"IHDR")
        # IEND should appear at the end (last 8 bytes: 4 length + "IEND" + 4 crc)
        self.assertEqual(data[-8:-4], b"IEND")

    def test_png_with_zero_size_uses_minimum_canvas(self):
        data = _make_png_bytes(0, 0, b"x")
        self.assertTrue(_png_magic_ok(data))


if __name__ == "__main__":
    unittest.main()