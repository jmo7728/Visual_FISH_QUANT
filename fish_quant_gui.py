# -*- coding: utf-8 -*-
"""Interactive FISH-Quant GUI.

A small standalone alternative to hand-editing runFISH_QUANT(...) calls in
fish_quant.py. Run it with:

    python fish_quant_gui.py

Flow:
  1. A small window to pick the image (.tif) to analyze.
  2. An interactive window with a threshold-modifier slider ("Run
     detection" re-runs spot detection at the chosen modifier) and a
     z-slice slider to page through the stack and check detections
     against the raw image.
  3. Once you click "Finish & Save", pick where to save the spots csv.
  4. You're then asked whether to filter those spots with an ROI file.

Detection/filtering logic itself lives in fish_quant_core.py, which mirrors
the logic already in fish_quant.py (kept untouched) minus the
napari/ipywidgets/notebook-only imports that don't belong in a plain script.
"""

import os

import numpy as np

import matplotlib
try:
  matplotlib.use("TkAgg")
except Exception:
  pass
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button, TextBox, RadioButtons
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.collections import EllipseCollection

import tkinter as tk
from tkinter import filedialog, messagebox

import fish_quant_core as core


def _solid_hue_lut(name, rgb):
  # matches ImageJ/Fiji's single-hue LUTs: a linear ramp from black to a
  # fully-saturated color, rather than a perceptual/multi-hue colormap
  return LinearSegmentedColormap.from_list(name, [(0, 0, 0), rgb])


LUTS = {
  "Grays": "gray",
  "Red": _solid_hue_lut("Red", (1, 0, 0)),
  "Green": _solid_hue_lut("Green", (0, 1, 0)),
  "Blue": _solid_hue_lut("Blue", (0, 0, 1)),
  "Cyan": _solid_hue_lut("Cyan", (0, 1, 1)),
  "Magenta": _solid_hue_lut("Magenta", (1, 0, 1)),
  "Yellow": _solid_hue_lut("Yellow", (1, 1, 0)),
  "Fire": "inferno",         # closest built-in match to ImageJ's "Fire" LUT
  "Spectrum": "nipy_spectral",  # closest built-in match to ImageJ's "Spectrum" LUT
}


def pick_image_and_threshold():
  """First screen: analyze a new image, or jump straight to filtering an
  existing csv with an roi. Returns a dict with a "mode" key ("analyze",
  "filter", or missing/None if cancelled)."""
  root = tk.Tk()
  root.title("FISH-Quant Interactive")
  root.resizable(False, False)

  result = {}
  path_var = tk.StringVar()
  thr_var = tk.StringVar(value="0.35")

  tk.Label(root, text="Image file (.tif) to analyze:").grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 0))

  entry = tk.Entry(root, textvariable=path_var, width=52)
  entry.grid(row=1, column=0, columnspan=2, padx=(10, 0), pady=6, sticky="we")

  def browse():
    p = filedialog.askopenfilename(
      title="Select image to analyze",
      filetypes=[("TIFF images", "*.tif *.tiff"), ("All files", "*.*")],
    )
    if p:
      path_var.set(p)

  tk.Button(root, text="Browse...", command=browse).grid(row=1, column=2, padx=10, pady=6)

  tk.Label(root, text="Starting threshold modifier:").grid(row=2, column=0, sticky="w", padx=10, pady=(6, 0))
  tk.Entry(root, textvariable=thr_var, width=10).grid(row=2, column=1, sticky="w", pady=(6, 0))

  def start():
    if not path_var.get():
      messagebox.showerror("Missing file", "Please select an image file first.")
      return
    try:
      thr = float(thr_var.get())
    except ValueError:
      messagebox.showerror("Invalid threshold", "Threshold modifier must be a number.")
      return
    result["mode"] = "analyze"
    result["path"] = path_var.get()
    result["threshold"] = thr
    root.destroy()

  def go_filter_only():
    result["mode"] = "filter"
    root.destroy()

  def cancel():
    root.destroy()

  tk.Label(root, text="— or —").grid(row=3, column=0, columnspan=3, pady=(10, 0))

  btn_frame = tk.Frame(root)
  btn_frame.grid(row=4, column=0, columnspan=3, pady=14)
  tk.Button(btn_frame, text="Start Analysis", command=start, width=16).pack(side="left", padx=6)
  tk.Button(btn_frame, text="Filter a csv with an ROI...", command=go_filter_only, width=22).pack(side="left", padx=6)
  tk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side="left", padx=6)

  root.mainloop()
  return result


