"""clean.image.face_blur — detect faces with OpenCV Haar cascade and Gaussian-blur them.

In-place mutation of the loaded PIL image (returns a list of dicts with the
blurred image bytes; pass-through mode if no faces detected).

params:
        blur_strength: int = 25  (kernel size; odd; >=5)
        min_face_size: int = 30
"""
from __future__ import annotations

import io
from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, _HAS_NUMPY, _HAS_PIL, _load_image


_CASCADE = None


def _get_cascade():
    """Lazy-load Haar cascade (singleton)."""
    global _CASCADE
    if _CASCADE is not None:
        return _CASCADE
    if not _HAS_CV2:
        return None
    try:
        import cv2
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _CASCADE = cv2.CascadeClassifier(path)
        if _CASCADE.empty():
            _CASCADE = None
    except Exception:  # noqa: BLE001
        _CASCADE = None
    return _CASCADE


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect faces and blur them.

    Returns list of {item, faces_detected, blurred: bool, image_bytes?: bytes}.
    """
    blur_strength = max(5, int(params.get("blur_strength", 25)) | 1)  # ensure odd
    min_face = int(params.get("min_face_size", 30))

    cascade = _get_cascade()
    if cascade is None or not _HAS_CV2 or not _HAS_PIL or not _HAS_NUMPY:
        return [{"item": x, "faces_detected": 0, "blurred": False,
                 "note": "cv2/PIL/numpy unavailable; pass-through"} for x in items]

    import cv2
    import numpy as np
    from PIL import Image, ImageFilter

    out: List[Dict[str, Any]] = []
    for x in items:
        try:
            img, _ = _load_image(x)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": str(e)})
            continue
        if img is None:
            out.append({"item": x, "error": "load_failed"})
            continue
        try:
            arr = np.asarray(img.convert("RGB"))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4,
                                             minSize=(min_face, min_face))
            face_count = len(faces)
            if face_count > 0:
                pil = img.convert("RGB")
                for (x0, y0, w, h) in faces:
                    face = pil.crop((x0, y0, x0 + w, y0 + h))
                    face = face.filter(ImageFilter.GaussianBlur(radius=blur_strength // 2))
                    pil.paste(face, (x0, y0, x0 + w, y0 + h))
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=85)
                out.append({
                    "item": x,
                    "faces_detected": int(face_count),
                    "blurred": True,
                    "image_bytes": buf.getvalue(),
                    "format": "JPEG",
                })
            else:
                out.append({"item": x, "faces_detected": 0, "blurred": False})
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"face_detect_failed: {e}"})
    return out