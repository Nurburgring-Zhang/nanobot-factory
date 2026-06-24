"""Build combined OWASP A06 dependency scan report (safety + pip-audit).

Inputs:
- reports/owasp_a06_safety.json — safety 2.3.5 output
- reports/owasp_a06_pip_audit.json — pip-audit output (if available)

Output:
- reports/owasp_a06.json — unified structure with by_severity tally
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    reports_dir = repo_root / "reports"
    out_path = reports_dir / "owasp_a06.json"

    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanners": [],
        "total_vulnerabilities": 0,
        "by_severity": {},
        "notes": [],
    }

    # 1. safety
    safety_path = reports_dir / "owasp_a06_safety.json"
    if safety_path.exists():
        try:
            d = json.loads(safety_path.read_text(encoding="utf-8"))
            vulns_meta = d.get("report_meta", {})
            vulns_list = []
            for pkg_name, pkg_info in d.get("affected_packages", {}).items():
                for v in pkg_info.get("vulnerabilities", []):
                    vulns_list.append({
                        "package": pkg_name,
                        "version": pkg_info.get("analyzed_version", "?"),
                        "id": v.get("CVE") or v.get("vulnerability_id") or "?",
                        "severity": (v.get("severity_source", {}).get("severity")
                                     if isinstance(v.get("severity_source"), dict)
                                     else v.get("severity", "UNKNOWN")),
                        "description": v.get("advisory", "")[:500],
                    })
            out["scanners"].append({
                "name": "safety-2.3.5",
                "version": vulns_meta.get("safety_version", "?"),
                "packages_found": vulns_meta.get("packages_found", 0),
                "vulnerabilities_found": vulns_meta.get("vulnerabilities_found", 0),
                "vulnerabilities": vulns_list,
            })
            n = vulns_meta.get("vulnerabilities_found", 0)
            out["total_vulnerabilities"] += n
            for v in vulns_list:
                sev = (v.get("severity") or "UNKNOWN").upper()
                out["by_severity"][sev] = out["by_severity"].get(sev, 0) + 1
        except Exception as e:
            out["notes"].append(f"safety parse error: {e}")

    # 2. pip-audit
    pip_path = reports_dir / "owasp_a06_pip_audit.json"
    if pip_path.exists():
        try:
            d = json.loads(pip_path.read_text(encoding="utf-8"))
            vulns_list = []
            for dep in d.get("dependencies", []):
                for v in dep.get("vulns", []):
                    vulns_list.append({
                        "package": dep.get("name", "?"),
                        "version": dep.get("version", "?"),
                        "id": v.get("id", "?"),
                        "severity": v.get("severity", "UNKNOWN"),
                        "fix_versions": v.get("fix_versions", []),
                        "description": (v.get("description") or "")[:500],
                    })
            out["scanners"].append({
                "name": "pip-audit",
                "dependencies_count": len(d.get("dependencies", [])),
                "vulnerabilities": vulns_list,
            })
            for v in vulns_list:
                sev = (v.get("severity") or "UNKNOWN").upper()
                out["by_severity"][sev] = out["by_severity"].get(sev, 0) + 1
            out["total_vulnerabilities"] += len(vulns_list)
        except Exception as e:
            out["notes"].append(f"pip-audit parse error: {e}")
    else:
        out["notes"].append(
            "pip-audit scan not run locally — OSV/PyPI network access blocked in this sandbox. "
            "CI (.github/workflows/security.yml) will run both scanners. "
            "Re-run locally with: pip-audit -r requirements_full.txt --format json "
            "--output reports/owasp_a06_pip_audit.json"
        )

    # Write
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"  total_vulnerabilities: {out['total_vulnerabilities']}")
    print(f"  by_severity: {out['by_severity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())