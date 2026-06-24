"""
资产管理引擎 (DAM Engine) — F1.8
================================
完整DAM: 90+格式预览 / 语义搜索 / AI打标 / 智能文件夹 / 血统图谱

Architecture:
  - FormatPreviewEngine: 90+ format preview generation (image/video/audio/3D/doc/dataset)
  - SmartFolderEngine: Rule-based dynamic folders (integrated with OSS triple bucket)
  - AITagEngine: AI auto-tagging via ModelGateway
  - SemanticSearchEngine: Semantic search across files + tags
  - LineageEngine: Data lineage DAG tracking

Dependencies:
  - PIL / Pillow (images)
  - ffmpeg / ffprobe (video/audio)
  - pdf2image (PDF)
  - ModelGateway (AI calls)
"""

from __future__ import annotations
import os
import json
import time
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ============================================================================
# Constants — 90+ Format Registry
# ============================================================================

FORMAT_REGISTRY = {
    # Images (20+)
    ".jpg":  {"category": "image", "mime": "image/jpeg", "preview": "thumbnail"},
    ".jpeg": {"category": "image", "mime": "image/jpeg", "preview": "thumbnail"},
    ".png":  {"category": "image", "mime": "image/png", "preview": "thumbnail"},
    ".gif":  {"category": "image", "mime": "image/gif", "preview": "thumbnail"},
    ".bmp":  {"category": "image", "mime": "image/bmp", "preview": "thumbnail"},
    ".webp": {"category": "image", "mime": "image/webp", "preview": "thumbnail"},
    ".svg":  {"category": "image", "mime": "image/svg+xml", "preview": "thumbnail"},
    ".tiff": {"category": "image", "mime": "image/tiff", "preview": "thumbnail"},
    ".tif":  {"category": "image", "mime": "image/tiff", "preview": "thumbnail"},
    ".ico":  {"category": "image", "mime": "image/x-icon", "preview": "thumbnail"},
    ".heic": {"category": "image", "mime": "image/heic", "preview": "thumbnail"},
    ".heif": {"category": "image", "mime": "image/heif", "preview": "thumbnail"},
    ".avif": {"category": "image", "mime": "image/avif", "preview": "thumbnail"},
    ".psd":  {"category": "image", "mime": "image/vnd.adobe.photoshop", "preview": "thumbnail"},
    ".ai":   {"category": "image", "mime": "application/postscript", "preview": "thumbnail"},
    ".eps":  {"category": "image", "mime": "application/postscript", "preview": "thumbnail"},
    ".raw":  {"category": "image", "mime": "image/x-raw", "preview": "thumbnail"},
    ".cr2":  {"category": "image", "mime": "image/x-canon-cr2", "preview": "thumbnail"},
    ".nef":  {"category": "image", "mime": "image/x-nikon-nef", "preview": "thumbnail"},
    ".dng":  {"category": "image", "mime": "image/x-adobe-dng", "preview": "thumbnail"},
    ".exr":  {"category": "image", "mime": "image/x-exr", "preview": "thumbnail"},
    ".hdr":  {"category": "image", "mime": "image/vnd.radiance", "preview": "thumbnail"},

    # Video (15+)
    ".mp4":  {"category": "video", "mime": "video/mp4", "preview": "keyframe"},
    ".avi":  {"category": "video", "mime": "video/x-msvideo", "preview": "keyframe"},
    ".mov":  {"category": "video", "mime": "video/quicktime", "preview": "keyframe"},
    ".mkv":  {"category": "video", "mime": "video/x-matroska", "preview": "keyframe"},
    ".webm": {"category": "video", "mime": "video/webm", "preview": "keyframe"},
    ".wmv":  {"category": "video", "mime": "video/x-ms-wmv", "preview": "keyframe"},
    ".flv":  {"category": "video", "mime": "video/x-flv", "preview": "keyframe"},
    ".m4v":  {"category": "video", "mime": "video/x-m4v", "preview": "keyframe"},
    ".3gp":  {"category": "video", "mime": "video/3gpp", "preview": "keyframe"},
    ".mpeg": {"category": "video", "mime": "video/mpeg", "preview": "keyframe"},
    ".mpg":  {"category": "video", "mime": "video/mpeg", "preview": "keyframe"},
    ".ts":   {"category": "video", "mime": "video/mp2t", "preview": "keyframe"},
    ".mts":  {"category": "video", "mime": "video/mp2t", "preview": "keyframe"},
    ".ogv":  {"category": "video", "mime": "video/ogg", "preview": "keyframe"},
    ".vob":  {"category": "video", "mime": "video/dvd", "preview": "keyframe"},

    # Audio (15+)
    ".mp3":  {"category": "audio", "mime": "audio/mpeg", "preview": "waveform"},
    ".wav":  {"category": "audio", "mime": "audio/wav", "preview": "waveform"},
    ".flac": {"category": "audio", "mime": "audio/flac", "preview": "waveform"},
    ".aac":  {"category": "audio", "mime": "audio/aac", "preview": "waveform"},
    ".ogg":  {"category": "audio", "mime": "audio/ogg", "preview": "waveform"},
    ".wma":  {"category": "audio", "mime": "audio/x-ms-wma", "preview": "waveform"},
    ".m4a":  {"category": "audio", "mime": "audio/mp4", "preview": "waveform"},
    ".opus": {"category": "audio", "mime": "audio/opus", "preview": "waveform"},
    ".aiff": {"category": "audio", "mime": "audio/aiff", "preview": "waveform"},
    ".alac": {"category": "audio", "mime": "audio/alac", "preview": "waveform"},
    ".ape":  {"category": "audio", "mime": "audio/ape", "preview": "waveform"},
    ".ac3":  {"category": "audio", "mime": "audio/ac3", "preview": "waveform"},
    ".dts":  {"category": "audio", "mime": "audio/vnd.dts", "preview": "waveform"},
    ".amr":  {"category": "audio", "mime": "audio/amr", "preview": "waveform"},
    ".mid":  {"category": "audio", "mime": "audio/midi", "preview": "waveform"},

    # 3D (10+)
    ".obj":  {"category": "3d", "mime": "application/wavefront-obj", "preview": "thumbnail_3d"},
    ".fbx":  {"category": "3d", "mime": "application/octet-stream", "preview": "thumbnail_3d"},
    ".gltf": {"category": "3d", "mime": "model/gltf+json", "preview": "thumbnail_3d"},
    ".glb":  {"category": "3d", "mime": "model/gltf-binary", "preview": "thumbnail_3d"},
    ".stl":  {"category": "3d", "mime": "model/stl", "preview": "thumbnail_3d"},
    ".ply":  {"category": "3d", "mime": "model/ply", "preview": "thumbnail_3d"},
    ".dae":  {"category": "3d", "mime": "model/vnd.collada+xml", "preview": "thumbnail_3d"},
    ".3ds":  {"category": "3d", "mime": "application/x-3ds", "preview": "thumbnail_3d"},
    ".blend":{"category": "3d", "mime": "application/x-blender", "preview": "thumbnail_3d"},
    ".usd":  {"category": "3d", "mime": "model/vnd.usd", "preview": "thumbnail_3d"},
    ".usdz": {"category": "3d", "mime": "model/vnd.usdz+zip", "preview": "thumbnail_3d"},
    ".ma":   {"category": "3d", "mime": "application/x-maya", "preview": "thumbnail_3d"},
    ".mb":   {"category": "3d", "mime": "application/x-maya", "preview": "thumbnail_3d"},

    # Documents (20+)
    ".pdf":  {"category": "document", "mime": "application/pdf", "preview": "page_image"},
    ".doc":  {"category": "document", "mime": "application/msword", "preview": "icon"},
    ".docx": {"category": "document", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "preview": "icon"},
    ".xls":  {"category": "document", "mime": "application/vnd.ms-excel", "preview": "icon"},
    ".xlsx": {"category": "document", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "preview": "icon"},
    ".ppt":  {"category": "document", "mime": "application/vnd.ms-powerpoint", "preview": "icon"},
    ".pptx": {"category": "document", "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "preview": "icon"},
    ".txt":  {"category": "document", "mime": "text/plain", "preview": "text_snippet"},
    ".csv":  {"category": "document", "mime": "text/csv", "preview": "table_preview"},
    ".html": {"category": "document", "mime": "text/html", "preview": "rendered"},
    ".htm":  {"category": "document", "mime": "text/html", "preview": "rendered"},
    ".xml":  {"category": "document", "mime": "application/xml", "preview": "text_snippet"},
    ".json": {"category": "document", "mime": "application/json", "preview": "text_snippet"},
    ".yaml": {"category": "document", "mime": "application/x-yaml", "preview": "text_snippet"},
    ".yml":  {"category": "document", "mime": "application/x-yaml", "preview": "text_snippet"},
    ".md":   {"category": "document", "mime": "text/markdown", "preview": "rendered"},
    ".rst":  {"category": "document", "mime": "text/x-rst", "preview": "text_snippet"},
    ".rtf":  {"category": "document", "mime": "application/rtf", "preview": "icon"},
    ".odt":  {"category": "document", "mime": "application/vnd.oasis.opendocument.text", "preview": "icon"},
    ".ods":  {"category": "document", "mime": "application/vnd.oasis.opendocument.spreadsheet", "preview": "icon"},
    ".odp":  {"category": "document", "mime": "application/vnd.oasis.opendocument.presentation", "preview": "icon"},
    ".tex":  {"category": "document", "mime": "application/x-tex", "preview": "text_snippet"},
    ".log":  {"category": "document", "mime": "text/plain", "preview": "text_snippet"},

    # Datasets (10+)
    ".csv":   {"category": "dataset", "mime": "text/csv", "preview": "table_preview"},
    ".parquet":{"category": "dataset", "mime": "application/parquet", "preview": "table_preview"},
    ".arrow": {"category": "dataset", "mime": "application/arrow", "preview": "table_preview"},
    ".jsonl": {"category": "dataset", "mime": "application/jsonlines", "preview": "text_snippet"},
    ".avro":  {"category": "dataset", "mime": "application/avro", "preview": "table_preview"},
    ".orc":   {"category": "dataset", "mime": "application/x-orc", "preview": "table_preview"},
    ".feather":{"category": "dataset", "mime": "application/feather", "preview": "table_preview"},
    ".h5":    {"category": "dataset", "mime": "application/x-hdf5", "preview": "icon"},
    ".hdf5":  {"category": "dataset", "mime": "application/x-hdf5", "preview": "icon"},
    ".tfrecord":{"category": "dataset", "mime": "application/octet-stream", "preview": "icon"},
    ".npy":   {"category": "dataset", "mime": "application/octet-stream", "preview": "icon"},
    ".npz":   {"category": "dataset", "mime": "application/octet-stream", "preview": "icon"},

    # Archives
    ".zip": {"category": "archive", "mime": "application/zip", "preview": "icon"},
    ".tar": {"category": "archive", "mime": "application/x-tar", "preview": "icon"},
    ".gz":  {"category": "archive", "mime": "application/gzip", "preview": "icon"},
    ".7z":  {"category": "archive", "mime": "application/x-7z-compressed", "preview": "icon"},
    ".rar": {"category": "archive", "mime": "application/vnd.rar", "preview": "icon"},
}

# Format counts per category
FORMAT_COUNTS = {}
for __ext, __info in FORMAT_REGISTRY.items():
    FORMAT_COUNTS[__info["category"]] = FORMAT_COUNTS.get(__info["category"], 0) + 1

THUMB_DIR = Path("data/thumbnails")
THUMB_DIR.mkdir(parents=True, exist_ok=True)
DAM_DB_PATH = Path("data/dam_state.db")

# ============================================================================
# Path Traversal Protection
# ============================================================================

# Allowed base directories for file operations (resolved to absolute paths)
_ALLOWED_DIRS = [
    Path("data/uploads"),
    Path("data/output"),
    Path("data/test_images"),
    THUMB_DIR,
]

def _resolve_allowed_dirs():
    """Resolve allowed directories to absolute real paths."""
    resolved = []
    for d in _ALLOWED_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        resolved.append(os.path.realpath(str(d)))
    return resolved

def is_safe_path(file_path: str, allowed_dirs: Optional[List[str]] = None) -> bool:
    """Check if a file path is within allowed directories (path traversal protection).
    
    Args:
        file_path: The path to check
        allowed_dirs: Optional list of allowed directory realpaths. 
                      If None, uses default _resolve_allowed_dirs().
    
    Returns:
        True if the path is safe, False otherwise
    """
    if allowed_dirs is None:
        allowed_dirs = _SAFE_DIRS
    
    try:
        real_path = os.path.realpath(file_path)
    except Exception:
        return False
    
    for allowed in allowed_dirs:
        if real_path.startswith(allowed + os.sep) or real_path == allowed:
            return True
    return False

# Pre-resolve safe directories at module load
_SAFE_DIRS = _resolve_allowed_dirs()

# ============================================================================
# Data Models
# ============================================================================

class FileCategory(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MODEL_3D = "3d"
    DOCUMENT = "document"
    DATASET = "dataset"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"

@dataclass
class DAMFile:
    """DAM managed file record"""
    id: str
    path: str
    name: str
    ext: str
    category: str
    mime: str
    size_bytes: int
    tags: List[str] = field(default_factory=list)
    labels: Dict[str, List[str]] = field(default_factory=dict)
    preview_url: str = ""
    thumbnail_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    modified_at: float = 0.0
    lineage_parents: List[str] = field(default_factory=list)  # parent file ids
    lineage_children: List[str] = field(default_factory=list)  # child file ids

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "name": self.name,
            "ext": self.ext,
            "category": self.category,
            "mime": self.mime,
            "size_bytes": self.size_bytes,
            "tags": self.tags,
            "labels": self.labels,
            "preview_url": self.preview_url,
            "thumbnail_url": self.thumbnail_url,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "lineage_parents": self.lineage_parents,
            "lineage_children": self.lineage_children,
        }

@dataclass
class SmartFolder:
    """Smart folder with matching rules"""
    id: str
    name: str
    description: str = ""
    rules: List[Dict[str, Any]] = field(default_factory=list)
    # rule format: {"field": "ext", "operator": "in", "value": [".jpg", ".png"]}
    # operators: eq, ne, in, not_in, contains, starts_with, ends_with, gt, lt, regex
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rules": self.rules,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass
class LineageNode:
    """Node in a data lineage graph"""
    file_id: str
    name: str
    category: str
    parents: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)  # what ops created this
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "category": self.category,
            "parents": self.parents,
            "children": self.children,
            "operations": self.operations,
            "metadata": self.metadata,
        }


