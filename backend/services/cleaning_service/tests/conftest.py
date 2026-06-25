"""Shared conftest for cleaning_service tests.

Adds the ``backend`` directory to sys.path so absolute-style imports
(``from services.cleaning_service.wordlist_providers import ...``) work
when pytest is invoked from the backend root.
"""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))