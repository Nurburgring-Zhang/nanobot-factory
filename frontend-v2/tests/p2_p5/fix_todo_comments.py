#!/usr/bin/env python3
"""Fix the TODO comment placement in non-en locale files.

The previous script generated lines like:
    tNNN: 'value' // TODO: native review,
where the `,` is part of the comment, making the JS invalid.

This script rewrites them to:
    tNNN: 'value', // TODO: native review
"""
import os
import re

LOCALES_DIR = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\locales"

NON_EN_FILES = ["zh-CN.ts", "ja-JP.ts", "ko-KR.ts", "fr-FR.ts", "de-DE.ts",
                "es-ES.ts", "ru-RU.ts", "ar-SA.ts", "pt-PT.ts"]

for fname in NON_EN_FILES:
    path = os.path.join(LOCALES_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Pattern: <spaces>key: 'value' // TODO: native review,
    # Replace with: <spaces>key: 'value', // TODO: native review
    # Use a regex that matches the value, captures key+value, then moves the comma
    new_content = re.sub(
        r"(\s+\w+:\s*'[^']*')\s*(//\s*TODO:\s*native\s+review),",
        r"\1, \2",
        content
    )

    # Also handle the case where the line is the LAST key (no comma at end):
    # <spaces>key: 'value' // TODO: native review}
    # This is OK as-is (the } is on the same line as the comment)
    # but check for any orphan comments where the comma is missing entirely.

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Fixed {fname}")
    else:
        print(f"  No change for {fname}")
