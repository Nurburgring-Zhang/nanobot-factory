"""clean.text.sensitive — filter against a sensitive word list.

Loads words from a JSON list (default: hard-coded safe samples). Production
deployment should wire a configurable wordlist via params.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# English placeholders — wordlist is operator-supplied at runtime via params.
DEFAULT_WORDS = ["forbidden_word_1", "forbidden_word_2", "blocked_term"]


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Drop items containing any sensitive word (mode='drop') or mask them.

    params:
        mode: str = "drop" (drop | mask)
        wordlist: list[str] = DEFAULT_WORDS
        case_sensitive: bool = False
    """
    mode = str(params.get("mode", "drop"))
    words = list(params.get("wordlist", DEFAULT_WORDS))
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