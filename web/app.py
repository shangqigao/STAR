from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "manifests" / "images.json"
QUESTIONS_PATH = PROJECT_ROOT / "questions" / "q2_sites.json"
ANSWERS_DIR = PROJECT_ROOT / "answers"
USERS_DIR = PROJECT_ROOT / "users"
STATIC_DIR = PROJECT_ROOT / "web" / "static"
TEMPLATE_PATH = PROJECT_ROOT / "web" / "templates" / "index.html"
ASSIGNMENTS_DIR = PROJECT_ROOT / "assignments"
MLLM_SPLIT_PATH = ASSIGNMENTS_DIR / "mllm_split.json"
RADIOLOGIST_GROUPS_PATH = ASSIGNMENTS_DIR / "radiologist_groups.json"
GROUP_REGISTRY_PATH = ASSIGNMENTS_DIR / "group_registry.json"

DEFAULT_DATA_DIR = Path("/Users/sg2162/Datasets/CancerDatasets/STAR")
KNOWN_DATASETS = ("CPTAC", "EAY131", "R2Seg")
DATA_DIR = DEFAULT_DATA_DIR
IMAGE_DIRS = []

REGIONS = ["Chest", "Abdomen", "Pelvis", "Others"]
LYMPH_NODE_CHOICES = ["Yes", "No", "Unsure"]
QUALITY_ISSUES = [
    "No issue",
    "Multiple acquisitions visible",
    "Slice misalignment or discontinuity",
    "Limited field of view / anatomical context",
    "Red overlay appears mismatched with tumor",
    "Other issue",
    "Unsure",
]
STAGES = ["q1", "q_lymph_node", "q2", "q4", "complete"]
MANIFEST_ORDER_SEED = "STAR_v1_deterministic_shuffle"
MAX_CURVE_POINTS = 300
GENERAL_USER_TYPES = {"human", "mllm"}
RADIOLOGIST_GROUPS = tuple(f"group_{chr(code)}" for code in range(ord("a"), ord("t") + 1))
SPECIALIST_GROUPS = {"radiologist": RADIOLOGIST_GROUPS}
VALID_USER_TYPES = GENERAL_USER_TYPES | set(SPECIALIST_GROUPS)
ASSIGNMENT_LOCK = threading.Lock()


class NoAvailableGroupError(ValueError):
    pass


def image_dirs_for_data_dir(data_dir: Path) -> list[tuple[str, Path]]:
    data_dir = data_dir.expanduser().resolve()
    dirs = []
    for dataset in KNOWN_DATASETS:
        image_dir = data_dir / dataset / "vis_check"
        dirs.append((dataset, image_dir))
    return dirs


def configure_data_dir(data_dir: str | Path) -> None:
    global DATA_DIR, IMAGE_DIRS
    DATA_DIR = Path(data_dir).expanduser().resolve()
    IMAGE_DIRS = image_dirs_for_data_dir(DATA_DIR)


configure_data_dir(DEFAULT_DATA_DIR)


def path_under(path: Path, root: Path) -> Path | None:
    try:
        return path.absolute().relative_to(root.absolute())
    except ValueError:
        return None


def remap_manifest_image_paths(manifest: list[dict]) -> list[dict]:
    if DATA_DIR == DEFAULT_DATA_DIR:
        return manifest

    remapped = []
    for item in manifest:
        updated = dict(item)
        image_path = Path(str(item.get("image_path", ""))).expanduser()
        source_root = Path(item.get("source_data_dir") or DEFAULT_DATA_DIR).expanduser()
        relative_path = path_under(image_path, source_root)

        if relative_path is None:
            dataset = item.get("dataset")
            if dataset:
                relative_path = Path(dataset) / "vis_check" / image_path.name

        if relative_path is not None:
            updated["image_path"] = str(DATA_DIR / relative_path)
        remapped.append(updated)
    return remapped


