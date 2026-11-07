#!/usr/bin/env python3
"""Build manifests/imaging_covariates.json from NIfTI masks and STAR PNGs."""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import cv2
import nibabel as nib
import numpy as np
import pandas as pd
from nibabel.affines import obliquity
from nibabel.orientations import (
    aff2axcodes,
    apply_orientation,
    axcodes2ornt,
    io_orientation,
    ornt_transform,
)
from scipy import ndimage
from skimage.transform import resize


R2SEG_ROOT = Path("/Users/sg2162/Datasets/CancerDatasets/R2Seg")
EAY131_ROOT = Path("/Users/sg2162/Datasets/CancerDatasets/EAY131")
CPTAC_ROOT = Path("/Users/sg2162/Datasets/CancerDatasets/CPTAC-Annotated")
PANEL_SIZE = 256
VIEW_NAMES = ("sagittal", "coronal", "axial")
CALCULATION_VERSION = "star-imaging-covariates-1.0"


def nii_stem(path):
    name = Path(path).name
    return name[:-7] if name.endswith(".nii.gz") else Path(name).stem


def scalar(value, digits=6):
    value = float(value)
    if not math.isfinite(value):
        return None
    return round(value, digits)


def sequence_type(dataset, stem):
    lower = stem.lower()
    if dataset == "Prostate_Tumor_00":
        if lower.endswith("_adc"):
            return "ADC", "filename"
        if lower.endswith("_t2"):
            return "T2-weighted", "filename"
    if dataset == "Uterus_Tumor_00" and lower.endswith("_t2"):
        return "T2-weighted", "filename"
    if dataset == "Cervix_Tumor_00" and "_t2" in lower:
        return "T2-weighted", "filename"
    if dataset == "Breast_Tumor_00":
        return "DCE-MRI", "dataset_definition"
    return None, "unavailable"


def add_unique(mapping, key, value, label):
    if key in mapping and mapping[key] != value:
        raise ValueError(f"Ambiguous {label} {key}")
    mapping[key] = value


def build_source_lookup():
    lookup = {"R2Seg": {}, "EAY131": {}, "CPTAC": {}}

    for dataset_json in sorted(R2SEG_ROOT.glob("*/dataset.json")):
        dataset = dataset_json.parent.name
        data = json.loads(dataset_json.read_text())
        modality_value = data.get("modality")
        if isinstance(modality_value, dict):
            modality_value = next(iter(modality_value.values()), None)
        labels = data.get("labels", {})
        tumor_label = next(
            (int(key) for key, value in labels.items() if str(value).lower() == "tumor"),
            1,
        )
        for split in ("train", "test"):
            for item in data.get(split, []):
                stem = nii_stem(item["image"])
                key = f"{dataset}_{stem}"
                seq, seq_source = sequence_type(dataset, stem)
                record = {
                    "source_image": str(dataset_json.parent / item["image"]),
                    "source_mask": str(dataset_json.parent / item["label"]),
                    "modality": modality_value,
                    "modality_source": "dataset_json",
                    "sequence_type": seq,
                    "sequence_type_source": seq_source,
                    "tumor_label": tumor_label,
                }
                add_unique(lookup["R2Seg"], key, record, "R2Seg key")

    metadata_path = (
        EAY131_ROOT
        / "Metadata"
        / "Metadata_Report_EAY131_Tumor_Annotationsv2_2026-03-24.csv"
    )
    metadata = pd.read_csv(metadata_path, dtype=str, low_memory=False)
    modality_by_annotation = {}
    for _, row in metadata.iterrows():
        uid = str(row.get("SeriesInstanceUID", "")).strip()
        modality_value = str(row.get("ReferencedSeriesModality", "")).strip()
        if uid and modality_value and modality_value.lower() != "nan":
            add_unique(modality_by_annotation, uid, modality_value, "EAY131 modality UID")

    eay_index = json.loads((EAY131_ROOT / "Radiology_NIFTI" / "output_index.json").read_text())
    for items in eay_index.values():
        for item in items:
            uid = Path(item["label"]).parent.name
            record = {
                "source_image": str(EAY131_ROOT / "Radiology_NIFTI" / item["image"]),
                "source_mask": str(EAY131_ROOT / "Radiology_NIFTI_Post" / item["label"]),
                "modality": modality_by_annotation.get(uid),
                "modality_source": "metadata_report" if uid in modality_by_annotation else "unavailable",
                "sequence_type": None,
                "sequence_type_source": "unavailable",
                "tumor_label": None,
            }
            add_unique(lookup["EAY131"], uid, record, "EAY131 annotation UID")

    cptac_cases = json.loads((CPTAC_ROOT / "dataset.json").read_text())["cases"]
    for items in cptac_cases.values():
        for item in items:
            uid = Path(item["label"]).parent.name
            parts = Path(item["image"]).parts
            modality_value = next((value for value in parts if value in {"CT", "MR"}), None)
            record = {
                "source_image": str(CPTAC_ROOT / item["image"]),
                "source_mask": str(CPTAC_ROOT / item["label"]),
                "modality": modality_value,
                "modality_source": "dataset_path" if modality_value else "unavailable",
                "sequence_type": None,
                "sequence_type_source": "unavailable",
                "tumor_label": None,
            }
            add_unique(lookup["CPTAC"], uid, record, "CPTAC annotation UID")
    return lookup