# ============================================================================
# FormatPreviewEngine: 90+ format preview generation
# ============================================================================

class FormatPreviewEngine:
    """Generate previews for 90+ file formats."""

    @staticmethod
    def get_format_info(ext: str) -> Optional[Dict[str, str]]:
        """Get registered format info for extension."""
        ext_lower = ext.lower()
        return FORMAT_REGISTRY.get(ext_lower)

    @staticmethod
    def get_all_categories() -> List[Dict[str, Any]]:
        """List all supported categories with format counts."""
        return [
            {"category": cat, "count": count, "formats": sorted([
                ext for ext, info in FORMAT_REGISTRY.items()
                if info["category"] == cat
            ])}
            for cat, count in sorted(FORMAT_COUNTS.items(), key=lambda x: -x[1])
        ]

    @staticmethod
    def get_total_format_count() -> int:
        """Return total supported formats across all categories."""
        return len(FORMAT_REGISTRY)

    @staticmethod
    def generate_preview(file_path: str) -> Optional[Dict[str, Any]]:
        """Generate preview for a file, returns preview info dict."""
        # Path traversal protection
        if not is_safe_path(file_path):
            logger.warning(f"Path traversal blocked: {file_path}")
            return None
        
        if not os.path.exists(file_path):
            return None

        ext = Path(file_path).suffix.lower()
        fmt_info = FORMAT_REGISTRY.get(ext)
        if not fmt_info:
            fmt_info = {"category": "unknown", "mime": "application/octet-stream", "preview": "icon"}

        preview_type = fmt_info.get("preview", "icon")
        file_hash = hashlib.md5(f"{file_path}{os.path.getmtime(file_path)}".encode()).hexdigest()[:12]

        result = {
            "path": file_path,
            "name": Path(file_path).name,
            "ext": ext,
            "category": fmt_info["category"],
            "mime": fmt_info["mime"],
            "preview_type": preview_type,
            "size_bytes": os.path.getsize(file_path),
            "preview_data": None,
            "preview_url": None,
            "media_info": {},
        }

        # Generate actual preview based on type
        try:
            if preview_type == "thumbnail":
                result.update(FormatPreviewEngine._preview_image(file_path, file_hash))
            elif preview_type == "keyframe":
                result.update(FormatPreviewEngine._preview_video(file_path, file_hash))
            elif preview_type == "waveform":
                result.update(FormatPreviewEngine._preview_audio(file_path, file_hash))
            elif preview_type == "thumbnail_3d":
                result.update(FormatPreviewEngine._preview_3d(file_path, file_hash))
            elif preview_type == "page_image":
                result.update(FormatPreviewEngine._preview_pdf(file_path, file_hash))
            elif preview_type == "text_snippet":
                result.update(FormatPreviewEngine._preview_text(file_path))
            elif preview_type == "table_preview":
                result.update(FormatPreviewEngine._preview_table(file_path))
            elif preview_type == "rendered":
                result.update(FormatPreviewEngine._preview_rendered(file_path))
            else:
                result["preview_data"] = {"type": "icon", "icon": FormatPreviewEngine._category_icon(fmt_info["category"])}
        except Exception as e:
            logger.warning(f"Preview generation failed for {file_path}: {e}")
            result["preview_data"] = {"type": "icon", "icon": FormatPreviewEngine._category_icon(fmt_info["category"]), "error": str(e)}

        return result

    @staticmethod
    def _category_icon(category: str) -> str:
        icons = {
            "image": "🖼️", "video": "🎬", "audio": "🎵",
            "3d": "🎯", "document": "📄", "dataset": "📊",
            "archive": "📦", "unknown": "📎",
        }
        return icons.get(category, "📎")

    @staticmethod
    def _preview_image(file_path: str, file_hash: str) -> Dict[str, Any]:
        """Generate image thumbnail."""
        thumb_path = THUMB_DIR / f"{file_hash}.jpg"
        info = {"width": 0, "height": 0, "format": ""}

        try:
            from PIL import Image
            img = Image.open(file_path)
            info["width"] = img.width
            info["height"] = img.height
            info["format"] = img.format or ""

            if not thumb_path.exists():
                img.thumbnail((512, 512))
                img.convert("RGB").save(thumb_path, "JPEG", quality=75)

            return {
                "preview_url": f"/static/thumbnails/{file_hash}.jpg",
                "preview_data": {"type": "image", "width": info["width"], "height": info["height"]},
                "media_info": info,
            }
        except ImportError:
            return {"preview_data": {"type": "icon", "icon": "🖼️"}, "media_info": info}

    @staticmethod
    def _preview_video(file_path: str, file_hash: str) -> Dict[str, Any]:
        """Generate video keyframe thumbnail."""
        thumb_path = THUMB_DIR / f"{file_hash}.jpg"
        info = {}

        try:
            import subprocess, json
            # Get media info
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path],
                capture_output=True, timeout=15
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                info["duration"] = float(data.get("format", {}).get("duration", 0))
                for s in data.get("streams", []):
                    if s.get("codec_type") == "video":
                        info["width"] = s.get("width")
                        info["height"] = s.get("height")
                        info["codec"] = s.get("codec_name")
                        info["fps"] = eval(str(s.get("r_frame_rate", "0/1")))
                        break

            if not thumb_path.exists():
                subprocess.run(
                    ["ffmpeg", "-i", file_path, "-vframes", "1", "-vf", "scale=512:-1",
                     "-y", str(thumb_path)],
                    capture_output=True, timeout=30
                )

            if thumb_path.exists():
                return {
                    "preview_url": f"/static/thumbnails/{file_hash}.jpg",
                    "preview_data": {"type": "video", "duration": info.get("duration", 0)},
                    "media_info": info,
                }
        except Exception as e:
            logger.warning(f"Video preview failed: {e}")

        return {"preview_data": {"type": "icon", "icon": "🎬"}, "media_info": info}

    @staticmethod
    def _preview_audio(file_path: str, file_hash: str) -> Dict[str, Any]:
        """Generate audio waveform info."""
        info = {}
        try:
            import subprocess, json
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path],
                capture_output=True, timeout=10
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                info["duration"] = float(data.get("format", {}).get("duration", 0))
                info["bit_rate"] = int(data.get("format", {}).get("bit_rate", 0))
                for s in data.get("streams", []):
                    if s.get("codec_type") == "audio":
                        info["sample_rate"] = s.get("sample_rate")
                        info["channels"] = s.get("channels")
                        info["codec"] = s.get("codec_name")
                        break
        except Exception as e:
            logger.error(f"Operation failed: {e}")

        return {
            "preview_data": {"type": "audio", "waveform": "placeholder", "duration": info.get("duration", 0)},
            "media_info": info,
        }

    @staticmethod
    def _preview_3d(file_path: str, file_hash: str) -> Dict[str, Any]:
        """Generate 3D model info."""
        info = {
            "file_size": os.path.getsize(file_path),
            "ext": Path(file_path).suffix.lower(),
        }
        return {
            "preview_data": {"type": "3d", "format": info["ext"], "size": info["file_size"]},
            "media_info": info,
        }

    @staticmethod
    def _preview_pdf(file_path: str, file_hash: str) -> Dict[str, Any]:
        """Generate PDF first page preview."""
        thumb_path = THUMB_DIR / f"{file_hash}.jpg"
        info = {"pages": 0}

        try:
            from pdf2image import convert_from_path
            images = convert_from_path(file_path, first_page=1, last_page=1, size=(512, 512))
            if images:
                images[0].save(thumb_path, "JPEG", quality=75)
                info["pages"] = images[0].info.get("pages", 1) if hasattr(images[0], 'info') else 1

            # Try to get page count
            try:
                import subprocess
                r = subprocess.run(
                    ["pdfinfo", file_path], capture_output=True, timeout=10, text=True
                )
                for line in r.stdout.split("\n"):
                    if line.startswith("Pages:"):
                        info["pages"] = int(line.split(":")[1].strip())
                        break
            except Exception as e:
                logger.error(f"Operation failed: {e}")

            if thumb_path.exists():
                return {
                    "preview_url": f"/static/thumbnails/{file_hash}.jpg",
                    "preview_data": {"type": "document", "format": "pdf", "pages": info["pages"]},
                    "media_info": info,
                }
        except ImportError:
            pass

        return {"preview_data": {"type": "icon", "icon": "📄"}, "media_info": info}

    @staticmethod
    def _preview_text(file_path: str) -> Dict[str, Any]:
        """Generate text snippet preview."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4096)
            lines = content.split("\n")[:20]
            return {
                "preview_data": {
                    "type": "text",
                    "snippet": "\n".join(lines),
                    "total_lines": len(content.split("\n")),
                    "total_chars": len(content),
                },
                "media_info": {"chars": len(content), "lines": len(content.split("\n"))},
            }
        except Exception:
            return {"preview_data": {"type": "icon", "icon": "📄"}, "media_info": {}}

    @staticmethod
    def _preview_table(file_path: str) -> Dict[str, Any]:
        """Generate table preview (CSV, etc.)."""
        try:
            import csv
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                rows = [row for _, row in zip(range(10), reader)]

            return {
                "preview_data": {
                    "type": "table",
                    "headers": headers,
                    "rows": rows,
                    "total_rows": len(rows),
                },
                "media_info": {"columns": len(headers), "rows": len(rows)},
            }
        except Exception:
            return {"preview_data": {"type": "icon", "icon": "📊"}, "media_info": {}}

    @staticmethod
    def _preview_rendered(file_path: str) -> Dict[str, Any]:
        """Generate rendered HTML/MD preview."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4096)
            return {
                "preview_data": {
                    "type": "html",
                    "snippet": content,
                    "total_chars": os.path.getsize(file_path),
                },
                "media_info": {"size": os.path.getsize(file_path)},
            }
        except Exception:
            return {"preview_data": {"type": "icon", "icon": "📄"}, "media_info": {}}


