#!/usr/bin/env python3
"""
i18n key extraction & coverage audit for frontend-v2.

Walks the .vue / .ts source under frontend-v2/src, parses `t('ns.key', ...)` /
`$t('ns.key', ...)` / `i18n.key('ns.key')` style calls and the locale files
(zh-CN.ts / en-US.ts), and produces:

  1. coverage report  — how many views reference t() at all, how often,
                         how many t() keys are present per namespace.
  2. missing-key list — t() keys referenced from code but absent from
                         the locale files.
  3. unused-key list   — keys defined in locale files but never used.
  4. parity check      — same key set in zh-CN.ts and en-US.ts.
  5. hardcoded CN      — Chinese characters in template/script bodies
                         (the residual stub count the P13-B2 gate tracks).

Usage:
  python scripts/extract_i18n_keys.py [--src frontend-v2/src] \\
         [--locales frontend-v2/src/locales/zh-CN.ts \\
                     frontend-v2/src/locales/en-US.ts] \\
         [--report reports/p13_b2_i18n_audit.json] \\
         [--strict]    # exit non-zero on missing keys

Exit codes:
  0   — clean
  1   — missing keys (when --strict) or scan error
  2   — invalid arguments
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------- patterns ----------
# Match `t('ns.key', ...)`, `t("ns.key", ...)`, `t(`ns.key`, ...)`,
# optionally preceded by `$` or `i18n.` (in templates / composables).
T_CALL = re.compile(
    r"""(?<![A-Za-z0-9_$])              # not part of an identifier
        (?:\$?t|\$?i18n\.t|i18n\.key)  # t / $t / i18n.t / i18n.key
        \s*\(\s*[`'"]([A-Za-z][\w]*(?:\.[A-Za-z_][\w]*)+)[`'"]""",
    re.VERBOSE,
)

# Hardcoded Chinese ranges — basic CJK ideographs (U+4E00–U+9FFF) + extension A.
CN_RANGE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]+")

# Locale namespace block — top-level `  name: {` lines.
NS_START = re.compile(r"^  (\w+): \{", re.MULTILINE)
# Locale leaf key — `    keyName: ...`
LOCALE_KEY = re.compile(r"^\s+([\w$]+):", re.MULTILINE)


# ---------- core scans ----------
def scan_files(src_root: Path) -> tuple[dict[str, dict], set[str], int]:
    """Return per-file t() stats, total unique t() keys, total CN runs.

    Excludes the locales/ subtree from the CN run tally (locales are
    *supposed* to contain Chinese values — counting them would inflate the
    "hardcoded" metric). t() key extraction still walks locales so we can
    report them as 'unused' if no source references them.
    """
    per_file: dict[str, dict] = {}
    used_keys: set[str] = set()
    total_cn_runs = 0
    for path in sorted(src_root.rglob("*")):
        if path.suffix not in {".vue", ".ts", ".tsx", ".js"}:
            continue
        rel = str(path).replace("\\", "/")
        in_locales = "/locales/" in rel or rel.endswith("/locales")
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"warn: cannot read {path}: {exc}", file=sys.stderr)
            continue
        matches = T_CALL.findall(text)
        cn_runs = CN_RANGE.findall(text)
        if not in_locales:
            total_cn_runs += len(cn_runs)
        per_file[rel] = {
            "tCalls": len(matches),
            "keys": sorted(set(matches)),
            "cnRuns": len(cn_runs),
            "inLocales": in_locales,
        }
        used_keys.update(matches)
    return per_file, used_keys, total_cn_runs


def load_locale(path: Path) -> dict[str, set[str]]:
    """Return {namespace: set(full keys)} from a locale file.

    Full keys are `ns.leaf` (e.g. `agentManagement.create`) so they can be
    diffed against the dotted t() call keys extracted from source.
    """
    text = path.read_text(encoding="utf-8")
    starts = [(m.start(), m.group(1)) for m in NS_START.finditer(text)]
    out: dict[str, set[str]] = {}
    for i, (pos, ns) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        body = text[pos:end]
        # Strip the namespace's own name line so it doesn't sneak in.
        leaves = set(LOCALE_KEY.findall(body))
        leaves.discard(ns)  # the `ns: {` line itself
        out[ns] = {f"{ns}.{leaf}" for leaf in leaves}
    return out


