"""eval.bleu — Bilingual Evaluation Understudy (BLEU) for text generation.

Standard n-gram precision BLEU-4 with brevity penalty.
Reference: Papineni et al. 2002.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List


def _tokenize(s: str) -> List[str]:
    return s.lower().split()


def _ngrams(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def _clip_count(cand_n: Counter, ref_ns: List[Counter]) -> Counter:
    """Clipped count: min(cand_n, max_ref_count)."""
    if not ref_ns:
        return Counter()
    max_ref = Counter()
    for rn in ref_ns:
        for ng, c in rn.items():
            if c > max_ref[ng]:
                max_ref[ng] = c
    out = Counter()
    for ng, c in cand_n.items():
        out[ng] = min(c, max_ref.get(ng, 0))
    return out


def _sentence_bleu(cand: List[str], refs: List[List[str]], max_n: int = 4) -> float:
    if not cand:
        return 0.0
    cand_lens = [len(r) for r in refs]
    closest = min(cand_lens, key=lambda r: abs(r - len(cand)))
    bp = 1.0 if len(cand) >= closest else math.exp(1 - closest / max(1, len(cand)))
    log_bleu = 0.0
    for n in range(1, max_n + 1):
        cand_n = _ngrams(cand, n)
        ref_ns = [_ngrams(r, n) for r in refs]
        clipped = _clip_count(cand_n, ref_ns)
        num = sum(clipped.values())
        den = max(1, sum(cand_n.values()))
        if num == 0:
            return 0.0
        log_bleu += (1.0 / max_n) * math.log(num / den)
    return bp * math.exp(log_bleu)


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of {candidate, references} OR candidate texts (params has refs).

    params:
        refs: list[str] — global references if items are just candidates
        max_n: int = 4
        mode: "score" | "filter" | "aggregate"
        threshold: float = 0.1
    """
    max_n = int(params.get("max_n", 4))
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.1))
    global_refs = params.get("refs")
    out: List[Dict[str, Any]] = []
    scores: List[float] = []
    for i, it in enumerate(items):
        if isinstance(it, dict):
            cand = _tokenize(it.get("candidate", ""))
            refs_list = it.get("references") or []
        else:
            cand = _tokenize(str(it))
            refs_list = []
        if not refs_list and global_refs:
            refs_list = global_refs if isinstance(global_refs[0], str) else global_refs
        if not refs_list:
            out.append({"sample_id": i, "bleu": None, "ok": False, "note": "no_reference"})
            scores.append(0.0)
            continue
        ref_toks = [_tokenize(r) for r in refs_list]
        s = _sentence_bleu(cand, ref_toks, max_n)
        scores.append(s)
        out.append({
            "sample_id": i,
            "bleu": round(s, 4),
            "above_threshold": s >= threshold,
        })
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        out = [{
            "count": len(scores),
            "mean": round(sum(scores) / max(1, len(scores)), 4),
            "max": round(max(scores, default=0.0), 4),
            "min": round(min(scores, default=0.0), 4),
        }]
    return out


__all__ = ["run"]
