from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS_PATH = PROJECT_ROOT / "assignments" / "radiologist_groups.json"
REGISTRY_PATH = PROJECT_ROOT / "assignments" / "group_registry.json"
MLLM_SPLIT_PATH = PROJECT_ROOT / "assignments" / "mllm_split.json"
MANIFEST_PATH = PROJECT_ROOT / "manifests" / "images.json"
ANSWERS_PATH = PROJECT_ROOT / "answers" / "sg2162.jsonl"
SEED = "STAR_phase3_remaining_v1"
NEW_GROUP_IDS = tuple(f"group_{chr(code)}" for code in range(ord("f"), ord("t") + 1))
CAPACITIES = {group_id: (565 if group_id == "group_t" else 500) for group_id in NEW_GROUP_IDS}


def stable_key(value: str) -> str:
    return hashlib.sha256(f"{SEED}:{value}".encode("utf-8")).hexdigest()


def latest_complete_answers() -> dict[str, dict]:
    latest = {}
    with ANSWERS_PATH.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("user_id") == "sg2162" and row.get("stage") == "complete":
                latest[row["image_id"]] = row
    return latest


def sampling_lymph_status(record: dict) -> str:
    if record["dataset"] in {"EAY131", "CPTAC"} and record.get("q_lymph_node") == "Yes":
        return "Yes"
    return "No"


def cell(record: dict) -> tuple[str, str, str, str]:
    return (
        record.get("region") or "",
        record["dataset"],
        sampling_lymph_status(record),
        record.get("q2_site") or "",
    )


def allocate(records: list[dict]) -> dict[str, list[dict]]:
    groups = {group_id: [] for group_id in NEW_GROUP_IDS}
    cell_counts = {group_id: defaultdict(int) for group_id in NEW_GROUP_IDS}
    dataset_counts = {group_id: defaultdict(int) for group_id in NEW_GROUP_IDS}
    region_counts = {group_id: defaultdict(int) for group_id in NEW_GROUP_IDS}
    lymph_counts = {group_id: defaultdict(int) for group_id in NEW_GROUP_IDS}
    buckets = defaultdict(list)
    for record in records:
        buckets[cell(record)].append(record)

    ordered_buckets = sorted(buckets.items(), key=lambda pair: (-len(pair[1]), stable_key(repr(pair[0]))))
    for key, bucket in ordered_buckets:
        region, dataset, lymph, _ = key
        for record in sorted(bucket, key=lambda row: stable_key(row["image_id"])):
            candidates = [gid for gid in NEW_GROUP_IDS if len(groups[gid]) < CAPACITIES[gid]]
            if not candidates:
                raise SystemExit("All Phase 3 groups filled before all images were assigned.")
            group_id = min(
                candidates,
                key=lambda gid: (
                    cell_counts[gid][key] / CAPACITIES[gid],
                    dataset_counts[gid][dataset] / CAPACITIES[gid],
                    region_counts[gid][region] / CAPACITIES[gid],
                    lymph_counts[gid][lymph] / CAPACITIES[gid],
                    len(groups[gid]) / CAPACITIES[gid],
                    stable_key(f"{record['image_id']}:{gid}"),
                ),
            )
            groups[group_id].append(record)
            cell_counts[group_id][key] += 1
            dataset_counts[group_id][dataset] += 1
            region_counts[group_id][region] += 1
            lymph_counts[group_id][lymph] += 1

    actual = {gid: len(rows) for gid, rows in groups.items()}
    if actual != CAPACITIES:
        raise SystemExit(f"Phase 3 group sizes are wrong: {actual}")
    for group_id, rows in groups.items():
        rows.sort(key=lambda row: stable_key(f"order:{group_id}:{row['image_id']}"))
    return groups


