"""eval.bert_score — BERTScore (lightweight proxy, no transformer dep).

Real BERTScore uses contextual embeddings. This is a deterministic proxy
based on:
  - token-level IDF-weighted cosine similarity (idf = log(N/df))
  - greedy matching between candidate and reference tokens

Returns precision / recall / F1 in [0, 1].  No model download.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List


def _tokenize(s: str) -> List[str]:
    return s.lower().split()


def _idf_weights(corpus: List[List[str]]) -> Dict[str, float]:
    N = max(1, len(corpus))
    df = Counter()
    for toks in corpus:
        for t in set(toks):
            df[t] += 1
    return {t: math.log((N + 1) / (1 + c)) + 1 for t, c in df.items()}


def _char_ngrams(s: str, n: int = 3) -> List[str]:
    s = f"  {s.lower()}  "
    return [s[i:i + n] for i in range(len(s) - n + 1)]


def _vec(toks: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    """Token-level bag of char-trigrams weighted by IDF."""
    v: Dict[str, float] = {}
    for t in toks:
        w = idf.get(t, 1.0)
        for ng in _char_ngrams(t):
            v[ng] = v.get(ng, 0.0) + w
    return v


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    num = sum(a[k] * b.get(k, 0.0) for k in a)
    da = math.sqrt(sum(x * x for x in a.values()))
    db = math.sqrt(sum(x * x for x in b.values()))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def _bertscore_pair(cand: List[str], ref: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    """Token-level greedy IDF-weighted F1."""
    if not cand or not ref:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    cv = [_vec([t], idf) for t in cand]
    rv = [_vec([t], idf) for t in ref]
    used = [False] * len(ref)
    p_num = 0.0
    for ci in cv:
        best, best_j = -1.0, -1
        for j, rj in enumerate(rv):
            if used[j]:
                continue
            sim = _cosine(ci, rj)
            if sim > best:
                best, best_j = sim, j
        if best_j >= 0:
            used[best_j] = True
            p_num += best
    p = p_num / max(1, len(cand))
    used = [False] * len(cand)
    r_num = 0.0
    for rj in rv:
        best, best_j = -1.0, -1
        for ci_idx, ci in enumerate(cv):
            if used[ci_idx]:
                continue
            sim = _cosine(ci, rj)
            if sim > best:
                best, best_j = sim, ci_idx
        if best_j >= 0:
            used[best_j] = True
            r_num += best
    r = r_num / max(1, len(ref))
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """items: list of {candidate, references} or candidates (global refs).

    params:
        refs: list[str]
        mode: "score" | "filter" | "aggregate"
        threshold: float = 0.5
    """
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.5))
    global_refs = params.get("refs")
    out: List[Dict[str, Any]] = []
    f1_scores: List[float] = []
    # Build corpus for IDF
    corpus: List[List[str]] = []
    for it in items:
        if isinstance(it, dict):
            c = _tokenize(it.get("candidate", ""))
            rs = it.get("references") or []
        else:
            c = _tokenize(str(it))
            rs = global_refs or []
        corpus.append(c)
        for r in rs:
            corpus.append(_tokenize(r))
    if global_refs and not any(isinstance(it, dict) for it in items):
        for r in global_refs:
            corpus.append(_tokenize(r))
    idf = _idf_weights(corpus) if corpus else {}
    for i, it in enumerate(items):
        if isinstance(it, dict):
            cand = _tokenize(it.get("candidate", ""))
            refs = it.get("references") or []
        else:
            cand = _tokenize(str(it))
            refs = global_refs or []
        if not refs:
            out.append({"sample_id": i, "bert_score": None, "ok": False, "note": "no_reference"})
            f1_scores.append(0.0)
            continue
        best_f1 = 0.0
        best_metrics = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        for r in refs:
            m = _bertscore_pair(cand, _tokenize(r), idf)
            if m["f1"] > best_f1:
                best_f1 = m["f1"]
                best_metrics = m
        f1_scores.append(best_f1)
        out.append({
            "sample_id": i,
            "bert_score": best_metrics,
            "above_threshold": best_f1 >= threshold,
        })
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        out = [{
            "count": len(f1_scores),
            "f1_mean": round(sum(f1_scores) / max(1, len(f1_scores)), 4),
        }]
    return out


__all__ = ["run"]
