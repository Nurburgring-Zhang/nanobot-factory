#!/usr/bin/env python3
"""Fix the last-key comment placement in non-en locale files.

The previous fix left the last key in each namespace with:
    tNNN: 'value' // TODO: native review}
where the `}` is part of the comment, so the namespace is never closed.

This script rewrites them to:
    tNNN: 'value'
    // TODO: native review
  }
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

    # Pattern: <spaces>key: 'value' // TODO: native review}
    # Replace with: <spaces>key: 'value',\n<spaces>// TODO: native review\n<spaces>}
    new_content = re.sub(
        r"(\s+\w+:\s*'[^']*')\s*//\s*TODO:\s*native\s+review\s*\}",
        r"\1\n    // TODO: native review\n  }",
        content
    )

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Fixed last-key in {fname}")
    else:
        print(f"  No last-key fix needed for {fname}")
