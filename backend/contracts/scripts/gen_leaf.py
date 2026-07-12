"""gen_leaf.py — 基于现有 CA 颁发叶子证书 (signer cert).

用法:
    python -m contracts.scripts.gen_leaf \\
        --subject "智影签署服务" \\
        --email "ops@zhiying.ai" \\
        --validity-days 1095 \\
        --out-dir backend/data

输出:
    backend/data/contracts_leaves/<safe_name>.json
        {
          "cert_pem": "...",
          "key_pem":  "...",
          "serial":   ...,
          "subject_cn": "...",
          "issuer_cn":  "ZhiYing-NB-CA-2026",
          "not_before": "...",
          "not_after":  "...",
          "public_key_alg": "ecdsa-p256",
          "fingerprint": "..."
        }

前置:
    - 已有 CA:  backend/data/contracts_ca.pem + contracts_ca.key
                或 env CONTRACT_CA_CERT_PATH / CONTRACT_CA_KEY_PATH 指向其他位置.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:64]
    if not s:
        s = "default"
    return s


def main():
    parser = argparse.ArgumentParser(description="基于现有 CA 颁发叶子证书 (F-6.7)")
    parser.add_argument("--subject", required=True, help="证书 Subject CN")
    parser.add_argument("--email", default=None, help="可选 email, 写入 SAN")
    parser.add_argument(
        "--validity-days", type=int, default=1095,
        help="validity days (default 3y)",
    )
    parser.add_argument(
        "--out-dir", default=str(_BACKEND / "data"),
        help="Output dir (default backend/data)",
    )
    args = parser.parse_args()

    from contracts.signing.factory import ensure_dev_ca, issue_leaf_for_subject

    # 复用 singleton — 没 CA 就生成一个
    ca = ensure_dev_ca()

    leaf = issue_leaf_for_subject(
        subject_cn=args.subject,
        subject_email=args.email,
        validity_days=args.validity_days,
    )

    out_dir = Path(args.out_dir) / "contracts_leaves"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_safe_name(args.subject)}.json"
    out_path.write_text(
        json.dumps({
            "cert_pem": leaf.cert_pem.decode("ascii"),
            "key_pem": leaf.key_pem.decode("ascii"),
            "serial": leaf.serial,
            "subject_cn": leaf.subject_cn,
            "issuer_cn": leaf.issuer_cn,
            "not_before": leaf.not_before,
            "not_after": leaf.not_after,
            "public_key_alg": leaf.public_key_alg,
            "fingerprint": leaf.fingerprint,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(out_path, 0o600)
    except Exception:
        pass

    print(f"Leaf cert generated:")
    print(f"  output:  {out_path}")
    print(f"  subject: {leaf.subject_cn}")
    print(f"  issuer:  {leaf.issuer_cn}")
    print(f"  serial:  {leaf.serial}")
    print(f"  fingerprint (SHA-256): {leaf.fingerprint}")
    print(f"  public_key_alg:        {leaf.public_key_alg}")
    print(f"  not_valid:  {leaf.not_before} ~ {leaf.not_after}")


if __name__ == "__main__":
    main()
