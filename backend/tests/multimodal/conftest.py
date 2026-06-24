"""Conftest for tests/multimodal/ — wire up sys.path so imdf.* resolves."""
import os
import sys

# Add backend/ to sys.path
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Avoid network downloads during test collection
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
