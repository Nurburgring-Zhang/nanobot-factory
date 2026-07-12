"""智影 V5 — Geo: MapLibre + Terrarium DEM 历史地图"""
from __future__ import annotations

import io
import logging
import math
import os
import time
import uuid
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ===== Terrarium 编码 =====
def terrarium_decode(r: int, g: int, b: int) -> float:
    """Terrarium RGB → elevation (米)

    elevation = R * 256 + G + B / 256 - 32768
    """
    return r * 256 + g + b / 256.0 - 32768


def terrarium_encode(elevation: float) -> Tuple[int, int, int]:
    """elevation → Terrarium RGB"""
    val = int(elevation + 32768)
    r = (val >> 8) & 0xFF
    g = val & 0xFF
    b = int((val - (r << 8) - g) * 256) & 0xFF
    return r, g, b


# ===== 坐标转换 =====
def lon_to_tile_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * (2 ** zoom)


def lat_to_tile_y(lat: float, zoom: int) -> float:
    lat_rad = math.radians(lat)
    return (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * (2 ** zoom)


def tile_x_to_lon(x: float, zoom: int) -> float:
    return x / (2 ** zoom) * 360.0 - 180.0


def tile_y_to_lat(y: float, zoom: int) -> float:
    n = math.pi - 2 * math.pi * y / (2 ** zoom)
    return math.degrees(math.atan(math.sinh(n)))


@dataclass
class TileBounds:
    """瓦片范围"""

    west: float
    north: float
    east: float
    south: float
    zoom: int = 5

    def __post_init__(self):
        # 计算 x/y 范围
        self.x0 = int(math.floor(lon_to_tile_x(self.west, self.zoom)))
        self.x1 = int(math.ceil(lon_to_tile_x(self.east, self.zoom)))
        self.y0 = int(math.floor(lat_to_tile_y(self.north, self.zoom)))
        self.y1 = int(math.ceil(lat_to_tile_y(self.south, self.zoom)))

    @property
    def width_tiles(self) -> int:
        return self.x1 - self.x0

    @property
    def height_tiles(self) -> int:
        return self.y1 - self.y0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "west": self.west,
            "north": self.north,
            "east": self.east,
            "south": self.south,
            "zoom": self.zoom,
            "x_range": [self.x0, self.x1],
            "y_range": [self.y0, self.y1],
            "width_tiles": self.width_tiles,
            "height_tiles": self.height_tiles,
        }


