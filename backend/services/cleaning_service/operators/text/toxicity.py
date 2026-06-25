"""clean.text.toxicity — heuristic toxicity scoring.

Heuristics (NOT ML):
  * Profanity density (loaded list, English placeholders)
  * ALL CAPS run-on
  * Excessive punctuation (!?? in succession)

Wordlist source (P6-2 P1-5):
  * ``params["wordlist"]`` if supplied by caller (highest priority)
  * ``WordlistProvider(kind="toxic")`` from ``wordlist_providers`` registry
  * ``DEFAULT_TOXIC`` placeholder list (only when no provider is wired)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Backwards-compat constant — only used when no provider is configured.
DEFAULT_TOXIC = ["toxic_word_1", "toxic_word_2"]
_CAPS_RX = re.compile(r"[A-Z]{4,}")
_EXCLAIM_RX = re.compile(r"[!?]{3,}")


def _resolve_words(params: Dict[str, Any]) -> List[str]:
    """Pick the wordlist from (in order): caller, registry provider, fallback."""
    if "wordlist" in params and params["wordlist"]:
        return list(params["wordlist"])
    try:
        from ...wordlist_providers import get_registry
        provider = get_registry().get("toxic")
        words = provider.get_words()
        if words:
            return words
    except Exception:  # noqa: BLE001
        pass
    return list(DEFAULT_TOXIC)


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item toxicity score in [0,1] + verdict.

    params:
        threshold: float = 0.5
        mode: str = "score"
        wordlist: list[str] = None (resolved via provider)
    """
    threshold = float(params.get("threshold", 0.5))
    mode = str(params.get("mode", "score"))
    words = _resolve_words(params)
    out = []
    for x in items:
        s = x if isinstance(x, str) else repr(x)
        sl = s.lower()
        n_words = max(1, len(sl.split()))
        toxic_hits = sum(sl.count(w) for w in words)
        caps = len(_CAPS_RX.findall(s))
        exclaim = len(_EXCLAIM_RX.findall(s))
        score = min(1.0, toxic_hits / n_words * 3.0 + caps * 0.1 + exclaim * 0.2)
        rec = {"item": x, "toxicity_score": round(score, 4),
               "is_toxic": score >= threshold,
               "signals": {"toxic_words": toxic_hits, "caps_runs": caps,
                           "exclaim_runs": exclaim}}
        if mode == "filter":
            rec["passed"] = score < threshold
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out