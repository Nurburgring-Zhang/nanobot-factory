"""
P6-Fix-C-5: Tickets Celery task package
======================================

Tasks under this package are scheduled by the IMDF Celery beat (see
``imdf.config.settings.CELERY_BEAT_SCHEDULE``).

Modules:
- ``sla_monitor``  — Periodic SLA breach scan + oncall alerting
                     (P0 1h alert / P1 4h escalation).
"""
from __future__ import annotations

__all__: list[str] = []
