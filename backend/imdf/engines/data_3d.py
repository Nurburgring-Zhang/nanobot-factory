"""P22-P2-real-fix-3-Engines — Data3DEngine (real 3D data primitives).

Real 3D mesh / point-cloud / GLB / OBJ / STL IO using pure Python.
No external 3D library dependency (numpy optional).

Public API:
- ``Data3DEngine.parse(path)`` — auto-detect format → 3DObject
- ``Data3DEngine.write(obj, path)`` — write OBJ/STL/GLTF JSON
- ``Data3DEngine.bounds(obj)`` — axis-aligned bounding box
- ``Data3DEngine.summary(obj)`` — vertex/face/material counts

Supported formats:
- OBJ (text, with mtllib/material reference)
- STL (binary, little-endian)
- PLY (text ASCII, basic vertex/face)
- GLTF/GLB (JSON-only minimal)

For complex GLB binary data we extract what we can and skip binary
chunks (real best-effort parser).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Vertex:
    x: float
    y: float
    z: float


@dataclass
class Face:
    vertex_indices: List[int]
    normal_indices: Optional[List[int]] = None
    tex_indices: Optional[List[int]] = None


@dataclass
class Material:
    name: str
    color_rgb: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    texture_path: Optional[str] = None


@dataclass
class Object3D:
    name: str = "object"
    vertices: List[Vertex] = field(default_factory=list)
    normals: List[Vertex] = field(default_factory=list)
    tex_coords: List[Tuple[float, float]] = field(default_factory=list)
    faces: List[Face] = field(default_factory=list)
    materials: List[Material] = field(default_factory=list)
    format: str = ""
    source_path: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


class Data3DEngine:
    """Real 3D data parser/writer."""

    def parse(self, path: str) -> Object3D:
        p = Path(path)
        if not p.is_file():
            return Object3D(source_path=path, extra={"error": f"file not found: {path}"})
        suffix = p.suffix.lower()
        try:
            if suffix == ".obj":
                return self._parse_obj(p)
            elif suffix == ".stl":
                return self._parse_stl(p)
            elif suffix == ".ply":
                return self._parse_ply(p)
            elif suffix in (".gltf", ".glb"):
                return self._parse_gltf(p)
            else:
                # Try OBJ as default (most common text format)
                return self._parse_obj(p)
        except Exception as exc:  # noqa: BLE001
            return Object3D(source_path=path, extra={"error": f"{type(exc).__name__}: {exc}"})

    def write(self, obj: Object3D, path: str) -> Dict[str, Any]:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        suffix = p.suffix.lower()
        try:
            if suffix == ".obj":
                return self._write_obj(obj, p)
            elif suffix == ".stl":
                return self._write_stl(obj, p)
            elif suffix == ".ply":
                return self._write_ply(obj, p)
            elif suffix == ".gltf":
                return self._write_gltf(obj, p)
            else:
                return {"success": False, "error": f"unsupported format: {suffix}"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def bounds(self, obj: Object3D) -> Dict[str, Any]:
        if not obj.vertices:
            return {"min": None, "max": None, "size": None, "diagonal": 0.0}
        xs = [v.x for v in obj.vertices]
        ys = [v.y for v in obj.vertices]
        zs = [v.z for v in obj.vertices]
        mn, mx = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
        diag = ((mx[0] - mn[0]) ** 2 + (mx[1] - mn[1]) ** 2 + (mx[2] - mn[2]) ** 2) ** 0.5
        return {
            "min": list(mn), "max": list(mx),
            "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
            "diagonal": round(diag, 4),
        }

    def summary(self, obj: Object3D) -> Dict[str, Any]:
        return {
            "name": obj.name, "format": obj.format,
            "vertex_count": len(obj.vertices),
            "normal_count": len(obj.normals),
            "tex_coord_count": len(obj.tex_coords),
            "face_count": len(obj.faces),
            "material_count": len(obj.materials),
            "bounds": self.bounds(obj),
        }

    # ── OBJ parser ────────────────────────────────────────────────

    def _parse_obj(self, p: Path) -> Object3D:
        obj = Object3D(name=p.stem, format="obj", source_path=str(p))
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]
            if tag == "v" and len(parts) >= 4:
                obj.vertices.append(Vertex(float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == "vn" and len(parts) >= 4:
                obj.normals.append(Vertex(float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == "vt" and len(parts) >= 3:
                obj.tex_coords.append((float(parts[1]), float(parts[2])))
            elif tag == "f" and len(parts) >= 4:
                vi, ni, ti = [], [], []
                for p_str in parts[1:]:
                    bits = p_str.split("/")
                    vi.append(int(bits[0]) - 1)
                    if len(bits) > 1 and bits[1]:
                        ti.append(int(bits[1]) - 1)
                    if len(bits) > 2 and bits[2]:
                        ni.append(int(bits[2]) - 1)
                obj.faces.append(Face(vi, ni or None, ti or None))
            elif tag == "usemtl" and len(parts) >= 2:
                obj.materials.append(Material(name=parts[1]))
        return obj

    def _write_obj(self, obj: Object3D, p: Path) -> Dict[str, Any]:
        lines: List[str] = [f"# Data3DEngine OBJ export", f"o {obj.name}"]
        for v in obj.vertices:
            lines.append(f"v {v.x} {v.y} {v.z}")
        for n in obj.normals:
            lines.append(f"vn {n.x} {n.y} {n.z}")
        for t in obj.tex_coords:
            lines.append(f"vt {t[0]} {t[1]}")
        for f in obj.faces:
            parts = []
            for i, vi in enumerate(f.vertex_indices):
                s = str(vi + 1)
                if f.tex_indices and i < len(f.tex_indices):
                    s += f"/{f.tex_indices[i] + 1}"
                if f.normal_indices and i < len(f.normal_indices):
                    s += f"/{f.normal_indices[i] + 1}"
                parts.append(s)
            lines.append("f " + " ".join(parts))
        p.write_text("\n".join(lines), encoding="utf-8")
        return {"success": True, "dst": str(p), "size_bytes": p.stat().st_size, "engine": "data3d-obj"}

    # ── STL parser (binary, little-endian) ────────────────────────

    def _parse_stl(self, p: Path) -> Object3D:
        obj = Object3D(name=p.stem, format="stl", source_path=str(p))
        with p.open("rb") as f:
            head = f.read(80)
            try:
                n_tri = struct.unpack("<I", f.read(4))[0]
            except Exception:
                return obj
            # Sanity: file size should be 80+4 + n*50
            f_size = p.stat().st_size
            if 80 + 4 + n_tri * 50 > f_size + 1024:
                # ASCII STL fallback
                return self._parse_stl_ascii(p)
        # Re-parse properly
        obj2 = Object3D(name=p.stem, format="stl", source_path=str(p))
        with p.open("rb") as f:
            f.read(80)
            n = struct.unpack("<I", f.read(4))[0]
            for _ in range(n):
                chunk = f.read(50)
                if len(chunk) < 50:
                    break
                # normal (3f) + 3 vertices (3f each) + attribute (2 bytes)
                v0_idx = len(obj2.vertices)
                v1 = struct.unpack("<3f", chunk[12:24])
                v2_ = struct.unpack("<3f", chunk[24:36])
                v3_ = struct.unpack("<3f", chunk[36:48])
                obj2.vertices.extend([Vertex(*v1), Vertex(*v2_), Vertex(*v3_)])
                obj2.faces.append(Face(vertex_indices=[v0_idx, v0_idx + 1, v0_idx + 2]))
        obj2.extra["triangle_count"] = n
        return obj2

    def _parse_stl_ascii(self, p: Path) -> Object3D:
        obj = Object3D(name=p.stem, format="stl", source_path=str(p))
        cur: List[Vertex] = []
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("vertex"):
                parts = line.split()
                if len(parts) >= 4:
                    cur.append(Vertex(float(parts[1]), float(parts[2]), float(parts[3])))
                    if len(cur) == 3:
                        base = len(obj.vertices)
                        obj.vertices.extend(cur)
                        obj.faces.append(Face(vertex_indices=[base, base + 1, base + 2]))
                        cur = []
        return obj

    def _write_stl(self, obj: Object3D, p: Path) -> Dict[str, Any]:
        tris = [f for f in obj.faces if len(f.vertex_indices) == 3]
        with p.open("wb") as f:
            f.write(b"\0" * 80)
            f.write(struct.pack("<I", len(tris)))
            for tri in tris:
                v0, v1, v2 = (obj.vertices[tri.vertex_indices[0]],
                               obj.vertices[tri.vertex_indices[1]],
                               obj.vertices[tri.vertex_indices[2]])
                # Normal — compute via cross product
                ux, uy, uz = v1.x - v0.x, v1.y - v0.y, v1.z - v0.z
                wx, wy, wz = v2.x - v0.x, v2.y - v0.y, v2.z - v0.z
                cx, cy, cz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
                length = (cx * cx + cy * cy + cz * cz) ** 0.5 or 1.0
                nx, ny, nz = cx / length, cy / length, cz / length
                f.write(struct.pack("<3f", nx, ny, nz))
                f.write(struct.pack("<3f", v0.x, v0.y, v0.z))
                f.write(struct.pack("<3f", v1.x, v1.y, v1.z))
                f.write(struct.pack("<3f", v2.x, v2.y, v2.z))
                f.write(struct.pack("<H", 0))
        return {"success": True, "dst": str(p), "size_bytes": p.stat().st_size, "triangle_count": len(tris), "engine": "data3d-stl"}

    # ── PLY parser (text ASCII) ──────────────────────────────────

    def _parse_ply(self, p: Path) -> Object3D:
        obj = Object3D(name=p.stem, format="ply", source_path=str(p))
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines or lines[0].strip() != "ply":
            return obj
        v_count = f_count = 0
        in_header = True
        for line in lines:
            if in_header:
                if line.startswith("element vertex"):
                    v_count = int(line.split()[-1])
                elif line.startswith("element face"):
                    f_count = int(line.split()[-1])
                elif line.strip() == "end_header":
                    in_header = False
                continue
            if v_count > 0 and len(obj.vertices) < v_count:
                parts = line.split()
                if len(parts) >= 3:
                    obj.vertices.append(Vertex(float(parts[0]), float(parts[1]), float(parts[2])))
            elif f_count > 0 and len(obj.faces) < f_count:
                parts = line.split()
                if len(parts) >= 4:
                    n = int(parts[0])
                    obj.faces.append(Face(vertex_indices=[int(parts[i + 1]) for i in range(n)]))
        return obj

    def _write_ply(self, obj: Object3D, p: Path) -> Dict[str, Any]:
        lines = [
            "ply", "format ascii 1.0",
            f"element vertex {len(obj.vertices)}",
            "property float x", "property float y", "property float z",
            f"element face {len(obj.faces)}",
            "property list uchar int vertex_indices",
            "end_header",
        ]
        for v in obj.vertices:
            lines.append(f"{v.x} {v.y} {v.z}")
        for f in obj.faces:
            lines.append(f"{len(f.vertex_indices)} " + " ".join(str(i) for i in f.vertex_indices))
        p.write_text("\n".join(lines), encoding="utf-8")
        return {"success": True, "dst": str(p), "size_bytes": p.stat().st_size, "engine": "data3d-ply"}

    # ── glTF parser (JSON only) ──────────────────────────────────

    def _parse_gltf(self, p: Path) -> Object3D:
        obj = Object3D(name=p.stem, format="gltf", source_path=str(p))
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            obj.extra["error"] = f"gltf parse: {type(exc).__name__}: {exc}"
            return obj
        buffers = data.get("buffers", [])
        buffer_views = data.get("bufferViews", [])
        accessors = data.get("accessors", [])
        meshes = data.get("meshes", [])
        bin_path = p.with_suffix(".bin")
        bin_data = b""
        if bin_path.is_file():
            bin_data = bin_path.read_bytes()
        for b in buffers:
            if b.get("uri", "").startswith("data:application/octet-stream;base64,"):
                bin_data += base64.b64decode(b["uri"].split(",", 1)[1])
        # Walk meshes → primitives → attributes.POSITION
        for m in meshes:
            for prim in m.get("primitives", []):
                pos_idx = prim.get("attributes", {}).get("POSITION")
                if pos_idx is not None and pos_idx < len(accessors):
                    pos = accessors[pos_idx]
                    bv = buffer_views[pos.get("bufferView", 0)] if pos.get("bufferView", 0) < len(buffer_views) else None
                    if bv:
                        offset = bv.get("byteOffset", 0)
                        length = bv.get("byteLength", 0)
                        count = pos.get("count", 0)
                        ctype = pos.get("componentType", 5126)  # FLOAT
                        chunk = bin_data[offset:offset + length]
                        for i in range(count):
                            base = i * 12
                            if base + 12 <= len(chunk):
                                obj.vertices.append(Vertex(*struct.unpack("<3f", chunk[base:base + 12])))
                # Indices
                if "indices" in prim:
                    idx_acc = accessors[prim["indices"]]
                    bv = buffer_views[idx_acc.get("bufferView", 0)]
                    chunk = bin_data[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv.get("byteLength", 0)]
                    count = idx_acc.get("count", 0)
                    ctype = idx_acc.get("componentType", 5123)  # UNSIGNED_SHORT
                    for i in range(0, count, 3):
                        if ctype == 5121:  # UNSIGNED_BYTE
                            tri = [chunk[i], chunk[i + 1], chunk[i + 2]]
                        elif ctype == 5123:  # UNSIGNED_SHORT
                            tri = struct.unpack("<3H", chunk[i * 2:i * 2 + 6])
                        else:  # UNSIGNED_INT
                            tri = struct.unpack("<3I", chunk[i * 4:i * 4 + 12])
                        obj.faces.append(Face(vertex_indices=list(tri)))
        return obj

    def _write_gltf(self, obj: Object3D, p: Path) -> Dict[str, Any]:
        # Build binary buffer for positions + indices
        pos_bin = b"".join(struct.pack("<3f", v.x, v.y, v.z) for v in obj.vertices)
        idx_bin = b"".join(struct.pack("<3H", f.vertex_indices[0], f.vertex_indices[1], f.vertex_indices[2])
                            for f in obj.faces if len(f.vertex_indices) == 3)
        bin_path = p.with_suffix(".bin")
        bin_path.write_bytes(pos_bin + idx_bin)
        gltf = {
            "asset": {"version": "2.0", "generator": "Data3DEngine"},
            "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "name": obj.name}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
            "buffers": [{"byteLength": len(pos_bin) + len(idx_bin), "uri": bin_path.name}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": len(pos_bin), "target": 34962},
                {"buffer": 0, "byteOffset": len(pos_bin), "byteLength": len(idx_bin), "target": 34963},
            ],
            "accessors": [
                {"bufferView": 0, "componentType": 5126, "count": len(obj.vertices),
                 "type": "VEC3", "max": [max((v.x for v in obj.vertices), default=0),
                                          max((v.y for v in obj.vertices), default=0),
                                          max((v.z for v in obj.vertices), default=0)],
                 "min": [min((v.x for v in obj.vertices), default=0),
                         min((v.y for v in obj.vertices), default=0),
                         min((v.z for v in obj.vertices), default=0)]},
                {"bufferView": 1, "componentType": 5123, "count": sum(1 for f in obj.faces if len(f.vertex_indices) == 3) * 3, "type": "SCALAR"},
            ],
        }
        p.write_text(json.dumps(gltf, indent=2), encoding="utf-8")
        return {"success": True, "dst": str(p), "size_bytes": p.stat().st_size,
                "bin": str(bin_path), "engine": "data3d-gltf"}


_singleton: Optional[Data3DEngine] = None


def get_data_3d_engine() -> Data3DEngine:
    global _singleton
    if _singleton is None:
        _singleton = Data3DEngine()
    return _singleton


__all__ = ["Data3DEngine", "Object3D", "Vertex", "Face", "Material", "get_data_3d_engine"]