def main() -> None:
    assignments = json.loads(ASSIGNMENTS_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if any(group_id in assignments["groups"] or group_id in registry["groups"] for group_id in NEW_GROUP_IDS):
        raise SystemExit("Phase 3 groups already exist; refusing to replace frozen assignments.")

    original_group_ids = tuple(assignments["groups"])
    if original_group_ids != ("group_a", "group_b", "group_c", "group_d", "group_e"):
        raise SystemExit(f"Unexpected original groups: {original_group_ids}")
    original_snapshot = json.dumps(
        {gid: assignments["groups"][gid] for gid in original_group_ids},
        sort_keys=True,
    )
    shared_ids = assignments["phase_1_image_ids"]
    if len(shared_ids) != 500 or any(assignments["groups"][gid]["phase_1_image_ids"] != shared_ids for gid in original_group_ids):
        raise SystemExit("Original Phase 1 assignments are inconsistent.")

    mllm_ids = json.loads(MLLM_SPLIT_PATH.read_text(encoding="utf-8"))["image_ids"]
    previously_assigned = {
        image_id
        for gid in original_group_ids
        for image_id in assignments["groups"][gid]["image_ids"]
    }
    remaining_ids = [image_id for image_id in mllm_ids if image_id not in previously_assigned]
    if len(previously_assigned) != 3000 or len(remaining_ids) != 7565:
        raise SystemExit(
            f"Expected 3,000 assigned and 7,565 remaining; got {len(previously_assigned)} and {len(remaining_ids)}."
        )

    manifest = {item["image_id"]: item for item in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))}
    answers = latest_complete_answers()
    records = []
    for image_id in remaining_ids:
        answer = answers.get(image_id)
        item = manifest.get(image_id)
        if answer is None or item is None or answer.get("q4_quality_issue") != "No issue":
            raise SystemExit(f"Invalid remaining Phase 3 image: {image_id}")
        records.append({
            "image_id": image_id,
            "dataset": item["dataset"],
            "region": answer.get("q1_region"),
            "q_lymph_node": answer.get("q_lymph_node"),
            "q2_site": answer.get("q2_site"),
        })

    allocated = allocate(records)
    for index, group_id in enumerate(NEW_GROUP_IDS, start=6):
        phase_3_ids = [record["image_id"] for record in allocated[group_id]]
        assignments["groups"][group_id] = {
            "label": f"Group {chr(ord('A') + index - 1)}",
            "cohort": "phase_3",
            "phase_1_image_count": len(shared_ids),
            "phase_3_image_count": len(phase_3_ids),
            "image_count": len(shared_ids) + len(phase_3_ids),
            "phase_1_image_ids": shared_ids,
            "phase_3_image_ids": phase_3_ids,
            "image_ids": shared_ids + phase_3_ids,
        }
        registry["groups"][group_id] = {
            "label": assignments["groups"][group_id]["label"],
            "image_count": assignments["groups"][group_id]["image_count"],
            "phase_1_image_count": len(shared_ids),
            "phase_3_image_count": len(phase_3_ids),
            "assigned_user_id": None,
            "assigned_at": None,
        }

    if json.dumps({gid: assignments["groups"][gid] for gid in original_group_ids}, sort_keys=True) != original_snapshot:
        raise SystemExit("Original Phase 1/2 assignments changed unexpectedly.")
    new_ids = [image_id for gid in NEW_GROUP_IDS for image_id in assignments["groups"][gid]["phase_3_image_ids"]]
    if len(new_ids) != 7565 or len(set(new_ids)) != 7565 or set(new_ids).intersection(previously_assigned):
        raise SystemExit("Phase 3 images overlap or do not cover the full remaining cohort.")

    generated_at = datetime.now(timezone.utc).isoformat()
    assignments["version"] = 5
    assignments["phase_3"] = {
        "generated_at": generated_at,
        "seed": SEED,
        "group_ids": list(NEW_GROUP_IDS),
        "shared_phase_1_image_count": 500,
        "exclusive_image_count": 7565,
        "group_capacities": CAPACITIES,
        "stratification_fields": ["region", "dataset", "q2_site", "q_lymph_node"],
        "preserved_original_groups": list(original_group_ids),
    }
    registry["version"] = 5
    registry["phase_3_added_at"] = generated_at

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ASSIGNMENTS_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ASSIGNMENTS_PATH, backup_dir / f"radiologist_groups.before_phase3_{stamp}.json")
    shutil.copy2(REGISTRY_PATH, backup_dir / f"group_registry.before_phase3_{stamp}.json")
    for path, data in ((ASSIGNMENTS_PATH, assignments), (REGISTRY_PATH, registry)):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    print(json.dumps({
        "version": 5,
        "preserved_groups": list(original_group_ids),
        "new_groups": {gid: CAPACITIES[gid] for gid in NEW_GROUP_IDS},
        "phase_3_unique_images": len(new_ids),
        "remaining_unassigned_images": 0,
        "backup_stamp": stamp,
    }, indent=2))


if __name__ == "__main__":
    main()
