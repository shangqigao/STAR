#!/usr/bin/env python3
"""Add globally unique canonical patient IDs to manifests/images.json."""

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOTS = {
    "R2Seg": Path("/Users/sg2162/Datasets/CancerDatasets/R2Seg"),
    "EAY131": Path("/Users/sg2162/Datasets/CancerDatasets/EAY131"),
    "CPTAC": Path("/Users/sg2162/Datasets/CancerDatasets/CPTAC-Annotated"),
}


def nii_stem(path):
    name = Path(path).name
    return name[:-7] if name.endswith(".nii.gz") else Path(name).stem


def add_unique(mapping, key, patient_id, description):
    if key in mapping and mapping[key] != patient_id:
        raise ValueError(f"Ambiguous {description} {key}: {mapping[key]} vs {patient_id}")
    mapping[key] = patient_id


def r2seg_patient_id(dataset, stem):
    if dataset == "Bladder_Tumor_00":
        match = re.fullmatch(r"(Center\d+)_(\d+)", stem)
        if not match:
            raise ValueError(f"Unexpected bladder identifier: {stem}")
        source_id = f"{match.group(1)}_{int(match.group(2))}"
        return f"R2Seg::Bladder_Tumor_00::{source_id}"
    if dataset == "Breast_Tumor_00":
        return "R2Seg::Breast_Tumor_00::" + re.sub(r"_0001$", "", stem)
    if dataset == "Cervix_Tumor_00":
        return "R2Seg::Cervix_Tumor_00::" + stem.split("_MR", 1)[0]
    if dataset in {"Colon_Tumor_00", "Liver_Tumor_00", "Pancreas_Tumor_00"}:
        # These subsets share the same source case namespace.
        return f"R2Seg::FLARE23::{stem}"
    if dataset == "Lung_Tumor_01":
        return "R2Seg::Lung_Tumor_01::" + re.sub(r"_CT$", "", stem)
    if dataset == "Prostate_Tumor_00":
        return "R2Seg::Prostate_Tumor_00::" + re.sub(r"_(adc|t2)$", "", stem)
    if dataset == "Uterus_Tumor_00":
        return "R2Seg::Uterus_Tumor_00::" + re.sub(r"_t2$", "", stem)
    return f"R2Seg::{dataset}::{stem}"


def build_r2seg_lookup(root):
    lookup = {}
    for dataset_json in sorted(root.glob("*/dataset.json")):
        dataset = dataset_json.parent.name
        data = json.loads(dataset_json.read_text())
        for split in ("train", "test"):
            for item in data.get(split, []):
                stem = nii_stem(item["image"])
                key = f"{dataset}_{stem}"
                add_unique(lookup, key, r2seg_patient_id(dataset, stem), "R2Seg image key")
    return lookup


def build_eay131_lookup(root):
    index = json.loads((root / "Radiology_NIFTI" / "output_index.json").read_text())
    lookup = {}
    for case_id, items in index.items():
        patient_id = f"EAY131::{case_id}"
        for item in items:
            annotation_uid = Path(item["label"]).parent.name
            add_unique(lookup, annotation_uid, patient_id, "EAY131 annotation UID")
    return lookup


def build_cptac_lookup(root):
    cases = json.loads((root / "dataset.json").read_text())["cases"]
    lookup = {}
    for case_id, items in cases.items():
        patient_id = f"CPTAC::{case_id}"
        for item in items:
            annotation_uid = Path(item["label"]).parent.name
            add_unique(lookup, annotation_uid, patient_id, "CPTAC annotation UID")
    return lookup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("manifests/images.json"))
    parser.add_argument("--benchmark-split", type=Path, default=Path("assignments/mllm_split.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lookups = {
        "R2Seg": build_r2seg_lookup(ROOTS["R2Seg"]),
        "EAY131": build_eay131_lookup(ROOTS["EAY131"]),
        "CPTAC": build_cptac_lookup(ROOTS["CPTAC"]),
    }
    data = json.loads(args.manifest.read_text())
    unresolved = []
    for item in data:
        key = Path(item["image_path"]).name.split("-site_in_", 1)[0]
        patient_id = lookups[item["dataset"]].get(key)
        if patient_id is None:
            unresolved.append((item["image_id"], item["dataset"], key))
        else:
            item["patient_id"] = patient_id
    if unresolved:
        print(f"unresolved={len(unresolved)} examples={unresolved[:10]}")
        raise SystemExit(1)

    full_counts = Counter(item["dataset"] for item in data)
    full_patients = {item["patient_id"] for item in data}
    benchmark_ids = set(json.loads(args.benchmark_split.read_text())["image_ids"])
    benchmark = [item for item in data if item["image_id"] in benchmark_ids]
    benchmark_counts = Counter(item["dataset"] for item in benchmark)
    benchmark_patients = {item["patient_id"] for item in benchmark}
    print(f"manifest_rows={len(data)} manifest_patients={len(full_patients)}")
    print("manifest_rows_by_dataset=" + json.dumps(full_counts, sort_keys=True))
    print(f"benchmark_rows={len(benchmark)} benchmark_patients={len(benchmark_patients)}")
    print("benchmark_rows_by_dataset=" + json.dumps(benchmark_counts, sort_keys=True))
    for dataset in ("EAY131", "CPTAC", "R2Seg"):
        patients = {item["patient_id"] for item in benchmark if item["dataset"] == dataset}
        print(f"benchmark_{dataset}_patients={len(patients)}")

    if args.dry_run:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = args.manifest.with_name(f"{args.manifest.stem}.before_patient_ids_{timestamp}.json")
    shutil.copy2(args.manifest, backup)
    temporary = args.manifest.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(args.manifest)
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
