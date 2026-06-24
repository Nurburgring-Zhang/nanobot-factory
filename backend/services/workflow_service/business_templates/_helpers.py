"""Helpers shared by business_templates/* modules.

Mirrors ``basic_templates._helpers`` (``_n`` / ``_meta``) so individual
business template files use the same node-building primitives.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _n(id_: str, name: str, node_type: str, *deps: str,
       retry_max: int = 0) -> Dict[str, Any]:
    """Build a single-node spec for a business template DAG."""
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