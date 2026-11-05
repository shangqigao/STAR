#!/usr/bin/env python3
"""Build an image-level demographic table for EAY131."""

import argparse
import json
from pathlib import Path

import pandas as pd


def normalize_gender(value):
    value = str(value).strip()
    return {"F": "Female", "M": "Male"}.get(value, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    index = json.loads((args.root / "Radiology_NIFTI" / "output_index.json").read_text())
    clinical_path = args.root / "Clinical" / "EAY131_Clinical_data_v01_20260216.csv"
    clinical = pd.read_csv(clinical_path, dtype=str)

    if clinical["Patient ID"].duplicated().any():
        duplicates = clinical.loc[clinical["Patient ID"].duplicated(False), "Patient ID"].tolist()
        raise ValueError(f"Duplicate clinical patient IDs: {duplicates[:10]}")

    clinical_map = clinical.set_index("Patient ID")[["age", "sex", "race"]].to_dict("index")
    missing_cases = sorted(set(index) - set(clinical_map))
    if missing_cases:
        raise ValueError(f"Manifest cases without clinical records: {missing_cases[:10]}")

    image_to_case = {}
    for case_id, items in index.items():
        for item in items:
            # output_index.json paths are relative to Radiology_NIFTI; the CSV uses
            # paths relative to the EAY131 dataset root, consistent with CPTAC.
            image_path = str(Path("Radiology_NIFTI") / item["image"])
            previous = image_to_case.setdefault(image_path, case_id)
            if previous != case_id:
                raise ValueError(f"Image belongs to multiple cases: {image_path}")

    rows = []
    for image_path, case_id in image_to_case.items():
        source = clinical_map[case_id]
        rows.append(
            {
                "image_relative_path": image_path,
                "age": int(source["age"]),
                "gender": normalize_gender(source["sex"]),
                "race": source["race"],
            }
        )

    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"manifest_cases={len(index)} clinical_cases={len(clinical)}")
    print(f"annotation_entries={sum(len(items) for items in index.values())}")
    print(f"unique_images={len(out)} unique_paths={out.image_relative_path.nunique()}")
    print(
        "nonmissing="
        + json.dumps(
            {column: int(out[column].ne("").sum()) for column in ("age", "gender", "race")}
        )
    )


if __name__ == "__main__":
    main()
