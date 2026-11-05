#!/usr/bin/env python3
"""Add age, gender, and race to STAR manifests/images.json."""

import argparse
import csv
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path


DEFAULT_SOURCE_ROOTS = {
    "R2Seg": Path("/Users/sg2162/Datasets/CancerDatasets/R2Seg"),
    "EAY131": Path("/Users/sg2162/Datasets/CancerDatasets/EAY131"),
    "CPTAC": Path("/Users/sg2162/Datasets/CancerDatasets/CPTAC-Annotated"),
}


def nii_stem(path):
    name = Path(path).name
    return name[:-7] if name.endswith(".nii.gz") else Path(name).stem


def parse_age(value):
    value = value.strip()
    if not value:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def load_clinical_csv(path):
    records = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            image_path = row["image_relative_path"]
            if image_path in records:
                raise ValueError(f"Duplicate clinical image path in {path}: {image_path}")
            records[image_path] = {
                "age": parse_age(row["age"]),
                "gender": row["gender"].strip() or None,
                "race": row["race"].strip() or None,
            }
    return records


def add_unique(mapping, key, value, description):
    if key in mapping and mapping[key] != value:
        raise ValueError(f"Ambiguous {description} {key}: {mapping[key]} versus {value}")
    mapping[key] = value


def build_r2seg_lookup(root):
    clinical = load_clinical_csv(root / "clinical_data.csv")
    lookup = {}
    for image_path, demographics in clinical.items():
        dataset = image_path.split("/", 1)[0]
        key = f"{dataset}_{nii_stem(image_path)}"
        add_unique(lookup, key, demographics, "R2Seg image key")
    return lookup


def build_eay131_lookup(root):
    clinical = load_clinical_csv(root / "clinical_data.csv")
    index = json.loads((root / "Radiology_NIFTI" / "output_index.json").read_text())
    lookup = {}
    for items in index.values():
        for item in items:
            clinical_path = str(Path("Radiology_NIFTI") / item["image"])
            demographics = clinical[clinical_path]
            annotation_uid = Path(item["label"]).parent.name
            add_unique(lookup, annotation_uid, demographics, "EAY131 annotation UID")
    return lookup


def build_cptac_lookup(root):
    clinical = load_clinical_csv(root / "clinical_data.csv")
    dataset = json.loads((root / "dataset.json").read_text())
    lookup = {}
    for items in dataset["cases"].values():
        for item in items:
            demographics = clinical[item["image"]]
            annotation_uid = Path(item["label"]).parent.name
            add_unique(lookup, annotation_uid, demographics, "CPTAC annotation UID")
    return lookup


def manifest_key(item):
    filename = Path(item["image_path"]).name
    key = filename.split("-site_in_", 1)[0]
    if item["dataset"] in {"EAY131", "CPTAC"}:
        return key
    if item["dataset"] == "R2Seg":
        return key
    raise ValueError(f"Unsupported dataset: {item['dataset']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("manifests/images.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lookups = {
        "R2Seg": build_r2seg_lookup(DEFAULT_SOURCE_ROOTS["R2Seg"]),
        "EAY131": build_eay131_lookup(DEFAULT_SOURCE_ROOTS["EAY131"]),
        "CPTAC": build_cptac_lookup(DEFAULT_SOURCE_ROOTS["CPTAC"]),
    }
    manifest = json.loads(args.manifest.read_text())

    unresolved = []
    resolved = Counter()
    coverage = {dataset: Counter() for dataset in lookups}
    for item in manifest:
        dataset = item["dataset"]
        key = manifest_key(item)
        demographics = lookups[dataset].get(key)
        if demographics is None:
            unresolved.append((item["image_id"], dataset, key))
            continue
        item.update(demographics)
        resolved[dataset] += 1
        for field, value in demographics.items():
            if value is not None:
                coverage[dataset][field] += 1

    if unresolved:
        print(f"unresolved={len(unresolved)} examples={unresolved[:10]}")
        raise SystemExit(1)

    print(f"rows={len(manifest)} resolved={sum(resolved.values())}")
    print("resolved_by_dataset=" + json.dumps(resolved, sort_keys=True))
    print("nonmissing_by_dataset=" + json.dumps(coverage, sort_keys=True))

    if args.dry_run:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = args.manifest.with_name(f"{args.manifest.stem}.before_demographics_{timestamp}.json")
    shutil.copy2(args.manifest, backup)
    temporary = args.manifest.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(args.manifest)
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
