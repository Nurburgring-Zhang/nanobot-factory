"""
P5-R2-T4 测试 — 标注画布 part 1 (rect 工具 + 任务载入 + 坐标变换)
================================================================
覆盖 6 个测试用例:
  1. test_normalize_rect_positive       - normalizeRect 正向拖拽 (右上)
  2. test_normalize_rect_negative       - normalizeRect 反向拖拽 (左下)
  3. test_normalize_rect_zero_clamped   - normalizeRect 最小尺寸
  4. test_rect_to_dict_round_trip       - RectGeometry dict 序列化/反序列化 (后端兼容)
  5. test_coord_transform_event_to_canvas - 屏幕坐标 → SVG 画布坐标变换数学
  6. test_clamp_inside_canvas           - clamp 越界裁剪到画布范围

注: 这些函数是 Annotation.vue 里的纯逻辑,与后端 workbench_engine 共享 RectGeometry schema
    (x, y, width, height),可作为后续 R3 polygon/obb/keypoint 的几何基础
"""
from __future__ import annotations

import os
import sys
import math
from pathlib import Path

# 路径注入: backend/imdf 在 path 中,tests/ 同级
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMDF = PROJECT_ROOT
sys.path.insert(0, str(IMDF))
sys.path.insert(0, str(PROJECT_ROOT))

import pytest


# ────────────────────────── 镜像前端常量 ──────────────────────────
CANVAS_W = 800
CANVAS_H = 600
HANDLE_SIZE = 10
SNAP_PIXEL = 1


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def normalize_rect(a: dict, b: dict) -> dict:
    """Annotation.vue 中 normalizeRect 的纯函数镜像 (用于单元测试)"""
    x = min(a["x"], b["x"])
    y = min(a["y"], b["y"])
    width = max(SNAP_PIXEL, abs(a["x"] - b["x"]))
    height = max(SNAP_PIXEL, abs(a["y"] - b["y"]))
    return {"x": x, "y": y, "width": width, "height": height}


def event_to_canvas_point(
    client_x: float,
    client_y: float,
    svg_rect: dict,
) -> dict:
    """Annotation.vue 中 eventToCanvasPoint 的纯函数镜像
    svg_rect: {left, top, width, height} (CSS 像素)
    """
    px = client_x - svg_rect["left"]
    py = client_y - svg_rect["top"]
    sx = (px / svg_rect["width"]) * CANVAS_W
    sy = (py / svg_rect["height"]) * CANVAS_H
    return {"x": clamp(round(sx), 0, CANVAS_W), "y": clamp(round(sy), 0, CANVAS_H)}


def rect_to_dict(geometry: dict, label: str = "obj", ann_id: str = "a-1") -> dict:
    """AnnotationRecord 转 dict — 后端 saveAnnotation body 序列化"""
    return {
        "id": ann_id,
        "geometry_type": "rect",
        "geometry": {
            "x": float(geometry["x"]),
            "y": float(geometry["y"]),
            "width": float(geometry["width"]),
            "height": float(geometry["height"]),
        },
        "label": label,
    }


# ────────────────────────── Fixtures ──────────────────────────

@pytest.fixture
def default_svg_rect():
    """画布 SVG 默认 rect (无缩放/无平移)"""
    return {"left": 0, "top": 0, "width": CANVAS_W, "height": CANVAS_H}


# ────────────────────────── 测试 ──────────────────────────

class TestNormalizeRect:
    """normalizeRect 几何对齐 — 拖拽起点/终点 → 标准 rect"""

    def test_normalize_rect_positive(self):
        """正向拖拽 (左→右, 上→下): 起点 (100, 100) → 终点 (300, 200)"""
        a = {"x": 100, "y": 100}
        b = {"x": 300, "y": 200}
        rect = normalize_rect(a, b)
        assert rect == {"x": 100, "y": 100, "width": 200, "height": 100}

    def test_normalize_rect_negative(self):
        """反向拖拽 (右→左, 下→上): 起点 (300, 200) → 终点 (100, 100)"""
        a = {"x": 300, "y": 200}
        b = {"x": 100, "y": 100}
        rect = normalize_rect(a, b)
        assert rect == {"x": 100, "y": 100, "width": 200, "height": 100}

    def test_normalize_rect_mixed(self):
        """混合方向 (右下→左上): 起点 (500, 400) → 终点 (200, 150)"""
        a = {"x": 500, "y": 400}
        b = {"x": 200, "y": 150}
        rect = normalize_rect(a, b)
        assert rect == {"x": 200, "y": 150, "width": 300, "height": 250}

    def test_normalize_rect_zero_clamped(self):
        """零尺寸被提升到 SNAP_PIXEL=1 (避免除零 / 不可见矩形)"""
        a = {"x": 100, "y": 100}
        b = {"x": 100, "y": 100}  # 拖拽 0 距离
        rect = normalize_rect(a, b)
        assert rect["width"] >= 1
        assert rect["height"] >= 1
        assert rect["width"] == 1
        assert rect["height"] == 1

    def test_normalize_rect_horizontal_only(self):
        """纯水平线 → height = 1"""
        a = {"x": 0, "y": 50}
        b = {"x": 100, "y": 50}
        rect = normalize_rect(a, b)
        assert rect["x"] == 0
        assert rect["y"] == 50
        assert rect["width"] == 100
        assert rect["height"] == 1

    def test_normalize_rect_vertical_only(self):
        """纯垂直线 → width = 1"""
        a = {"x": 50, "y": 0}
        b = {"x": 50, "y": 200}
        rect = normalize_rect(a, b)
        assert rect["x"] == 50
        assert rect["y"] == 0
        assert rect["width"] == 1
        assert rect["height"] == 200


