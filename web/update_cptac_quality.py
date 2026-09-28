from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "manifests" / "images.json"
ANSWERS_PATH = PROJECT_ROOT / "answers" / "sg2162.jsonl"
DEFAULT_CPTAC_DIR = Path("/Users/sg2162/Datasets/CancerDatasets/CPTAC")


def latest_complete_answers() -> dict[str, dict]:
    latest = {}
    with ANSWERS_PATH.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("user_id") == "sg2162" and row.get("stage") == "complete":
                latest[row["image_id"]] = row
    return latest


def segmentation_uid_from_preview(path: str) -> str:
    return Path(path).name.split("-site_in_", 1)[0]


def segmentation_uid_from_label(path: str) -> str:
    return Path(path).parent.name


def prefixed(path: str, root: str) -> str:
    path = path.replace("\\", "/")
    prefix = root.rstrip("/") + "/"
    return path if path.startswith(prefix) else prefix + path.lstrip("/")


def backup(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    destination = path.with_name(f"{path.stem}.before_quality_{stamp}{path.suffix}")
    shutil.copy2(path, destination)
    return destination


def write_json(path: Path, data) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach STAR Q4 quality labels to the CPTAC index.")
    parser.add_argument("--cptac-dir", type=Path, default=DEFAULT_CPTAC_DIR)
    args = parser.parse_args()
    cptac_dir = args.cptac_dir.expanduser().resolve()
    index_path = cptac_dir / "output_index.json"
    if not index_path.exists():
        moved_index_path = cptac_dir / "Radiology_NIFTI" / "output_index.json"
        if moved_index_path.exists():
            index_path = moved_index_path
    dataset_path = cptac_dir / "dataset.json"

    index = json.loads(index_path.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    answers = latest_complete_answers()
    uid_to_manifest_item = {
        segmentation_uid_from_preview(item["image_path"]): item
        for item in manifest
        if item.get("dataset") == "CPTAC"
    }

    quality_counts = Counter()
    matched = 0
    unassessed = 0
    for entries in index.values():
        for entry in entries:
            uid = segmentation_uid_from_label(entry["label"])
            manifest_item = uid_to_manifest_item.get(uid)
            image_id = manifest_item["image_id"] if manifest_item else None
            answer = answers.get(image_id, {}) if image_id else {}
            site = manifest_item.get("gt_site", "").strip().lower() if manifest_item else None
            quality = answer.get("q4_quality_issue")
            entry.pop("site", None)
            entry.pop("quality", None)
            entry["site"] = site or None
            entry["quality"] = quality
            if quality is None:
                unassessed += 1
            else:
                matched += 1
                quality_counts[quality] += 1

    if matched != 870 or unassessed != 35:
        raise SystemExit(f"Unexpected mapping counts: matched={matched}, unassessed={unassessed}")

    cases = {
        case_id: [
            {
                "image": prefixed(entry["image"], "Radiology_NIFTI"),
                "label": prefixed(entry["label"], "Radiology_NIFTI_Post"),
                "site": entry["site"],
                "quality": entry["quality"],
            }
            for entry in entries
        ]
        for case_id, entries in index.items()
    }
    generated_at = datetime.now(timezone.utc).isoformat()
    dataset = {
        "site": "multi-site",
        "description": "CPTAC multi-site tumor segmentation with STAR image-quality annotations",
        "DOI": {
            "CPTAC-CCRCC": "10.7937/K9/TCIA.2018.OBLAMN27",
            "CPTAC-PDA": "10.7937/K9/TCIA.2018.SC20FO18",
            "CPTAC-UCEC": "10.7937/K9/TCIA.2018.3R3JUISW",
        },
        "licence": "Creative Commons Attribution 3.0 Unported License",
        "release": "STAR quality annotations 19/09/2026",
        "tensorImageSize": "3D",
        "modality": {"1": "CT", "2": "MR"},
        "labels": {"0": "background", "1": "tumor"},
        "quality_annotation": {
            "annotator": "sg2162",
            "question": "Does this image contain any visual issue that could make anatomical interpretation unreliable?",
            "source": str(ANSWERS_PATH),
            "source_sha256": hashlib.sha256(ANSWERS_PATH.read_bytes()).hexdigest(),
            "generated_at": generated_at,
            "assessed": matched,
            "unassessed": unassessed,
            "distribution": dict(quality_counts),
            "unassessed_value": None,
        },
        "site_annotation": {
            "source": "manifests/images.json gt_site",
            "format": "lowercase detailed anatomical site",
            "unassessed_value": None,
        },
        "cases": cases,
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    index_backup = backup(index_path, stamp)
    dataset_backup = backup(dataset_path, stamp)
    write_json(index_path, index)
    write_json(dataset_path, dataset)
    print(json.dumps({
        "output_index": str(index_path),
        "dataset": str(dataset_path),
        "output_index_backup": str(index_backup) if index_backup else None,
        "dataset_backup": str(dataset_backup) if dataset_backup else None,
        "cases": len(cases),
        "records": matched + unassessed,
        "assessed": matched,
        "unassessed": unassessed,
        "quality_distribution": dict(quality_counts),
    }, indent=2))


if __name__ == "__main__":
    main()