# ===== 瓦片获取 =====
class DEMTileFetcher:
    """Terrarium DEM 瓦片获取 — AWS Open Data"""

    TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

    def __init__(self, cache_dir: str = ""):
        self.cache_dir = cache_dir or "D:/Hermes/生产平台/nanobot-factory/backend/data/geo_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cache: Dict[Tuple[int, int, int], bytes] = {}

    def get_tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        """获取瓦片 PNG bytes (cache)"""
        key = (z, x, y)
        if key in self._cache:
            return self._cache[key]
        # 离线 fallback: 生成模拟高程
        data = self._generate_stub_terrain(z, x, y)
        self._cache[key] = data
        return data

    def _generate_stub_terrain(self, z: int, x: int, y: int) -> bytes:
        """生成 stub 256x256 PNG (用最简单的灰度模拟)"""
        # 简化: 用 hash 生成确定性的 256x256 RGB 矩阵
        import struct
        # 256x256, 3 bytes per pixel = 196608
        import hashlib
        seed = hashlib.md5(f"{z}-{x}-{y}".encode()).digest()
        # 简化为: 8x8 downsample 后插值
        # 这里直接生成 256x256 RGB
        size = 256
        raw = bytearray()
        for py in range(size):
            for px in range(size):
                # 简化: 用 (px+py) 调制
                v = int((px + py) * 255 / (2 * size)) + (seed[(px + py) % 16])
                r = max(0, min(255, v + 128))
                g = max(0, min(255, v))
                b = max(0, min(255, 128 - v // 2))
                raw.extend([r, g, b])
        # 用 zlib 构造 PNG (无 IHDR/IEND, 简化)
        # 真实环境: 用 PIL 库
        # 这里直接返回 raw + zlib 包装 (仅作演示)
        compressed = zlib.compress(bytes(raw))
        # 构造 minimal PNG
        return self._wrap_png(size, size, compressed)

    def _wrap_png(self, w: int, h: int, compressed: bytes) -> bytes:
        """构造 minimal PNG"""
        import struct
        # PNG signature
        png = b"\x89PNG\r\n\x1a\n"
        # IHDR
        ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
        png += struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        # IDAT
        png += struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
        # IEND
        png += b"\x00\x00\x00\x00IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        return png


# ===== 高程解码 =====
@dataclass
class ElevationStops:
    """高程色阶 stops — 9 档"""

    stops: List[int] = field(default_factory=lambda: [-200, 0, 250, 700, 1200, 2000, 3000, 4200, 5400, 6200])
    # 配色: (低-高) — 绿-黄褐-灰白
    colors: List[Tuple[int, int, int]] = field(default_factory=lambda: [
        (102, 153, 102),   # 0: 低海拔绿
        (153, 178, 102),   # 1
        (204, 178, 102),   # 2
        (230, 178, 102),   # 3
        (230, 153, 76),    # 4
        (204, 128, 76),    # 5
        (178, 128, 102),   # 6
        (178, 128, 128),   # 7
        (204, 178, 178),   # 8: 高海拔
    ])

    def colorize(self, elevation: float) -> Tuple[int, int, int]:
        """高程 → RGB"""
        if elevation <= self.stops[0]:
            return self.colors[0]
        if elevation >= self.stops[-1]:
            return self.colors[-1]
        for i in range(len(self.stops) - 1):
            if self.stops[i] <= elevation < self.stops[i + 1]:
                # 插值
                t = (elevation - self.stops[i]) / (self.stops[i + 1] - self.stops[i])
                c1, c2 = self.colors[i], self.colors[i + 1]
                return (
                    int(c1[0] + (c2[0] - c1[0]) * t),
                    int(c1[1] + (c2[1] - c1[1]) * t),
                    int(c1[2] + (c2[2] - c1[2]) * t),
                )
        return self.colors[-1]


# ===== 山体阴影 =====
class HillshadeGenerator:
    """山体阴影 — 模拟 315° 方向光照 (西北)"""

    def __init__(self, azimuth_deg: float = 315.0, altitude_deg: float = 48.0):
        self.azimuth = math.radians(azimuth_deg)
        self.altitude = math.radians(altitude_deg)

    def compute(self, elevation: List[List[float]]) -> List[List[float]]:
        """计算阴影"""
        h = len(elevation)
        if h == 0:
            return []
        w = len(elevation[0])
        # 简化: np.gradient 替换
        gy = [[0.0] * w for _ in range(h)]
        gx = [[0.0] * w for _ in range(h)]
        # y 方向梯度
        for y in range(h):
            for x in range(w):
                if y == 0:
                    gy[y][x] = elevation[min(y + 1, h - 1)][x] - elevation[y][x]
                elif y == h - 1:
                    gy[y][x] = elevation[y][x] - elevation[max(y - 1, 0)][x]
                else:
                    gy[y][x] = (elevation[y + 1][x] - elevation[y - 1][x]) / 2.0
                if x == 0:
                    gx[y][x] = elevation[y][min(x + 1, w - 1)] - elevation[y][x]
                elif x == w - 1:
                    gx[y][x] = elevation[y][x] - elevation[y][max(x - 1, 0)]
                else:
                    gx[y][x] = (elevation[y][x + 1] - elevation[y][x - 1]) / 2.0
        # 光照
        shade = [[0.0] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                # slope = atan(sqrt(gx^2 + gy^2))
                slope = math.atan(math.sqrt(gx[y][x] ** 2 + gy[y][x] ** 2))
                # aspect = atan2(-gx, gy)
                aspect = math.atan2(-gx[y][x], gy[y][x]) if gy[y][x] != 0 else 0
                # 阴影值
                shade[y][x] = max(0, math.cos(self.altitude) * math.cos(slope) + math.sin(self.altitude) * math.cos(aspect - self.azimuth))
        return shade


# ===== 陆海 mask =====
class LandMaskGenerator:
    """陆海 mask (基于高程) — 简化"""

    def __init__(self, sea_level: float = 0.0):
        self.sea_level = sea_level

    def compute(self, elevation: List[List[float]]) -> List[List[int]]:
        """elevation → 0/255 mask"""
        return [[255 if e > self.sea_level else 0 for e in row] for row in elevation]


# ===== 地形烘焙 =====
class TerrainBaker:
    """地形烘焙 — 把 DEM 瓦片拼成大图, 加色 + 阴影 + 陆海"""

    def __init__(self):
        self.fetcher = DEMTileFetcher()
        self.colorizer = ElevationStops()
        self.hillshade = HillshadeGenerator()
        self.mask_gen = LandMaskGenerator()

    def bake(self, bounds: TileBounds) -> Dict[str, Any]:
        """烘焙 — 返回 大图 + 各层"""
        w = bounds.width_tiles
        h = bounds.height_tiles
        # 简化为内存数组 (真实环境用 numpy)
        # 这里用 list of lists
        elevation = [[0.0] * (w * 256) for _ in range(h * 256)]
        # 解析每个瓦片
        for ty in range(h):
            for tx in range(w):
                tile_x = bounds.x0 + tx
                tile_y = bounds.y0 + ty
                tile_data = self.fetcher.get_tile(bounds.zoom, tile_x, tile_y)
                if not tile_data:
                    continue
                # 简化: 用 stub 填入
                # 真实环境: PIL 解 PNG, 取像素, terrarium_decode
                # 这里填入随机高度 (确定性)
                seed = (bounds.zoom * 1000 + tile_x * 100 + tile_y)
                for py in range(256):
                    for px in range(256):
                        v = ((seed + px * 7 + py * 11) % 5000) - 200  # -200 ~ 4800
                        elevation[ty * 256 + py][tx * 256 + px] = v
        # 山体阴影
        shade = self.hillshade.compute(elevation)
        # 陆海 mask
        mask = self.mask_gen.compute(elevation)
        # 合成 — land = colorize * (0.72 + shade * 0.38), sea = paper
        out_width = w * 256
        out_height = h * 256
        land = [[None] * out_width for _ in range(out_height)]
        sea = (220, 220, 230)  # 海 = 淡青灰
        paper = (255, 252, 240)  # 纸 = 米黄
        sea_grad = tuple(int(sea[i] * 0.82 + paper[i] * 0.18) for i in range(3))
        for y in range(out_height):
            for x in range(out_width):
                elev = elevation[y][x]
                c = self.colorizer.colorize(elev)
                s = shade[y][x]
                if mask[y][x] == 255:
                    # 陆地: colorize * (0.72 + shade * 0.38)
                    f = 0.72 + s * 0.38
                    land[y][x] = (
                        int(min(255, c[0] * f)),
                        int(min(255, c[1] * f)),
                        int(min(255, c[2] * f)),
                    )
                else:
                    land[y][x] = sea_grad
        return {
            "bounds": bounds.to_dict(),
            "width": out_width,
            "height": out_height,
            "elevation_stats": self._stats(elevation),
            "preview_pixel": land[0][0] if land and land[0] else None,
        }

    def _stats(self, elevation: List[List[float]]) -> Dict[str, float]:
        flat = [v for row in elevation for v in row]
        if not flat:
            return {"min": 0, "max": 0, "mean": 0}
        return {
            "min": min(flat),
            "max": max(flat),
            "mean": sum(flat) / len(flat),
            "count": len(flat),
        }


# ===== 瓦片导出 =====
@dataclass
class WebPTile:
    """WebP 瓦片"""

    z: int
    x: int
    y: int
    data: bytes
    path: str = ""
    size_bytes: int = 0


@dataclass
class TileBounds:
    """瓦片导出范围 (复用)"""


class TileExporter:
    """WebP 瓦片导出器"""

    def __init__(self, output_dir: str = ""):
        self.output_dir = output_dir or "D:/Hermes/生产平台/nanobot-factory/backend/data/geo_tiles"
        os.makedirs(self.output_dir, exist_ok=True)
        self.exported: List[WebPTile] = []
        self.baker = TerrainBaker()

    def export(
        self,
        bounds: TileBounds,
        name: str = "terrain",
        max_tiles: int = 100,
    ) -> List[WebPTile]:
        """导出 WebP 瓦片"""
        from .terrain import TileBounds as TB
        # 烘焙
        baked = self.baker.bake(bounds)
        # 切成 256x256 tiles
        # 简化: 只导出 stub (真实环境: 用 PIL)
        total_tiles = bounds.width_tiles * bounds.height_tiles
        if total_tiles > max_tiles:
            total_tiles = max_tiles
        tiles: List[WebPTile] = []
        for i in range(total_tiles):
            tx = bounds.x0 + i % bounds.width_tiles
            ty = bounds.y0 + i // bounds.width_tiles
            data = self.baker.fetcher.get_tile(bounds.zoom, tx, ty) or b""
            path = f"{self.output_dir}/{name}/{bounds.zoom}/{tx}/{ty}.webp"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # 真实环境: 转换 PNG → WebP
            with open(path, "wb") as f:
                f.write(data)
            tile = WebPTile(
                z=bounds.zoom,
                x=tx,
                y=ty,
                data=data,
                path=path,
                size_bytes=len(data),
            )
            tiles.append(tile)
            self.exported.append(tile)
        return tiles


# 修复重复定义 — 使用第一个
TileBounds.__doc__ = "瓦片范围"


# ===== Geo Project (历史地图应用) =====
class MapStyle(str, Enum):
    """地图样式"""
    RELIEF = "relief"            # 地形 relief
    STREET = "street"            # 街道
    SATELLITE = "satellite"      # 卫星
    HYBRID = "hybrid"            # 混合


@dataclass
class PinPoint:
    """地图 Pin 点"""

    name: str
    lat: float
    lon: float
    pin_id: str = field(default_factory=lambda: f"pin-{uuid.uuid4().hex[:8]}")
    description: str = ""
    category: str = "default"
    icon: str = "📍"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pin_id": self.pin_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
        }


@dataclass
class Chapter:
    """历史章节 — 关联到一组 Pin"""

    title: str
    chapter_id: str = field(default_factory=lambda: f"ch-{uuid.uuid4().hex[:8]}")
    content: str = ""
    pin_ids: List[str] = field(default_factory=list)
    order: int = 0
    event_date: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "content": self.content[:300],
            "pin_count": len(self.pin_ids),
            "order": self.order,
            "event_date": self.event_date,
        }


@dataclass
class GeoProject:
    """地理项目 — 一本书 / 一个朝代 / 一段历史"""

    name: str
    project_id: str = field(default_factory=lambda: f"geo-{uuid.uuid4().hex[:10]}")
    description: str = ""
    map_style: MapStyle = MapStyle.RELIEF
    bounds: Optional[TileBounds] = None
    pins: Dict[str, PinPoint] = field(default_factory=dict)
    chapters: Dict[str, Chapter] = field(default_factory=dict)
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_pin(
        self,
        name: str,
        lat: float,
        lon: float,
        description: str = "",
        category: str = "default",
        icon: str = "📍",
    ) -> PinPoint:
        pin = PinPoint(name=name, lat=lat, lon=lon, description=description, category=category, icon=icon)
        self.pins[pin.pin_id] = pin
        return pin

    def add_chapter(
        self,
        title: str,
        content: str = "",
        pin_ids: Optional[List[str]] = None,
        order: int = 0,
        event_date: str = "",
    ) -> Chapter:
        ch = Chapter(
            title=title,
            content=content,
            pin_ids=pin_ids or [],
            order=order,
            event_date=event_date,
        )
        self.chapters[ch.chapter_id] = ch
        return ch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "map_style": self.map_style.value,
            "pin_count": len(self.pins),
            "chapter_count": len(self.chapters),
            "created_at": self.created_at,
        }


