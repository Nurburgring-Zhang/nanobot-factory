"""Count K8s resources by kind."""
import glob
from collections import Counter

import yaml

files = sorted(glob.glob("k8s/**/*.yaml", recursive=True))
kinds: Counter = Counter()
for f in files:
    with open(f, encoding="utf-8") as fp:
        for d in yaml.safe_load_all(fp):
            if d and isinstance(d, dict):
                kinds[d.get("kind", "unknown")] += 1
print("K8s resource counts by kind:")
for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
    print(f"  {v:>3d}  {k}")
print(f"Total: {sum(kinds.values())} resources")