"""clean.text.html — strip HTML tags and unescape entities."""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List

_TAG_RX = re.compile(r"<[^>]+>")
_WS_RX = re.compile(r"\s{2,}")
_INLINE_TAG_RX = re.compile(r"<(b|i|u|em|strong|span|a|font|small|big|sup|sub|mark)\b[^>]*>",
                            re.IGNORECASE)
_CLOSE_INLINE_RX = re.compile(r"</(b|i|u|em|strong|span|a|font|small|big|sup|sub|mark)>",
                              re.IGNORECASE)


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Strip HTML tags, unescape entities, collapse whitespace.

    Inline tags (b/i/span) are removed without injecting whitespace so that
    `<b>world</b>!` becomes `world!` instead of `world !`.

    params:
        collapse_whitespace: bool = True
    """
    collapse = bool(params.get("collapse_whitespace", True))
    out = []
    for x in items:
        if not isinstance(x, str):
            out.append(x); continue
        # 1) Inline tags: remove open + close without injecting space
        s = _INLINE_TAG_RX.sub("", x)
        s = _CLOSE_INLINE_RX.sub("", s)
        # 2) Block tags (p/div/br/h1...): replace with whitespace
        s = _TAG_RX.sub(" ", s)
        # 3) Unescape HTML entities (&amp; &lt; etc.)
        s = html.unescape(s)
        if collapse:
            s = _WS_RX.sub(" ", s).strip()
        out.append(s)
    return out