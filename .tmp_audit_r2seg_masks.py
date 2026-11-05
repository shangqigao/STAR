import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nibabel as nib
import numpy as np


root = Path("/Users/sg2162/Datasets/CancerDatasets/R2Seg")
tasks = []
for metadata_path in sorted(root.glob("*/dataset.json")):
    metadata = json.loads(metadata_path.read_text())
    tumor_label = [
        int(key)
        for key, value in metadata["labels"].items()
        if str(value).strip().lower() == "tumor"
    ][0]
    entries = sum(
        (metadata.get(key, []) for key in ("train", "validation", "val", "test")),
        [],
    )
    for entry in entries:
        tasks.append(
            (
                metadata_path.parent.name,
                str(metadata_path.parent / entry["label"]),
                tumor_label,
            )
        )


def check(task):
    dataset, path, tumor_label = task
    try:
        if not os.path.exists(path):
            return dataset, "missing", path
        array = np.asanyarray(nib.load(path).dataobj)
        status = "nonempty" if np.any(array == tumor_label) else "empty"
        return dataset, status, path
    except Exception as exc:
        return dataset, f"error:{type(exc).__name__}", path


counts = Counter()
examples = {}
with ThreadPoolExecutor(max_workers=8) as executor:
    for dataset, status, path in executor.map(check, tasks):
        counts[(dataset, status)] += 1
        examples.setdefault((dataset, status), path)

print("TOTAL", len(tasks))
for dataset in sorted({task[0] for task in tasks}):
    print(dataset, {status: count for (name, status), count in counts.items() if name == dataset})
print(
    "ALL",
    {
        status: sum(count for (name, current), count in counts.items() if current == status)
        for status in sorted({current for name, current in counts})
    },
)
for key, path in examples.items():
    if key[1] != "nonempty":
        print("EXAMPLE", key, path)
