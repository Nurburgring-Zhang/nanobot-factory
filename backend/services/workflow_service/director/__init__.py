"""P4-6-W2: three-module Director studio (Story → Visual → Assembly).

Public surface
==============
* :class:`DirectorSession` / :class:`DirectorState` / :class:`Shot` /
  :class:`VisualAsset`   — shared models
* :class:`LLMClient`      — pluggable LLM adapter (default = deterministic stub)
* :class:`StoryDirector`  — ``story.py``
* :class:`VisualDirector` — ``visual.py``
* :class:`AssemblyDirector` — ``assembly.py``
* :class:`DirectorStudio` — 3-module orchestrator
* :func:`get_director_studio` — singleton accessor
"""
from .assembly import AssemblyDirector
from .story import StoryDirector
from .studio import (
    DirectorSession,
    DirectorState,
    DirectorStudio,
    LLMClient,
    Shot,
    VisualAsset,
    get_director_studio,
)
from .visual import VisualDirector

__all__ = [
    "AssemblyDirector",
    "DirectorSession",
    "DirectorState",
    "DirectorStudio",
    "LLMClient",
    "Shot",
    "StoryDirector",
    "VisualAsset",
    "VisualDirector",
    "get_director_studio",
]
