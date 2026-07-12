"""P19-B2: Upsert 5 new providers to the persistent registry DB.

P19-A2 noted that ``ensure_samples()`` only runs when the count is 0.
Since the persistent DB has 13 rows from P19-A2 era, the 5 new
batch-3 providers won't be auto-populated. We need an explicit
``r.upsert(p)`` for each new SAMPLE_PROVIDER.

This is a one-shot maintenance script — should be run once when
upgrading from P19-A2 to P19-B2.

Idempotent: re-running has no effect because we use upsert (INSERT OR REPLACE).
"""
import os
import sys

# 1. Make imdf/ importable
sys.path.insert(0, "D:/Hermes/生产平台/nanobot-factory/backend/imdf")

from providers import registry as reg


def main():
    """Upsert the 5 P19-B2 batch 3 providers to the persistent DB."""
    r = reg.get_registry()
    # Reload to ensure latest SAMPLE_PROVIDERS
    target_new = {"mistral", "cohere", "minimax", "stepfun", "nova"}
    upserted = []
    for p in reg.SAMPLE_PROVIDERS:
        if p.id in target_new:
            r.upsert(p)
            upserted.append(p.id)
    # Verify
    ids = {p.id for p in r.list()}
    print(f"Upserted: {sorted(upserted)}")
    print(f"Total in DB now: {len(ids)}")
    missing = target_new - ids
    if missing:
        print(f"ERROR: still missing: {missing}")
        return 1
    print("All 5 P19-B2 batch 3 providers now in persistent DB.")
    print(f"Final list (sorted): {sorted(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
