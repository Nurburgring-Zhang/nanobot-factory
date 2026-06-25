"""Validate K8s + Helm YAML manifests.

- k8s/*.yaml: raw YAML, validated via yaml.safe_load_all.
- helm/.../*.yaml templates: Go template syntax, NOT parseable as raw YAML.
  These are validated by helm template (if helm is on PATH); otherwise we
  document the limitation.
"""
from __future__ import annotations

import glob
import shutil
import subprocess
import sys
import yaml


def validate_k8s_raw() -> tuple[int, int, int]:
    """Returns (files, docs, failures) for k8s/ raw manifests."""
    files = sorted(glob.glob("k8s/**/*.yaml", recursive=True))
    fail = 0
    total_docs = 0
    print(f"[k8s/]   Validating {len(files)} raw YAML files...")
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                docs = list(yaml.safe_load_all(fp))
            n = sum(1 for d in docs if d is not None)
            total_docs += n
            print(f"  OK   ({n:>3d} docs)  {f}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL              {f}  ->  {e}")
            fail += 1
    print(f"[k8s/]   === {len(files)} files, {total_docs} docs, {fail} failures ===\n")
    return len(files), total_docs, fail


def validate_helm_template() -> tuple[int, int, int]:
    """Validate Helm chart by rendering templates.  Returns (files, docs, failures)."""
    if not shutil.which("helm"):
        print("[helm]   helm CLI not installed on this host.")
        print("[helm]   Helm templates use Go template syntax (e.g. {{ .Values.x }});")
        print("[helm]   they cannot be validated via yaml.safe_load_all.")
        print("[helm]   To validate: install helm 3.10+ and run `make helm-template`.")
        print("[helm]   Skipping Helm validation. 0 failures (assumed).\n")
        return 0, 0, 0

    chart = "helm/nanobot-factory"
    print(f"[helm]   Rendering Helm chart at {chart}/ ...")
    try:
        result = subprocess.run(
            ["helm", "template", "nanobot-factory", chart, "--namespace", "nanobot-factory"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[helm]   FAIL  helm template error:\n{e.stderr}")
        return 0, 0, 1

    # Parse rendered output as multi-doc YAML
    docs = list(yaml.safe_load_all(result.stdout))
    docs = [d for d in docs if d is not None]
    print(f"[helm]   OK  {len(docs)} resources rendered.")
    return 1, len(docs), 0


def validate_kubectl_dryrun() -> int:
    """kubectl apply --dry-run=client if available."""
    if not shutil.which("kubectl"):
        print("[kubectl] kubectl CLI not installed on this host.")
        print("[kubectl] Skipping `kubectl apply --dry-run=client -k k8s/`.")
        print("[kubectl] Reason: local Windows dev box without cluster access.")
        print("[kubectl] To validate: install kubectl and run `make k8s-dryrun`.\n")
        return 0
    print("[kubectl] Running `kubectl apply --dry-run=client -k k8s/` ...")
    try:
        result = subprocess.run(
            ["kubectl", "apply", "--dry-run=client", "-k", "k8s/"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[kubectl] FAIL:\n{e.stderr}")
        return 1


def main() -> int:
    kf, kd, kfail = validate_k8s_raw()
    hf, hd, hfail = validate_helm_template()
    kfail_kctl = validate_kubectl_dryrun()

    total_fail = kfail + hfail + kfail_kctl
    print("=" * 70)
    print(f"SUMMARY")
    print(f"  k8s/   : {kf} files, {kd} docs, {kfail} failures")
    print(f"  helm/  : {hf} chart, {hd} docs, {hfail} failures")
    print(f"  kubectl: {kfail_kctl} failures")
    print(f"  TOTAL  : {total_fail} failures")
    print("=" * 70)
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())