def canonical_site(value: str | None) -> str:
    value = (value or "").upper()
    value = value.replace("-", " ")
    value = value.replace("/", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(LEFT|RIGHT)\s+", "", value)
    value = re.sub(r"\s+\d+$", "", value)

    rules = [
        ("AXILARY", "Axillary lymph node"),
        ("MEDIASTINAL LYMPH NODE", "Mediastinal lymph node"),
        ("MEDIASTINAL", "Mediastinal lymph node"),
        ("CARDIOPHRENIC ANGLE", "Cardiophrenic lymph node"),
        ("CARDIOPHRENIC", "Cardiophrenic lymph node"),
        ("SUBCARINAL", "Subcarinal lymph node"),
        ("SUPRACLAVICULAR", "Supraclavicular lymph node"),
        ("INFRACLAVICULAR", "Infraclavicular lymph node"),
        ("INTERNAL MAMMARY", "Internal mammary lymph node"),
        ("PARA TRACHEAL", "Paratracheal lymph node"),
        ("PARATRACHEAL", "Paratracheal lymph node"),
        ("PRETRACHEAL", "Paratracheal lymph node"),
        ("PERICARDIAC", "Pericardial lymph node"),
        ("PERICARDIAL LYMPH", "Pericardial lymph node"),
        ("PERICARDIUM", "Heart / pericardium"),
        ("THYMUS", "Thymus"),
        ("THYROID", "Thyroid"),
        ("CERVICAL LYMPH", "Cervical lymph node"),
        ("NECK LYMPH", "Cervical lymph node"),
        ("NECK", "Neck"),
        ("HILAR", "Hilar lymph node"),
        ("HILUM", "Hilar lymph node"),
        ("AXILLARY", "Axillary lymph node"),
        ("AXILLA", "Axillary lymph node"),
        ("PLEURA", "Pleura"),
        ("CHEST WALL", "Chest wall"),
        ("CHEST", "Chest wall"),
        ("DIAPHRAGMATIC LYMPH", "Diaphragmatic lymph node"),
        ("DIAPHRAGM", "Diaphragm"),
        ("BREAST", "Breast"),
        ("PARAESOPHAGEAL", "Paraesophageal lymph node"),
        ("PARAOESOPHAGEAL", "Paraesophageal lymph node"),
        ("ESOPHAGEAL LYMPH", "Paraesophageal lymph node"),
        ("GASTROESOPHAGEAL JUNCTION", "Gastroesophageal junction"),
        ("GASTROESOPHAGEAL LYMPH", "Gastroesophageal lymph node"),
        ("ESOPHAGUS", "Esophagus"),
        ("LUNG", "Lung"),
        ("PANCREATIC DUCT", "Pancreatic duct"),
        ("PANCREATIC LYMPH", "Peripancreatic lymph node"),
        ("PERIPANCREATIC", "Peripancreatic lymph node"),
        ("PANCREAS", "Pancreas"),
        ("GALLBLADDER", "Gallbladder / biliary tract"),
        ("BILE DUCT", "Gallbladder / biliary tract"),
        ("BILIARY", "Gallbladder / biliary tract"),
        ("LIVER", "Liver"),
        ("HEPATIC", "Hepatic lymph node"),
        ("KIDNEY", "Kidney"),
        ("ADRENAL", "Adrenal"),
        ("SPLEEN", "Spleen"),
        ("STOMACH", "Stomach"),
        ("COLON", "Colon"),
        ("SIGMOID", "Colon"),
        ("SMALL INTESTINE", "Small bowel"),
        ("SMALL BOWEL", "Small bowel"),
        ("BOWEL", "Small bowel"),
        ("DUODENUM", "Small bowel"),
        ("CELIAC", "Celiac lymph node"),
        ("PERIGASTRIC", "Perigastric lymph node"),
        ("PORTA HEPATIS", "Porta hepatis lymph node"),
        ("PORTAHEPATIS", "Porta hepatis lymph node"),
        ("PORTACAVAL", "Portacaval lymph node"),
        ("PARACAVAL", "Paracaval lymph node"),
        ("AORTOCAVAL", "Aortocaval lymph node"),
        ("PARA AORTIC", "Para-aortic lymph node"),
        ("PARAAORTIC", "Para-aortic lymph node"),
        ("AORTIC LYMPH", "Para-aortic lymph node"),
        ("PERIAORTIC", "Para-aortic lymph node"),
        ("MESENTRIC", "Mesenteric lymph node"),
        ("MESENTERIC", "Mesenteric lymph node"),
        ("MESENTERY", "Mesentery"),
        ("RETROCRURAL", "Retrocrural lymph node"),
        ("RETROCAVAL", "Retrocaval lymph node"),
        ("RETROPERITONEAL LYMPH", "Retroperitoneal lymph node"),
        ("RETROPERITONEUM", "Retroperitoneum"),
        ("RETROPERITONEAL", "Retroperitoneum"),
        ("INFERIOR VENA CAVA", "Inferior vena cava"),
        ("RENAL VEIN", "Renal vein"),
        ("URETER", "Ureter"),
        ("RENAL", "Kidney"),
        ("PSOAS", "Psoas"),
        ("PERIPORTAL", "Periportal lymph node"),
        ("ABDOMINAL WALL", "Abdominal wall"),
        ("ABDOMINAL LYMPH", "Abdominal lymph node"),
        ("ABDOMEN", "Abdomen"),
        ("OMENTUM", "Omentum"),
        ("OMENTAL", "Omentum"),
        ("PERITONEUM", "Peritoneum"),
        ("PERITONEAL", "Peritoneum"),
        ("PELVIC LYMPH", "Pelvic lymph node"),
        ("PELVIC MASS", "Pelvis"),
        ("PELVIC", "Pelvis"),
        ("PELVIS", "Pelvis"),
        ("ILIAC LYMPH", "Iliac lymph node"),
        ("ILIAC CHAIN", "Iliac lymph node"),
        ("EXTERNAL ILIAC", "Iliac lymph node"),
        ("INTERNAL ILIAC", "Iliac lymph node"),
        ("INGUINAL", "Inguinal lymph node"),
        ("UTERUS", "Uterus"),
        ("CERVIX", "Cervix"),
        ("OVARY", "Ovary / adnexa"),
        ("ADNEXA", "Ovary / adnexa"),
        ("BLADDER", "Bladder"),
        ("PROSTATE", "Prostate"),
        ("PERIRECTAL", "Perirectal lymph node"),
        ("PARARECTAL", "Perirectal lymph node"),
        ("RECTUM", "Rectum"),
        ("VAGINA", "Vagina"),
        ("VULVA", "Vulva"),
        ("ANUS", "Anus"),
        ("GLUTEAL", "Gluteal"),
        ("PUBIC SYMPHYSIS", "Pubic bone"),
        ("PUBIC RAMUS", "Pubic bone"),
        ("PUBIC BONE", "Pubic bone"),
        ("ISCHIUM", "Pelvic bone"),
        ("ILIUM", "Pelvic bone"),
        ("ILIAC BONE", "Pelvic bone"),
        ("ILIAC CREST", "Pelvic bone"),
        ("SACROILIAC", "Sacrum"),
        ("SACRUM", "Sacrum"),
        ("BONE", "Bone"),
        ("RIB", "Bone"),
        ("SPINE", "Bone"),
        ("VERTEBRAL", "Bone"),
        ("FEMUR", "Bone"),
        ("SCAPULA", "Bone"),
        ("HUMERUS", "Bone"),
        ("STERNUM", "Bone"),
        ("SHOULDER", "Bone"),
        ("HIP", "Bone"),
        ("SOFT TISSUE", "Soft tissue"),
        ("SUBCUTANEOUS", "Soft tissue"),
        ("SUBPECTORAL", "Soft tissue"),
        ("ARM", "Soft tissue"),
        ("HAND", "Soft tissue"),
        ("LEG", "Soft tissue"),
        ("THIGH", "Soft tissue"),
        ("LYMPH NODES OF BODY AS A WHOLE", "Lymph node"),
        ("LYMPH NODE", "Lymph node"),
    ]
    for needle, site in rules:
        if needle in value:
            return site
    return value.title() if value else ""


def region_for_site(value: str | None) -> str | None:
    site = canonical_site(value)
    chest = {
        "Lung",
        "Pleura",
        "Mediastinum",
        "Mediastinal lymph node",
        "Hilar lymph node",
        "Axillary lymph node",
        "Chest wall",
        "Breast",
        "Esophagus",
        "Heart / pericardium",
        "Cardiophrenic lymph node",
        "Subcarinal lymph node",
        "Supraclavicular lymph node",
        "Infraclavicular lymph node",
        "Internal mammary lymph node",
        "Paratracheal lymph node",
        "Pericardial lymph node",
        "Thymus",
        "Thyroid",
        "Cervical lymph node",
        "Neck",
        "Paraesophageal lymph node",
        "Diaphragm",
        "Diaphragmatic lymph node",
    }
    abdomen = {
        "Abdomen",
        "Liver",
        "Pancreas",
        "Pancreatic duct",
        "Peripancreatic lymph node",
        "Kidney",
        "Adrenal",
        "Spleen",
        "Stomach",
        "Colon",
        "Small bowel",
        "Gallbladder / biliary tract",
        "Peritoneum",
        "Omentum",
        "Abdominal wall",
        "Retroperitoneum",
        "Retroperitoneal lymph node",
        "Para-aortic lymph node",
        "Aortocaval lymph node",
        "Paracaval lymph node",
        "Portacaval lymph node",
        "Celiac lymph node",
        "Mesenteric lymph node",
        "Mesentery",
        "Hepatic lymph node",
        "Perigastric lymph node",
        "Porta hepatis lymph node",
        "Retrocrural lymph node",
        "Retrocaval lymph node",
        "Inferior vena cava",
        "Renal vein",
        "Ureter",
        "Psoas",
        "Periportal lymph node",
        "Abdominal lymph node",
        "Gastroesophageal junction",
        "Gastroesophageal lymph node",
        "Lymph node",
    }
    pelvis = {
        "Pelvis",
        "Pelvic lymph node",
        "Iliac lymph node",
        "Inguinal lymph node",
        "Uterus",
        "Cervix",
        "Ovary / adnexa",
        "Bladder",
        "Prostate",
        "Rectum",
        "Perirectal lymph node",
        "Vagina",
        "Vulva",
        "Anus",
        "Gluteal",
        "Pubic bone",
        "Pelvic bone",
        "Sacrum",
    }
    if site in chest:
        return "Chest"
    if site in abdomen:
        return "Abdomen"
    if site in pelvis:
        return "Pelvis"
    return None


def q1_region_for_site(value: str | None) -> str:
    return region_for_site(value) or "Others"


def is_lymph_node_site(value: str | None) -> bool:
    return "lymph node" in canonical_site(value).lower()


def q2_choices_for_region(region: str | None) -> list[str]:
    q2_sites = load_q2_sites()
    if region != "Others":
        return q2_sites.get(region, [])
    return ["Lymph node", "Bone", "Soft tissue", "Other", "Unsure"]


def filtered_q2_choices(region: str | None, lymph_node_answer: str | None) -> list[str]:
    choices = q2_choices_for_region(region)
    if region == "Others":
        return choices

    terminal = [choice for choice in choices if choice in {"Other", "Unsure"}]

    if lymph_node_answer == "Yes":
        filtered = [choice for choice in choices if is_lymph_node_site(choice)]
        return filtered + [choice for choice in terminal if choice not in filtered]

    if lymph_node_answer == "No":
        filtered = [
            choice for choice in choices
            if not is_lymph_node_site(choice) and choice not in {"Other", "Unsure"}
        ]
        return filtered + terminal

    return choices


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_user_id(user_id: str) -> str:
    user_id = user_id.strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", user_id)
    return safe.strip("._-") or "anonymous"


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def append_jsonl(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def normalize_tracking_id(value: str) -> str:
    value = value.strip()
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    value = value.replace("LT ", "LEFT ").replace("RT ", "RIGHT ")
    value = value.replace("LT-", "LEFT ").replace("RT-", "RIGHT ")
    value = value.replace("-", " ")
    value = re.sub(r"\s+\d+$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    replacements = {
        "PARAAORTIC LYMP": "PARA AORTIC LYMPH NODE",
        "MEDIASTINAL LYM": "MEDIASTINAL LYMPH NODE",
        "RT LUNG MET": "RIGHT LUNG",
        "LT LUNG MET": "LEFT LUNG",
    }
    upper = value.upper()
    value = replacements.get(upper, value)
    return value.title()


def tracking_from_png(dataset: str, path: Path) -> str:
    stem = path.stem
    if "-site_in_" in stem:
        return stem.rsplit("-site_in_", 1)[1]
    if "-mask_" in stem:
        return stem.split("-mask_", 1)[1]
    if "-" in stem:
        return stem.split("-", 1)[1]
    return stem


def manifest_shuffle_key(item: dict) -> str:
    key = f"{MANIFEST_ORDER_SEED}:{item['image_id']}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_manifest() -> list[dict]:
    items = []
    for dataset, image_dir in IMAGE_DIRS:
        if not image_dir.exists():
            continue
        for path in sorted(image_dir.glob("*.png")):
            raw_tracking_id = tracking_from_png(dataset, path)
            digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
            items.append(
                {
                    "image_id": f"{dataset.lower()}_{digest}",
                    "dataset": dataset,
                    "image_path": str(path),
                    "raw_tracking_id": raw_tracking_id,
                    "gt_site": normalize_tracking_id(raw_tracking_id),
                    "order_seed": MANIFEST_ORDER_SEED,
                    "source_data_dir": str(DATA_DIR),
                }
            )
    items.sort(key=manifest_shuffle_key)
    for index, item in enumerate(items):
        item["order_index"] = index
    write_json(MANIFEST_PATH, items)
    return items


def load_manifest() -> list[dict]:
    manifest = read_json(MANIFEST_PATH, None)
    if manifest is None:
        manifest = build_manifest()
    return remap_manifest_image_paths(manifest)


def load_q2_sites() -> dict:
    return read_json(QUESTIONS_PATH, {})


def load_radiologist_groups() -> dict:
    assignments = read_json(RADIOLOGIST_GROUPS_PATH, None)
    if assignments is None:
        raise ValueError(
            "Radiologist assignments have not been generated. "
            "Run python3 web/generate_radiologist_groups.py first."
        )
    return assignments


def load_mllm_split() -> dict:
    split = read_json(MLLM_SPLIT_PATH, None)
    if split is None:
        raise ValueError(
            "MLLM benchmark split has not been generated. "
            "Run python3 web/generate_mllm_split.py first."
        )
    return split


def load_group_registry() -> dict:
    assignments = load_radiologist_groups()
    registry = read_json(GROUP_REGISTRY_PATH, None)
    if registry is None:
        registry = {
            "version": assignments.get("version", 1),
            "groups": {
                group_id: {
                    "label": group["label"],
                    "image_count": group["image_count"],
                    "assigned_user_id": None,
                    "assigned_at": None,
                }
                for group_id, group in assignments["groups"].items()
            },
        }
    return registry


def assignment_summary() -> dict:
    registry = load_group_registry()
    roles = {}
    for user_type, group_ids in SPECIALIST_GROUPS.items():
        available = [
            group_id for group_id in group_ids
            if not registry["groups"][group_id].get("assigned_user_id")
        ]
        roles[user_type] = {
            "available": len(available),
            "total": len(group_ids),
            "available_group_ids": available,
        }
    return {"version": registry.get("version"), "roles": roles}


def claim_specialist_group(user_id: str, user_type: str, registry: dict) -> str:
    for group_id in SPECIALIST_GROUPS[user_type]:
        group = registry["groups"].get(group_id)
        if group is not None and not group.get("assigned_user_id"):
            group["assigned_user_id"] = user_id
            group["assigned_at"] = utc_now()
            return group_id
    raise NoAvailableGroupError("All radiologist image groups have already been assigned.")


def manifest_for_user(user: dict, manifest: list[dict]) -> list[dict]:
    user_type = user.get("user_type", "human")
    if user_type == "human":
        return manifest
    if user_type == "mllm":
        image_ids = load_mllm_split().get("image_ids", [])
        lookup = image_lookup(manifest)
        missing = [image_id for image_id in image_ids if image_id not in lookup]
        if missing:
            raise ValueError(f"MLLM split contains {len(missing)} images missing from the manifest.")
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("MLLM split contains duplicate image IDs.")
        return [lookup[image_id] for image_id in image_ids]
    if user_type not in SPECIALIST_GROUPS:
        raise ValueError(f"Unsupported user type: {user_type}")
    group_id = user.get("assignment_group")
    if not group_id:
        raise ValueError("Specialist user has no assignment group.")
    group = load_radiologist_groups()["groups"].get(group_id)
    if group is None or group_id not in SPECIALIST_GROUPS[user_type]:
        raise ValueError("Specialist user has an invalid assignment group.")
    phase = radiologist_phase_status(user, group)
    lookup = image_lookup(manifest)
    missing = [image_id for image_id in phase["image_ids"] if image_id not in lookup]
    if missing:
        raise ValueError(f"Assignment contains {len(missing)} images missing from the manifest.")
    return [lookup[image_id] for image_id in phase["image_ids"]]


def radiologist_phase_status(user: dict, group: dict | None = None) -> dict:
    if group is None:
        group_id = user.get("assignment_group")
        group = load_radiologist_groups()["groups"].get(group_id)
        if group is None:
            raise ValueError("Radiologist user has an invalid assignment group.")
    completed = set(user.get("completed_image_ids", []))
    phase_1_ids = group["phase_1_image_ids"]
    followup_phase = "phase_2" if "phase_2_image_ids" in group else "phase_3"
    followup_ids = group[f"{followup_phase}_image_ids"]
    phase_1_completed = len(completed.intersection(phase_1_ids))
    followup_completed = len(completed.intersection(followup_ids))
    if phase_1_completed < len(phase_1_ids):
        phase = "phase_1"
        phase_ids = phase_1_ids
        phase_completed = phase_1_completed
    else:
        phase = followup_phase
        phase_ids = followup_ids
        phase_completed = followup_completed
    return {
        "study_phase": phase,
        "image_ids": phase_ids,
        "phase_completed": phase_completed,
        "phase_total": len(phase_ids),
        "overall_completed": phase_1_completed + followup_completed,
        "overall_total": len(phase_1_ids) + len(followup_ids),
        "done": phase_1_completed == len(phase_1_ids) and followup_completed == len(followup_ids),
    }


def assignment_metadata(user: dict, image_id: str) -> dict:
    if user.get("user_type") != "radiologist":
        return {}
    group_id = user["assignment_group"]
    group = load_radiologist_groups()["groups"][group_id]
    if image_id in set(group["phase_1_image_ids"]):
        return {"study_phase": "phase_1", "assignment_group": group_id, "assignment_kind": "shared"}
    for phase in ("phase_2", "phase_3"):
        if image_id in set(group.get(f"{phase}_image_ids", [])):
            return {"study_phase": phase, "assignment_group": group_id, "assignment_kind": "exclusive"}
    raise ValueError("Image is outside this radiologist assignment.")


def user_path(user_id: str) -> Path:
    return USERS_DIR / f"{slug_user_id(user_id)}.json"


def answer_path(user_id: str) -> Path:
    return ANSWERS_DIR / f"{slug_user_id(user_id)}.jsonl"


def load_user(user_id: str) -> dict | None:
    return read_json(user_path(user_id), None)


def save_user(user: dict) -> None:
    write_json(user_path(user["user_id"]), user)


def list_users() -> list[dict]:
    users = []
    if USERS_DIR.exists():
        for path in sorted(USERS_DIR.glob("*.json")):
            try:
                users.append(read_json(path, {}))
            except json.JSONDecodeError:
                continue
    return users


def image_lookup(manifest: list[dict]) -> dict[str, dict]:
    return {item["image_id"]: item for item in manifest}


def answer_events(user_id: str) -> list[dict]:
    path = answer_path(user_id)
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def user_stats(user_id: str) -> dict:
    q1_correct = 0
    q_lymph_node_correct = 0
    q2_correct = 0
    completed = 0
    q1_curve = []
    q_lymph_node_curve = []
    q2_curve = []

    for event in answer_events(user_id):
        if event.get("stage") != "complete":
            continue
        gt_site = event.get("gt_site")
        gt_region = q1_region_for_site(gt_site)
        gt_q2_site = canonical_site(gt_site)
        gt_lymph_node = is_lymph_node_site(gt_site)
        q1_answer = event.get("q1_region")
        q_lymph_node_answer = event.get("q_lymph_node")
        q2_answer = event.get("q2_site")

        completed += 1
        if q1_answer == gt_region:
            q1_correct += 1
        if q_lymph_node_answer is None and q2_answer:
            q_lymph_node_answer = "Yes" if is_lymph_node_site(q2_answer) else "No"
        if q_lymph_node_answer != "Unsure":
            q_lymph_node_correct += int({
                "Yes": True,
                "No": False,
            }.get(q_lymph_node_answer) == gt_lymph_node)
        if canonical_site(q2_answer) == gt_q2_site:
            q2_correct += 1

        q1_curve.append(round(q1_correct / completed, 4))
        q_lymph_node_curve.append(round(q_lymph_node_correct / completed, 4))
        q2_curve.append(round(q2_correct / completed, 4))

    return {
        "completed": completed,
        "q1_correct": q1_correct,
        "q_lymph_node_correct": q_lymph_node_correct,
        "q2_correct": q2_correct,
        "q1_accuracy": round(q1_correct / completed, 4) if completed else None,
        "q_lymph_node_accuracy": round(q_lymph_node_correct / completed, 4) if completed else None,
        "q2_accuracy": round(q2_correct / completed, 4) if completed else None,
        "q1_curve": downsample_curve(q1_curve),
        "q_lymph_node_curve": downsample_curve(q_lymph_node_curve),
        "q2_curve": downsample_curve(q2_curve),
    }


def downsample_curve(values: list[float]) -> list[float]:
    if len(values) <= MAX_CURVE_POINTS:
        return values
    sampled = []
    last_index = len(values) - 1
    for i in range(MAX_CURVE_POINTS):
        index = round(i * last_index / (MAX_CURVE_POINTS - 1))
        sampled.append(values[index])
    return sampled


def first_uncompleted_image(manifest: list[dict], completed: list[str]) -> str | None:
    completed_set = set(completed)
    for item in manifest:
        if item["image_id"] not in completed_set:
            return item["image_id"]
    return None


def ensure_current_task(user: dict, manifest: list[dict]) -> dict:
    manifest = manifest_for_user(user, manifest)
    completed = user.setdefault("completed_image_ids", [])
    eligible_ids = {item["image_id"] for item in manifest}
    if user.get("stage") == "q3":
        user["stage"] = "q4" if user.get("current_answers", {}).get("q2_site") else "q1"
    if user.get("stage") == "q2" and not user.get("current_answers", {}).get("q_lymph_node"):
        user["stage"] = "q_lymph_node"
    current_id = user.get("current_image_id")
    if current_id and (current_id in set(completed) or current_id not in eligible_ids):
        user["current_image_id"] = None
        user["stage"] = "q1"
        user["current_answers"] = {}

    if not user.get("current_image_id"):
        user["current_image_id"] = first_uncompleted_image(manifest, completed)
        user["stage"] = "q1"
        user["current_answers"] = {}
        save_user(user)
    return user


def public_task(user: dict, manifest: list[dict]) -> dict:
    user = ensure_current_task(user, manifest)
    manifest = manifest_for_user(user, manifest)
    lookup = image_lookup(manifest)
    current_id = user.get("current_image_id")
    phase = radiologist_phase_status(user) if user.get("user_type") == "radiologist" else None
    if phase:
        completed = phase["phase_completed"]
        total = phase["phase_total"]
        overall_completed = phase["overall_completed"]
        overall_total = phase["overall_total"]
    else:
        eligible_ids = set(lookup)
        completed = len(eligible_ids.intersection(user.get("completed_image_ids", [])))
        total = len(manifest)
        overall_completed = completed
        overall_total = total
    if not current_id:
        payload = {
            "done": True,
            "completed": completed,
            "total": total,
            "overall_completed": overall_completed,
            "overall_total": overall_total,
            "message": "All assigned images are complete for this user.",
            "show_accuracy": user.get("user_type") != "radiologist",
        }
        if user.get("assignment_group"):
            group = load_radiologist_groups()["groups"][user["assignment_group"]]
            payload["assignment_group"] = user["assignment_group"]
            payload["assignment_label"] = group["label"]
        if phase:
            payload.update({key: phase[key] for key in ("study_phase", "phase_completed", "phase_total")})
        return payload

    item = lookup[current_id]
    payload = {
        "done": False,
        "image_id": current_id,
        "image_url": f"/image/{current_id}",
        "dataset": item["dataset"],
        "stage": user.get("stage", "q1"),
        "answers": user.get("current_answers", {}),
        "completed": completed,
        "total": total,
        "overall_completed": overall_completed,
        "overall_total": overall_total,
        "regions": REGIONS,
        "show_accuracy": user.get("user_type") != "radiologist",
    }
    if user.get("assignment_group"):
        group = load_radiologist_groups()["groups"][user["assignment_group"]]
        payload["assignment_group"] = user["assignment_group"]
        payload["assignment_label"] = group["label"]
        payload.update({key: phase[key] for key in ("study_phase", "phase_completed", "phase_total")})
        payload["phase_transition"] = (
            phase["study_phase"] in {"phase_2", "phase_3"}
            and phase["phase_completed"] == 0
            and payload["stage"] == "q1"
        )
    if payload["stage"] == "q_lymph_node":
        payload["lymph_node_choices"] = LYMPH_NODE_CHOICES
    if payload["stage"] == "q2":
        q1 = payload["answers"].get("q1_region")
        lymph_node_answer = payload["answers"].get("q_lymph_node")
        payload["q2_choices"] = filtered_q2_choices(q1, lymph_node_answer)
    if payload["stage"] == "q4":
        payload["q4_choices"] = QUALITY_ISSUES
    return payload


def advance_after_answer(user: dict, item: dict, stage: str, answer: dict) -> None:
    answers = user.setdefault("current_answers", {})
    if stage == "q1":
        q1_region = answer.get("q1_region")
        if q1_region not in REGIONS:
            raise ValueError("Q1 answer must be Chest, Abdomen, Pelvis, or Others.")
        answers["q1_region"] = q1_region
        user["stage"] = "q_lymph_node"
    elif stage == "q_lymph_node":
        q_lymph_node = str(answer.get("q_lymph_node", "")).strip()
        if q_lymph_node not in LYMPH_NODE_CHOICES:
            raise ValueError("Lymph node answer must be Yes, No, or Unsure.")
        answers["q_lymph_node"] = q_lymph_node
        user["stage"] = "q2"
    elif stage == "q2":
        q2_site = str(answer.get("q2_site", "")).strip()
        q1_region = answers.get("q1_region")
        choices = filtered_q2_choices(q1_region, answers.get("q_lymph_node"))
        if q2_site not in choices:
            raise ValueError("Q2 answer is not valid for the selected region.")
        answers["q2_site"] = q2_site
        user["stage"] = "q4"
    elif stage == "q4":
        q4_quality_issue = str(answer.get("q4_quality_issue", "")).strip()
        if q4_quality_issue not in QUALITY_ISSUES:
            raise ValueError("Q4 answer is not a valid image quality choice.")
        answers["q4_quality_issue"] = q4_quality_issue
        completed = user.setdefault("completed_image_ids", [])
        if item["image_id"] not in completed:
            completed.append(item["image_id"])
        user["stage"] = "q1"
        user["current_image_id"] = None
        user["current_answers"] = {}
    else:
        raise ValueError("Unknown stage.")


class StarHandler(BaseHTTPRequestHandler):
    server_version = "STARWeb/0.1"

    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str | None = None):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_file(TEMPLATE_PATH, "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            self.send_file(STATIC_DIR / path.removeprefix("/static/"))
            return
        if path == "/api/users":
            self.send_json({"users": list_users()})
            return
        if path == "/api/q2-sites":
            self.send_json(load_q2_sites())
            return
        if path == "/api/assignment-summary":
            self.send_json(assignment_summary())
            return
        if path == "/api/current":
            user_id = parse_qs(parsed.query).get("user_id", [""])[0]
            user = load_user(user_id)
            if user is None:
                self.send_json({"error": "Unknown user."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(public_task(user, load_manifest()))
            return
        if path == "/api/stats":
            user_id = parse_qs(parsed.query).get("user_id", [""])[0]
            if not user_id:
                self.send_json({"error": "Missing user_id."}, HTTPStatus.BAD_REQUEST)
                return
            user = load_user(user_id)
            if user is None:
                self.send_json({"error": "Unknown user."}, HTTPStatus.NOT_FOUND)
                return
            if user.get("user_type") == "radiologist":
                self.send_json({"hidden": True, "message": "Accuracy feedback is hidden for radiologists."})
                return
            self.send_json(user_stats(user_id))
            return
        if path == "/api/manifest-summary":
            manifest = load_manifest()
            datasets = {}
            for item in manifest:
                datasets[item["dataset"]] = datasets.get(item["dataset"], 0) + 1
            self.send_json({"total": len(manifest), "datasets": datasets})
            return
        if path.startswith("/image/"):
            image_id = path.removeprefix("/image/")
            item = image_lookup(load_manifest()).get(image_id)
            if item is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_file(Path(item["image_path"]), "image/png")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            data = self.read_body()
            if parsed.path == "/api/users":
                user_id = slug_user_id(str(data.get("user_id", "")))
                if not user_id:
                    raise ValueError("User ID is required.")
                requested_type = str(data.get("user_type", "human")).strip().lower()
                if requested_type not in VALID_USER_TYPES:
                    raise ValueError("Invalid user type.")
                with ASSIGNMENT_LOCK:
                    user = load_user(user_id)
                    registry = None
                    if user is None:
                        user = {
                            "user_id": user_id,
                            "user_type": requested_type,
                            "display_name": data.get("display_name", user_id),
                            "model": data.get("model", ""),
                            "created_at": utc_now(),
                            "updated_at": utc_now(),
                            "stage": "q1",
                            "current_image_id": None,
                            "current_answers": {},
                            "completed_image_ids": [],
                        }
                        if requested_type in SPECIALIST_GROUPS:
                            registry = load_group_registry()
                            user["assignment_group"] = claim_specialist_group(
                                user_id, requested_type, registry
                            )
                    else:
                        user["updated_at"] = utc_now()
                    ensure_current_task(user, load_manifest())
                    save_user(user)
                    if registry is not None:
                        write_json(GROUP_REGISTRY_PATH, registry)
                self.send_json({"user": user, "task": public_task(user, load_manifest())})
                return

            if parsed.path == "/api/answer":
                manifest = load_manifest()
                lookup = image_lookup(manifest)
                user_id = data.get("user_id", "")
                user = load_user(user_id)
                if user is None:
                    raise ValueError("Unknown user.")
                ensure_current_task(user, manifest)
                image_id = data.get("image_id")
                stage = data.get("stage")
                eligible_lookup = image_lookup(manifest_for_user(user, manifest))
                if image_id not in eligible_lookup:
                    raise ValueError("Submitted image is outside this user's assignment.")
                if image_id != user.get("current_image_id"):
                    raise ValueError("Submitted image does not match current task.")
                if stage != user.get("stage"):
                    raise ValueError("Submitted stage does not match current task.")
                item = lookup[image_id]
                assignment = assignment_metadata(user, image_id)
                before = dict(user.get("current_answers", {}))
                advance_after_answer(user, item, stage, data)
                user["updated_at"] = utc_now()
                save_user(user)
                event = {
                    "timestamp": utc_now(),
                    "user_id": user["user_id"],
                    "user_type": user.get("user_type", "human"),
                    "image_id": image_id,
                    "dataset": item["dataset"],
                    "stage": "complete" if stage == "q4" else stage,
                    "answer": data,
                    "answers_before_stage": before,
                }
                event.update(assignment)
                if stage == "q1":
                    event["q1_region"] = data["q1_region"]
                elif stage == "q_lymph_node":
                    event["q1_region"] = before.get("q1_region")
                    event["q_lymph_node"] = data["q_lymph_node"]
                elif stage == "q2":
                    event["q1_region"] = before.get("q1_region")
                    event["q_lymph_node"] = before.get("q_lymph_node")
                    event["q2_site"] = data["q2_site"]
                elif stage == "q4":
                    gt_region = q1_region_for_site(item["gt_site"])
                    gt_q2_site = canonical_site(item["gt_site"])
                    gt_lymph_node = is_lymph_node_site(item["gt_site"])
                    q1_region = before.get("q1_region")
                    q_lymph_node = before.get("q_lymph_node")
                    q2_site = before.get("q2_site")
                    event["q1_region"] = before.get("q1_region")
                    event["q_lymph_node"] = before.get("q_lymph_node")
                    event["q2_site"] = before.get("q2_site")
                    event["q4_quality_issue"] = data["q4_quality_issue"]
                    event["q1_correct"] = q1_region == gt_region
                    event["q_lymph_node_correct"] = {
                        "Yes": True,
                        "No": False,
                        "Unsure": None,
                    }.get(q_lymph_node) == gt_lymph_node if q_lymph_node != "Unsure" else None
                    event["q2_correct"] = canonical_site(q2_site) == gt_q2_site
                    event["gt_site"] = item["gt_site"]
                    event["raw_tracking_id"] = item["raw_tracking_id"]
                append_jsonl(answer_path(user["user_id"]), event)
                self.send_json({"ok": True, "task": public_task(user, manifest)})
                return

            if parsed.path == "/api/rebuild-manifest":
                manifest = build_manifest()
                self.send_json({"ok": True, "total": len(manifest)})
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except NoAvailableGroupError as exc:
            self.send_json(
                {"error": str(exc), "code": "no_available_group"},
                HTTPStatus.CONFLICT,
            )
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON body."}, HTTPStatus.BAD_REQUEST)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the STAR annotation web app.")
    parser.add_argument(
        "--data_dir",
        default=str(DEFAULT_DATA_DIR),
        help=(
            "Root directory containing dataset folders such as "
            "CPTAC/vis_check, EAY131/vis_check, and R2Seg/vis_check."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_data_dir(args.data_dir)
    load_manifest()
    host = args.host
    port = args.port
    server = ThreadingHTTPServer((host, port), StarHandler)
    print(f"STAR annotation app running at http://{host}:{port}")
    print(f"Using image data from {DATA_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