# ============================================================================
# SmartFolderEngine: Rule-based dynamic folders
# ============================================================================

class SmartFolderEngine:
    """Manages smart folders with rule-based auto-classification."""

    OPERATORS = {
        "eq": lambda v, c: v == c,
        "ne": lambda v, c: v != c,
        "in": lambda v, c: v in c,
        "not_in": lambda v, c: v not in c,
        "contains": lambda v, c: str(c).lower() in str(v).lower(),
        "starts_with": lambda v, c: str(v).lower().startswith(str(c).lower()),
        "ends_with": lambda v, c: str(v).lower().endswith(str(c).lower()),
        "gt": lambda v, c: float(v) > float(c),
        "lt": lambda v, c: float(v) < float(c),
        "gte": lambda v, c: float(v) >= float(c),
        "lte": lambda v, c: float(v) <= float(c),
        "regex": lambda v, c: bool(__import__("re").search(c, str(v))),
    }

    def __init__(self):
        self._folders: Dict[str, SmartFolder] = {}
        self._init_defaults()

    def _init_defaults(self):
        """Initialize default smart folders."""
        defaults = [
            SmartFolder(
                id="sf_images",
                name="📷 图片素材",
                description="所有图片文件",
                rules=[{"field": "category", "operator": "eq", "value": "image"}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_videos",
                name="🎬 视频素材",
                description="所有视频文件",
                rules=[{"field": "category", "operator": "eq", "value": "video"}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_audio",
                name="🎵 音频素材",
                description="所有音频文件",
                rules=[{"field": "category", "operator": "eq", "value": "audio"}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_3d",
                name="🎯 3D模型",
                description="所有3D模型文件",
                rules=[{"field": "category", "operator": "eq", "value": "3d"}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_documents",
                name="📄 文档",
                description="所有文档文件",
                rules=[{"field": "category", "operator": "eq", "value": "document"}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_datasets",
                name="📊 数据集",
                description="所有数据集文件",
                rules=[{"field": "category", "operator": "eq", "value": "dataset"}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_recent",
                name="🕐 最近7天",
                description="最近一周的文件",
                rules=[{"field": "modified_at", "operator": "gt", "value": str(time.time() - 7 * 86400)}],
                created_at=time.time(),
            ),
            SmartFolder(
                id="sf_large",
                name="💾 大文件 (>100MB)",
                description="大于100MB的文件",
                rules=[{"field": "size_bytes", "operator": "gt", "value": "104857600"}],
                created_at=time.time(),
            ),
        ]
        for sf in defaults:
            self._folders[sf.id] = sf

    def create(self, name: str, rules: List[Dict[str, Any]], description: str = "") -> SmartFolder:
        """Create a new smart folder."""
        folder_id = f"sf_{hashlib.md5(name.encode()).hexdigest()[:10]}"
        sf = SmartFolder(
            id=folder_id,
            name=name,
            description=description,
            rules=rules,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._folders[folder_id] = sf
        return sf

    def get(self, folder_id: str) -> Optional[SmartFolder]:
        return self._folders.get(folder_id)

    def list_all(self) -> List[SmartFolder]:
        return list(self._folders.values())

    def delete(self, folder_id: str) -> bool:
        if folder_id in self._folders:
            del self._folders[folder_id]
            return True
        return False

    def match_files(self, folder_id: str, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Match files against a smart folder's rules."""
        sf = self._folders.get(folder_id)
        if not sf:
            return []

        matched = []
        for f in files:
            if self._evaluate_rules(f, sf.rules):
                matched.append(f)
        return matched

    def match_all_folders(self, files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Match files against all smart folders."""
        results = {}
        for folder_id, sf in self._folders.items():
            matched = []
            for f in files:
                if self._evaluate_rules(f, sf.rules):
                    matched.append(f)
            results[folder_id] = matched
        return results

    def _evaluate_rules(self, file_item: Dict[str, Any], rules: List[Dict[str, Any]]) -> bool:
        """Evaluate all rules against a file item (AND logic)."""
        if not rules:
            return True
        for rule in rules:
            field = rule.get("field", "")
            operator = rule.get("operator", "eq")
            value = rule.get("value")

            field_val = file_item.get(field)
            op_func = self.OPERATORS.get(operator)
            if not op_func:
                continue

            try:
                # Convert string numbers for comparison operators
                if operator in ("gt", "lt", "gte", "lte") and isinstance(value, str):
                    try:
                        value = float(value)
                        field_val = float(field_val)
                    except (ValueError, TypeError):
                        return False

                if not op_func(field_val, value):
                    return False
            except Exception:
                return False
        return True


# ============================================================================
# AITagEngine: AI auto-tagging via Model Gateway
# ============================================================================

class AITagEngine:
    """AI-powered automatic file tagging using the model gateway."""

    TAG_PROMPT = """You are a data asset tagging assistant. Analyze the following file information 
and generate relevant tags and labels. Return ONLY valid JSON with this structure:
{
  "tags": ["tag1", "tag2", ...],
  "labels": {"category": ["label1"], "quality": ["high/medium/low"], "content_type": ["..."], "style": ["..."]},
  "description": "brief description"
}

File info:
- Name: {name}
- Extension: {ext}
- Category: {category}
- Size: {size_bytes} bytes
- Content preview: {preview}

Generate 3-8 tags and labels that best describe this file's content and characteristics."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._gateway = None

    def _get_gateway(self):
        if self._gateway is None:
            try:
                from engines.model_gateway import get_gateway
                self._gateway = get_gateway()
            except Exception as e:
                logger.warning(f"ModelGateway not available: {e}")
        return self._gateway

    async def tag_file(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI tags for a single file."""
        cache_key = hashlib.md5(
            f"{file_info.get('path','')}{file_info.get('size_bytes',0)}".encode()
        ).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build prompt
        prompt = self.TAG_PROMPT.format(
            name=file_info.get("name", "unknown"),
            ext=file_info.get("ext", ""),
            category=file_info.get("category", "unknown"),
            size_bytes=file_info.get("size_bytes", 0),
            preview=str(file_info.get("preview_data", {}))[:500],
        )

        gateway = self._get_gateway()
        if not gateway:
            return self._fallback_tags(file_info)

        try:
            resp = await gateway.chat(
                messages=[{"role": "user", "content": prompt}],
                model="auto",
                temperature=0.3,
                max_tokens=500,
            )
            if resp.success:
                # Parse JSON response
                content = resp.content.strip()
                # Handle markdown code blocks
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
                result = json.loads(content)
                result["ai_model"] = resp.model
                self._cache[cache_key] = result
                return result
        except Exception as e:
            logger.warning(f"AI tagging failed: {e}")

        return self._fallback_tags(file_info)

    def _fallback_tags(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate basic tags without AI (fallback)."""
        ext = file_info.get("ext", "")
        category = file_info.get("category", "unknown")
        name = file_info.get("name", "")

        tags = [category]
        if ext:
            tags.append(ext.lstrip("."))
        size = file_info.get("size_bytes", 0)
        if size > 104857600:
            tags.append("large")
        elif size > 1048576:
            tags.append("medium")
        else:
            tags.append("small")

        # Add name-based tags
        for word in name.lower().replace("_", " ").replace("-", " ").split(".")[0].split():
            if len(word) > 2 and word not in tags:
                tags.append(word)
                if len(tags) >= 8:
                    break

        return {
            "tags": tags[:8],
            "labels": {
                "category": [category],
                "format": [ext.lstrip(".")] if ext else [],
            },
            "description": f"{category} file: {name}",
        }

    async def tag_files_batch(self, files: List[Dict[str, Any]], concurrency: int = 5) -> List[Dict[str, Any]]:
        """Tag multiple files with controlled concurrency."""
        sem = asyncio.Semaphore(concurrency)

        async def tag_one(f):
            async with sem:
                tags = await self.tag_file(f)
                f["tags"] = tags.get("tags", [])
                f["labels"] = tags.get("labels", {})
                f["ai_description"] = tags.get("description", "")
                return f

        tasks = [tag_one(f) for f in files]
        return await asyncio.gather(*tasks)


# ============================================================================
# SemanticSearchEngine: File content + tag semantic search
# ============================================================================

class SemanticSearchEngine:
    """Semantic search across file metadata, content, and AI tags."""

    def __init__(self):
        self._file_index: List[Dict[str, Any]] = []
        self._tag_index: Dict[str, Set[str]] = {}  # tag -> set of file ids

    def index_files(self, files: List[Dict[str, Any]]):
        """Build search index from file list."""
        self._file_index = files
        self._tag_index = {}

        for f in files:
            fid = f.get("id", f.get("path", ""))
            # Index tags
            for tag in f.get("tags", []):
                tag_lower = tag.lower()
                if tag_lower not in self._tag_index:
                    self._tag_index[tag_lower] = set()
                self._tag_index[tag_lower].add(fid)
            # Index labels
            for label_category, labels in f.get("labels", {}).items():
                for label in labels:
                    label_lower = label.lower()
                    if label_lower not in self._tag_index:
                        self._tag_index[label_lower] = set()
                    self._tag_index[label_lower].add(fid)

    def search(self, query: str, limit: int = 50, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Semantic search across files.

        Args:
            query: Search query string
            limit: Maximum results
            filters: Optional dict of {field: value} filters

        Returns:
            Ranked list of matching files
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return self._file_index[:limit]

        results: List[Tuple[Dict[str, Any], float]] = []

        for f in self._file_index:
            score = 0.0
            fid = f.get("id", f.get("path", ""))

            # 1. Exact tag match (highest weight)
            for tag in f.get("tags", []):
                if query_lower in tag.lower() or tag.lower() in query_lower:
                    score += 0.5
                # Partial word match
                if query_lower in tag.lower():
                    score += 0.2

            # 2. Label match
            for label_cat, labels in f.get("labels", {}).items():
                for label in labels:
                    if query_lower in label.lower() or label.lower() in query_lower:
                        score += 0.3

            # 3. Name match
            name = f.get("name", "").lower()
            if query_lower in name:
                score += 0.4
            # Partial word
            for word in query_lower.split():
                if word in name:
                    score += 0.15

            # 4. Category match
            if query_lower in f.get("category", "").lower():
                score += 0.2

            # 5. Description / AI description match
            desc = f.get("ai_description", "") + f.get("description", "")
            if query_lower in desc.lower():
                score += 0.1

            # 6. Extension match
            if query_lower in f.get("ext", "").lower():
                score += 0.15

            # Apply filters
            if filters and not self._matches_filters(f, filters):
                continue

            if score > 0:
                results.append((f, score))

        # Sort by score descending
        results.sort(key=lambda x: -x[1])
        return [r[0] for r in results[:limit]]

    def _matches_filters(self, file_item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if file matches filter criteria."""
        for field, value in filters.items():
            field_val = file_item.get(field)
            if field_val is None:
                return False
            if isinstance(value, list):
                if field_val not in value:
                    return False
            elif str(field_val).lower() != str(value).lower():
                return False
        return True

    def suggest(self, prefix: str, limit: int = 10) -> List[str]:
        """Get autocomplete suggestions."""
        prefix_lower = prefix.lower().strip()
        if not prefix_lower:
            return []

        suggestions: Set[str] = set()
        for tag, file_ids in self._tag_index.items():
            if tag.startswith(prefix_lower) or prefix_lower in tag:
                suggestions.add(tag)

        for f in self._file_index:
            if prefix_lower in f.get("name", "").lower():
                suggestions.add(f["name"])
            if prefix_lower in f.get("category", "").lower():
                suggestions.add(f["category"])

        return sorted(suggestions)[:limit]


# ============================================================================
# LineageEngine: Data lineage DAG
# ============================================================================

class LineageEngine:
    """Track data lineage — how files derive from each other."""

    def __init__(self):
        self._nodes: Dict[str, LineageNode] = {}

    def add_node(self, file_id: str, name: str, category: str,
                 parents: Optional[List[str]] = None,
                 operations: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        """Add a node to the lineage graph."""
        node = LineageNode(
            file_id=file_id,
            name=name,
            category=category,
            parents=parents or [],
            operations=operations or [],
            metadata=metadata or {},
        )
        self._nodes[file_id] = node

        # Update parent's children
        for parent_id in node.parents:
            if parent_id in self._nodes:
                if file_id not in self._nodes[parent_id].children:
                    self._nodes[parent_id].children.append(file_id)

    def get_lineage(self, file_id: str, depth: int = 5) -> Optional[Dict[str, Any]]:
        """Get the lineage graph for a file (ancestors + descendants)."""
        node = self._nodes.get(file_id)
        if not node:
            return None

        return {
            "node": node.to_dict(),
            "ancestors": self._get_ancestors(file_id, depth),
            "descendants": self._get_descendants(file_id, depth),
            "full_graph": self._build_dag_subset(file_id, depth),
        }

    def _get_ancestors(self, file_id: str, depth: int) -> List[Dict[str, Any]]:
        """Get ancestor nodes up to depth."""
        ancestors = []
        visited = set()

        def traverse(fid, d):
            if d <= 0 or fid in visited:
                return
            visited.add(fid)
            node = self._nodes.get(fid)
            if node:
                for parent_id in node.parents:
                    pnode = self._nodes.get(parent_id)
                    if pnode:
                        ancestors.append(pnode.to_dict())
                        traverse(parent_id, d - 1)

        traverse(file_id, depth)
        return ancestors

    def _get_descendants(self, file_id: str, depth: int) -> List[Dict[str, Any]]:
        """Get descendant nodes up to depth."""
        descendants = []
        visited = set()

        def traverse(fid, d):
            if d <= 0 or fid in visited:
                return
            visited.add(fid)
            node = self._nodes.get(fid)
            if node:
                for child_id in node.children:
                    cnode = self._nodes.get(child_id)
                    if cnode:
                        descendants.append(cnode.to_dict())
                        traverse(child_id, d - 1)

        traverse(file_id, depth)
        return descendants

    def _build_dag_subset(self, file_id: str, depth: int) -> Dict[str, Any]:
        """Build a sub-DAG around a file."""
        nodes = {}
        edges = []
        visited = set()

        def traverse(fid, d, direction="both"):
            if d < 0 or fid in visited:
                return
            visited.add(fid)
            node = self._nodes.get(fid)
            if not node:
                return
            nodes[fid] = {"name": node.name, "category": node.category}

            if direction in ("both", "up"):
                for parent_id in node.parents:
                    if parent_id not in visited:
                        edges.append({"from": parent_id, "to": fid})
                        traverse(parent_id, d - 1, "up")

            if direction in ("both", "down"):
                for child_id in node.children:
                    if child_id not in visited:
                        edges.append({"from": fid, "to": child_id})
                        traverse(child_id, d - 1, "down")

        traverse(file_id, depth)
        return {"nodes": nodes, "edges": edges}

    def add_lineage_link(self, parent_id: str, child_id: str, operation: str = ""):
        """Add a lineage link between two files."""
        if parent_id not in self._nodes:
            self._nodes[parent_id] = LineageNode(
                file_id=parent_id, name=parent_id, category="unknown"
            )
        if child_id not in self._nodes:
            self._nodes[child_id] = LineageNode(
                file_id=child_id, name=child_id, category="unknown"
            )

        if child_id not in self._nodes[parent_id].children:
            self._nodes[parent_id].children.append(child_id)
        if parent_id not in self._nodes[child_id].parents:
            self._nodes[child_id].parents.append(parent_id)
        if operation and operation not in self._nodes[child_id].operations:
            self._nodes[child_id].operations.append(operation)


# ============================================================================
# DAMManager: Unified DAM interface
# ============================================================================

class DAMManager:
    """Unified Digital Asset Management interface."""

    def __init__(self):
        self.preview_engine = FormatPreviewEngine()
        self.smart_folder_engine = SmartFolderEngine()
        self.ai_tag_engine = AITagEngine()
        self.search_engine = SemanticSearchEngine()
        self.lineage_engine = LineageEngine()
        self._files: Dict[str, DAMFile] = {}
        self._scan_directories: List[str] = ["data/uploads", "data/output", "data/test_images"]
        self._setup_lineage_defaults()

    def _setup_lineage_defaults(self):
        """Set up some demo lineage links."""
        # Example: raw_image → processed_image → thumbnail
        self.lineage_engine.add_lineage_link(
            "raw_001", "processed_001", "image_enhancement"
        )
        self.lineage_engine.add_lineage_link(
            "processed_001", "thumb_001", "thumbnail_generation"
        )
        self.lineage_engine.add_lineage_link(
            "raw_002", "dataset_001", "dataset_assembly"
        )

    def scan_directory(self, directory: str) -> List[DAMFile]:
        """Scan a directory and register files."""
        discovered = []
        # Path traversal protection
        if not is_safe_path(directory):
            logger.warning(f"Path traversal blocked for directory scan: {directory}")
            return discovered
        
        base = Path(directory)
        if not base.exists():
            return discovered

        for file_path in base.rglob("*"):
            if not file_path.is_file():
                continue
            ext = file_path.suffix.lower()
            fmt_info = FORMAT_REGISTRY.get(ext, {"category": "unknown", "mime": "application/octet-stream"})

            file_id = hashlib.md5(str(file_path).encode()).hexdigest()[:16]
            stat = file_path.stat()

            dam_file = DAMFile(
                id=file_id,
                path=str(file_path),
                name=file_path.name,
                ext=ext,
                category=fmt_info["category"],
                mime=fmt_info["mime"],
                size_bytes=stat.st_size,
                created_at=stat.st_ctime,
                modified_at=stat.st_mtime,
            )
            self._files[file_id] = dam_file
            discovered.append(dam_file)

        return discovered

    def scan_all(self) -> List[DAMFile]:
        """Scan all registered directories."""
        all_files = []
        for directory in self._scan_directories:
            discovered = self.scan_directory(directory)
            all_files.extend(discovered)
        return all_files

    def get_files(self, category: Optional[str] = None,
                  search: Optional[str] = None,
                  page: int = 1, size: int = 50) -> Dict[str, Any]:
        """Get paginated file list with optional filtering."""
        files = list(self._files.values())

        if category:
            files = [f for f in files if f.category == category]

        if search:
            files_dicts = [f.to_dict() for f in files]
            self.search_engine.index_files(files_dicts)
            matched = self.search_engine.search(search)
            matched_ids = {m["id"] for m in matched}
            files = [f for f in files if f.id in matched_ids]

        total = len(files)
        total_pages = max(1, (total + size - 1) // size)
        start = (page - 1) * size
        end = start + size

        return {
            "items": [f.to_dict() for f in files[start:end]],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
        }

    def get_file(self, file_id: str) -> Optional[DAMFile]:
        return self._files.get(file_id)

    async def generate_preview(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Generate preview for a file."""
        dam_file = self._files.get(file_id)
        if not dam_file:
            return None
        return self.preview_engine.generate_preview(dam_file.path)

    async def ai_tag_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Run AI tagging on a file."""
        dam_file = self._files.get(file_id)
        if not dam_file:
            return None

        file_dict = dam_file.to_dict()
        # Add preview data for better tagging
        preview = self.preview_engine.generate_preview(dam_file.path)
        if preview:
            file_dict["preview_data"] = preview.get("preview_data", {})

        result = await self.ai_tag_engine.tag_file(file_dict)
        dam_file.tags = result.get("tags", [])
        dam_file.labels = result.get("labels", {})
        return result

    async def ai_tag_all(self, concurrency: int = 5) -> List[Dict[str, Any]]:
        """Run AI tagging on all files."""
        files = [f.to_dict() for f in self._files.values()]
        return await self.ai_tag_engine.tag_files_batch(files, concurrency)

    def get_lineage(self, file_id: str) -> Optional[Dict[str, Any]]:
        return self.lineage_engine.get_lineage(file_id)

    def add_lineage(self, parent_id: str, child_id: str, operation: str = ""):
        self.lineage_engine.add_lineage_link(parent_id, child_id, operation)

    def get_smart_folders(self) -> List[Dict[str, Any]]:
        return [sf.to_dict() for sf in self.smart_folder_engine.list_all()]

    def create_smart_folder(self, name: str, rules: List[Dict[str, Any]],
                            description: str = "") -> Dict[str, Any]:
        sf = self.smart_folder_engine.create(name, rules, description)
        return sf.to_dict()

    def get_smart_folder_contents(self, folder_id: str) -> List[Dict[str, Any]]:
        files = [f.to_dict() for f in self._files.values()]
        return self.smart_folder_engine.match_files(folder_id, files)

    def get_format_stats(self) -> Dict[str, Any]:
        """Get format statistics."""
        categories = {}
        for f in self._files.values():
            cat = f.category
            if cat not in categories:
                categories[cat] = {"count": 0, "total_size": 0, "extensions": set()}
            categories[cat]["count"] += 1
            categories[cat]["total_size"] += f.size_bytes
            categories[cat]["extensions"].add(f.ext)

        return {
            "total_files": len(self._files),
            "total_size_bytes": sum(f.size_bytes for f in self._files.values()),
            "categories": {
                cat: {
                    "count": stats["count"],
                    "total_size": stats["total_size"],
                    "extensions": sorted(stats["extensions"]),
                }
                for cat, stats in categories.items()
            },
            "supported_formats": self.preview_engine.get_total_format_count(),
            "format_categories": self.preview_engine.get_all_categories(),
        }


# ============================================================================
# Singleton
# ============================================================================

_dam_manager: Optional[DAMManager] = None


def get_dam_manager() -> DAMManager:
    """Get or create the global DAMManager singleton."""
    global _dam_manager
    if _dam_manager is None:
        _dam_manager = DAMManager()
        # Initial scan
        _dam_manager.scan_all()
    return _dam_manager