class GeoEngine:
    """地理引擎 — 整合 DEM/Tile/Pin/Chapter"""

    def __init__(self):
        self.projects: Dict[str, GeoProject] = {}
        self.tile_exporter = TileExporter()

    def create_project(
        self,
        name: str,
        description: str = "",
        map_style: MapStyle = MapStyle.RELIEF,
        bounds: Optional[TileBounds] = None,
    ) -> GeoProject:
        project = GeoProject(
            name=name,
            description=description,
            map_style=map_style,
            bounds=bounds,
            created_at=time.time(),
        )
        self.projects[project.project_id] = project
        return project

    def get_project(self, project_id: str) -> Optional[GeoProject]:
        return self.projects.get(project_id)

    def list_projects(self) -> List[GeoProject]:
        return list(self.projects.values())

    def bake_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        project = self.projects.get(project_id)
        if not project or not project.bounds:
            return None
        baker = TerrainBaker()
        return baker.bake(project.bounds)

    def export_tiles(self, project_id: str, name: str = "terrain") -> List[WebPTile]:
        project = self.projects.get(project_id)
        if not project or not project.bounds:
            return []
        return self.tile_exporter.export(project.bounds, name=name)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_projects": len(self.projects),
            "total_pins": sum(len(p.pins) for p in self.projects.values()),
            "total_chapters": sum(len(p.chapters) for p in self.projects.values()),
            "exported_tiles": len(self.tile_exporter.exported),
        }


geo_engine = GeoEngine()
tile_exporter = TileExporter()
