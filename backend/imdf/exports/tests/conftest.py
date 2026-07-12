"""Test conftest for exports/ — set offline env flags."""
import os

# 防止真实模型加载 (本模块不依赖大模型, 但保持一致)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-p19d3-1234567890abc")