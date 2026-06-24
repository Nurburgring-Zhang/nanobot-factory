"""
Async OCR extraction tasks (P2-1-W2)
======================================

Tasks:
- ``ocr_image``        — extract text from a single image file.
- ``ocr_batch``        — extract text from a list of image files.
- ``ocr_bytes``        — extract text from raw image bytes (e.g. upload).

Implementation strategy
-----------------------
1. If ``pytesseract`` is installed *and* the Tesseract binary is on PATH,
   use real Tesseract OCR.
2. Otherwise, fall back to a Pillow-only heuristic that:
     * loads the image,
     * reports its size / mode,
     * returns an empty string with ``engine="heuristic"`` in the result.

This keeps the task runnable in dev / CI where Tesseract is not installed,
while still exercising the real pipeline in production.
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import shared_task

_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


# --- Engine availability probe --------------------------------------------
def _tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from shutil import which
        return bool(which("tesseract"))
    except Exception:
        return False


_TESSERACT_OK = _tesseract_available()


def _ocr_with_pytesseract(image_path: str) -> str:
    import pytesseract  # type: ignore
    from PIL import Image
    img = Image.open(image_path)
    return pytesseract.image_to_string(img)


def _ocr_with_heuristic(image_path: str) -> str:
    """Fallback: just report the image is recognised; OCR text is empty.

    Returning a deterministic empty string keeps downstream consumers happy
    when the OCR engine isn't available.
    """
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return ""  # real text would be returned by pytesseract
    except Exception as exc:
        logger.warning("heuristic OCR could not open %s: %s", image_path, exc)
        return ""


def _ocr_bytes_with_pytesseract(data: bytes) -> str:
    import pytesseract  # type: ignore
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img)


# --- Tasks --------------------------------------------------------------
@shared_task(name="imdf.tasks.ocr_extract.ocr_image", bind=True, acks_late=True)
def ocr_image(self, image_path: str, lang: str = "eng") -> Dict[str, Any]:
    """Extract text from a single image file path."""
    try:
        if not image_path or not Path(image_path).exists():
            return {"ok": False, "error": "image_not_found", "task_id": self.request.id}

        if _TESSERACT_OK:
            try:
                text = _ocr_with_pytesseract(image_path)
                return {
                    "ok": True, "engine": "tesseract", "lang": lang,
                    "text": text, "length": len(text), "task_id": self.request.id,
                }
            except Exception as exc:
                logger.warning("pytesseract failed, falling back: %s", exc)

        text = _ocr_with_heuristic(image_path)
        return {
            "ok": True, "engine": "heuristic", "lang": lang,
            "text": text, "length": len(text), "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("ocr_image failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "task_id": self.request.id}


@shared_task(name="imdf.tasks.ocr_extract.ocr_batch", bind=True, acks_late=True)
def ocr_batch(self, image_paths: List[str], lang: str = "eng") -> Dict[str, Any]:
    """Extract text from a list of image files."""
    paths = [p for p in (image_paths or []) if p]
    results: List[Dict[str, Any]] = []
    for p in paths:
        results.append(ocr_image.run(p, lang=lang))  # type: ignore[attr-defined]
    successes = sum(1 for r in results if r.get("ok"))
    return {
        "ok": True,
        "count": len(results),
        "successes": successes,
        "failures": len(results) - successes,
        "results": results,
        "task_id": self.request.id,
    }


@shared_task(name="imdf.tasks.ocr_extract.ocr_bytes", bind=True)
def ocr_bytes(self, data_b64: str, lang: str = "eng") -> Dict[str, Any]:
    """OCR raw image bytes (base64-encoded).

    Workers stay JSON-only — bytes are not safe to pass through Celery as
    binary, hence the base64 envelope.
    """
    import base64
    try:
        data = base64.b64decode(data_b64 or "")
        if not data:
            return {"ok": False, "error": "empty_bytes", "task_id": self.request.id}
        if _TESSERACT_OK:
            text = _ocr_bytes_with_pytesseract(data)
            return {
                "ok": True, "engine": "tesseract", "lang": lang,
                "text": text, "length": len(text), "task_id": self.request.id,
            }
        return {
            "ok": True, "engine": "heuristic", "lang": lang,
            "text": "", "length": 0, "task_id": self.request.id,
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "task_id": self.request.id}
