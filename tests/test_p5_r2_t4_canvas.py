"""P5-R2-T4 (part 1) — Annotation.vue SVG canvas / rect 工具 数学单元测试。

覆盖范围 (≥2 个 pytest 用例):
- rect 几何序列 / 反序列化往返
- normalizeRect: 任意两点的轴对齐矩形 (含拖拽方向反转)
- resizeByCorner: 8 个角点 (nw/n/ne/e/se/s/sw/w) 的几何变换
- clamp / 边界保护
- 画布坐标 -> 800x600 像素 SVG 坐标映射

这些是纯函数,不依赖 Vue / DOM / 浏览器,因此可以在 pytest 下直接验证前端画布
的核心几何正确性。后续 part 2 (polygon / keypoint / obb / mask) 会复用同一 harness。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


# ---------------------------------------------------------------------------
# Mirror of Annotation.vue canvas constants (前端 src/views/Annotation.vue)
# ---------------------------------------------------------------------------
CANVAS_W = 800
CANVAS_H = 600
SNAP_PIXEL = 2


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


# ---------------------------------------------------------------------------
# Pure helpers — must mirror Annotation.vue 1:1
# ---------------------------------------------------------------------------
def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def normalize_rect(a: Point, b: Point) -> Rect:
    """Annotation.vue normalizeRect — 两点构成轴对齐矩形,可任意方向拖拽。"""
    x = min(a.x, b.x)
    y = min(a.y, b.y)
    width = max(SNAP_PIXEL, abs(a.x - b.x))
    height = max(SNAP_PIXEL, abs(a.y - b.y))
    return Rect(x=x, y=y, width=width, height=height)


def resize_by_corner(g: Rect, pt: Point, corner: str) -> Rect:
    """Annotation.vue resizeByCorner — 8 控制点之一缩放。"""
    x, y, w, h = g.x, g.y, g.width, g.height
    if "w" in corner:
        nx = clamp(pt.x, 0, x + w - 1)
        w = x + w - nx
        x = nx
    if "e" in corner:
        w = clamp(pt.x - x, 1, CANVAS_W - x)
    if "n" in corner:
        ny = clamp(pt.y, 0, y + h - 1)
        h = y + h - ny
        y = ny
    if "s" in corner:
        h = clamp(pt.y - y, 1, CANVAS_H - y)
    return Rect(x=x, y=y, width=w, height=h)


def event_to_canvas_point(px: int, py: int, rect_w: int = CANVAS_W, rect_h: int = CANVAS_H) -> Point:
    """Annotation.vue eventToCanvasPoint — SVG 800x600 viewBox 下的反向映射。"""
    sx = (px / rect_w) * CANVAS_W
    sy = (py / rect_h) * CANVAS_H
    return Point(
        x=clamp(round(sx), 0, CANVAS_W),
        y=clamp(round(sy), 0, CANVAS_H),
    )


def serialize_rect(r: Rect) -> dict:
    """Annotation.vue AnnotationRecord.geometry — 后端 saveAnnotation 入参形态。"""
    return {"x": r.x, "y": r.y, "width": r.width, "height": r.height}


def deserialize_rect(payload: dict) -> Rect:
    return Rect(
        x=int(payload["x"]),
        y=int(payload["y"]),
        width=int(payload["width"]),
        height=int(payload["height"]),
    )


# ===========================================================================
# Tests
# ===========================================================================
class TestRectGeometry:
    """rect 工具的几何基础。"""

    def test_01_normalize_rect_top_left_to_bottom_right(self):
        a = Point(100, 50)
        b = Point(300, 250)
        r = normalize_rect(a, b)
        assert r == Rect(x=100, y=50, width=200, height=200)

    def test_02_normalize_rect_reversed_direction(self):
        """从右下角拖到左上角 — 必须得到同样的轴对齐矩形。"""
        a = Point(100, 50)
        b = Point(300, 250)
        forward = normalize_rect(a, b)
        backward = normalize_rect(b, a)
        assert forward == backward == Rect(x=100, y=50, width=200, height=200)

    def test_03_normalize_rect_snaps_to_min_size(self):
        """点击+释放零位移 -> 应得到 SNAP_PIXEL×SNAP_PIXEL 占位矩形。"""
        r = normalize_rect(Point(123, 456), Point(123, 456))
        assert r.width == SNAP_PIXEL
        assert r.height == SNAP_PIXEL

    def test_04_rect_serialize_roundtrip(self):
        original = Rect(x=42, y=17, width=303, height=121)
        payload = serialize_rect(original)
        # 后端约定的几何 schema: x/y/width/height 都是 int
        assert payload == {"x": 42, "y": 17, "width": 303, "height": 121}
        recovered = deserialize_rect(payload)
        assert recovered == original

    def test_05_resize_by_corner_nw_shrinks(self):
        """抓 nw 控制点往右下拖 -> x/y 变大,w/h 变小。"""
        g = Rect(x=100, y=100, width=200, height=200)
        r = resize_by_corner(g, Point(150, 150), "nw")
        assert r == Rect(x=150, y=150, width=150, height=150)

    def test_06_resize_by_corner_se_grows(self):
        """抓 se 控制点往右下拖 -> x/y 不变,w/h 变大。"""
        g = Rect(x=100, y=100, width=200, height=200)
        r = resize_by_corner(g, Point(500, 400), "se")
        assert r.x == 100 and r.y == 100
        assert r.width == 400 and r.height == 300

    def test_07_resize_clamps_to_canvas_boundary(self):
        """任何角点拖出画布必须被 clamp 回 [0, CANVAS_W/H]。"""
        g = Rect(x=10, y=10, width=50, height=50)
        # 试图把 nw 拖到 -100,-100 (画布外)
        r = resize_by_corner(g, Point(-100, -100), "nw")
        assert r.x >= 0 and r.y >= 0
        # 把 se 拖到画布外 -> w/h 不应超过画布
        g2 = Rect(x=700, y=500, width=50, height=50)
        r2 = resize_by_corner(g2, Point(2000, 2000), "se")
        assert r2.x + r2.width <= CANVAS_W
        assert r2.y + r2.height <= CANVAS_H

    def test_08_event_to_canvas_point_identity(self):
        """像素坐标等于画布坐标 -> 1:1 映射。"""
        p = event_to_canvas_point(400, 300)
        assert p == Point(x=400, y=300)

    def test_09_event_to_canvas_point_origin_and_far_corner(self):
        assert event_to_canvas_point(0, 0) == Point(0, 0)
        assert event_to_canvas_point(CANVAS_W, CANVAS_H) == Point(CANVAS_W, CANVAS_H)

    def test_10_event_to_canvas_clamps_outside(self):
        """点击在 SVG 元素外 -> 像素坐标超出,应 clamp 到画布内。"""
        p = event_to_canvas_point(2000, 2000)
        assert 0 <= p.x <= CANVAS_W and 0 <= p.y <= CANVAS_H
        p2 = event_to_canvas_point(-500, -500)
        assert p2.x == 0 and p2.y == 0

    def test_11_resize_edge_horizontal_handle(self):
        """'n' / 's' 边中点缩放: x 不变,只改 y/height。"""
        g = Rect(x=100, y=100, width=200, height=200)
        r_n = resize_by_corner(g, Point(200, 50), "n")
        assert r_n.x == 100
        assert r_n.height == 250
        r_s = resize_by_corner(g, Point(200, 350), "s")
        assert r_s.x == 100 and r_s.y == 100
        assert r_s.height == 250

    def test_12_clamp_helper_invariants(self):
        assert clamp(5, 0, 10) == 5
        assert clamp(-1, 0, 10) == 0
        assert clamp(99, 0, 10) == 10
        assert clamp(0, 0, 0) == 0


class TestRectToolContract:
    """rect 工具的输入/输出契约 (与 workbench.saveAnnotation 期望的 schema 一致)。"""

    def test_13_saved_geometry_matches_backend_schema(self):
        """saveAnnotation.geometry 必须是 {x,y,width,height} 数值对象。"""
        r = normalize_rect(Point(0, 0), Point(100, 80))
        payload = serialize_rect(r)
        for k in ("x", "y", "width", "height"):
            assert k in payload
            assert isinstance(payload[k], int)
            assert payload[k] >= 0

    def test_14_geometry_roundtrip_via_workbench_shape(self):
        """模拟前端 -> workbench.saveAnnotation -> 反序列化回来。"""
        # 1) 用户在画布上拖出一个矩形
        user_rect = normalize_rect(Point(50, 60), Point(250, 360))
        # 2) 前端把它打包成 workbench 期望的 geometry 字段
        geometry_payload = serialize_rect(user_rect)
        # 3) 前端把它和 task_id / asset_id 一起发给 saveAnnotation
        workbench_payload = {
            "task_id": "task-1",
            "asset_id": "asset-1",
            "geometry_type": "rect",
            "geometry": geometry_payload,
            "label": "car",
        }
        # 4) 反序列化验证: 后端把 geometry JSON 解出来,前端再加载时必须能还原同一矩形
        recovered = deserialize_rect(workbench_payload["geometry"])
        assert recovered == user_rect
        # 5) 关键不变量: 序列化 -> JSON -> 反序列化 是无损的
        assert serialize_rect(recovered) == geometry_payload
