"""P19 v5.1-A: The Agency — 232 专家 (16 部门) loader.

This package provides a static, declarative roster of expert personas
("The Agency") used by the platform's intent-classification and
agent-routing layers (V5 Chapter 28).  Unlike the runtime plugin
contract in :mod:`imdf.agents`, an :class:`AgentRole` is a **data**
record — a frozen persona with a system prompt — not an executable
class.  Two separate concerns:

  * :mod:`imdf.agents`     — runtime plugin contract (BaseAgent ABC)
  * :mod:`imdf.agency`     — static persona roster (this module)

Why a separate package?
  The 232-expert roster is configuration-like data (JSON + dataclass),
  not behaviour.  Keeping it out of :mod:`imdf.agents` lets the
  plugin loader keep its narrow contract, and lets us evolve the
  roster (add/remove experts, edit system prompts) without touching
  the agent runtime.

Public API:
  * :class:`AgentRole`        — frozen persona dataclass
  * :class:`AgencyLoader`     — JSON-backed loader with search + capability
                                 matrix helpers
  * :class:`Bilingual`        — small (zh, en) helper used in persona fields
  * :data:`AGENCY_DIR`        — absolute path to the bundled JSON files
  * :data:`DEPARTMENT_ORDER`  — 16 canonical department names (canonical order)
  * :data:`DEPARTMENT_SEAT_QUOTAS` — per-department seat quota (sums to 232)
  * :data:`EXPECTED_TOTAL_ROLES`   — the assertion target (232)
"""
from __future__ import annotations

import os
from pathlib import Path

from .loader import (
    AGENCY_DIR,
    DEFAULT_DEPARTMENTS_FILE,
    DEPARTMENT_ORDER,
    DEPARTMENT_SEAT_QUOTAS,
    EXPECTED_TOTAL_ROLES,
    AgentRole,
    AgencyLoader,
    Bilingual,
)

__all__ = [
    "AGENCY_DIR",
    "DEFAULT_DEPARTMENTS_FILE",
    "DEPARTMENT_ORDER",
    "DEPARTMENT_SEAT_QUOTAS",
    "EXPECTED_TOTAL_ROLES",
    "AgentRole",
    "AgencyLoader",
    "Bilingual",
]
