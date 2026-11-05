import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUTPUT = Path(
    "/Users/sg2162/.codex/visualizations/2026/07/16/"
    "019f6ad4-fa4a-7311-a6ff-53ffc42e64e5/accuracy-with-sg2162.png"
)
SUMMARY_ROOT = Path(
    "/Users/sg2162/Library/CloudStorage/OneDrive-UniversityofCambridge/"
    "backup/project/MLLM_benchmark/star_full_20260920_v1"
)

model_specs = [
    ("GPT-6 Astra", "gpt-6-astra"),
    ("Claude Fable\n5.1", "claude-fable-5-1"),
    ("GLM-5.3-Flash", "glm-5.3-flash"),
    ("Qwen3-VL-Plus", "qwen3-vl-plus"),
    ("Lingshu-7B", "lingshu-7b"),
    ("MedGemma\n1.5-4B-IT", "medgemma-1.5-4b-it"),
    ("DeepSeek-V4\nFlash Vision", "deepseek-v4-flash-vision-exp"),
    ("InternVL3.5-8B", "internvl3.5-8b-hf"),
    ("Kimi-K3", "kimi-k3"),
    ("LLaVA-1.5-7B", "llava-1.5-7b-hf"),
]

models = ["sg2162"]
region = [96.10]
lymph_node = [92.85]
site = [78.05]
scored_counts = {"sg2162": 10565}

for label, directory in model_specs:
    summary_path = SUMMARY_ROOT / directory / "summary.json"
    summary = json.loads(summary_path.read_text())
    accuracy = summary["accuracy"]
    if any(accuracy[field] is None for field in ("q1_region", "q_lymph_node", "q2_site")):
        continue
    models.append(label)
    region.append(100 * accuracy["q1_region"])
    lymph_node.append(100 * accuracy["q_lymph_node"])
    site.append(100 * accuracy["q2_site"])
    scored_counts[label] = summary["scored_count"]["q1_region"]

# Rank models by end-to-end routed Q3 (site) accuracy, highest first.
ranked = sorted(zip(models, region, lymph_node, site), key=lambda row: row[3], reverse=True)
models, region, lymph_node, site = map(list, zip(*ranked))

x = np.arange(len(models))
width = 0.20
colors = {"Region": "#476f89", "Lymph node": "#7da89b", "Site": "#c47e67"}

fig, ax = plt.subplots(figsize=(22, 8.6), dpi=160)
bars = [
    ax.bar(x - width, region, width, label="Region", color=colors["Region"]),
    ax.bar(x, lymph_node, width, label="Lymph node", color=colors["Lymph node"]),
    ax.bar(x + width, site, width, label="Site", color=colors["Site"]),
]

for group in bars:
    ax.bar_label(group, fmt="%.2f", padding=4, fontsize=10)

ax.set_title("Accuracy across evaluation tasks grouped by question type", fontsize=15, pad=38)
ax.set_ylabel("Accuracy (%)", fontsize=12)
ax.set_ylim(0, 100)
ax.set_yticks(np.arange(0, 101, 20))
ax.set_xticks(x)
ax.set_xticklabels(models, fontsize=11)
ax.tick_params(axis="y", labelsize=11)
ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.18), ncol=3, frameon=False, fontsize=11)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("#333333")
ax.spines["bottom"].set_color("#333333")
ax.grid(False)
incomplete = [
    f"{label.replace(chr(10), ' ')} n={scored_counts[label]:,}"
    for label in models
    if scored_counts[label] != 10565
]
if incomplete:
    fig.text(
        0.5,
        0.035,
        "Accuracy is calculated over completed cases; incomplete runs: " + "; ".join(incomplete) + ".",
        ha="center",
        fontsize=9,
        color="#555555",
    )
fig.subplots_adjust(left=0.055, right=0.992, bottom=0.19, top=0.78)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUTPUT, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(OUTPUT)
