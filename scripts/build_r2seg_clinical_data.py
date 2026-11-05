#!/usr/bin/env python3
"""Build a flat R2Seg image-level demographic table from supplied clinical files."""

import argparse
import json
import re
from pathlib import Path

import pandas as pd


def clean(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize_sex(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().lower()
    return {"m": "Male", "male": "Male", "f": "Female", "female": "Female"}.get(
        value, str(value).strip()
    )


def image_stem(path):
    name = Path(path).name
    return name[:-7] if name.endswith(".nii.gz") else Path(name).stem


def load_images(root):
    rows = []
    for dataset_json in sorted(root.glob("*/dataset.json")):
        dataset = dataset_json.parent.name
        data = json.loads(dataset_json.read_text())
        for split in ("train", "test"):
            for item in data.get(split, []):
                rel = f"{dataset}/{item['image']}"
                rows.append(
                    {
                        "image_relative_path": rel,
                        "age": "",
                        "gender": "",
                        "race": "",
                        "_dataset": dataset,
                        "_stem": image_stem(item["image"]),
                    }
                )
    return rows


def bladder_map(clinical_dir):
    result = {}
    xls = pd.ExcelFile(clinical_dir / "Bladder_Tumor_00.xlsx")
    for center in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=center)
        image_col = "image" if "image" in df.columns else "image_name"
        for _, row in df.iterrows():
            raw = str(row[image_col]).replace(".nii.gz", "")
            key = f"{center}_{int(raw)}"
            result[key] = {
                "age": clean(row.get("Age (years)")),
                "gender": normalize_sex(row.get("Gender")),
                "race": "",
            }
    return result


def breast_map(clinical_dir):
    df = pd.read_excel(clinical_dir / "Breast_Tumor_00.xlsx", sheet_name="dataset_info")
    result = {}
    for _, row in df.iterrows():
        key = str(row["patient_id"]).strip()
        result[key] = {
            "age": clean(row.get("age")),
            # The official MAMA-MIA dataset description defines the cohort as women.
            # https://www.ub.edu/mama-mia/dataset/
            "gender": "Female",
            "race": clean(row.get("ethnicity")),
        }
    return result


def kidney_map(clinical_dir):
    data = json.loads((clinical_dir / "Kidney_Tumor_00.json").read_text())
    return {
        str(row["case_id"]): {
            "age": clean(row.get("age_at_nephrectomy")),
            "gender": normalize_sex(row.get("gender")),
            "race": "",
        }
        for row in data
    }


def lung_map(clinical_dir):
    df = pd.read_csv(clinical_dir / "Lung_Tumor_01.csv")
    return {
        str(row["PatientID"]).strip(): {
            "age": clean(row.get("age")),
            "gender": normalize_sex(row.get("gender")),
            "race": "",
        }
        for _, row in df.iterrows()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--r2seg-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    clinical_dir = args.r2seg_root / "Clinical_data"
    mappings = {
        "Bladder_Tumor_00": bladder_map(clinical_dir),
        "Breast_Tumor_00": breast_map(clinical_dir),
        "Kidney_Tumor_00": kidney_map(clinical_dir),
        "Lung_Tumor_01": lung_map(clinical_dir),
    }

    rows = load_images(args.r2seg_root)
    matched = {name: 0 for name in mappings}
    for row in rows:
        dataset = row["_dataset"]
        stem = row["_stem"]
        record = None
        if dataset == "Breast_Tumor_00":
            # Image names append a sequence suffix to the clinical patient ID.
            candidates = [key for key in mappings[dataset] if stem == key or stem.startswith(key + "_")]
            if len(candidates) == 1:
                record = mappings[dataset][candidates[0]]
        elif dataset == "Lung_Tumor_01":
            record = mappings[dataset].get(stem.removesuffix("_CT"))
        elif dataset in mappings:
            lookup_stem = stem
            if dataset == "Bladder_Tumor_00":
                match = re.fullmatch(r"(Center\d+)_(\d+)", stem)
                if match:
                    lookup_stem = f"{match.group(1)}_{int(match.group(2))}"
            record = mappings[dataset].get(lookup_stem)
        if record is not None:
            row.update(record)
            matched[dataset] += 1

    out = pd.DataFrame(rows).drop(columns=["_dataset", "_stem"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"rows={len(out)} unique_paths={out.image_relative_path.nunique()}")
    print("matched=" + json.dumps(matched, sort_keys=True))
    print("nonmissing=" + json.dumps({c: int(out[c].ne("").sum()) for c in ["age", "gender", "race"]}))
    print("duplicates=" + str(int(out.image_relative_path.duplicated().sum())))


if __name__ == "__main__":
    main()
