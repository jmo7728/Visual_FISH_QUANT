# -*- coding: utf-8 -*-
"""Shared FISH-Quant backend: spot detection and ROI filtering.

No GUI or notebook-only imports live here (no napari, no ipywidgets, no
matplotlib) so this module stays cheap to import from both the Colab
script (fish_quant.py) and the standalone interactive tool
(fish_quant_gui.py).
"""

import os
from pathlib import Path
import bigfish.plot as plot
import pandas as pd
import bigfish.stack as stack
import bigfish.detection as detection
import roifile
from shapely.geometry import Point, Polygon


def load_image(path_to_data):
  return stack.read_image(path_to_data)


DEFAULT_VOXEL_SIZE = (560, 360, 360)   # (z, y, x) nm
DEFAULT_SPOT_RADIUS = (560, 300, 300)  # (z, y, x) nm


def detect_spots(image_raw, thrshld_modifier,
                  voxel_size=DEFAULT_VOXEL_SIZE, spot_radius=DEFAULT_SPOT_RADIUS):
  """Detect spots on the full 3D volume at once (not per 2D slice).

  Returns (all_spots, auto_threshold) where all_spots is an (N, 3) array
  of (z, y, x) -- still filterable/viewable by z index -- and the
  threshold actually used is auto_threshold * thrshld_modifier.
  """
  _, auto_threshold = detection.detect_spots(
    image_raw,
    return_threshold=True,
    voxel_size=voxel_size,
    spot_radius=spot_radius,
  )

  all_spots = detection.detect_spots(
    image_raw,
    threshold=auto_threshold * thrshld_modifier,
    voxel_size=voxel_size,
    spot_radius=spot_radius,
  )
  return all_spots, auto_threshold

def dense_detect_spots(image_raw, thrshld_modifier,
                       voxel_size=DEFAULT_VOXEL_SIZE, spot_radius=DEFAULT_SPOT_RADIUS):
  
  spots, auto_threshold = detect_spots(image_raw, thrshld_modifier, voxel_size=voxel_size, spot_radius=spot_radius)
  print("\r shape: {0}".format(spots.shape))
  all_spots, dense_regions, reference_spot = detection.decompose_dense(image_raw, spots, voxel_size=voxel_size, spot_radius=spot_radius, alpha = 0.5, beta = 1, gamma = 5)
  return all_spots, auto_threshold

def spots_to_dataframe(all_spots):
  return pd.DataFrame({"z": all_spots[:, 0], "y": all_spots[:, 1], "x": all_spots[:, 2]})


def save_spots_csv(all_spots, output_path):
  spots_to_dataframe(all_spots).to_csv(output_path, index=False)
  return output_path


def load_spots_csv(csv_path):
  """Inverse of save_spots_csv: read a previously-saved (or ROI-filtered)
  spots csv back into an (N, 3) array of (z, y, x), for viewing without
  re-running detection."""
  df = pd.read_csv(csv_path)
  missing = [col for col in ("z", "y", "x") if col not in df.columns]
  if missing:
    raise ValueError(f"csv is missing required column(s) {missing}; expected z, y, x")
  return df[["z", "y", "x"]].to_numpy()


def filter_roi(roi_path, csv_path, output_path=None):
  """Keep only the spots of csv_path that fall inside roi_path.

  output_path lets the caller name the result explicitly -- needed when one
  csv is filtered by several rois in a row, since the default name depends
  only on the csv and every roi would otherwise overwrite the last one.
  """
  spots_df = pd.read_csv(csv_path)
  roi = roifile.ImagejRoi.fromfile(roi_path)
  pachytene_polygon = Polygon(roi.coordinates())

  inside_roi = [pachytene_polygon.contains(Point(row['x'], row['y']))
                for _, row in spots_df.iterrows()]
  filtered_df = spots_df[inside_roi]

  if output_path is None:
    folder = os.path.dirname(csv_path)
    orig_name = os.path.basename(csv_path).replace(".csv", "")
    output_path = os.path.join(folder, f"{orig_name}_filtered_ROI.csv")
  filtered_df.to_csv(output_path, index=False)

  print("\n--- 🔬 ANALYSIS COMPLETE 🔬 ---")
  print(f"Total spots in raw file: {len(spots_df)}")
  print(f"Final spots inside this specific ROI: {len(filtered_df)}")
  print(f"🎉 Filtered file saved to:\n{output_path}\n")

  return len(spots_df), len(filtered_df), output_path


def filter_multiple_roi(csv_dir="./csv"):
  # each worm folder under csv_dir holds one .roi plus its mex6 (C3-) and
  # puf5 (C2-) spots csvs side by side -- group by folder and filter both
  by_folder = {}
  for p in Path(csv_dir).rglob("*"):
    if p.suffix == ".roi":
      by_folder.setdefault(p.parent, {})["roi"] = p
    elif p.suffix == ".csv" and not p.name.endswith("_filtered_ROI.csv"):
      by_folder.setdefault(p.parent, {}).setdefault("csvs", []).append(p)

  for folder, entry in sorted(by_folder.items()):
    roi_path = entry.get("roi")
    csv_paths = entry.get("csvs", [])
    if roi_path is None:
      if csv_paths:
        print(f"WARNING: no ROI found in {folder} for {len(csv_paths)} csv(s)")
      continue
    if len(csv_paths) != 2:
      print(f"WARNING: expected 2 csvs (mex6+puf5) in {folder}, found {len(csv_paths)}: {csv_paths}")
    for csv_path in csv_paths:
      filter_roi(roi_path, csv_path)


# image_raw = load_image("/Users/johnny5201/Downloads/C3-FLP21_EMPY_MEX6_24HR_Project (2).lif - 24hr_FLP21_mex6_w5.tif")
# image_mip = stack.maximum_projection(image_raw)
# before_spots, before_thr = detect_spots(image_raw, 1.0)
# plot.plot_detection(image_mip, before_spots, contrast=True)
# spots, dense_thr = dense_detect_spots(image_raw, 1.0)

# print("\r shape: {0}".format(spots.shape))

#plot.plot_detection(image_mip, spots, contrast=True)