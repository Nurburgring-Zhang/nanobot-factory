"""P21 P2 P2 — Path-traversal guard FastAPI dependency.

Background
----------
R2 audit finding **R2-NEW-04** (P0 / CWE-22) confirmed that
``backend.imdf.security.owasp_protection.Injection.validate_path`` is defined
(``backend/imdf/security/owasp_protection.py:264``) but **not wired into any
of the 122 routes**. ``data_video.py``, ``data_dataset.py``,
``production.py`` etc. all consume user-supplied paths via raw
``os.path.join()`` or ``f"data/{user_input}"`` — full path-traversal vector.

This module is the wiring layer that closes that gap.

Usage
-----
1. **As a helper inside a route handler** (preferred for retrofitting existing
   ``request: Request``-style routes without changing their signature)::

       from backend.common.path_dep import validated_path

       @router.post("/api/data/dataset/export")
       async def data_dataset_export(request: Request):
           body = await request.json()
           input_dir = validated_path(body.get("input_dir", ""))
           output_path = validated_path(body.get("output_path", "./data/dataset_export"),
                                        allowed_roots=None)  # relative OK
           ...

2. **As a FastAPI Depends target** (preferred for new routes with a
   ``path: str`` query/body parameter)::

       from fastapi import Depends
       from backend.common.path_dep import validated_path

       @router.get("/api/data/dataset/stats")
       async def data_dataset_stats(path: str = Depends(validated_path)):
           ...

   When the path fails validation, FastAPI converts the
   :class:`fastapi.HTTPException` raised here into a 400 response with
   ``detail="Path traversal detected: <reason>"``.

Notes
-----
* ``Injection.validate_path`` (the upstream implementation) is **not**
  modified — this module only consumes it.
* When ``allowed_roots`` is ``None`` the guard rejects:
    - empty paths
    - absolute paths (``/foo`` or ``C:\\foo``)
    - any component equal to ``..``
    - any component starting with ``~``
  This is the default for the existing ``data_*`` routes that operate on
  *project-relative* paths (e.g. ``"./data/dataset_export"``).
* When ``allowed_roots`` is provided, the (already-validated) path must also
  have a prefix matching one of those roots. This is the right tool for
  routes that take a fully-qualified absolute path inside a known sandbox.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Union

from fastapi import HTTPException

from backend.imdf.security.owasp_protection import Injection


# Default sandbox root — kept as a module-level constant so a future
# configuration source (env var / config.py) can override it without
# touching every call site. Currently the production data directory.
DEFAULT_ALLOWED_ROOTS: List[str] = ["/var/lib/nanobot-factory/data"]


def validated_path(
    path: str,
    allowed_roots: Optional[Union[str, Iterable[str]]] = None,
) -> str:
    """Validate a user-supplied filesystem path.

    Parameters
    ----------
    path
        The raw user-supplied path string (typically from a request body
        or query parameter).
    allowed_roots
        Optional allow-list of absolute root directories. ``None`` (the
        default) means "any project-relative path that does not traverse
        upwards". A single string is treated as a one-element list.

    Returns
    -------
    str
        The same ``path`` that was passed in, **unchanged** when it is
        valid. The return value is provided so callers can use the
        function as a one-liner replacement for ``body.get("path", "")``.

    Raises
    ------
    fastapi.HTTPException
        ``status_code=400`` with a ``detail`` string of the form
        ``"Path traversal detected: <reason>"`` when the upstream
        :func:`Injection.validate_path` returns ``(False, reason)``.
    """
    if allowed_roots is None:
        roots_list: Optional[List[str]] = None
    elif isinstance(allowed_roots, str):
        roots_list = [allowed_roots]
    else:
        roots_list = list(allowed_roots)

    ok, reason = Injection.validate_path(path, allowed_roots=roots_list)
    if not ok:
        # ``reason`` comes from Injection.validate_path and is already
        # operator-readable (e.g. "path traversal '..' blocked"); safe to
        # echo to the client because the *path* itself is the dangerous
        # part and we are rejecting the whole request.
        raise HTTPException(
            status_code=400,
            detail=f"Path traversal detected: {reason}",
        )
    return path


__all__ = ["validated_path", "DEFAULT_ALLOWED_ROOTS"]
