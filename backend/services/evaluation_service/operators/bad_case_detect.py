"""eval.bad_case_detect — Bad Case auto-detection across metrics.

Combines multiple operator scores and flags samples where ANY metric
falls below its threshold (configurable).

items: list of {sample_id, scores: {metric: float, ...}, ...}
params:
    rules: dict[metric_name, threshold]  — per-metric thresholds
    min_violations: int = 1              — how many rules to violate to be bad
    mode: "score" | "filter" | "aggregate"

Returns: list of {sample_id, is_bad, violations, severity}
"""
from __future__ import annotations

from typing import Any, Dict, List


_DEFAULT_RULES: Dict[str, float] = {
    "accuracy": 0.5,
    "f1_score": 0.5,
    "bleu": 0.1,
    "rouge_l": 0.2,
    "clip_score": 0.25,
    "aesthetic": 5.0,
    "hps": 0.4,
    "fid": 100.0,
    "video_quality": 0.4,
    "audio_quality": 0.4,
}


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = dict(_DEFAULT_RULES)
    rules.update(params.get("rules") or {})
    min_violations = int(params.get("min_violations", 1))
    mode = params.get("mode", "score")
    out: List[Dict[str, Any]] = []
    n_bad = 0
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            out.append({"sample_id": i, "is_bad": False, "violations": [], "severity": 0.0})
            continue
        sid = it.get("sample_id", i)
        scores = it.get("scores", {}) or {}
        violations: List[Dict[str, Any]] = []
        worst_severity = 0.0
        for metric, threshold in rules.items():
            v = scores.get(metric)
            if v is None:
                continue
            # FID is "lower is better", invert check
            if metric == "fid":
                if v > threshold:
                    sev = min(1.0, (v - threshold) / max(1.0, threshold))
                    violations.append({"metric": metric, "value": v, "threshold": threshold, "severity": round(sev, 4)})
                    worst_severity = max(worst_severity, sev)
            else:
                if v < threshold:
                    sev = min(1.0, max(0.0, (threshold - v) / max(1e-9, threshold)))
                    violations.append({"metric": metric, "value": v, "threshold": threshold, "severity": round(sev, 4)})
                    worst_severity = max(worst_severity, sev)
        is_bad = len(violations) >= min_violations
        if is_bad:
            n_bad += 1
        out.append({
            "sample_id": sid,
            "is_bad": is_bad,
            "violations": violations,
            "severity": round(worst_severity, 4),
        })
    if mode == "filter":
        out = [o for o in out if o.get("is_bad")]
    elif mode == "aggregate":
        out = [{
            "total": len(items),
            "bad_count": n_bad,
            "bad_rate": round(n_bad / max(1, len(items)), 4),
        }]
    return out


__all__ = ["run"]
