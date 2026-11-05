#!/usr/bin/env python3
"""Independently audit CPTAC-Annotated clinical_data.csv."""

import json
from pathlib import Path

import pandas as pd


ROOT = Path("/Users/sg2162/Datasets/CancerDatasets/CPTAC-Annotated")
CSV_PATH = ROOT / "clinical_data.csv"
CLINICAL_PATH = (
    ROOT
    / "Clinical"
    / "clinical.project-cptac-3.2026-09-15"
    / "clinical.tsv"
)
MISSING = {"", "'--", "--"}


def clean(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    return "" if value in MISSING else value


manifest = json.loads((ROOT / "dataset.json").read_text())
cases = manifest["cases"]

# Establish image ownership independently from the generated CSV.
owners = {}
annotation_entries = 0
for case_id, items in cases.items():
    for item in items:
        annotation_entries += 1
        image = item["image"]
        if image in owners and owners[image] != case_id:
            raise AssertionError(f"Image assigned to two cases: {image}")
        owners[image] = case_id

clinical = pd.read_csv(CLINICAL_PATH, sep="\t", dtype=str, low_memory=False)
clinical = clinical[clinical["cases.submitter_id"].isin(cases)].copy()

# Confirm repeated rows do not disagree before reducing to one record per case.
source_records = {}
source_conflicts = []
for case_id, group in clinical.groupby("cases.submitter_id"):
    reduced = {}
    for output_name, source_name in {
        "days_to_birth": "demographic.days_to_birth",
        "gender": "demographic.sex_at_birth",
        "race": "demographic.race",
    }.items():
        values = {clean(x) for x in group[source_name] if clean(x)}
        if len(values) > 1:
            source_conflicts.append((case_id, output_name, sorted(values)))
        reduced[output_name] = next(iter(values), "")
    source_records[case_id] = reduced

if source_conflicts:
    raise AssertionError(f"Conflicting source demographics: {source_conflicts[:5]}")

actual = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
errors = []

if list(actual.columns) != ["image_relative_path", "age", "gender", "race"]:
    errors.append(("columns", list(actual.columns)))
if len(actual) != len(owners):
    errors.append(("row_count", len(actual), len(owners)))
if actual.image_relative_path.duplicated().any():
    errors.append(("duplicate_paths", int(actual.image_relative_path.duplicated().sum())))
if set(actual.image_relative_path) != set(owners):
    errors.append(
        (
            "path_set",
            sorted(set(owners) - set(actual.image_relative_path))[:5],
            sorted(set(actual.image_relative_path) - set(owners))[:5],
        )
    )

for _, row in actual.iterrows():
    image = row["image_relative_path"]
    case_id = owners.get(image)
    source = source_records.get(case_id)
    if source:
        expected_age = ""
        if source["days_to_birth"]:
            expected_age = str(round(abs(float(source["days_to_birth"])) / 365.25, 1))
        expected_gender = {"female": "Female", "male": "Male"}.get(
            source["gender"].lower(), source["gender"]
        )
        expected = {
            "age": expected_age,
            "gender": expected_gender,
            "race": source["race"],
        }
    else:
        expected = {"age": "", "gender": "", "race": ""}
    for field in ("age", "gender", "race"):
        if row[field] != expected[field]:
            errors.append((image, case_id, field, row[field], expected[field]))

missing_files = [image for image in owners if not (ROOT / image).exists()]
if missing_files:
    errors.append(("missing_files", missing_files[:5], len(missing_files)))

print(f"annotation_entries={annotation_entries}")
print(f"unique_images={len(owners)} csv_rows={len(actual)}")
print(f"manifest_cases={len(cases)} clinical_cases={len(source_records)}")
print(f"source_conflicts={len(source_conflicts)}")
print(f"missing_files={len(missing_files)}")
print(f"mapping_errors={len(errors)}")
if errors:
    print("error_examples=", errors[:10])
    raise SystemExit(1)

actual["case_id"] = actual.image_relative_path.map(owners)
actual["cohort"] = actual.image_relative_path.str.split("/").str[3]
print(
    actual.groupby("cohort")
    .agg(
        images=("image_relative_path", "size"),
        cases=("case_id", "nunique"),
        age=("age", lambda x: x.ne("").sum()),
        gender=("gender", lambda x: x.ne("").sum()),
        race=("race", lambda x: x.ne("").sum()),
    )
    .to_string()
)
print("gender_values=", actual.gender.value_counts(dropna=False).to_dict())
print("race_values=", actual.race.value_counts(dropna=False).to_dict())
