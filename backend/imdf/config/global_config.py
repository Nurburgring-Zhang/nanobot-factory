"""
IMDF Global Configuration
=========================
Re-exports from platform_config for backward compatibility.
All path logic is centralized in platform_config.py.
"""
from config.platform_config import (
    PROJECT_ROOT,
    CURRENT_OS,
    get_data_root,
    get_input_dir,
    get_output_dir,
    get_thumbnails_dir,
    get_data_dir,
    get_settings_dir,
    get_settings_file,
    get_canvas_list_file,
    get_temp_dir,
    get_default_local_save_dir,
    get_default_canvas_auto_save_dir,
    get_default_resource_library_dir,
    get_default_theme_template_dir,
    get_default_eagle_api_base,
    get_port,
    get_max_upload_bytes,
    get_max_base64_bytes,
    get_thumbnail_concurrency,
    get_figma_bridge_base,
)

# Eagerly-evaluated constants for backward compatibility
RESOURCE_LIBRARY_DB = "resource_library.json"
DATA_ROOT = get_data_root()
INPUT_DIR = get_input_dir()
OUTPUT_DIR = get_output_dir()
THUMBNAILS_DIR = get_thumbnails_dir()
DATA_DIR = get_data_dir()
SETTINGS_DIR = get_settings_dir()
SETTINGS_FILE = get_settings_file()
CANVAS_FILE = get_canvas_list_file()
TEMP_DIR = get_temp_dir()
PORT = get_port()
MAX_UPLOAD_BYTES = get_max_upload_bytes()
MAX_BASE64_BYTES = get_max_base64_bytes()
THUMBNAIL_CONCURRENCY = get_thumbnail_concurrency()
DEFAULT_FIGMA_BRIDGE_BASE = get_figma_bridge_base()

# ── Limits ───────────────────────────────────────────────────────────
MAX_DUCK_BATCH = 30
MAX_GRID_ROWS = 12
MAX_GRID_COLS = 12
MAX_GRID_DIMENSION = 4096

# ── Thumbnails ───────────────────────────────────────────────────────
THUMBNAIL_SIZE = 320
THUMBNAIL_QUALITY = 78

# ── Default paths ────────────────────────────────────────────────────
DEFAULT_LOCAL_SAVE_DIR = get_default_local_save_dir()
DEFAULT_CANVAS_AUTO_SAVE_DIR = get_default_canvas_auto_save_dir()
DEFAULT_RESOURCE_LIBRARY_DIR = get_default_resource_library_dir()
DEFAULT_THEME_TEMPLATE_DIR = get_default_theme_template_dir()
DEFAULT_EAGLE_API_BASE = get_default_eagle_api_base()

# ── MIME mapping ─────────────────────────────────────────────────────
MIME_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".avif": "image/avif",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".m4a": "audio/mp4", ".flac": "audio/flac", ".aac": "audio/aac",
    ".json": "application/json",
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
    ".obj": "model/obj", ".fbx": "model/fbx",
}
