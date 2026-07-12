"""V5 FR-8.3 - AQL Sampling (ISO 2859-1 normal inspection, 7 levels).

Implements the Acceptance Quality Limit sampling protocol from ISO 2859-1
with the 7 standard AQL levels: 0.1 / 0.65 / 1.0 / 1.5 / 2.5 / 4.0 / 6.5.

Core flow:
  1. AQLSampling(level, lot_size) - configure a sampling plan
  2. await sample(lot)            - draw random sample sized per ISO 2859-1 Table II-A
  3. await inspect(sample, defects) - accept if defects <= Ac, reject otherwise

The (lot_size_bucket, aql_level) -> (sample_size, Ac, Re) lookup table is
defined in `auto_strategy_schemas.SAMPLE_TABLE` (a curated subset of the
ISO standard covering lot sizes 26-50000).

For lots outside [26, 50000] we clamp to the nearest bucket and document
the clamping in the SampledLot.metadata field.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from imdf.labeling.auto_strategy_schemas import (
    AQLLevel,
    Asset,
    DefectRecord,
    InspectionDecision,
    InspectionResult,
    SAMPLE_TABLE,
    SampledLot,
)

_log = logging.getLogger(__name__)


# - Lot-size bucket boundaries -
# (lower, upper, table_key) - strictly increasing
_LOT_BUCKETS: List[Tuple[int, int, int]] = [
    (26, 50, 50),
    (51, 90, 90),
    (91, 150, 150),
    (151, 280, 280),
    (281, 500, 500),
    (501, 1200, 1200),
    (1201, 3200, 3200),
    (3201, 10000, 10000),
    (10001, 35000, 35000),
    (35001, 50000, 50000),
]


def _resolve_bucket(lot_size: int) -> Tuple[int, bool]:
    """Return (table_key, was_clamped) for the given lot size."""
    if lot_size <= 0:
        return 50, True
    if lot_size < 26:
        return 50, True
    if lot_size > 50000:
        return 50000, True
    for lo, hi, key in _LOT_BUCKETS:
        if lo <= lot_size <= hi:
            return key, False
    return 50000, True


def _lookup_plan(lot_size: int, aql: AQLLevel) -> Tuple[int, int, int]:
    """Return (sample_size, accept_count, reject_count)."""
    bucket, _ = _resolve_bucket(lot_size)
    if (bucket, aql) not in SAMPLE_TABLE:
        raise KeyError(f"AQL plan missing for (lot_bucket={bucket}, aql={aql})")
    return SAMPLE_TABLE[(bucket, aql)]


class AQLSampling:
    """ISO 2859-1 normal inspection AQL sampler + inspector.

    Usage:
        sampler = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000)
        sample = await sampler.sample(lot)
        result = await sampler.inspect(sample, 2)
    """

    def __init__(
        self,
        level: AQLLevel = AQLLevel.AQL_1_0,
        lot_size: int = 1000,
        seed: Optional[int] = None,
    ) -> None:
        if not isinstance(level, AQLLevel):
            level = AQLLevel(level)
        if lot_size <= 0:
            raise ValueError(f"lot_size must be > 0, got {lot_size}")

        self.level = level
        self.lot_size = lot_size
        self._rng = random.Random(seed)

        bucket, was_clamped = _resolve_bucket(lot_size)
        sample_size, ac, re_ = _lookup_plan(lot_size, level)

        self._bucket = bucket
        self._was_clamped = was_clamped
        self._sample_size = sample_size
        self._accept_count = ac
        self._reject_count = re_

    @property
    def sample_size(self) -> int:
        return self._sample_size

    @property
    def accept_count(self) -> int:
        return self._accept_count

    @property
    def reject_count(self) -> int:
        return self._reject_count

    @property
    def bucket(self) -> int:
        return self._bucket

    @property
    def was_clamped(self) -> bool:
        return self._was_clamped

    def plan_summary(self) -> Dict[str, Any]:
        return {
            "aql_level": self.level.value,
            "lot_size": self.lot_size,
            "sample_size": self._sample_size,
            "accept_count": self._accept_count,
            "reject_count": self._reject_count,
            "bucket": self._bucket,
            "clamped": self._was_clamped,
        }

    async def sample(self, lot: List[Asset]) -> SampledLot:
        """Draw a random sample of self._sample_size from `lot`.

        For lots smaller than the planned sample size, we use the entire lot
        and document the under-sampling in metadata.
        """
        if lot is None:
            raise ValueError("lot must be a list of Asset")

        n = len(lot)
        if n == 0:
            raise ValueError("lot is empty")

        sample_n = self._sample_size
        under_sampled = False
        if n < sample_n:
            under_sampled = True
            sample_n = n

        # Fisher-Yates partial shuffle
        idx = list(range(n))
        for i in range(sample_n):
            j = self._rng.randint(i, n - 1)
            idx[i], idx[j] = idx[j], idx[i]

        sampled = [lot[idx[i]] for i in range(sample_n)]

        sampled_lot = SampledLot(
            aql_level=self.level,
            lot_size=self.lot_size,
            sample_size=sample_n,
            accept_count=self._accept_count,
            reject_count=self._reject_count,
            sampled_assets=sampled,
            metadata={
                "actual_lot_size": n,
                "clamped": self._was_clamped,
                "under_sampled": under_sampled,
                "bucket": self._bucket,
            },
        )
        return sampled_lot

    async def inspect(
        self,
        sample: SampledLot,
        defect_count: int,
        defect_records: Optional[List[DefectRecord]] = None,
    ) -> InspectionResult:
        """Apply the AQL accept/reject rule to a sampled lot.

        Acceptance rule (ISO 2859-1):
            defects_found <= accept_count  -> ACCEPT
            defects_found > accept_count   -> REJECT
        """
        if sample is None:
            raise ValueError("sample must be a SampledLot")
        if defect_count < 0:
            raise ValueError(f"defect_count must be >= 0, got {defect_count}")

        ac = self._accept_count
        re_ = self._reject_count

        if defect_count <= ac:
            decision = InspectionDecision.ACCEPT
            rationale = f"defects {defect_count} <= Ac {ac} - lot accepted"
        else:
            decision = InspectionDecision.REJECT
            rationale = (
                f"defects {defect_count} > Ac {ac} (Re={re_}) - lot rejected"
            )

        return InspectionResult(
            lot_id=sample.lot_id,
            aql_level=self.level,
            sample_size=sample.sample_size,
            accept_count_threshold=ac,
            reject_count_threshold=re_,
            defects_found=defect_count,
            defect_records=defect_records or [],
            decision=decision,
            rationale=rationale,
        )


__all__ = [
    "AQLSampling",
    "_resolve_bucket",
    "_lookup_plan",
    "_LOT_BUCKETS",
]