# ---------- report assembly ----------
def build_report(
    per_file: dict[str, dict],
    used_keys: set[str],
    total_cn_runs: int,
    zh: dict[str, set[str]],
    en: dict[str, set[str]],
) -> dict:
    # 1. View-level coverage — count views (.vue under src/views) that have
    #    at least one t() call.
    view_files = {p: st for p, st in per_file.items() if "/views/" in p or p.endswith("\\views\\") or "/views" in p}
    views_total = len(view_files)
    views_with_t = sum(1 for st in view_files.values() if st["tCalls"] > 0)
    coverage_pct = round(100 * views_with_t / views_total, 2) if views_total else 0.0

    # 2. Parity between zh-CN and en-US
    all_ns = set(zh) | set(en)
    parity_issues = []
    for ns in sorted(all_ns):
        zk, ek = zh.get(ns, set()), en.get(ns, set())
        if zk != ek:
            parity_issues.append({
                "ns": ns,
                "missingInEn": sorted(zk - ek),
                "missingInZh": sorted(ek - zk),
            })

    # 3. Missing & unused keys (full dotted form)
    zh_all = set().union(*zh.values())
    en_all = set().union(*en.values())
    locale_keys = zh_all | en_all
    missing_in_locale = sorted(used_keys - locale_keys)
    unused_in_code = sorted(locale_keys - used_keys)

    # 4. Hardcoded CN views (top 20)
    cn_top = sorted(
        ((p, st["cnRuns"]) for p, st in per_file.items() if st["cnRuns"] > 0),
        key=lambda x: -x[1],
    )[:20]

    # 5. Per-namespace usage from code
    ns_usage: dict[str, int] = defaultdict(int)
    for k in used_keys:
        ns = k.split(".", 1)[0]
        ns_usage[ns] += 1

    return {
        "summary": {
            "filesScanned": len(per_file),
            "viewFiles": views_total,
            "viewsWithT": views_with_t,
            "tCoveragePct": coverage_pct,
            "totalTCalls": sum(st["tCalls"] for st in per_file.values()),
            "uniqueTKeys": len(used_keys),
            "totalCnRuns": total_cn_runs,
            "totalCnRunsExclLocales": sum(
                st["cnRuns"] for p, st in per_file.items() if not st.get("inLocales")
            ),
            "localeNamespacesZh": len(zh),
            "localeNamespacesEn": len(en),
            "totalLocaleKeysZh": len(zh_all),
            "totalLocaleKeysEn": len(en_all),
            "missingInLocale": len(missing_in_locale),
            "unusedInCode": len(unused_in_code),
            "parityIssues": len(parity_issues),
        },
        "perNamespaceKeyCount": {
            ns: {"zh": len(zh.get(ns, set())), "en": len(en.get(ns, set()))}
            for ns in sorted(all_ns)
        },
        "target5NamespaceKeyCount": {
            ns: {"zh": len(zh.get(ns, set())), "en": len(en.get(ns, set()))}
            for ns in ("common", "menu", "button", "form", "table")
        },
        "perNamespaceTUsage": dict(sorted(ns_usage.items())),
        "missingInLocale": missing_in_locale,
        "unusedInCode": unused_in_code,
        "parityIssues": parity_issues,
        "topHardcodedCN": [{"file": p, "runs": n} for p, n in cn_top],
    }


# ---------- CLI ----------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", type=Path, default=Path("frontend-v2/src"),
                   help="Source root to scan (default: frontend-v2/src)")
    p.add_argument("--locales", type=Path, nargs="+",
                   default=[Path("frontend-v2/src/locales/zh-CN.ts"),
                            Path("frontend-v2/src/locales/en-US.ts")],
                   help="Locale files (default: zh-CN.ts en-US.ts)")
    p.add_argument("--report", type=Path, default=None,
                   help="Optional JSON report output path")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero on missing keys")
    args = p.parse_args()

    if not args.src.exists():
        print(f"error: --src {args.src} does not exist", file=sys.stderr)
        return 2
    for lf in args.locales:
        if not lf.exists():
            print(f"error: --locales {lf} does not exist", file=sys.stderr)
            return 2

    per_file, used_keys, total_cn = scan_files(args.src)
    zh = load_locale(args.locales[0])
    en = load_locale(args.locales[1]) if len(args.locales) > 1 else {}
    report = build_report(per_file, used_keys, total_cn, zh, en)

    # stdout summary
    s = report["summary"]
    print("=== i18n Coverage ===")
    print(f"Files scanned:           {s['filesScanned']}")
    print(f"View files:              {s['viewFiles']}")
    print(f"Views with t() call:     {s['viewsWithT']} ({s['tCoveragePct']}%)")
    print(f"Total t() calls:         {s['totalTCalls']}")
    print(f"Unique t() keys:         {s['uniqueTKeys']}")
    print(f"Hardcoded CN runs (excl locales): {s['totalCnRunsExclLocales']}")
    print(f"Hardcoded CN runs (incl locales): {s['totalCnRuns']}")
    print(f"Locale namespaces:       {s['localeNamespacesZh']} zh / {s['localeNamespacesEn']} en")
    print(f"Locale keys total:       {s['totalLocaleKeysZh']} zh / {s['totalLocaleKeysEn']} en")
    print(f"Missing in locale:       {s['missingInLocale']}")
    print(f"Unused in code:          {s['unusedInCode']}")
    print(f"Parity issues:           {s['parityIssues']}")
    print()
    print("=== Per-namespace key count (zh / en) ===")
    for ns, c in report["perNamespaceKeyCount"].items():
        flag = "" if c["zh"] == c["en"] else "  ⚠ PARITY MISMATCH"
        print(f"  {ns:24s}  zh={c['zh']:4d}  en={c['en']:4d}{flag}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote report: {args.report}")

    if args.strict and (s["missingInLocale"] > 0 or s["parityIssues"] > 0):
        print("\n[strict] failing with errors above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
