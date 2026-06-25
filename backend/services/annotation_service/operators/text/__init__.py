"""annot.text — re-exports for 4 text annotation operators."""
from services._none_safety import safe_dict_run  # P6-Fix-P0-1: NoneType guard

from . import (
    ner,
    sentiment,
    text_classification,
    qa_pair,
)

# P6-Fix-P0-1: wrap each module's run() with None-safety guard.
for _mod in (ner, sentiment, text_classification, qa_pair):
    _mod.run = safe_dict_run(_mod.run)  # type: ignore[attr-defined]

__all__ = [
    "ner",
    "sentiment",
    "text_classification",
    "qa_pair",
]