def standalone_roi_filter():
  """Filter an arbitrary spots csv with an arbitrary roi -- independent of
  any image currently open, taking both file paths as separate inputs."""
  roi_path = filedialog.askopenfilename(
    title="Select ROI file",
    filetypes=[("ImageJ ROI", "*.roi"), ("All files", "*.*")],
  )
  if not roi_path:
    return

  csv_path = filedialog.askopenfilename(
    title="Select spots csv to filter",
    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
  )
  if not csv_path:
    return

  try:
    total, inside, output_path = core.filter_roi(roi_path, csv_path)
  except Exception as exc:
    messagebox.showerror("Filtering failed", f"Could not filter this csv with this ROI:\n{exc}")
    return

  messagebox.showinfo(
    "ROI filtering complete",
    f"ROI:\n{roi_path}\n\nCSV:\n{csv_path}\n\n"
    f"Total spots: {total}\nInside ROI: {inside}\n\nSaved to:\n{output_path}",
  )


def interactive_analysis(image_raw, initial_modifier):
  """Threshold + z-slice review window. Returns dict with all_spots/thr/finished."""
  state = {
    "all_spots": np.empty((0, 3)),
    "thr_auto": None,
    "modifier": initial_modifier,
    "spot_radius": core.DEFAULT_SPOT_RADIUS,
    "voxel_size": core.DEFAULT_VOXEL_SIZE,
    "finished": False,
  }

  zmax = image_raw.shape[0] - 1
  z0 = zmax // 2

  # sane starting brightness window, derived from the image itself
  p95, p995 = np.percentile(image_raw, [95, 99.5])
  vmin0 = max(1, int(round(p95)))
  vmax0 = max(vmin0 + 1, int(round(p995)))
  img_max = max(2, int(image_raw.max()))

  fig, (ax_raw, ax_ovl) = plt.subplots(1, 2, figsize=(15, 8), sharex=True, sharey=True)
  fig.canvas.manager.set_window_title("FISH-Quant Interactive — detection review")
  plt.subplots_adjust(bottom=0.46, top=0.90, right=0.86)

  im_raw = ax_raw.imshow(image_raw[z0], cmap="gray", vmin=vmin0, vmax=vmax0)
  im_ovl = ax_ovl.imshow(image_raw[z0], cmap="gray", vmin=vmin0, vmax=vmax0)
  scat = ax_ovl.scatter([], [], s=10, facecolors="none", edgecolors="red", linewidths=1.2)
  ax_raw.set_title(f"raw — z={z0}")
  ax_ovl.set_title("no detection run yet")

  status = fig.text(0.5, 0.955, "Set a threshold modifier and click 'Regular Detect' or 'Dense Detect' to start",
                     ha="center", fontsize=10)

  # LUT (lookup table) picker, à la Image > Lookup Tables in Fiji/ImageJ --
  # changes how raw intensities are colored, applied to both panels
  ax_lut = fig.add_axes([0.89, 0.45, 0.10, 0.40])
  ax_lut.set_title("LUT", fontsize=9)
  lut_radio = RadioButtons(ax_lut, list(LUTS.keys()), active=0)
  for lbl in lut_radio.labels:
    lbl.set_fontsize(8)

  def set_lut(label):
    cmap = LUTS[label]
    im_raw.set_cmap(cmap)
    im_ovl.set_cmap(cmap)
    fig.canvas.draw_idle()

  lut_radio.on_clicked(set_lut)

  # each slider gets a paired text box (type an exact value, press Enter) and
  # can be nudged with the up/down arrow keys while that box has focus
  nudge_targets = []  # (textbox, slider, step) -- checked on every keypress

  def add_precise_slider(y, label, valmin, valmax, valinit, valstep=None, nudge_step=1):
    ax_s = fig.add_axes([0.15, y, 0.55, 0.025])
    slider = Slider(ax_s, label, valmin, valmax, valinit=valinit, valstep=valstep)

    ax_b = fig.add_axes([0.76, y - 0.003, 0.09, 0.03])
    box = TextBox(ax_b, "", initial=f"{valinit:g}")

    guard = {"busy": False}

    def on_slider_change(val):
      if guard["busy"]:
        return
      guard["busy"] = True
      box.set_val(f"{val:g}")
      guard["busy"] = False

    def on_box_submit(text):
      try:
        val = float(text)
      except ValueError:
        box.set_val(f"{slider.val:g}")
        return
      val = min(max(val, valmin), valmax)
      guard["busy"] = True
      slider.set_val(val)
      guard["busy"] = False
      box.set_val(f"{val:g}")

    slider.on_changed(on_slider_change)
    box.on_submit(on_box_submit)
    nudge_targets.append((box, slider, nudge_step))
    return slider, box

  z_slider, _z_box = add_precise_slider(0.37, "z-slice", 0, zmax, z0, valstep=1, nudge_step=1)
  thr_slider, _thr_box = add_precise_slider(0.32, "threshold modifier", 0.05, 2.0, initial_modifier, nudge_step=0.01)
  vmin_slider, _vmin_box = add_precise_slider(0.27, "brightness min", 0, img_max, vmin0, valstep=1, nudge_step=1)
  vmax_slider, _vmax_box = add_precise_slider(0.22, "brightness max", 1, img_max, vmax0, valstep=1, nudge_step=1)

  def on_key_press(event):
    if event.key not in ("up", "down"):
      return
    direction = 1 if event.key == "up" else -1
    for box, slider, step in nudge_targets:
      if box.capturekeystrokes:
        new_val = min(max(slider.val + direction * step, slider.valmin), slider.valmax)
        slider.set_val(new_val)
        box.set_val(f"{new_val:g}")
        break

  fig.canvas.mpl_connect("key_press_event", on_key_press)

  # spot_radius and voxel_size (nm) -- xy and z are edited separately since
  # bigfish expects (z, y, x); text boxes rather than sliders since these
  # are typed, not dragged
  default_radius_z, default_radius_y, default_radius_x = core.DEFAULT_SPOT_RADIUS
  default_voxel_z, default_voxel_y, default_voxel_x = core.DEFAULT_VOXEL_SIZE

  ax_radius_xy = fig.add_axes([0.30, 0.09, 0.12, 0.04])
  radius_xy_box = TextBox(ax_radius_xy, "spot radius xy (nm)   ", initial=str(default_radius_x))

  ax_radius_z = fig.add_axes([0.68, 0.09, 0.12, 0.04])
  radius_z_box = TextBox(ax_radius_z, "spot radius z (nm)   ", initial=str(default_radius_z))

  ax_voxel_xy = fig.add_axes([0.30, 0.14, 0.12, 0.04])
  voxel_xy_box = TextBox(ax_voxel_xy, "voxel size xy (nm)   ", initial=str(default_voxel_x))

  ax_voxel_z = fig.add_axes([0.68, 0.14, 0.12, 0.04])
  voxel_z_box = TextBox(ax_voxel_z, "voxel size z (nm)   ", initial=str(default_voxel_z))

  def redraw(_=None):
    z = int(round(z_slider.val))
    im_raw.set_data(image_raw[z])
    im_ovl.set_data(image_raw[z])
    im_raw.set_clim(vmin_slider.val, vmax_slider.val)
    im_ovl.set_clim(vmin_slider.val, vmax_slider.val)

    all_spots = state["all_spots"]
    if len(all_spots):
      zr = np.round(all_spots[:, 0]).astype(int)
      on = all_spots[zr == z]
    else:
      on = np.empty((0, 3))
    scat.set_offsets(on[:, [2, 1]] if len(on) else np.empty((0, 2)))
    ax_raw.set_title(f"raw — z={z}")
    ax_ovl.set_title(f"detections — {len(on)} on this plane / {len(all_spots)} total")
    fig.canvas.draw_idle()

  z_slider.on_changed(redraw)
  vmin_slider.on_changed(redraw)
  vmax_slider.on_changed(redraw)

  ax_regular = fig.add_axes([0.10, 0.03, 0.16, 0.05])
  regular_btn = Button(ax_regular, "Regular Detect")

  ax_dense = fig.add_axes([0.28, 0.03, 0.16, 0.05])
  dense_btn = Button(ax_dense, "Dense Detect")

  ax_finish = fig.add_axes([0.46, 0.03, 0.16, 0.05])
  finish_btn = Button(ax_finish, "Finish & Save")

  ax_cancel = fig.add_axes([0.64, 0.03, 0.16, 0.05])
  cancel_btn = Button(ax_cancel, "Cancel")

  def read_positive(box, label):
    val = float(box.text)
    if val <= 0:
      raise ValueError(f"{label} must be a positive number")
    return val

  def run_detection(detect_fn, method_label, running_note=""):
    try:
      radius_xy = read_positive(radius_xy_box, "spot radius xy")
      radius_z = read_positive(radius_z_box, "spot radius z")
      voxel_xy = read_positive(voxel_xy_box, "voxel size xy")
      voxel_z = read_positive(voxel_z_box, "voxel size z")
    except ValueError as exc:
      status.set_text(f"{exc} (nm). Fix it and try again.")
      fig.canvas.draw_idle()
      return
    spot_radius = (radius_z, radius_xy, radius_xy)
    voxel_size = (voxel_z, voxel_xy, voxel_xy)

    status.set_text(f"Running {method_label} on the full stack...{running_note}")
    fig.canvas.draw()
    fig.canvas.flush_events()

    modifier = thr_slider.val
    try:
      all_spots, thr_auto = detect_fn(image_raw, modifier, voxel_size=voxel_size, spot_radius=spot_radius)
    except Exception as exc:
      status.set_text(f"Detection failed with spot radius {spot_radius} / voxel size {voxel_size} "
                       f"(radius likely too small for this voxel size): {exc}")
      fig.canvas.draw_idle()
      return
    state["all_spots"] = all_spots
    state["thr_auto"] = thr_auto
    state["modifier"] = modifier
    state["spot_radius"] = spot_radius
    state["voxel_size"] = voxel_size

    used = thr_auto * modifier
    status.set_text(
      f"[{method_label}]  auto threshold={thr_auto:.4g}   modifier={modifier:.3f}   threshold used={used:.4g}   "
      f"spot radius (z,y,x)={spot_radius}   voxel size (z,y,x)={voxel_size}   total spots={len(all_spots)}"
    )
    redraw()

  def run_regular(_event):
    run_detection(core.detect_spots, "regular detection")

  def run_dense(_event):
    run_detection(core.dense_detect_spots, "dense detection",
                   running_note=" this decomposes dense/clustered regions and can take several minutes")

  def finish(_event):
    if len(state["all_spots"]) == 0:
      status.set_text("Run detection at least once before finishing.")
      fig.canvas.draw_idle()
      return
    state["finished"] = True
    plt.close(fig)

  def cancel(_event):
    state["finished"] = False
    plt.close(fig)

  regular_btn.on_clicked(run_regular)
  dense_btn.on_clicked(run_dense)
  finish_btn.on_clicked(finish)
  cancel_btn.on_clicked(cancel)

  plt.show()
  return state


