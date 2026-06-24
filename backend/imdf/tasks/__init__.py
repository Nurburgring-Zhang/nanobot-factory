"""
IMDF Celery task package
=========================

Each module here defines one or more Celery `@shared_task` functions that wrap
the underlying engine. Tasks live next to their engines (rather than inside the
engine modules) so the engine files remain free of Celery imports and keep
their backward-compatible sync APIs.

Modules
-------
- render_video      — VideoEngine.render_segments / single segment
- score_aesthetic   — AestheticScorer.score_batch / score_directory
- ocr_extract       — Image OCR (real Tesseract if pytesseract available, else heuristic)
- watermark_embed   — WatermarkEngine.add_text_watermark / add_image_watermark
- vector_index      — SemanticSearchEngine.index_asset / batch index
- model_gateway     — ModelGateway.chat (sync wrapper around async chat)
- stats_aggregate   — StatsDashboard.get_daily_report / compare_periods

Task naming convention: ``imdf.tasks.<module>.<function>`` — matches the
CELERY_TASK_ROUTES keys declared in config.settings.
"""

from __future__ import annotations

__all__: list[str] = []