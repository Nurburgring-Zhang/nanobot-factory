"""Layer 10 — Quality tracking.

Wraps the existing ``annotation_quality`` module and adds:

* drift detection — moving-average degradation alarm;
* inter-annotator agreement (Cohen's κ) for binary labels;
* a small in-memory ring buffer so the monitoring endpoint works without
  a database.

If the upstream ``annotation_quality`` module is missing, the tracker falls back
to recording raw (label, score) pairs and the drift detection still works.
"""

from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def cohens_kappa(rater_a: List[int], rater_b: List[int]) -> float:
    """Cohen's κ for two raters over binary labels {0, 1}.

    Returns NaN if the inputs are empty or have mismatched lengths.
    """
    if len(rater_a) != len(rater_b) or not rater_a:
        return float("nan")
    n = len(rater_a)
    po = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n
    p_a = sum(rater_a) / n
    p_b = sum(rater_b) / n
    pe = p_a * p_b + (1 - p_a) * (1 - p_b)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def pop_std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class QualityRecord:
    record_id: str
    timestamp: float
    annotator_id: str
    item_id: str
    label: int
    score: float
    modality: str = "image"
    task_type: str = "classification"
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp))
        return d


class QualityTracker:
    def __init__(self, *, buffer_size: int = 5_000,
                 drift_window: int = 50,
                 drift_threshold: float = 0.10) -> None:
        self.buffer: Deque[QualityRecord] = deque(maxlen=buffer_size)
        self.drift_window = drift_window
        self.drift_threshold = drift_threshold

    # -- record ------------------------------------------------------------- #
    def record(
        self,
        *,
        annotator_id: str,
        item_id: str,
        label: int,
        score: float,
        modality: str = "image",
        task_type: str = "classification",
        meta: Optional[Dict[str, Any]] = None,
    ) -> QualityRecord:
        rec = QualityRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            annotator_id=annotator_id,
            item_id=item_id,
            label=int(label),
            score=float(score),
            modality=modality,
            task_type=task_type,
            meta=dict(meta or {}),
        )
        self.buffer.append(rec)
        return rec

    # -- query -------------------------------------------------------------- #
    def recent(self, limit: int = 100, *, annotator_id: Optional[str] = None,
               task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rec in reversed(self.buffer):
            if annotator_id and rec.annotator_id != annotator_id:
                continue
            if task_type and rec.task_type != task_type:
                continue
            out.append(rec.to_dict())
            if len(out) >= limit:
                break
        return out

    def per_annotator(self) -> List[Dict[str, Any]]:
        agg: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "count": 0, "score_sum": 0.0,
        })
        for rec in self.buffer:
            a = agg[rec.annotator_id]
            a["count"] += 1
            a["score_sum"] += rec.score
        rows = []
        for uid, d in agg.items():
            cnt = d["count"]
            rows.append({
                "annotator_id": uid,
                "count": int(cnt),
                "avg_score": round(d["score_sum"] / cnt, 4) if cnt else 0.0,
            })
        rows.sort(key=lambda r: r["avg_score"])
        return rows

    def drift_report(self) -> Dict[str, Any]:
        """Compare the most recent ``drift_window`` records vs the rest.

        If the average score drop exceeds ``drift_threshold`` *and* there are
        at least ``drift_window`` recent records, the result is flagged.
        """
        recent_n = min(self.drift_window, len(self.buffer))
        if recent_n < 5 or len(self.buffer) < recent_n * 2:
            return {
                "drift_detected": False,
                "reason": "insufficient-data",
                "recent_avg": None,
                "baseline_avg": None,
                "delta": None,
            }
        rec_list = list(self.buffer)
        recent = [r.score for r in rec_list[-recent_n:]]
        baseline = [r.score for r in rec_list[:-recent_n]]
        recent_avg = mean(recent)
        baseline_avg = mean(baseline)
        delta = baseline_avg - recent_avg  # positive = score dropped
        drift = delta > self.drift_threshold
        return {
            "drift_detected": drift,
            "window_size": recent_n,
            "recent_avg": round(recent_avg, 4),
            "baseline_avg": round(baseline_avg, 4),
            "delta": round(delta, 4),
            "threshold": self.drift_threshold,
            "recent_std": round(pop_std(recent), 4),
            "baseline_std": round(pop_std(baseline), 4),
        }

    def agreement(self) -> Dict[str, Any]:
        """Pairwise Cohen's κ across annotators (per item)."""
        by_item: Dict[str, Dict[str, int]] = defaultdict(dict)
        for rec in self.buffer:
            by_item[rec.item_id][rec.annotator_id] = rec.label
        items = list(by_item.values())
        if len(items) < 2:
            return {"kappa": None, "items": len(items), "annotators": self._unique_annotators()}
        # pick the two most frequent annotators for pairwise κ
        ann_counts: Dict[str, int] = defaultdict(int)
        for d in items:
            for a in d:
                ann_counts[a] += 1
        top = sorted(ann_counts.items(), key=lambda x: -x[1])[:2]
        if len(top) < 2:
            return {"kappa": None, "items": len(items), "annotators": self._unique_annotators()}
        a, b = top[0][0], top[1][0]
        ra, rb = [], []
        for d in items:
            if a in d and b in d:
                ra.append(d[a])
                rb.append(d[b])
        kappa = cohens_kappa(ra, rb) if ra else float("nan")
        return {
            "kappa": None if math.isnan(kappa) else round(kappa, 4),
            "items_compared": len(ra),
            "annotator_a": a,
            "annotator_b": b,
            "total_items": len(items),
            "unique_annotators": self._unique_annotators(),
        }

    def _unique_annotators(self) -> int:
        return len({r.annotator_id for r in self.buffer})

    def stats(self) -> Dict[str, Any]:
        return {
            "buffer_size": len(self.buffer),
            "buffer_capacity": self.buffer.maxlen,
            "unique_annotators": self._unique_annotators(),
            "drift_report": self.drift_report(),
            "agreement": self.agreement(),
        }


_TRACKER: Optional[QualityTracker] = None


def get_tracker() -> QualityTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = QualityTracker()
    return _TRACKER
