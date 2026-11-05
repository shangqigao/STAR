#!/usr/bin/env python3
"""Audit identifier joins used by build_r2seg_clinical_data.py."""

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path("/Users/sg2162/Datasets/CancerDatasets/R2Seg")


def stem(path):
    name = Path(path).name
    return name[:-7] if name.endswith(".nii.gz") else Path(name).stem


out = pd.read_csv(ROOT / "clinical_data.csv")
print("OUTPUT", len(out), out.image_relative_path.nunique(), out.image_relative_path.duplicated().sum())

for dataset_json in sorted(ROOT.glob("*/dataset.json")):
    dataset = dataset_json.parent.name
    data = json.loads(dataset_json.read_text())
    paths = [f"{dataset}/{item['image']}" for split in ("train", "test") for item in data.get(split, [])]
    got = set(out.loc[out.image_relative_path.str.startswith(dataset + "/"), "image_relative_path"])
    print(
        dataset,
        "manifest", len(paths),
        "unique", len(set(paths)),
        "csv", len(got),
        "missing", len(set(paths) - got),
        "extra", len(got - set(paths)),
        "files_missing", sum(not (ROOT / path).exists() for path in paths),
    )

# Bladder: Center name plus integer image number.
bladder_source = {}
xls = pd.ExcelFile(ROOT / "Clinical_data/Bladder_Tumor_00.xlsx")
for center in xls.sheet_names:
    df = pd.read_excel(xls, center)
    col = "image" if "image" in df.columns else "image_name"
    for _, row in df.iterrows():
        number = int(str(row[col]).replace(".nii.gz", ""))
        bladder_source[f"{center}_{number}"] = row

def bladder_key(value):
    match = re.fullmatch(r"(Center\d+)_(\d+)", value)
    return f"{match.group(1)}_{int(match.group(2))}" if match else value

bladder_images = [stem(x) for x in out.loc[out.image_relative_path.str.startswith("Bladder_Tumor_00/"), "image_relative_path"]]
print(
    "BLADDER", "images", len(bladder_images),
    "mapped", sum(bladder_key(x) in bladder_source for x in bladder_images),
    "source_keys", len(bladder_source),
    "unused_source", len(set(bladder_source) - {bladder_key(x) for x in bladder_images}),
)

# Breast: image filename is patient_id plus a sequence suffix.
breast = pd.read_excel(ROOT / "Clinical_data/Breast_Tumor_00.xlsx", sheet_name="dataset_info")
breast_ids = breast.patient_id.astype(str).tolist()
breast_images = [stem(x) for x in out.loc[out.image_relative_path.str.startswith("Breast_Tumor_00/"), "image_relative_path"]]
candidate_sets = [[key for key in breast_ids if image == key or image.startswith(key + "_")] for image in breast_images]
print(
    "BREAST", "source", len(breast_ids), "source_unique", len(set(breast_ids)),
    "images", len(breast_images),
    "candidate_counts", pd.Series([len(x) for x in candidate_sets]).value_counts().sort_index().to_dict(),
    "unused_source", len(set(breast_ids) - {x[0] for x in candidate_sets if len(x) == 1}),
)

# Kidney: exact case ID.
kdata = json.loads((ROOT / "Clinical_data/Kidney_Tumor_00.json").read_text())
kidney_ids = {str(x["case_id"]) for x in kdata}
kidney_images = {stem(x) for x in out.loc[out.image_relative_path.str.startswith("Kidney_Tumor_00/"), "image_relative_path"]}
print("KIDNEY", "source", len(kdata), "source_unique", len(kidney_ids), "images", len(kidney_images), "mapped", len(kidney_images & kidney_ids), "unused_source", len(kidney_ids - kidney_images))

# Lung: image filename is PatientID plus literal _CT.
lung = pd.read_csv(ROOT / "Clinical_data/Lung_Tumor_01.csv")
lung_ids = set(lung.PatientID.astype(str))
lung_images = {stem(x).removesuffix("_CT") for x in out.loc[out.image_relative_path.str.startswith("Lung_Tumor_01/"), "image_relative_path"]}
print("LUNG", "source", len(lung), "source_unique", len(lung_ids), "images", len(lung_images), "mapped", len(lung_images & lung_ids), "unused_source", sorted(lung_ids - lung_images))

# Re-derive all populated values and compare against the CSV.
import sys
sys.path.insert(0, str(Path(__file__).parent))
from build_r2seg_clinical_data import bladder_map, breast_map, kidney_map, lung_map

maps = {
    "Bladder_Tumor_00": bladder_map(ROOT / "Clinical_data"),
    "Breast_Tumor_00": breast_map(ROOT / "Clinical_data"),
    "Kidney_Tumor_00": kidney_map(ROOT / "Clinical_data"),
    "Lung_Tumor_01": lung_map(ROOT / "Clinical_data"),
}
errors = []
for _, row in out.iterrows():
    dataset = row.image_relative_path.split("/", 1)[0]
    key = stem(row.image_relative_path)
    record = None
    if dataset == "Bladder_Tumor_00":
        record = maps[dataset].get(bladder_key(key))
    elif dataset == "Breast_Tumor_00":
        candidates = [x for x in maps[dataset] if key == x or key.startswith(x + "_")]
        record = maps[dataset][candidates[0]] if len(candidates) == 1 else None
    elif dataset == "Kidney_Tumor_00":
        record = maps[dataset].get(key)
    elif dataset == "Lung_Tumor_01":
        record = maps[dataset].get(key.removesuffix("_CT"))
    expected = record or {"age": "", "gender": "", "race": ""}
    for col in ("age", "gender", "race"):
        actual = "" if pd.isna(row[col]) else row[col]
        wanted = expected[col]
        if str(actual) != str(wanted) and not (col == "age" and float(actual) == float(wanted)):
            errors.append((row.image_relative_path, col, actual, wanted))
print("VALUE_COMPARISON", "errors", len(errors), "examples", errors[:5])
