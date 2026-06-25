"""clean.text.sensitive — filter against a sensitive word list.

Loads words from a JSON list (default: hard-coded safe samples). Production
deployment should wire a configurable wordlist via provider.

Wordlist source (P6-2 P1-5):
  * ``params["wordlist"]`` if supplied by caller (highest priority)
  * ``WordlistProvider(kind="sensitive")`` from ``wordlist_providers`` registry
  * ``DEFAULT_WORDS`` placeholder list (only when no provider is wired)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Backwards-compat constant — only used when no provider is configured.
DEFAULT_WORDS = ["forbidden_word_1", "forbidden_word_2", "blocked_term"]


def _resolve_words(params: Dict[str, Any]) -> List[str]:
    """Pick the wordlist from (in order): caller, registry provider, fallback."""
    if "wordlist" in params and params["wordlist"]:
        return list(params["wordlist"])
    try:
        from ...wordlist_providers import get_registry
        provider = get_registry().get("sensitive")
        words = provider.get_words()
        if words:
            return words
    except Exception:  # noqa: BLE001
        pass
    return list(DEFAULT_WORDS)


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Drop items containing any sensitive word (mode='drop') or mask them.

    params:
        mode: str = "drop" (drop | mask)
        wordlist: list[str] = None (resolved via provider)
        case_sensitive: bool = False
    """
    mode = str(params.get("mode", "drop"))
    words = _resolve_words(params)
    cs = bool(params.get("case_sensitive", False))
    if not words:
        return [{"item": x, "is_sensitive": False, "passed": True} for x in items]
    flags = 0 if cs else re.IGNORECASE
    pattern = re.compile("|".join(re.escape(w) for w in words), flags=flags)

    out = []
    for x in items:
        s = x if isinstance(x, str) else repr(x)
        if pattern.search(s):
            if mode == "mask":
                masked = pattern.sub("[MASKED]", s)
                out.append({"item": x, "is_sensitive": True, "passed": True,
                            "masked": masked})
            else:
                out.append({"item": x, "is_sensitive": True, "passed": False})
        else:
            out.append({"item": x, "is_sensitive": False, "passed": True})
    return [r for r in out if r.get("passed", True)] if mode == "drop" else out