def prepare_tasks(manifest, lookup):
    tasks = []
    unresolved = []
    for index, item in enumerate(manifest):
        key = Path(item["image_path"]).name.split("-site_in_", 1)[0]
        source = lookup[item["dataset"]].get(key)
        if source is None:
            unresolved.append((item["image_id"], item["dataset"], key))
            continue
        tasks.append(
            {
                "index": index,
                "image_id": item["image_id"],
                "dataset": item["dataset"],
                "prepared_png": item["image_path"],
                **source,
            }
        )
    if unresolved:
        raise ValueError(f"Unresolved manifest records: {unresolved[:10]} ({len(unresolved)} total)")
    return tasks


def lps_transform(nii):
    current = io_orientation(nii.affine)
    target = axcodes2ornt(("L", "P", "S"))
    return ornt_transform(current, target)


def reorient_data_to_lps(nii, data):
    transform = lps_transform(nii)
    return apply_orientation(data, transform), transform


def transformed_spacing(nii, transform):
    zooms = np.asarray(nib.affines.voxel_sizes(nii.affine), dtype=float)
    return zooms[transform[:, 0].astype(int)]


def largest_component(mask):
    labeled, count = ndimage.label(mask)
    if count == 0:
        return labeled, 0, None, 0
    sizes = np.bincount(labeled.ravel())
    largest_label = int(np.argmax(sizes[1:]) + 1)
    center = np.round(ndimage.center_of_mass(mask, labeled, largest_label)).astype(int)
    return labeled, count, center, int(sizes[largest_label])


def resize_to_isotropic(mask_slice, spacing_y, spacing_x):
    height, width = mask_slice.shape
    new_height = max(1, int(round(height * float(spacing_y))))
    new_width = max(1, int(round(width * float(spacing_x))))
    return resize(
        mask_slice.astype(float),
        (new_height, new_width),
        order=0,
        preserve_range=True,
        anti_aliasing=False,
    ) > 0.5


