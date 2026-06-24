"""eval.rouge — ROUGE-1, ROUGE-2, ROUGE-L F-measures for summarization.

Reference: Lin 2004. Pure-Python, no nltk dep.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


def _tokenize(s: str) -> List[str]:
    return s.lower().split()


def _ngram_counter(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def _lcs_length(a: List[str], b: List[str]) -> int:
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    dp = [0] * (n + 1)
    for i in range(1, m + 1):
        prev = 0
        for j in range(1, n + 1):
            tmp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = tmp
    return dp[n]


def _fmeasure(num: int, den: int) -> float:
    if den == 0:
        return 0.0
    p = num / den
    r = num / den  # for single-ref symmetry
    return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def _rouge(cand: List[str], refs: List[List[str]]) -> Dict[str, float]:
    """Average ROUGE over multiple references."""
    out = {"rouge_1": 0.0, "rouge_2": 0.0, "rouge_l": 0.0}
    if not cand or not refs:
        return out
    cand1 = _ngram_counter(cand, 1)
    cand2 = _ngram_counter(cand, 2)
    cand_lcs_max = 0
    r1, r2, rl = 0.0, 0.0, 0.0
    for r in refs:
        ref1 = _ngram_counter(r, 1)
        ref2 = _ngram_counter(r, 2)
        # 1-gram F (max over refs would be ideal; we sum for average)
        num1 = sum((cand1 & ref1).values())
        den1 = max(1, max(sum(cand1.values()), sum(ref1.values())))
        if den1 > 0:
            p = num1 / sum(cand1.values())
            rc = num1 / sum(ref1.values())
            f1 = 2 * p * rc / (p + rc) if (p + rc) > 0 else 0.0
        else:
            f1 = 0.0
        # 2-gram F
        num2 = sum((cand2 & ref2).values())
        den2 = max(1, max(sum(cand2.values()), sum(ref2.values())))
        if den2 > 0:
            p = num2 / sum(cand2.values())
            rc = num2 / sum(ref2.values())
            f2 = 2 * p * rc / (p + rc) if (p + rc) > 0 else 0.0
        else:
            f2 = 0.0
        # LCS F
        lcs = _lcs_length(cand, r)
        pl = lcs / max(1, len(cand))
        rl_v = lcs / max(1, len(r))
        fl = 2 * pl * rl_v / (pl + rl_v) if (pl + rl_v) > 0 else 0.0
        r1, r2, rl = r1 + f1, r2 + f2, rl + fl
    n = len(refs)
    return {"rouge_1": round(r1 / n, 4), "rouge_2": round(r2 / n, 4), "rouge_l": round(rl / n, 4)}


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of {candidate, references} or candidates with global refs.

    params:
        refs: list[str]
        mode: "score" | "filter" | "aggregate"
        threshold: float = 0.2 (rouge_l threshold)
    """
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.2))
    global_refs = params.get("refs")
    out: List[Dict[str, Any]] = []
    rl_scores: List[float] = []
    for i, it in enumerate(items):
        if isinstance(it, dict):
            cand = _tokenize(it.get("candidate", ""))
            refs = it.get("references") or []
        else:
            cand = _tokenize(str(it))
            refs = []
        if not refs and global_refs:
            refs = global_refs
        if not refs:
            out.append({"sample_id": i, "rouge": None, "ok": False, "note": "no_reference"})
            rl_scores.append(0.0)
            continue
        ref_toks = [_tokenize(r) for r in refs]
        scores = _rouge(cand, ref_toks)
        rl_scores.append(scores["rouge_l"])
        out.append({"sample_id": i, **scores, "above_threshold": scores["rouge_l"] >= threshold})
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        out = [{
            "count": len(rl_scores),
            "rouge_l_mean": round(sum(rl_scores) / max(1, len(rl_scores)), 4),
        }]
    return out


__all__ = ["run"]
