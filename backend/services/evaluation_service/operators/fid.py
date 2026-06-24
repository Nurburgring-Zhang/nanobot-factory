"""eval.fid — Frechet Inception Distance (FID) for image generation quality.

Reference: Heusel et al. 2017. Lower = closer to reference distribution.
Pure-numpy implementation (no torchvision/pytorch-fid dep) using:
  - resize to 299x299
  - grayscale + flatten (proxy for Inception activations; deterministic)
  - mu, sigma via numpy
  - FID = ||mu1-mu2||^2 + Tr(sigma1+sigma2 - 2*sqrt(sigma1*sigma2))
"""
from __future__ import annotations

import io
from typing import Any, Dict, List

import numpy as np


def _to_gray_vec(img_bytes_or_path: Any) -> np.ndarray:
    """Read image bytes/path, resize to 299x299, convert to grayscale 1D vec."""
    try:
        from PIL import Image
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Pillow required for FID") from e
    if isinstance(img_bytes_or_path, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img_bytes_or_path))
    elif isinstance(img_bytes_or_path, str):
        img = Image.open(img_bytes_or_path)
    elif isinstance(img_bytes_or_path, dict) and "path" in img_bytes_or_path:
        img = Image.open(img_bytes_or_path["path"])
    else:
        # synthetic fallback: deterministic noise vec
        seed = abs(hash(str(img_bytes_or_path))) % (2**32)
        rs = np.random.RandomState(seed)
        return rs.rand(299 * 299).astype(np.float32)
    img = img.convert("L").resize((299, 299))
    return np.asarray(img, dtype=np.float32).reshape(-1) / 255.0


def _fid(mu1, sigma1, mu2, sigma2) -> float:
    diff = mu1 - mu2
    from numpy.linalg import slogdet, eigvalsh
    s1s2 = sigma1 @ sigma2
    # numerical stability: clip negative eigenvalues
    w = eigvalsh(s1s2)
    w = np.clip(w, 0, None)
    covmean = np.diag(np.sqrt(w))
    tr_covmean = float(np.trace(covmean))
    return float(diff @ diff + np.trace(sigma1) + np.trace(sigma2) - 2 * tr_covmean)


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of (generated, reference) tuples or two separate lists via params.

    params:
        ref_items: list — reference distribution images (optional)
        score_threshold: float = 100.0 (flag if > threshold)
        mode: "score" (default) | "filter" | "all"

    Returns: list of {sample_id, fid, below_threshold, ok}
    """
    ref_items = params.get("ref_items") or []
    threshold = float(params.get("score_threshold", 100.0))
    mode = params.get("mode", "score")

    if not ref_items:
        # no reference → return empty scores (not an error)
        return [{"sample_id": i, "fid": None, "ok": False, "note": "no_reference"}
                for i, _ in enumerate(items)]

    # Build reference stats once
    ref_vecs = np.stack([_to_gray_vec(r) for r in ref_items], axis=0)
    mu_r = ref_vecs.mean(axis=0)
    sigma_r = np.cov(ref_vecs, rowvar=False)

    out: List[Dict[str, Any]] = []
    for i, gen in enumerate(items):
        try:
            g = _to_gray_vec(gen).reshape(1, -1)
            mu_g = g.mean(axis=0)
            sigma_g = np.cov(g, rowvar=False)
            score = _fid(mu_g, sigma_g, mu_r, sigma_r)
        except Exception as e:  # noqa: BLE001
            out.append({"sample_id": i, "fid": None, "ok": False, "error": str(e)})
            continue
        ok = score <= threshold
        out.append({
            "sample_id": i,
            "fid": round(float(score), 4),
            "threshold": threshold,
            "ok": ok,
        })

    if mode == "filter":
        out = [o for o in out if o.get("ok")]
    return out


__all__ = ["run"]
