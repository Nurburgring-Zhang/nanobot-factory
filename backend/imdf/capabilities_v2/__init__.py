"""VDP-2026 v1.1 — Platform Capability Module Registry v2.

The capability module system distinguishes from the legacy OpenClaw/MCP system
in backend/capabilities/. The v2 system wraps the platform's OWN business
capabilities (project / requirement / dataset / pack / annotation / review / qc /
acceptance / delivery / scoring / tagging / classification / cleaning / search /
evaluation / export) as 36+ first-class invocable modules with:

  - explicit input / output schemas (JSON Schema draft 2020-12)
  - module-level metadata (category / tags / owner / version / rate_limit / cost)
  - thin wrappers over the existing engine layer (so behaviour stays one source of
    truth and the v1.0 release does not regress)
  - invocation log persisted to SQLite for audit + data-flow tracing

The wrapped engines are imported lazily so an engine missing in a slim checkout
does not break the registry.

Capability ids use `<domain>.<verb>` convention to make them stable across API
clients (TypeScript) and Python bindings.
"""
from .engine import (
    Capability,
    CapabilityRegistry,
    CapabilityResult,
    CapabilityCategory,
    register_default_capabilities,
)
from .definitions import (
    build_default_registry,
    DOMAIN_CATEGORIES,
)
from .dataflow import (
    DataFlowTracker,
    DataFlowNode,
    DataFlowSnapshot,
)
from .routes import router

__all__ = [
    "Capability",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilityCategory",
    "DataFlowTracker",
    "DataFlowNode",
    "DataFlowSnapshot",
    "build_default_registry",
    "DOMAIN_CATEGORIES",
    "register_default_capabilities",
    "router",
]