def resize_panel_mask(mask_slice, target=PANEL_SIZE):
    height, width = mask_slice.shape
    scale = target / max(height, width)
    new_height = max(1, int(height * scale))
    new_width = max(1, int(width * scale))
    resized = cv2.resize(
        mask_slice.astype(np.float32),
        (new_width, new_height),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.zeros((target, target), dtype=np.float32)
    y0 = (target - new_height) // 2
    x0 = (target - new_width) // 2
    canvas[y0 : y0 + new_height, x0 : x0 + new_width] = resized
    return canvas >= 0.5, canvas


def prepared_views(mask, center, spacing):
    x, y, z = [int(value) for value in center]
    sx, sy, sz = spacing
    raw = [
        (np.rot90(mask[x, :, :]), sz, sy),
        (np.rot90(mask[:, y, :]), sz, sx),
        (np.rot90(mask[:, :, z]), sy, sx),
    ]
    views = []
    for name, (mask_slice, row_spacing, col_spacing) in zip(VIEW_NAMES, raw):
        isotropic = resize_to_isotropic(mask_slice, row_spacing, col_spacing)
        binary, fractional = resize_panel_mask(isotropic)
        coordinates = np.argwhere(binary)
        if coordinates.size:
            y_min, x_min = coordinates.min(axis=0)
            y_max, x_max = coordinates.max(axis=0)
            bbox_width = int(x_max - x_min + 1)
            bbox_height = int(y_max - y_min + 1)
            edge_distance = int(min(x_min, y_min, PANEL_SIZE - 1 - x_max, PANEL_SIZE - 1 - y_max))
            bbox_fraction = bbox_width * bbox_height / (PANEL_SIZE * PANEL_SIZE)
            edge_fraction = edge_distance / PANEL_SIZE
        else:
            bbox_width = bbox_height = 0
            bbox_fraction = edge_fraction = 0.0
        views.append(
            {
                "name": name,
                "tumor_pixel_count": int(binary.sum()),
                "tumor_pixel_coverage": scalar(fractional.sum()),
                "overlay_fraction": scalar(binary.mean()),
                "bbox_width_px": bbox_width,
                "bbox_height_px": bbox_height,
                "bbox_fraction": scalar(bbox_fraction),
                "min_bbox_dimension_px": min(bbox_width, bbox_height),
                "edge_distance_fraction": scalar(edge_fraction),
                "tumor_visible": bool(binary.any()),
            }
        )
    return views


def represented_voxel_count(mask, center):
    x, y, z = [int(value) for value in center]
    single = int(mask[x, :, :].sum() + mask[:, y, :].sum() + mask[:, :, z].sum())
    pairs = int(mask[x, y, :].sum() + mask[x, :, z].sum() + mask[:, y, z].sum())
    triple = int(mask[x, y, z])
    return single - pairs + triple


def process_task(task):
    try:
        image_path = Path(task["source_image"])
        mask_path = Path(task["source_mask"])
        png_path = Path(task["prepared_png"])
        if not image_path.is_file() or not mask_path.is_file() or not png_path.is_file():
            missing = [str(path) for path in (image_path, mask_path, png_path) if not path.is_file()]
            raise FileNotFoundError(f"Missing source files: {missing}")

        image_nii = nib.load(str(image_path))
        mask_nii = nib.load(str(mask_path))
        source_orientation = list(aff2axcodes(image_nii.affine))
        source_shape = [int(value) for value in image_nii.shape[:3]]
        source_spacing = nib.affines.voxel_sizes(image_nii.affine)[:3]
        source_obliquity = np.degrees(obliquity(image_nii.affine))
        qform_code = int(image_nii.header["qform_code"])
        sform_code = int(image_nii.header["sform_code"])

        raw_mask = np.asanyarray(mask_nii.dataobj)
        if task["tumor_label"] is None:
            raw_mask = raw_mask > 0
        else:
            raw_mask = raw_mask == task["tumor_label"]
        mask, mask_transform = reorient_data_to_lps(mask_nii, raw_mask)
        mask = np.asarray(mask, dtype=bool)
        image_transform = lps_transform(image_nii)
        spacing = transformed_spacing(image_nii, image_transform)
        image_lps_shape = tuple(
            np.asarray(image_nii.shape[:3])[np.argsort(image_transform[:, 0].astype(int))]
        )
        if tuple(mask.shape) != tuple(image_lps_shape):
            raise ValueError(
                f"Image/mask shape mismatch after LPS reorientation: "
                f"image={image_lps_shape}, mask={mask.shape}"
            )
        shape = np.asarray(mask.shape, dtype=int)
        if mask.ndim != 3:
            raise ValueError(f"Mask is not 3D: {mask.shape}")
        voxel_count = int(mask.sum())
        if voxel_count == 0:
            raise ValueError("Empty tumor mask")

        labeled, component_count, center, largest_count = largest_component(mask)
        coordinates = np.argwhere(mask)
        minimum = coordinates.min(axis=0)
        maximum = coordinates.max(axis=0)
        bbox_voxels = maximum - minimum + 1
        bbox_mm = bbox_voxels * spacing
        centroid = coordinates.mean(axis=0)
        denominator = np.maximum(shape - 1, 1)
        centroid_fraction = centroid / denominator
        lower_distance = minimum * spacing
        upper_distance = (shape - 1 - maximum) * spacing
        min_edge_distance = float(np.min(np.concatenate([lower_distance, upper_distance])))
        slice_counts = [int(np.unique(coordinates[:, axis]).size) for axis in range(3)]
        represented = represented_voxel_count(mask, center)

        views = prepared_views(mask, center, spacing)
        total_panel_pixels = len(views) * PANEL_SIZE * PANEL_SIZE
        total_tumor_pixels = sum(view["tumor_pixel_count"] for view in views)
        visible = [view for view in views if view["tumor_visible"]]
        png = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
        if png is None:
            raise ValueError("Prepared PNG could not be read")
        png_height, png_width = png.shape[:2]

        modality = task["modality"]
        if modality is not None:
            modality = str(modality).upper()
        record = {
            "source_image": {
                "modality": modality,
                "modality_source": task["modality_source"],
                "sequence_type": task["sequence_type"],
                "sequence_type_source": task["sequence_type_source"],
                "shape": source_shape,
                "voxel_spacing_mm": [scalar(value) for value in source_spacing],
                "physical_extent_mm": [
                    scalar(source_shape[index] * source_spacing[index]) for index in range(3)
                ],
                "voxel_volume_mm3": scalar(np.prod(source_spacing)),
                "orientation_codes": source_orientation,
                "max_obliquity_deg": scalar(np.max(source_obliquity)),
                "is_oblique": bool(np.max(source_obliquity) > 1.0),
                "qform_code": qform_code,
                "sform_code": sform_code,
                "intensity_datatype": str(image_nii.get_data_dtype()),
            },
            "tumor_geometry": {
                "voxel_count": voxel_count,
                "volume_ml": scalar(voxel_count * np.prod(spacing) / 1000.0),
                "bbox_extent_mm_lps": [scalar(value) for value in bbox_mm],
                "max_bbox_extent_mm": scalar(np.max(bbox_mm)),
                "slice_count_lps_axes": slice_counts,
                "centroid_fraction_lps": [scalar(value) for value in centroid_fraction],
                "min_volume_edge_distance_mm": scalar(min_edge_distance),
                "connected_component_count": int(component_count),
                "largest_component_fraction": scalar(largest_count / voxel_count),
            },
            "prepared_input": {
                "width_px": int(png_width),
                "height_px": int(png_height),
                "panel_size_px": PANEL_SIZE,
                "view_order": list(VIEW_NAMES),
                "displayed_view_count": len(views),
                "visible_view_count": len(visible),
                "largest_component_center_lps_voxel": [int(value) for value in center],
                "tumor_pixel_count_total": int(total_tumor_pixels),
                "overlay_panel_fraction_total": scalar(total_tumor_pixels / total_panel_pixels),
                "tumor_pixel_fraction_full_png": scalar(total_tumor_pixels / (png_width * png_height)),
                "max_view_overlay_fraction": scalar(max(view["overlay_fraction"] for view in views)),
                "mean_nonzero_overlay_fraction": scalar(
                    np.mean([view["overlay_fraction"] for view in visible]) if visible else 0
                ),
                "min_nonzero_bbox_dimension_px": int(
                    min(view["min_bbox_dimension_px"] for view in visible) if visible else 0
                ),
                "tumor_voxel_fraction_represented": scalar(represented / voxel_count),
                "views": {view.pop("name"): view for view in views},
            },
            "provenance": {
                "source_image": str(image_path),
                "source_mask": str(mask_path),
                "prepared_png": str(png_path),
                "geometry_source": "NIfTI header",
                "tumor_geometry_source": "reference segmentation mask",
                "prepared_visibility_source": "reference mask transformed with STAR renderer",
                "renderer": "vision/m_prepare_nifiti_slices_masks.py",
                "calculation_version": CALCULATION_VERSION,
            },
        }
        return task["index"], task["image_id"], record, None
    except Exception as exc:
        return task["index"], task["image_id"], None, f"{type(exc).__name__}: {exc}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("manifests/images.json"))
    parser.add_argument("--output", type=Path, default=Path("manifests/imaging_covariates.json"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    lookup = build_source_lookup()
    tasks = prepare_tasks(manifest, lookup)
    if args.limit:
        # Spread a pilot across the complete manifest rather than taking only its first rows.
        indices = np.linspace(0, len(tasks) - 1, min(args.limit, len(tasks)), dtype=int)
        tasks = [tasks[index] for index in indices]

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for completed, result in enumerate(executor.map(process_task, tasks), start=1):
            results.append(result)
            if completed % 250 == 0 or completed == len(tasks):
                print(f"processed={completed}/{len(tasks)}", flush=True)

    errors = [(image_id, error) for _, image_id, _, error in results if error]
    if errors:
        print(f"errors={len(errors)} examples={errors[:20]}")
        raise SystemExit(1)

    results.sort(key=lambda item: item[0])
    records = {image_id: record for _, image_id, record, _ in results}
    output = {
        "schema_version": "1.0",
        "calculation_version": CALCULATION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_count": len(records),
        "definitions": {
            "source_image": "Geometry and modality of the original NIfTI volume.",
            "tumor_geometry": "Physical tumor properties calculated from the reference 3D mask after LPS reorientation.",
            "prepared_input": "Visibility of the transformed reference mask in the 768x512 STAR PNG renderer.",
            "voxel_spacing_mm": "NIfTI voxel spacing; not asserted to equal original DICOM slice thickness.",
            "physical_extent_mm": "NIfTI shape multiplied by voxel spacing for each stored source axis.",
            "overlay_panel_fraction_total": "Tumor pixels across the three 256x256 overlay panels divided by their total pixels.",
            "tumor_pixel_fraction_full_png": "Tumor pixels in the overlay row divided by all pixels in the full clean-plus-overlay PNG.",
            "prepared_visibility_threshold": "After renderer-matched resampling, a panel pixel is counted as tumor when its fractional mask occupancy is at least 0.5; sub-threshold signal remains available as tumor_pixel_coverage.",
            "tumor_voxel_fraction_represented": "Fraction of 3D tumor voxels intersected by the three orthogonal slices through the largest-component center.",
            "null_policy": "Unavailable values are JSON null and are not inferred from dataset averages.",
        },
        "images": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(args.output)
    print(f"saved={args.output} images={len(records)}")


if __name__ == "__main__":
    main()
