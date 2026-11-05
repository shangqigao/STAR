#!/usr/bin/env python3
"""Harmonize race labels in manifests/images.json."""

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path


RACE_MAP = {
    "White": "White",
    "white": "White",
    "caucasian": "White",
    "Black": "Black or African American",
    "black or african american": "Black or African American",
    "african american": "Black or African American",
    "Asian": "Asian",
    "asian": "Asian",
    "Pacific Islander": "Native Hawaiian or Pacific Islander",
    "hawaiian/pacific islander": "Native Hawaiian or Pacific Islander",
    "hawaian": "Native Hawaiian or Pacific Islander",
    "Native American": "American Indian or Alaska Native",
    "native american": "American Indian or Alaska Native",
    "american indian/alaskan native": "American Indian or Alaska Native",
    "american indian": "American Indian or Alaska Native",
    "Multirace": "Multiracial",
    "multiple race": "Multiracial",
    "hispanic": "Hispanic",
    "Not Reported": "Not Reported",
    "not reported": "Not Reported",
    "Unknown": "Not Reported",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("manifests/images.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text())
    before = Counter(item.get("race") for item in data)
    unmapped = sorted(value for value in before if value is not None and value not in RACE_MAP)
    if unmapped:
        raise ValueError(f"Unmapped race labels: {unmapped}")

    changed = 0
    for item in data:
        value = item.get("race")
        harmonized = None if value is None else RACE_MAP[value]
        if harmonized != value:
            changed += 1
        item["race"] = harmonized

    after = Counter(item.get("race") for item in data)
    printable_before = {"null" if key is None else key: value for key, value in before.items()}
    printable_after = {"null" if key is None else key: value for key, value in after.items()}
    print("before=" + json.dumps(printable_before, sort_keys=True))
    print("after=" + json.dumps(printable_after, sort_keys=True))
    print(f"rows={len(data)} changed={changed} null={after[None]}")

    if args.dry_run:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = args.manifest.with_name(f"{args.manifest.stem}.before_race_harmonization_{timestamp}.json")
    shutil.copy2(args.manifest, backup)
    temporary = args.manifest.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(args.manifest)
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
