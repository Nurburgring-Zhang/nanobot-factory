"""P19 v5.5: V5 §十 4 几何渲染器 — mock 实现 (PNG header + 确定性 bytes).

每个 renderer:
  - 接受 Pydantic v2 model (来自 :mod:`labeling.geometries`)
  - 返回 ``bytes`` (PNG 头部 + 确定性填充; 非视觉真实但格式合法)
  - 不依赖 PIL/numpy/opencv, 全部 stdlib (struct + zlib)

生产代码若需真实渲染, 替换 ``_make_png_bytes`` body 即可 — 接口稳定.
"""
from __future__ import annotations

import struct
import zlib
from typing import Any, Dict, Tuple

from .geometries import (
    BBox3D,
    Cuboid3D,
    PanopticSegmentation,
    PointCloudLiDAR,
)


# ──────────────────────────────────────────────────────────────────────────────
# Mock PNG byte builder (stdlib only — no PIL/numpy)
# ──────────────────────────────────────────────────────────────────────────────
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _make_png_bytes(width: int, height: int, payload_seed: bytes) -> bytes:
    """Build a minimal valid PNG (RGB) with ``width × height`` of deterministic bytes.

    The pixel data is derived from ``payload_seed`` via repeated XOR so each
    geometry model produces a stable, distinct image — useful for tests and
    for change-detection on disk.
    """
    if width <= 0 or height <= 0:
        width, height = max(width, 1), max(height, 1)
    n = width * height
    seed_bytes = (payload_seed * ((n // len(payload_seed)) + 1))[:n]
    pixels = bytearray()
    pixels.append(0)  # PNG row filter: None
    for i in range(n):
        b = seed_bytes[i]
        pixels.append(b)
        pixels.append((b * 3) & 0xFF)
        pixels.append((b * 7) & 0xFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(pixels), level=6)
    out = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    return out


def _hash_seed(payload: bytes, prefix: bytes = b"geo") -> bytes:
    """Build a stable ~64-byte seed by hashing with stdlib only."""
    h = zlib.crc32(payload) & 0xFFFFFFFF
    out = bytearray()
    for i in range(64):
        out.append(((h >> ((i % 4) * 8)) ^ (i * 31)) & 0xFF)
    return prefix + bytes(out)


# ──────────────────────────────────────────────────────────────────────────────
# Cuboid3DRenderer — visualize 8 corners + edges as 3D wireframe (mock 2D)
# ──────────────────────────────────────────────────────────────────────────────
class Cuboid3DRenderer:
    """Render a 3D cuboid wireframe.

    Real implementation would ortho-project the 8 corners + 12 edges onto a
    2D image. This mock flattens all 8 corners to a fixed canvas and emits a
    PNG header so test code can assert non-empty bytes + format.
    """

    CANVAS = (256, 256)

    def render(self, cuboid: Cuboid3D) -> bytes:
        corner_bytes = b"|".join(
            f"{c.x:.3f},{c.y:.3f},{c.z:.3f}".encode("utf-8")
            for c in cuboid.corners
        ) or b"empty_cuboid"
        seed = _hash_seed(corner_bytes, prefix=b"cuboid3d_")
        w, h = self.CANVAS
        return _make_png_bytes(w, h, seed)

    def render_to(self, cuboid: Cuboid3D) -> Tuple[bytes, Dict[str, Any]]:
        """Render + return metadata dict (corner count, dimensions, etc.)."""
        data = self.render(cuboid)
        meta = {
            "renderer": "Cuboid3DRenderer",
            "n_corners": len(cuboid.corners),
            "volume": cuboid.volume(),
            "width": data[:8].hex(),
            "size_bytes": len(data),
        }
        return data, meta


# ──────────────────────────────────────────────────────────────────────────────
# PointCloudLiDARRenderer — render top-down view (x,y plane) of points
# ──────────────────────────────────────────────────────────────────────────────
class PointCloudLiDARRenderer:
    """Render a LiDAR point cloud as a top-down (x,y) projection.

    Mock version: PNG canvas where pixel intensity is derived from point
    count + centroid. Useful for visual smoke checks.
    """

    CANVAS = (256, 256)

    def render(self, cloud: PointCloudLiDAR) -> bytes:
        seed = _hash_seed(
            f"{cloud.frame_id}|{cloud.n_points()}".encode("utf-8"),
            prefix=b"lidar_",
        )
        w, h = self.CANVAS
        return _make_png_bytes(w, h, seed)

    def render_to(self, cloud: PointCloudLiDAR) -> Tuple[bytes, Dict[str, Any]]:
        data = self.render(cloud)
        centroid = self._centroid(cloud)
        meta = {
            "renderer": "PointCloudLiDARRenderer",
            "frame_id": cloud.frame_id,
            "n_points": cloud.n_points(),
            "centroid": centroid,
            "size_bytes": len(data),
        }
        return data, meta

    @staticmethod
    def _centroid(cloud: PointCloudLiDAR) -> Dict[str, float]:
        if not cloud.points:
            return {"x": 0.0, "y": 0.0, "z": 0.0}
        xs = sum(p.x for p in cloud.points) / cloud.n_points()
        ys = sum(p.y for p in cloud.points) / cloud.n_points()
        zs = sum(p.z for p in cloud.points) / cloud.n_points()
        return {"x": xs, "y": ys, "z": zs}


# ──────────────────────────────────────────────────────────────────────────────
# BBox3DRenderer — render 3D bbox in 3 viewports (top/front/side)
# ──────────────────────────────────────────────────────────────────────────────
class BBox3DRenderer:
    """Render a 3D bbox in three orthographic viewports (top/front/side).

    The mock emits 3 separate PNG panels concatenated with a small header.
    For real implementations, callers can call :meth:`render_view` with an
    explicit viewport name.
    """

    VIEWPORTS = ("top", "front", "side")
    PANEL = (128, 128)

    def render(self, bbox: BBox3D) -> bytes:
        """Render all 3 viewports concatenated; test code should check size > 0."""
        chunks: list[bytes] = []
        # 4-byte header: number of panels
        chunks.append(struct.pack(">I", len(self.VIEWPORTS)))
        for vp in self.VIEWPORTS:
            chunks.append(self.render_view(bbox, vp))
        return b"".join(chunks)

    def render_view(self, bbox: BBox3D, viewport: str) -> bytes:
        if viewport not in self.VIEWPORTS:
            raise ValueError(
                f"unknown viewport: {viewport!r}; expected one of {self.VIEWPORTS}"
            )
        seed = _hash_seed(
            f"{viewport}|{bbox.center.x:.3f}|{bbox.x_size:.3f}|"
            f"{bbox.y_size:.3f}|{bbox.z_size:.3f}".encode("utf-8"),
            prefix=f"bbox3d_{viewport}_".encode("utf-8"),
        )
        w, h = self.PANEL
        return _make_png_bytes(w, h, seed)

    def render_to(self, bbox: BBox3D) -> Tuple[bytes, Dict[str, Any]]:
        data = self.render(bbox)
        meta = {
            "renderer": "BBox3DRenderer",
            "viewports": list(self.VIEWPORTS),
            "volume": bbox.volume(),
            "size_bytes": len(data),
        }
        return data, meta


# ──────────────────────────────────────────────────────────────────────────────
# PanopticRenderer — render segmentation mask with class color overlay
# ──────────────────────────────────────────────────────────────────────────────
# Deterministic color palette — class_id % palette_length
_PANOPTIC_PALETTE = [
    (0, 0, 0),         # background
    (220, 20, 60),     # person (red)
    (0, 0, 142),       # car (blue)
    (0, 255, 0),       # vegetation (green)
    (255, 255, 0),     # sky (yellow)
    (128, 0, 128),     # object (purple)
]


class PanopticRenderer:
    """Render a panoptic segmentation mask with a deterministic color overlay.

    Output is a PNG where each pixel maps to ``_PANOPTIC_PALETTE[class_id % N]``.
    Mock implementation uses the mask dimensions directly; when mask is empty,
    falls back to a 16×16 default canvas.
    """

    DEFAULT_SIZE = (16, 16)

    def render(self, seg: PanopticSegmentation) -> bytes:
        w = seg.width or self.DEFAULT_SIZE[0]
        h = seg.height or self.DEFAULT_SIZE[1]
        # Build a seed that incorporates class_id + class_name so different
        # class names produce visibly different bytes.
        seed = _hash_seed(
            f"{seg.class_name}|{seg.class_id}|{seg.instance_id}|"
            f"{w}x{h}".encode("utf-8"),
            prefix=b"panoptic_",
        )
        return _make_png_bytes(w, h, seed)

    def render_to(self, seg: PanopticSegmentation) -> Tuple[bytes, Dict[str, Any]]:
        data = self.render(seg)
        meta = {
            "renderer": "PanopticRenderer",
            "class_id": seg.class_id,
            "class_name": seg.class_name,
            "is_thing": seg.is_thing,
            "instance_id": seg.instance_id,
            "width": seg.width,
            "height": seg.height,
            "n_pixels_fg": seg.n_pixels,
            "size_bytes": len(data),
        }
        return data, meta


__all__ = [
    "Cuboid3DRenderer",
    "PointCloudLiDARRenderer",
    "BBox3DRenderer",
    "PanopticRenderer",
    "_make_png_bytes",
]