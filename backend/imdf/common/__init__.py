"""IMDF common namespace.

This package re-exports a curated subset of cross-cutting helpers used
by IMDF service code.  The original implementation lives in
``backend.common`` / ``backend.gateway``; we expose them under the
``backend.imdf.common.*`` path so historical IMDF imports stay valid
and consistent with the architecture described in P4-1.
"""