class TestRectSerialization:
    """RectGeometry 与后端 schema 互转"""

    def test_rect_to_dict_round_trip(self):
        """dict → JSON-string → dict (模拟 HTTP body 传输)"""
        import json
        original = rect_to_dict(
            {"x": 50, "y": 30, "width": 200, "height": 150},
            label="car",
            ann_id="rect-001",
        )
        encoded = json.dumps(original)
        decoded = json.loads(encoded)
        assert decoded == original
        assert decoded["geometry_type"] == "rect"
        assert decoded["geometry"]["x"] == 50
        assert decoded["geometry"]["y"] == 30
        assert decoded["geometry"]["width"] == 200
        assert decoded["geometry"]["height"] == 150
        assert decoded["label"] == "car"
        assert decoded["id"] == "rect-001"

    def test_rect_to_dict_types(self):
        """几何坐标必须是数值 (符合后端 Pydantic 校验)"""
        d = rect_to_dict({"x": 1, "y": 2, "width": 3, "height": 4})
        assert isinstance(d["geometry"]["x"], (int, float))
        assert isinstance(d["geometry"]["y"], (int, float))
        assert isinstance(d["geometry"]["width"], (int, float))
        assert isinstance(d["geometry"]["height"], (int, float))


class TestCoordTransform:
    """屏幕坐标 → SVG 画布坐标"""

    def test_coord_transform_identity(self, default_svg_rect):
        """无缩放/无平移时, 屏幕坐标直接映射 (1:1)"""
        pt = event_to_canvas_point(100, 50, default_svg_rect)
        assert pt == {"x": 100, "y": 50}

    def test_coord_transform_origin(self, default_svg_rect):
        """左上角 (0, 0) → (0, 0)"""
        pt = event_to_canvas_point(0, 0, default_svg_rect)
        assert pt == {"x": 0, "y": 0}

    def test_coord_transform_bottom_right(self, default_svg_rect):
        """右下角 (800, 600) → (800, 600)"""
        pt = event_to_canvas_point(800, 600, default_svg_rect)
        assert pt == {"x": 800, "y": 600}

    def test_coord_transform_clamp_out_of_bounds(self, default_svg_rect):
        """越界点被 clamp 到画布范围"""
        pt = event_to_canvas_point(2000, 3000, default_svg_rect)
        assert pt == {"x": 800, "y": 600}

        pt_neg = event_to_canvas_point(-100, -50, default_svg_rect)
        assert pt_neg == {"x": 0, "y": 0}

    def test_coord_transform_with_offset(self):
        """SVG 被 padding 偏移 (left=50, top=20) 时正确还原"""
        rect = {"left": 50, "top": 20, "width": CANVAS_W, "height": CANVAS_H}
        pt = event_to_canvas_point(150, 120, rect)  # 相对 offset 后是 (100, 100)
        assert pt == {"x": 100, "y": 100}

    def test_coord_transform_scaled(self):
        """CSS 缩放 (SVG 渲染为 400x300, 即 0.5x) 时,坐标按比例还原"""
        rect = {"left": 0, "top": 0, "width": 400, "height": 300}  # 0.5x
        pt = event_to_canvas_point(100, 50, rect)
        # (100/400)*800 = 200, (50/300)*600 = 100
        assert pt == {"x": 200, "y": 100}

    def test_coord_transform_with_round(self, default_svg_rect):
        """坐标被四舍五入到整数像素"""
        pt = event_to_canvas_point(100.4, 50.6, default_svg_rect)
        assert pt["x"] == 100
        assert pt["y"] == 51


class TestClamp:
    """clamp 工具函数"""

    def test_clamp_inside_canvas(self):
        """在范围内不动"""
        assert clamp(100, 0, CANVAS_W) == 100
        assert clamp(0, 0, CANVAS_W) == 0
        assert clamp(CANVAS_W, 0, CANVAS_W) == CANVAS_W

    def test_clamp_negative(self):
        """负数被提升到 0"""
        assert clamp(-50, 0, CANVAS_W) == 0
        assert clamp(-1, 0, CANVAS_W) == 0

    def test_clamp_overflow(self):
        """超过画布被裁剪"""
        assert clamp(CANVAS_W + 100, 0, CANVAS_W) == CANVAS_W
        assert clamp(99999, 0, CANVAS_W) == CANVAS_W

    def test_clamp_floats(self):
        """浮点也支持"""
        assert clamp(50.5, 0, 100) == 50.5
        assert clamp(-0.1, 0, 100) == 0
        assert clamp(100.1, 0, 100) == 100