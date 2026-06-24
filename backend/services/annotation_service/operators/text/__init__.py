"""annot.text — re-exports for 4 text annotation operators."""
from . import (
    ner,
    sentiment,
    text_classification,
    qa_pair,
)

__all__ = [
    "ner",
    "sentiment",
    "text_classification",
    "qa_pair",
]