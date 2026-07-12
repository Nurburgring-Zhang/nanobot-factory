"""gen_ca.py — 生成自签 CA 根证书.

用法:
    python -m contracts.scripts.gen_ca \\
        --cn "ZhiYing-NB-CA-2026" \\
        --org "ZhiYing NanoBot" \\
        --country CN \\
        --validity-days 3650 \\
        --key-type ecdsa \\
        --out-dir backend/data

输出:
    backend/data/contracts_ca.pem   (证书 PEM)
    backend/data/contracts_ca.key   (私钥 PEM, 0600)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 让脚本能 import 父目录的 backend/contracts
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main():
    parser = argparse.ArgumentParser(description="生成自签 CA 根证书 (F-6.7)")
    parser.add_argument("--cn", required=True, help="CA Common Name, e.g. 'ZhiYing-NB-CA-2026'")
    parser.add_argument("--org", default="ZhiYing NanoBot", help="Organization")
    parser.add_argument("--country", default="CN", help="Country (2 letters)")
    parser.add_argument("--validity-days", type=int, default=3650, help="validity days (default 10y)")
    parser.add_argument(
        "--key-type", default="ecdsa", choices=["ecdsa", "rsa"],
        help="CA key type (default ecdsa = ECDSA-P256)",
    )
    parser.add_argument(
        "--out-dir", default=str(_BACKEND / "data"),
        help="Output dir (default backend/data)",
    )
    args = parser.parse_args()

    from contracts.signing.pki import generate_ca

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ca = generate_ca(
        common_name=args.cn,
        org_name=args.org,
        country=args.country,
        validity_days=args.validity_days,
        key_type=args.key_type,
    )
    cert_path = out_dir / "contracts_ca.pem"
    key_path = out_dir / "contracts_ca.key"
    cert_path.write_bytes(ca.cert_pem)
    key_path.write_bytes(ca.key_pem)
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass

    print(f"CA generated:")
    print(f"  cert  -> {cert_path}")
    print(f"  key   -> {key_path}  (mode 0600)")
    print(f"  serial:           {ca.serial}")
    print(f"  fingerprint (SHA-256):  {ca.fingerprint}")
    print(f"  subject_cn:       {ca.subject_cn}")
    print(f"  public_key_alg:   {ca.public_key_alg}")
    print(f"  not_valid:        {ca.not_before} ~ {ca.not_after}")


if __name__ == "__main__":
    main()