def save_csv_dialog(source_image_path, all_spots):
  default_dir = os.path.dirname(source_image_path) or "."
  default_name = os.path.splitext(os.path.basename(source_image_path))[0] + "_spots.csv"

  out_path = filedialog.asksaveasfilename(
    title="Save detected spots as...",
    initialdir=default_dir,
    initialfile=default_name,
    defaultextension=".csv",
    filetypes=[("CSV files", "*.csv")],
  )
  if not out_path:
    return None
  return core.save_spots_csv(all_spots, out_path)


def offer_roi_filter(csv_path):
  do_filter = messagebox.askyesno(
    "Filter with ROI?",
    f"Spots saved to:\n{csv_path}\n\nFilter these spots using an ROI now?",
  )
  if not do_filter:
    return

  roi_path = filedialog.askopenfilename(
    title="Select ROI file",
    filetypes=[("ImageJ ROI", "*.roi"), ("All files", "*.*")],
  )
  if not roi_path:
    return

  total, inside, output_path = core.filter_roi(roi_path, csv_path)
  messagebox.showinfo(
    "ROI filtering complete",
    f"Total spots: {total}\nInside ROI: {inside}\n\nSaved to:\n{output_path}",
  )


def main():
  choice = pick_image_and_threshold()
  mode = choice.get("mode")

  if mode == "filter":
    standalone_roi_filter()
    return

  if mode != "analyze":
    print("No image selected. Exiting.")
    return

  image_path = choice["path"]
  initial_modifier = choice["threshold"]

  print(f"Loading {image_path} ...")
  image_raw = core.load_image(image_path)

  state = interactive_analysis(image_raw, initial_modifier)
  if not state.get("finished") or len(state["all_spots"]) == 0:
    print("Cancelled before saving.")
    return

  csv_path = save_csv_dialog(image_path, state["all_spots"])
  if not csv_path:
    print("Save cancelled.")
    return
  print(f"Saved {len(state['all_spots'])} spots to {csv_path}")

  offer_roi_filter(csv_path)


if __name__ == "__main__":
  main()
