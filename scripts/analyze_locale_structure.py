#!/usr/bin/env python3
"""
Analyze 8 broken locale files to understand structure and produce a restructure plan.

Outputs:
- Per-file line counts (current, pre-p2p4)
- Per-file top-level key lists with line numbers (current, pre-p2p4)
- Per-file duplicate key detection
- Per-file boundary line for "p2p4 content starts here"
"""
from pathlib import Path
import re
import json

LOCALES_DIR = Path(r"D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales")
BROKEN_FILES = ["ar-SA", "de-DE", "es-ES", "fr-FR", "ja-JP", "ko-KR", "pt-PT", "ru-RU"]

# Top-level block regex: looks for `  blockName: {` at column 2 (after the export default {)
# Top-level keys: common, nav, auth, dashboard, annotation, billing, workflows, engines,
# workflowBuilder, dataFlowTracker, form, menu, multimodalAgentChat, userManagement,
# projectCenter, requirementCenter, internalQC, requesterAccept, collectionCenter, delivery,
# capabilityRegistry, packManager
TOP_KEYS = [
    "common", "nav", "auth", "dashboard", "annotation", "billing", "workflows", "engines",
    "workflowBuilder", "dataFlowTracker", "form", "menu", "multimodalAgentChat",
    "userManagement", "projectCenter", "requirementCenter", "internalQC", "requesterAccept",
    "collectionCenter", "delivery", "capabilityRegistry", "packManager"
]

def find_top_level_keys(content: str) -> list[tuple[str, int]]:
    """Return list of (key, line_number) for each top-level key found."""
    results = []
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        # Match `  keyName: {` at column 2 (2 leading spaces)
        for key in TOP_KEYS:
            if line.strip() == f"{key}:":
                results.append((key, i))
                break
            # Also match `  keyName: {` (with leading brace)
            if line.strip() == f"{key}: {{":
                results.append((key, i))
                break
    return results

def main():
    summary = {}
    for locale in BROKEN_FILES:
        current_path = LOCALES_DIR / f"{locale}.ts"
        pre_path = LOCALES_DIR / f"{locale}.ts.pre-p2p4"
        current = current_path.read_text(encoding="utf-8")
        pre = pre_path.read_text(encoding="utf-8")

        current_keys = find_top_level_keys(current)
        pre_keys = find_top_level_keys(pre)

        # Count occurrences of each key
        from collections import Counter
        current_counter = Counter(k for k, _ in current_keys)
        pre_counter = Counter(k for k, _ in pre_keys)

        # Find duplicates in current
        current_dupes = {k: c for k, c in current_counter.items() if c > 1}
        # Find duplicates in pre
        pre_dupes = {k: c for k, c in pre_counter.items() if c > 1}

        # Find the boundary: the line of the 2nd occurrence of the first duplicate key
        # The first duplicate key (in order of first appearance) - take the 1st key with > 1 occurrence
        first_dupe_key = None
        first_dupe_2nd_line = None
        for k, line in current_keys:
            if current_counter[k] > 1:
                # Find the 2nd occurrence of this key
                occurrences = [l for kk, l in current_keys if kk == k]
                if len(occurrences) >= 2:
                    first_dupe_key = k
                    first_dupe_2nd_line = occurrences[1]
                    break

        summary[locale] = {
            "current_keys": current_keys,
            "pre_keys": pre_keys,
            "current_dupes": current_dupes,
            "pre_dupes": pre_dupes,
            "first_dupe_key": first_dupe_key,
            "first_dupe_2nd_line": first_dupe_2nd_line,
            "current_line_count": len(current.split("\n")),
            "pre_line_count": len(pre.split("\n")),
        }

    # Print summary
    for locale, data in summary.items():
        print(f"\n=== {locale} ===")
        print(f"  Current lines: {data['current_line_count']}, Pre lines: {data['pre_line_count']}")
        print(f"  Current top-level keys (with line numbers):")
        from collections import Counter
        cc = Counter(k for k, _ in data['current_keys'])
        for k, l in data['current_keys']:
            marker = " [DUP]" if cc[k] > 1 else ""
            print(f"    L{l:4d}: {k}{marker}")
        print(f"  Duplicate keys (current): {data['current_dupes']}")
        print(f"  Duplicate keys (pre-p2p4): {data['pre_dupes']}")
        print(f"  First duplicate key: {data['first_dupe_key']} (2nd occurrence at L{data['first_dupe_2nd_line']})")

if __name__ == "__main__":
    main()
