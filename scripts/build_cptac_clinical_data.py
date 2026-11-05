#!/usr/bin/env python3
"""Build an image-level demographic table for CPTAC-Annotated."""

import argparse
import json
from pathlib import Path

import pandas as pd


MISSING_TOKENS = {"", "'--", "--"}


def clean(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    return "" if value in MISSING_TOKENS else value


def normalize_gender(value):
    value = clean(value)
    return {"female": "Female", "male": "Male"}.get(value.lower(), value) if value else ""


def load_demographics(clinical_path, case_ids):
    df = pd.read_csv(clinical_path, sep="\t", dtype=str, low_memory=False)
    df = df[df["cases.submitter_id"].isin(case_ids)].copy()
    fields = {
        "days_to_birth": "demographic.days_to_birth",
        "gender": "demographic.sex_at_birth",
        "race": "demographic.race",
    }

    records = {}
    for case_id, group in df.groupby("cases.submitter_id", sort=False):
        values = {}
        for name, column in fields.items():
            distinct = {clean(value) for value in group[column] if clean(value)}
            if len(distinct) > 1:
                raise ValueError(f"Conflicting {name} values for {case_id}: {sorted(distinct)}")
            values[name] = next(iter(distinct), "")

        age = ""
        if values["days_to_birth"]:
            # GDC days_to_birth is negative and measured relative to the index event.
            age = round(abs(float(values["days_to_birth"])) / 365.25, 1)
        records[case_id] = {
            "age": age,
            "gender": normalize_gender(values["gender"]),
            "race": values["race"],
        }
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads((args.root / "dataset.json").read_text())
    cases = manifest["cases"]
    clinical_path = (
        args.root
        / "Clinical"
        / "clinical.project-cptac-3.2026-09-15"
        / "clinical.tsv"
    )
    demographics = load_demographics(clinical_path, set(cases))

    image_to_case = {}
    for case_id, items in cases.items():
        for item in items:
            image_path = item["image"]
            previous = image_to_case.setdefault(image_path, case_id)
            if previous != case_id:
                raise ValueError(f"Image belongs to multiple cases: {image_path}")

    rows = []
    for image_path, case_id in image_to_case.items():
        row = {
            "image_relative_path": image_path,
            "age": "",
            "gender": "",
            "race": "",
        }
        row.update(demographics.get(case_id, {}))
        rows.append(row)

    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"cases={len(cases)} cases_with_clinical_data={len(demographics)}")
    print(f"annotation_entries={sum(len(x) for x in cases.values())}")
    print(f"unique_images={len(out)} unique_paths={out.image_relative_path.nunique()}")
    print(
        "nonmissing="
        + json.dumps(
            {column: int(out[column].ne("").sum()) for column in ("age", "gender", "race")}
        )
    )


if __name__ == "__main__":
    main()
