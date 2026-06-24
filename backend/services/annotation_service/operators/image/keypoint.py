"""annot.image.keypoint — keypoint / skeleton annotation operator.

Inputs:
    items: list of dicts {'path'|'url'|'data': image, 'keypoints'?: [kpt,...]}
    params:
        num_keypoints: int = 17          — expected K (COCO=17, body=18)
        min_visible: float = 0.0        — drop keypoints below visibility threshold
        coco_skeleton: bool = True      — validate against COCO 17-keypoint layout
        auto_harris: bool = False       — auto-extract via cv2.goodFeaturesToTrack
        max_auto: int = 50              — max auto-detected keypoints per image

Each keypoint: {'x': float, 'y': float, 'visibility': 0|1|2, 'name'?: str}.

Returns per-image: {image_index, ok, count, keypoints, skeleton_edges}.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, ensure_numpy_bgr, load_image_any

COCO_KPT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
COCO_SKELETON = [
    (16, 14), (14, 12), (17, 15), (15, 13), (12, 13),
    (6, 12), (7, 13), (6, 7), (6, 8), (7, 9),
    (8, 10), (9, 11), (2, 3), (1, 2), (1, 3),
    (2, 4), (3, 5), (4, 6), (5, 7),
]


def _validate(k: Dict[str, Any], idx: int) -> Dict[str, Any]:
    return {
        "id": k.get("id", idx),
        "x": float(k.get("x", 0.0)),
        "y": float(k.get("y", 0.0)),
        "visibility": int(k.get("visibility", 1)),
        "name": str(k.get("name") or (COCO_KPT_NAMES[idx] if idx < len(COCO_KPT_NAMES) else f"kpt_{idx}")),
    }


def _auto_harris(img: Any, max_n: int) -> List[Dict[str, Any]]:
    if not _HAS_CV2:
        return []
    arr = ensure_numpy_bgr(img)
    if arr is None:
        return []
    try:
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        corners = cv2.goodFeaturesToTrack(gray, maxCorners=max_n,
                                          qualityLevel=0.01, minDistance=10)
    except Exception:  # noqa: BLE001
        return []
    if corners is None:
        return []
    return [
        {"x": float(c[0][0]), "y": float(c[0][1]), "visibility": 2, "name": f"auto_{i}"}
        for i, c in enumerate(corners)
    ]


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    num_k = int(params.get("num_keypoints", 17))
    min_vis = float(params.get("min_visible", 0.0))
    coco = bool(params.get("coco_skeleton", True))
    auto = bool(params.get("auto_harris", False))
    max_auto = int(params.get("max_auto", 50))

    out: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        img_input = item.get("image") if isinstance(item, dict) and "image" in item else (
            {k: v for k, v in item.items() if k != "keypoints"}
            if isinstance(item, dict) else item
        )
        img, meta = load_image_any(img_input)
        rec: Dict[str, Any] = {"image_index": i, "image_meta": meta}
        if img is None:
            rec.update({"ok": False, "count": 0, "keypoints": []})
            out.append(rec)
            continue
        raw_kpts: List[Dict[str, Any]] = []
        if isinstance(item, dict) and isinstance(item.get("keypoints"), list):
            raw_kpts = [_validate(k, idx) for idx, k in enumerate(item["keypoints"])]
        if auto:
            raw_kpts.extend(_validate(k, idx=len(raw_kpts))
                            for idx, k in enumerate(_auto_harris(img, max_auto)))
        kept = [k for k in raw_kpts if float(k["visibility"]) >= min_vis]
        if coco and num_k == 17:
            for idx, k in enumerate(kept):
                if idx < len(COCO_KPT_NAMES) and k.get("name", "").startswith("kpt_"):
                    k["name"] = COCO_KPT_NAMES[idx]
        rec.update({
            "ok": True,
            "count": len(kept),
            "keypoints": kept,
            "skeleton_edges": COCO_SKELETON if coco and num_k == 17 else [],
            "expected_count": num_k,
        })
        out.append(rec)
    return out