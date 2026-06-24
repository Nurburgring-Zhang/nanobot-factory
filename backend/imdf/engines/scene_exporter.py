"""
3D Scene Exporter
=================
Exports 3D scenes to glTF and OBJ formats using pure Python (no external deps).
If trimesh is available, it will be used for richer export; otherwise,
pure-text minimal structure is emitted.

Usage:
    exporter = SceneExporter()
    exporter.export_gltf("scene_001", "output/scene.gltf")
    exporter.export_obj("scene_001", "output/scene.obj")
"""

import os
import json
import logging
import struct
import base64
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False

# Use numpy only if available for buffer packing
if HAS_NUMPY:
    _array = lambda x: x.tolist() if hasattr(x, 'tolist') else x
else:
    _array = lambda x: x


class SceneMesh:
    """Simple mesh representation for export"""
    def __init__(self, name: str = "mesh"):
        self.name = name
        self.vertices: List[List[float]] = []
        self.normals: List[List[float]] = []
        self.uvs: List[List[float]] = []
        self.faces: List[List[int]] = []
        self.material: Optional[Dict[str, Any]] = None


class SceneExporter:
    """
    3D Scene Exporter for glTF and OBJ formats.

    Uses trimesh if available (for real 3D file loading), otherwise
    creates minimal valid structures in pure Python.

    Methods:
        export_gltf(scene_id, output_path) — Export to glTF format
        export_obj(scene_id, output_path)  — Export to OBJ format
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        Args:
            data_dir: Directory containing 3D scene data files.
                      If None, generates synthetic geometry.
        """
        self.data_dir = data_dir
        self._meshes: Dict[str, SceneMesh] = {}

    # ── Scene Loading ─────────────────────────────────────────────────────

    def _load_scene(self, scene_id: str) -> List[SceneMesh]:
        """
        Load or generate scene meshes for the given scene_id.

        If a data directory is configured and contains files matching
        the scene_id, attempt to load them. Otherwise, generate a
        simple test mesh (a cube) to ensure the export works.
        """
        meshes: List[SceneMesh] = []

        # Try loading from data directory
        if self.data_dir:
            scene_dir = Path(self.data_dir) / scene_id
            if scene_dir.exists():
                # Try trimesh loading first
                if HAS_TRIMESH:
                    loaded = self._load_with_trimesh(scene_dir)
                    if loaded:
                        return loaded
                # Fallback: try loading OBJ manually
                obj_files = list(scene_dir.glob("*.obj"))
                if obj_files:
                    for obj_path in obj_files:
                        mesh = self._parse_obj_file(str(obj_path))
                        if mesh:
                            meshes.append(mesh)
                    if meshes:
                        return meshes

        # No data found — generate a default cube mesh
        logger.info(f"No scene data for '{scene_id}', generating default cube")
        meshes.append(self._create_default_cube())
        return meshes

    def _load_with_trimesh(self, scene_dir: Path) -> List[SceneMesh]:
        """Load meshes from a directory using trimesh"""
        meshes: List[SceneMesh] = []
        try:
            supported = list(scene_dir.glob("*.obj")) + \
                        list(scene_dir.glob("*.glb")) + \
                        list(scene_dir.glob("*.gltf")) + \
                        list(scene_dir.glob("*.stl")) + \
                        list(scene_dir.glob("*.ply")) + \
                        list(scene_dir.glob("*.off"))
            for filepath in supported:
                try:
                    tm_scene = trimesh.load(str(filepath), force="scene")
                    if isinstance(tm_scene, trimesh.Scene):
                        for name, geom in tm_scene.geometry.items():
                            meshes.append(self._trimesh_to_scene_mesh(geom, name))
                    elif isinstance(tm_scene, trimesh.Trimesh):
                        meshes.append(
                            self._trimesh_to_scene_mesh(tm_scene, filepath.stem)
                        )
                except Exception as e:
                    logger.warning(f"Failed to load {filepath}: {e}")
        except Exception as e:
            logger.warning(f"trimesh loading error: {e}")
        return meshes

    def _trimesh_to_scene_mesh(self, mesh: "trimesh.Trimesh",
                               name: str) -> SceneMesh:
        """Convert a trimesh Trimesh object to SceneMesh"""
        sm = SceneMesh(name=name)
        if HAS_NUMPY:
            sm.vertices = mesh.vertices.tolist()
            sm.normals = mesh.vertex_normals.tolist() if hasattr(mesh, 'vertex_normals') else []
            sm.faces = mesh.faces.tolist()
            if mesh.visual and hasattr(mesh.visual, 'uv'):
                sm.uvs = mesh.visual.uv.tolist() if mesh.visual.uv is not None else []
        else:
            sm.vertices = list(mesh.vertices)
            sm.faces = list(mesh.faces)
        return sm

    # ── glTF Export ───────────────────────────────────────────────────────

    def export_gltf(self, scene_id: str, output_path: str,
                    embed_buffers: bool = True) -> str:
        """
        Export a 3D scene to glTF format (JSON-based).

        Minimum fields: scene, nodes, meshes, accessors, bufferViews, buffers.

        Args:
            scene_id: Identifier for the scene
            output_path: Output .gltf file path
            embed_buffers: If True, embed buffer data as base64 data URIs

        Returns:
            Absolute path to the output file
        """
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        meshes = self._load_scene(scene_id)
        gltf = self._build_gltf(meshes, embed_buffers, scene_id)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(gltf, f, indent=2, ensure_ascii=False)

        file_size = os.path.getsize(output_path)
        logger.info(f"glTF exported: {output_path} ({file_size} bytes, "
                    f"{len(meshes)} mesh(es))")
        return output_path

    def _build_gltf(self, meshes: List[SceneMesh],
                    embed: bool, scene_id: str) -> Dict:
        """Build complete glTF JSON structure"""
        buffer_data = bytearray()
        accessors = []
        buffer_views = []
        gltf_meshes = []
        nodes = []
        byte_offset = 0
        accessor_idx = 0

        for mi, mesh in enumerate(meshes):
            if not mesh.vertices or not mesh.faces:
                continue

            # Positions
            vert_bytes = self._pack_float_array(mesh.vertices)
            buffer_views.append({
                "buffer": 0,
                "byteOffset": byte_offset,
                "byteLength": len(vert_bytes),
                "target": 34962,  # ARRAY_BUFFER
            })
            accessors.append({
                "bufferView": accessor_idx,
                "componentType": 5126,  # FLOAT
                "count": len(mesh.vertices),
                "type": "VEC3",
                "min": self._min_vec(mesh.vertices),
                "max": self._max_vec(mesh.vertices),
            })
            pos_accessor = accessor_idx
            accessor_idx += 1
            buffer_data.extend(vert_bytes)
            byte_offset += len(vert_bytes)

            # Normals (if available)
            norm_accessor = -1
            if mesh.normals and len(mesh.normals) == len(mesh.vertices):
                norm_bytes = self._pack_float_array(mesh.normals)
                buffer_views.append({
                    "buffer": 0,
                    "byteOffset": byte_offset,
                    "byteLength": len(norm_bytes),
                    "target": 34962,
                })
                accessors.append({
                    "bufferView": accessor_idx,
                    "componentType": 5126,
                    "count": len(mesh.normals),
                    "type": "VEC3",
                })
                norm_accessor = accessor_idx
                accessor_idx += 1
                buffer_data.extend(norm_bytes)
                byte_offset += len(norm_bytes)

            # UVs (if available)
            uv_accessor = -1
            if mesh.uvs and len(mesh.uvs) == len(mesh.vertices):
                uv_bytes = self._pack_float_array(mesh.uvs)
                buffer_views.append({
                    "buffer": 0,
                    "byteOffset": byte_offset,
                    "byteLength": len(uv_bytes),
                    "target": 34962,
                })
                accessors.append({
                    "bufferView": accessor_idx,
                    "componentType": 5126,
                    "count": len(mesh.uvs),
                    "type": "VEC2",
                })
                uv_accessor = accessor_idx
                accessor_idx += 1
                buffer_data.extend(uv_bytes)
                byte_offset += len(uv_bytes)

            # Indices
            flat_indices = []
            for tri in mesh.faces:
                flat_indices.extend(tri[:3])
            idx_bytes = self._pack_uint32_array(flat_indices)
            buffer_views.append({
                "buffer": 0,
                "byteOffset": byte_offset,
                "byteLength": len(idx_bytes),
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            })
            accessors.append({
                "bufferView": accessor_idx,
                "componentType": 5125,  # UNSIGNED_INT
                "count": len(flat_indices),
                "type": "SCALAR",
                "min": [min(flat_indices)],
                "max": [max(flat_indices)],
            })
            idx_accessor = accessor_idx
            accessor_idx += 1
            buffer_data.extend(idx_bytes)
            byte_offset += len(idx_bytes)

            # Mesh primitive
            attributes = {"POSITION": pos_accessor}
            if norm_accessor >= 0:
                attributes["NORMAL"] = norm_accessor
            if uv_accessor >= 0:
                attributes["TEXCOORD_0"] = uv_accessor

            gltf_meshes.append({
                "name": mesh.name,
                "primitives": [{
                    "attributes": attributes,
                    "indices": idx_accessor,
                }],
            })

            # Node
            nodes.append({
                "name": mesh.name,
                "mesh": mi,
            })

        # Create IDs for unique positions/indices
        if not gltf_meshes:
            # Fallback: this should never happen if _load_scene works,
            # but handle gracefully
            return {
                "asset": {"version": "2.0", "generator": "IMDF SceneExporter"},
                "scene": 0,
                "scenes": [{"name": scene_id, "nodes": []}],
                "nodes": [],
                "meshes": [],
                "accessors": [],
                "bufferViews": [],
                "buffers": [{"byteLength": 0}],
            }

        # Buffer
        if embed:
            b64 = base64.b64encode(bytes(buffer_data)).decode("ascii")
            buffers = [{
                "uri": f"data:application/octet-stream;base64,{b64}",
                "byteLength": len(buffer_data),
            }]
        else:
            buffer_filename = f"{scene_id}.bin"
            buffer_path = os.path.join(
                os.path.dirname(os.path.abspath(output_path or ".")),
                buffer_filename
            )
            with open(buffer_path, "wb") as f:
                f.write(bytes(buffer_data))
            buffers = [{
                "uri": buffer_filename,
                "byteLength": len(buffer_data),
            }]

        gltf = {
            "asset": {
                "version": "2.0",
                "generator": "IMDF SceneExporter",
            },
            "scene": 0,
            "scenes": [{
                "name": scene_id,
                "nodes": list(range(len(nodes))),
            }],
            "nodes": nodes,
            "meshes": gltf_meshes,
            "accessors": accessors,
            "bufferViews": buffer_views,
            "buffers": buffers,
        }

        return gltf

    # ── OBJ Export ────────────────────────────────────────────────────────

    def export_obj(self, scene_id: str, output_path: str) -> str:
        """
        Export a 3D scene to Wavefront OBJ format (simple text format).

        Args:
            scene_id: Identifier for the scene
            output_path: Output .obj file path

        Returns:
            Absolute path to the output file
        """
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        meshes = self._load_scene(scene_id)
        mtl_path = output_path.replace(".obj", ".mtl")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# OBJ exported from IMDF SceneExporter\n")
            f.write(f"# Scene: {scene_id}\n")
            f.write(f"# Date: {__import__('datetime').datetime.now().isoformat()}\n")
            f.write(f"mtllib {os.path.basename(mtl_path)}\n\n")

            vertex_offset = 1  # OBJ indices start at 1
            mtl_names = []

            for mi, mesh in enumerate(meshes):
                if not mesh.vertices or not mesh.faces:
                    continue

                obj_name = mesh.name or f"mesh_{mi}"
                f.write(f"o {obj_name}\n")

                # Vertices
                for v in mesh.vertices:
                    f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")

                # Normals
                if mesh.normals and len(mesh.normals) == len(mesh.vertices):
                    for n in mesh.normals:
                        f.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")

                # UVs
                if mesh.uvs and len(mesh.uvs) == len(mesh.vertices):
                    for uv in mesh.uvs:
                        f.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")

                # Faces
                has_normals = len(mesh.normals) == len(mesh.vertices)
                has_uvs = len(mesh.uvs) == len(mesh.vertices)

                mtl_name = mesh.name or f"material_{mi}"
                f.write(f"usemtl {mtl_name}\n")
                mtl_names.append(mtl_name)

                for tri in mesh.faces:
                    if len(tri) >= 3:
                        idxs = []
                        for i in range(3):
                            vi = tri[i] + vertex_offset
                            if has_normals and has_uvs:
                                idxs.append(f"{vi}/{vi}/{vi}")
                            elif has_normals:
                                idxs.append(f"{vi}//{vi}")
                            elif has_uvs:
                                idxs.append(f"{vi}/{vi}")
                            else:
                                idxs.append(str(vi))
                        f.write(f"f {' '.join(idxs)}\n")

                vertex_offset += len(mesh.vertices)

            f.write(f"\n# Total vertices: {vertex_offset - 1}\n")
            f.write(f"# Total meshes: {len(meshes)}\n")

        # Create MTL file
        with open(mtl_path, "w", encoding="utf-8") as f:
            f.write(f"# MTL exported from IMDF SceneExporter\n")
            for mtl_name in mtl_names:
                f.write(f"\nnewmtl {mtl_name}\n")
                f.write("Ka 0.8 0.8 0.8\n")
                f.write("Kd 0.7 0.7 0.7\n")
                f.write("Ks 0.3 0.3 0.3\n")
                f.write("Ns 20.0\n")
                f.write("d 1.0\n")
                f.write("illum 2\n")

        file_size = os.path.getsize(output_path)
        logger.info(f"OBJ exported: {output_path} ({file_size} bytes, "
                    f"{len(meshes)} mesh(es))")
        return output_path

    # ── Default Cube ──────────────────────────────────────────────────────

    def _create_default_cube(self) -> SceneMesh:
        """Create a simple unit cube mesh"""
        mesh = SceneMesh(name="cube")

        # 8 vertices
        v = [
            [-0.5, -0.5, -0.5],
            [0.5, -0.5, -0.5],
            [0.5, 0.5, -0.5],
            [-0.5, 0.5, -0.5],
            [-0.5, -0.5, 0.5],
            [0.5, -0.5, 0.5],
            [0.5, 0.5, 0.5],
            [-0.5, 0.5, 0.5],
        ]
        mesh.vertices = v

        # Normals (per-vertex, proper face normals for a cube)
        # Each vertex has 3 different normals (one per adjacent face)
        # We use the average of adjacent face normals
        mesh.normals = [
            [-0.577, -0.577, -0.577],  # vertex 0: left-bottom-back
            [0.577, -0.577, -0.577],   # vertex 1: right-bottom-back
            [0.577, 0.577, -0.577],    # vertex 2: right-top-back
            [-0.577, 0.577, -0.577],   # vertex 3: left-top-back
            [-0.577, -0.577, 0.577],   # vertex 4: left-bottom-front
            [0.577, -0.577, 0.577],    # vertex 5: right-bottom-front
            [0.577, 0.577, 0.577],     # vertex 6: right-top-front
            [-0.577, 0.577, 0.577],    # vertex 7: left-top-front
        ]

        # 12 triangles (6 faces)
        mesh.faces = [
            [0, 1, 2], [0, 2, 3],  # back
            [4, 6, 5], [4, 7, 6],  # front
            [0, 4, 5], [0, 5, 1],  # bottom
            [2, 6, 7], [2, 7, 3],  # top
            [0, 3, 7], [0, 7, 4],  # left
            [1, 5, 6], [1, 6, 2],  # right
        ]

        return mesh

    # ── Buffer Helpers ────────────────────────────────────────────────────

    def _pack_float_array(self, arr: List[List[float]]) -> bytes:
        """Pack a list of float vectors into bytes"""
        if HAS_NUMPY:
            return np.array(arr, dtype=np.float32).tobytes()
        data = bytearray()
        for vec in arr:
            for val in vec:
                data.extend(struct.pack("<f", float(val)))
        return bytes(data)

    def _pack_uint32_array(self, arr: List[int]) -> bytes:
        """Pack a list of unsigned ints into bytes"""
        if HAS_NUMPY:
            return np.array(arr, dtype=np.uint32).tobytes()
        data = bytearray()
        for val in arr:
            data.extend(struct.pack("<I", int(val)))
        return bytes(data)

    def _min_vec(self, vertices: List[List[float]]) -> List[float]:
        """Component-wise minimum of vertex array"""
        if not vertices:
            return [0.0, 0.0, 0.0]
        min_vals = list(vertices[0])
        for v in vertices[1:]:
            for i in range(min(3, len(v))):
                if v[i] < min_vals[i]:
                    min_vals[i] = v[i]
        return min_vals

    def _max_vec(self, vertices: List[List[float]]) -> List[float]:
        """Component-wise maximum of vertex array"""
        if not vertices:
            return [0.0, 0.0, 0.0]
        max_vals = list(vertices[0])
        for v in vertices[1:]:
            for i in range(min(3, len(v))):
                if v[i] > max_vals[i]:
                    max_vals[i] = v[i]
        return max_vals

    # ── OBJ Parser ────────────────────────────────────────────────────────

    def _parse_obj_file(self, obj_path: str) -> Optional[SceneMesh]:
        """Minimal OBJ file parser (vertices + faces only)"""
        mesh = SceneMesh(name=Path(obj_path).stem)
        vertices = []
        try:
            with open(obj_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("v ") or line.startswith("v\t"):
                        parts = line.split()
                        if len(parts) >= 4:
                            vertices.append([
                                float(parts[1]),
                                float(parts[2]),
                                float(parts[3]),
                            ])
                    elif line.startswith("f ") or line.startswith("f\t"):
                        parts = line.split()
                        if len(parts) >= 4:
                            tri = []
                            for p in parts[1:4]:
                                idx = p.split("/")[0]
                                try:
                                    tri.append(int(idx) - 1)
                                except ValueError:
                                    tri.append(0)
                            mesh.faces.append(tri)
            mesh.vertices = vertices
            return mesh if vertices else None
        except Exception as e:
            logger.warning(f"Failed to parse OBJ {obj_path}: {e}")
            return None
