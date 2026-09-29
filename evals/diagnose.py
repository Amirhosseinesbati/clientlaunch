"""Developer-only summary of an already inspected evaluation run.

Do not treat this diagnostic as a held-out result after changing the extractor.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    missing = Counter(key for case in result["per_case"] for key in case.get("required_missing", []))
    extra = Counter(key for case in result["per_case"] for key in case.get("extra_scope", []))
    print("Development-only diagnostic of inspected result")
    print("Missing required keys:")
    for key, count in sorted(missing.items()):
        print(f"  {key}: {count}")
    print("Extra scope keys:")
    for key, count in sorted(extra.items()):
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
