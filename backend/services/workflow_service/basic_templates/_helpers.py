"""P3-3-W2 + P3-6-W2 shared template helpers.

Used by ``_base`` (53 legacy templates) and the new business modules
(export / pipeline / multimodal / feedback). Each helper returns a dict
matching the NodeModel schema in ``routes.py`` (id / name / node_type /
depends_on / retry_max) plus optional metadata fields (inputs, outputs,
steps, metrics) for richer documentation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _n(id_: str, name: str, node_type: str, *deps: str,
       retry_max: int = 0) -> Dict[str, Any]:
    """Build a single-node spec.

    ``node_type`` maps to a logical operator capability. The actual
    service-level dispatch is wired in a later iteration.
    """
    return {
        "id": id_,
        "name": name,
        "node_type": node_type,
        "depends_on": list(deps),
        "retry_max": retry_max,
    }


def _meta(inputs: Optional[Dict[str, Any]] = None,
          outputs: Optional[List[str]] = None,
          steps: Optional[List[Dict[str, Any]]] = None,
          metrics: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build metadata fields for a richer business template spec."""
    out: Dict[str, Any] = {}
    if inputs is not None:
        out["inputs"] = inputs
    if outputs is not None:
        out["outputs"] = outputs
    if steps is not None:
        out["steps"] = steps
    if metrics is not None:
        out["metrics"] = metrics
    return out


__all__ = ["_n", "_meta"]