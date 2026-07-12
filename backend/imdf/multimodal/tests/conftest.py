"""P10-B test conftest — set env + skip real-model lazy probe in MultiModalEmbedder.

Without this, the first call to ``MultiModalEmbedder.encode_one`` triggers a
~10s lazy probe of ``sentence_transformers`` / BGE-M3 / CLIP that hangs in
CI containers without network.  We force the probe to be a no-op.
"""
import os

# Set offline mode + force deterministic fallback before any multimodal import
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-p10b-1234567890abc")


def pytest_configure(config):
    """Mark the real-model probe as already done — no lazy download."""
    try:
        from multimodal import embedding as _emb
        _emb._REAL_PROBED = True
        _emb._REAL_TEXT_ENC = None
        _emb._REAL_IMAGE_ENC = None
    except Exception:
        pass
