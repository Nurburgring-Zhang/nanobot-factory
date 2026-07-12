"""P10-B test conftest — shared fixtures + env setup.

Provides:
- tmp_dirs: redirect usage_tracker fallback log + audit_chain DB
- fast_embedder: pre-warm global embedder to skip lazy probe
"""
import os
import sys
from pathlib import Path

# Set offline mode + deterministic env before any test imports
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-p10b-1234567890abc")

# Make imdf/ the first thing on sys.path so that:
# 1. `import imdf.api.canvas_web` works (imdf/ is the top-level package).
# 2. Absolute imports like `from api.middleware.robustness import X` resolve
#    to imdf/api/middleware/robustness.py — NOT the empty backend/api/ that
#    would otherwise shadow it.
# BACKEND (parent of imdf/) is intentionally NOT added.
# Some pytest configurations add `backend/` to sys.path[0] which would shadow
# our real imdf/api/. Strip it out and put imdf/ first.
IMDF = Path(__file__).resolve().parent.parent
BACKEND = IMDF.parent
# Remove all backend/ entries (would shadow imdf/api, imdf/core, etc.)
sys.path = [p for p in sys.path if Path(p).resolve() != BACKEND.resolve()]
sp = str(IMDF.resolve())
if sp not in sys.path:
    sys.path.insert(0, sp)


def pytest_configure(config):
    """Mark real-model probe as done before any test imports trigger it."""
    try:
        from multimodal import embedding as _emb
        _emb._REAL_PROBED = True
        _emb._REAL_TEXT_ENC = None
        _emb._REAL_IMAGE_ENC = None
    except Exception:
        pass
