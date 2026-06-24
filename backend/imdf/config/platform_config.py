"""
IMDF Cross-Platform Configuration
===================================
Auto-detect OS, compute project root dynamically, provide
relative-path helpers for all data directories.

Supports optional .env or config.json overrides at project root.
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional


# ── Detect OS ────────────────────────────────────────────────────────────
def detect_os() -> str:
    """Return 'windows', 'linux', or 'macos'."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("darwin"):
        return "macos"
    return "linux"


CURRENT_OS = detect_os()


# ── Project root (dynamic) ───────────────────────────────────────────────
def find_project_root() -> Path:
    """
    Walk upward from this file's location until we find the project marker
    (pyproject.toml, .git, or run.py).  Falls back to grandparent of config/.
    """
    anchor = Path(__file__).resolve().parent  # config/
    for parent in [anchor, *anchor.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / ".git").exists():
            return parent
        if (parent / "run.py").exists():
            return parent
    # Fallback: config/ is one level below project root
    return anchor.parent.resolve()


PROJECT_ROOT: Path = find_project_root()


# ── Load optional overrides ──────────────────────────────────────────────
def _load_env_pair(path: Path) -> dict:
    """Minimal .env parser (no dependency on python-dotenv)."""
    result = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip().strip("'\"")
    return result


def _load_overrides() -> dict:
    """Merge .env and config.json overrides (config.json wins on conflict)."""
    overrides = {}

    # 1. .env file
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        overrides.update(_load_env_pair(env_path))

    # 2. config.json
    cfg_path = PROJECT_ROOT / "config.json"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            overrides.update(cfg)
        except (json.JSONDecodeError, OSError):
            pass

    return overrides


_OVERRIDES = _load_overrides()


def get_config_key(key: str, default: str = "") -> str:
    """Get a config value from overrides, env vars, or the default."""
    # Check config.json / .env
    if key in _OVERRIDES:
        return str(_OVERRIDES[key])
    # Check environment variable with IMDF_ prefix
    env_val = os.environ.get(f"IMDF_{key.upper()}")
    if env_val is not None:
        return env_val
    return default


# ── Directory helpers ────────────────────────────────────────────────────

def get_data_root() -> Path:
    """Root data directory under project root."""
    val = get_config_key("data_root", "")
    if val:
        return Path(val).resolve()
    return PROJECT_ROOT / "data"


def get_input_dir() -> str:
    return str(get_data_root() / "input")


def get_output_dir() -> str:
    return str(get_data_root() / "output")


def get_thumbnails_dir() -> str:
    return str(get_data_root() / "thumbnails")


def get_data_dir() -> str:
    """Canvas data files (board list, individual boards)."""
    return str(get_data_root() / "canvases")


def get_settings_dir() -> str:
    return str(get_data_root() / "settings")


def get_settings_file() -> str:
    return str(get_data_root() / "settings.json")


def get_canvas_list_file() -> str:
    return str(get_data_root() / "canvas_list.json")


def get_resource_library_db() -> str:
    return str(get_data_root() / "resource_library.json")


def get_temp_dir() -> str:
    """Temporary directory for uploads / processing."""
    val = get_config_key("temp_dir", "")
    if val:
        return val
    return str(get_data_root() / "temp")


def get_default_local_save_dir() -> str:
    return str(get_data_root() / "saved_files")


def get_default_canvas_auto_save_dir() -> str:
    return str(get_data_root() / "auto_save")


def get_default_resource_library_dir() -> str:
    return str(get_data_root() / "resource_library")


def get_default_theme_template_dir() -> str:
    return str(get_data_root() / "theme_templates")


def get_default_eagle_api_base() -> str:
    return get_config_key("eagle_api_base", "http://localhost:41595/api/")


def get_port() -> int:
    return int(get_config_key("port", "8000"))


def get_max_upload_bytes() -> int:
    return int(get_config_key("max_upload_bytes", str(20 * 1024 * 1024)))


def get_max_base64_bytes() -> int:
    return int(get_config_key("max_base64_bytes", str(20 * 1024 * 1024)))


def get_thumbnail_concurrency() -> int:
    return max(1, min(4, int(get_config_key("thumbnail_concurrency", "2"))))


def get_figma_bridge_base() -> str:
    return get_config_key("figma_bridge_base", "http://localhost:3845")


# ── Ensure directories exist ─────────────────────────────────────────────

def ensure_dirs():
    """Create all required data directories if they do not exist."""
    dirs = [
        get_input_dir(),
        get_output_dir(),
        get_thumbnails_dir(),
        get_data_dir(),
        get_settings_dir(),
        get_default_local_save_dir(),
        get_default_canvas_auto_save_dir(),
        get_default_resource_library_dir(),
        get_default_theme_template_dir(),
        get_temp_dir(),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


# Auto-create on import
ensure_dirs()
