"""采集类 (collection) workflow templates — 5 项."""
from __future__ import annotations
from .web_crawl_image import TEMPLATE as _TPL_WEB
from .youtube_video_batch import TEMPLATE as _TPL_YT
from .wikipedia_text import TEMPLATE as _TPL_WIKI
from .huggingface_dataset import TEMPLATE as _TPL_HF
from .kaggle_import import TEMPLATE as _TPL_KAGGLE

__all__ = [
    "_TPL_WEB", "_TPL_YT", "_TPL_WIKI", "_TPL_HF", "_TPL_KAGGLE",
]