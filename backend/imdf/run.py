"""
IMDF Cross-Platform Launcher
=============================
Usage: python run.py [--port PORT] [--host HOST]

Automatically:
  1. Checks Python version (>= 3.10)
  2. Installs missing dependencies from requirements.txt
  3. Checks port availability
  4. Starts the FastAPI/uvicorn web UI
  5. Opens the browser automatically
"""
import os
import sys
import subprocess
import argparse
import socket
import webbrowser
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"

MIN_PYTHON = (3, 10)


def check_python_version():
    """Ensure Python >= 3.10."""
    v = sys.version_info
    if (v.major, v.minor) < MIN_PYTHON:
        print(
            f"Error: Python {v.major}.{v.minor} detected, "
            f"but >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} is required.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"[OK] Python {v.major}.{v.minor}.{v.micro}")


def install_dependencies():
    """Install missing packages from requirements.txt via pip."""
    if not REQUIREMENTS.exists():
        print("[WARN] requirements.txt not found — skipping dependency check.")
        return
    print("[CHECK] Verifying dependencies...")
    try:
        # Check if all requirements are installed
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print("[OK] All dependencies satisfied.")
        else:
            print(f"[WARN] pip install output: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        print("[WARN] pip install timed out; proceeding anyway.")
    except Exception as e:
        print(f"[WARN] Could not verify dependencies: {e}")


def check_port(port: int) -> bool:
    """Check if a TCP port is available on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def find_free_port(start: int = 8000, max_attempts: int = 50) -> int:
    """Find a free port starting from `start`."""
    for port in range(start, start + max_attempts):
        if check_port(port):
            return port
    return 0  # no free port found


def main():
    parser = argparse.ArgumentParser(description="IMDF Cross-Platform Launcher")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    parser.add_argument("--no-install", action="store_true", help="Skip dependency installation")
    args = parser.parse_args()

    # 1. Python version check
    print("=" * 56)
    print("  IMDF — Infinite Multimodal Data Foundry")
    print("=" * 56)
    check_python_version()

    # 2. Install dependencies
    if not args.no_install:
        install_dependencies()

    # 3. Port check
    port = args.port
    if not check_port(port):
        alt = find_free_port(port + 1)
        if alt:
            print(f"[WARN] Port {port} is in use. Using port {alt} instead.")
            port = alt
        else:
            print(f"[ERROR] No free port found starting from {port}.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[OK] Port {port} is available.")

    # 4. Build module path
    sys.path.insert(0, str(PROJECT_ROOT))

    host = args.host
    url = f"http://localhost:{port}"
    print(f"\n[START] Launching IMDF at {url}")
    print(f"[INFO]  Press Ctrl+C to stop\n")

    # 5. Open browser (slightly delayed so server starts first)
    if not args.no_browser:
        import threading
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()

    # 6. Start uvicorn
    import uvicorn
    uvicorn.run(
        "api.canvas_web:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
