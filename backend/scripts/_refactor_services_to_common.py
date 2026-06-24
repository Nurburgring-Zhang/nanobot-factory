"""Refactor 12 services to use backend.common. Run once.

The 12 services had nearly-identical bootstrap code (sys.path, CORS,
monitoring quick_setup, FastAPI(...) boilerplate). This script replaces
that with:

    from common import create_app, mount_health, register_exception_handlers

    app = create_app("X_service", description=..., version=..., lifespan=...)
    mount_health(app)
    register_exception_handlers(app)

Idempotent: re-running on an already-refactored service is a no-op (we
look for the marker comment ``# P4-1-W1: migrated to backend.common``).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

SERVICES_ROOT = Path(r"D:\Hermes\生产平台\nanobot-factory\backend\services")
MARKER = "# P4-1-W1: migrated to backend.common"

# Per-service metadata; matches the original title/description/version.
SERVICE_META = {
    "agent_service":         ("Agent dispatch framework + 15 Agent type catalogue (P3-3-W1)", "0.1.0"),
    "annotation_service":    ("Annotation / task bounded context (P3-2-W1)", "0.1.0"),
    "asset_service":         ("Asset / DAM / OSS bounded context (P3-2-W1)", "0.1.0"),
    "cleaning_service":      ("Data cleaning bounded context — 32 operators (image/video/text/audio)", "0.4.0"),
    "collection_service":    ("Asset collection bounded context — 15 operators (P3-5-W2)", "0.1.0"),
    "dataset_service":       ("Dataset version + export bounded context (P3-2-W2)", "0.1.0"),
    "evaluation_service":    ("Model evaluation + Bad Case bounded context (P3-2-W2)", "0.1.0"),
    "notification_service":  ("WebSocket / email / webhook fan-out (P3-3-W2)", "0.1.0"),
    "scoring_service":       ("Data scoring bounded context — 15 operators (P3-2-W2)", "0.1.0"),
    "search_service":        ("Text / semantic / vector search (P3-3-W2)", "0.1.0"),
    "user_service":          ("User / auth / role bounded context (P3-2-W1)", "0.1.0"),
    "workflow_service":      ("Workflow definition / DAG execution / monitoring (P3-3-W2)", "0.1.0"),
}


def refactor(service: str, main_py: Path) -> bool:
    text = main_py.read_text(encoding="utf-8")

    if MARKER in text:
        print(f"  - {service}: already migrated, skipping")
        return False

    description, version = SERVICE_META[service]

    # 1) Replace the sys.path + CORSMiddleware + FastAPI() + quick_setup block.
    #    Strategy: locate the ``app = FastAPI(...)`` line and everything between
    #    the previous # ── block up to the include_router calls. We'll rebuild.

    # Pattern A: drop the first 16-line sys.path block
    syspath_block = re.compile(
        r"import os\nimport sys\nfrom contextlib import asynccontextmanager\n"
        r"from pathlib import Path\n\n"
        r"# Make ``imdf\.\*`` importable.*?\n"
        r"_BACKEND_ROOT = Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent\n"
        r"if str\(_BACKEND_ROOT\) not in sys\.path:\n"
        r"    sys\.path\.insert\(0, str\(_BACKEND_ROOT\)\)\n\n"
    )
    text2 = syspath_block.sub("", text, count=1)

    # Pattern B: drop the CORSMiddleware import (now provided by common)
    text2 = text2.replace(
        "from fastapi.middleware.cors import CORSMiddleware\n", ""
    )

    # Pattern C: drop the monitoring quick_setup try/except
    mon_block = re.compile(
        r"\n# P3-8-W2: monitoring endpoints.*?\n"
        r"try:\n"
        r"    from imdf\.monitoring import quick_setup\n"
        r"    quick_setup\(app, \".*?\"\)\n"
        r"except Exception as _mon_e:\n"
        r"    import logging\n"
        r"    logging\.getLogger\(__name__\)\.warning\(\"monitoring setup failed: %s\", _mon_e\)\n",
        re.DOTALL,
    )
    text2 = mon_block.sub("\n", text2)

    # Pattern D: drop the CORS middleware block
    cors_block = re.compile(
        r"_cors_origins = os\.environ\.get\(\"CORS_ALLOW_ORIGINS\", \"\*\"\)\.split\(\",\"\)\n"
        r"app\.add_middleware\(\n"
        r"    CORSMiddleware,\n"
        r"    allow_origins=_cors_origins,\n"
        r"    allow_credentials=True,\n"
        r"    allow_methods=\[\"\*\"\],\n"
        r"    allow_headers=\[\"\*\"\],\n"
        r"\)\n",
        re.DOTALL,
    )
    text2 = cors_block.sub("", text2)

    # Pattern E: replace ``app = FastAPI(...)`` with create_app + mount_health + register_exception_handlers
    fastapi_block = re.compile(
        r"app = FastAPI\(\n"
        r"    title=\"Nanobot Factory [—-] ?\w*-service\",\n"
        r"    description=\"(.*?)\",\n"
        r"    version=\"([^\"]+)\",\n"
        r"    lifespan=lifespan,\n"
        r"\)",
        re.DOTALL,
    )
    m = fastapi_block.search(text2)
    if not m:
        # Try alternative title (workflow/notification use " - " instead of " — ")
        fastapi_block_alt = re.compile(
            r"app = FastAPI\(\s*\n"
            r"    title=\"Nanobot Factory [—-] \w+-service\",\s*\n"
            r"    description=\"(.*?)\",\s*\n"
            r"    version=\"([^\"]+)\",\s*\n"
            r"    lifespan=lifespan,\s*\n"
            r"\)",
        )
        m = fastapi_block_alt.search(text2)
        if not m:
            print(f"  ! {service}: couldn't locate FastAPI(...) block; please refactor manually")
            return False

    # Build the replacement
    replacement = (
        f"app = create_app(\n"
        f"    \"{service}\",\n"
        f"    description={description!r},\n"
        f"    version={version!r},\n"
        f"    lifespan=lifespan,\n"
        f")\n"
        f"mount_health(app)\n"
        f"register_exception_handlers(app)\n"
    )
    text2 = text2[: m.start()] + replacement + text2[m.end():]

    # 2) Add the P4-1-W1 import header (right after ``from __future__ import annotations``)
    import_block = (
        f"\n# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)\n"
        f"from common import create_app, mount_health, register_exception_handlers\n"
    )
    text2 = re.sub(
        r"(from __future__ import annotations\n)",
        r"\1" + import_block,
        text2,
        count=1,
    )

    # 3) Add the marker to the docstring
    text2 = re.sub(
        r'("""[Pp]\d-\d-[Ww]\d:[^"]*""")',
        r"\1\n\nP4-1-W1: refactored — see backend/common/ for the shared library.\n",
        text2,
        count=1,
    )

    # 4) Write
    main_py.write_text(text2, encoding="utf-8")
    print(f"  + {service}: refactored ({len(text)} -> {len(text2)} bytes)")
    return True


def main() -> int:
    n_changed = 0
    n_skipped = 0
    for service in sorted(os.listdir(SERVICES_ROOT)):
        d = SERVICES_ROOT / service
        if not d.is_dir():
            continue
        main_py = d / "main.py"
        if not main_py.exists():
            continue
        try:
            changed = refactor(service, main_py)
            if changed:
                n_changed += 1
            else:
                n_skipped += 1
        except Exception as exc:
            print(f"  ! {service}: ERROR {exc!r}")
    print(f"\nTotal: {n_changed} changed, {n_skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())