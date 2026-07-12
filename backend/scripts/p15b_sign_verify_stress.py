"""P15-B: 1000-iteration sign→verify stress test for timestamp-drift fix.

Before the P15-B fix, ``sign_contract_real`` called ``datetime.utcnow()``
independently in three places (pre-snap.signed_at, SignResult.signed_at,
contract.signed_at) which produced 20-40% false-tamper failures on
``verify_contract_signature`` because the canonical bytes stored at signing
time and the canonical bytes reconstructed at verify time used different
timestamps.

After the fix a single ``t = datetime.utcnow().isoformat() + 'Z'`` is shared
across all three sites. This script runs the sign→verify loop 1000 times and
asserts zero failures.

Run::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    python backend\\scripts\\p15b_sign_verify_stress.py

Exits 0 on success, 1 on any failure.
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Path setup
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Isolated tmpdir for the CA / leaf cache / audit log so we don't pollute
# the production data directory.
_TMP = Path(tempfile.mkdtemp(prefix="p15b_stress_"))
os.environ["CONTRACT_CA_DIR"] = str(_TMP)
os.environ["CONTRACT_AUDIT_LOG_PATH"] = str(_TMP / "audit.jsonl")

import contracts  # noqa: E402
from contracts.signing import factory  # noqa: E402


def main() -> int:
    """Run 1000 sign→verify iterations. Returns 0 on success."""
    factory.reset_ca_for_tests()
    contracts._STORE.clear()

    failures = 0
    total = 1000
    first_fail_idx = -1
    first_fail_reasons: list = []

    for i in range(total):
        try:
            # Vary signer name to bypass leaf cache and exercise both cache
            # hit and cache miss paths.
            signer_name = f"stress-signer-{i % 50}"
            c = contracts.generate_contract(
                template="service_agreement",
                company_name=f"公司{i}",
                contact_email=f"u{i}@stress.test",
                plan_name="Pro",
                amount=100.0 + i,
            )
            sign_result = contracts.sign_contract_real(c.contract_id, signer=signer_name)
            v = contracts.verify_contract_signature(c.contract_id)
            ok = bool(v.get("ok"))
            if not ok:
                failures += 1
                if first_fail_idx == -1:
                    first_fail_idx = i
                    first_fail_reasons = list(v.get("reasons", []))
                    first_sign = sign_result.get("sign", {})
                    print(f"FAIL @ idx={i} signer={signer_name!r}")
                    print(f"  contract_id={c.contract_id}")
                    print(f"  sign.signed_at={first_sign.get('signed_at')!r}")
                    print(f"  sign.alg={first_sign.get('alg')!r}")
                    print(f"  verify.reasons={first_fail_reasons!r}")
                    print(f"  verify={v}")
        except Exception as exc:
            failures += 1
            if first_fail_idx == -1:
                first_fail_idx = i
                first_fail_reasons = [repr(exc)]
                print(f"EXC @ idx={i}: {exc!r}")

    print(f"\n=== P15-B sign→verify stress: {total - failures}/{total} OK ({failures} failures) ===")
    if failures > 0:
        print(f"First failure at idx={first_fail_idx}: {first_fail_reasons!r}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(rc)