# -*- coding: utf-8 -*-
"""Interactive FISH-Quant GUI.

A small standalone alternative to hand-editing runFISH_QUANT(...) calls in
fish_quant.py. Run it with:

    python fish_quant_gui.py

The startup screen offers three independent things to do:
  - Start Analysis: pick image(s) (.tif), then an interactive window with
    a threshold-modifier slider, spot radius / voxel size boxes, and
    Regular/Dense Detect buttons to run spot detection, plus a z-slice
    slider to page through the stack and check detections against the
    raw image. "Finish & Save" saves the resulting spots csv(s), then
    offers to filter them with ROI file(s). Analysis runs in one of two
    modes, chosen on the startup screen:
      * Multiple (or 1) tiffs -> 1 ROI: say how many tiffs to load, then
        switch between them in the review window (each keeps its own
        spots and settings) and filter all of their detections at the end
        with a single shared ROI.
      * 1 tiff -> multiple ROIs: the usual single-image run, except the
        ROI step asks how many ROIs and splits that one image's spots
        into one filtered csv per ROI.
  - Filter a csv with an ROI...: filter existing spots csv(s) against ROI
    file(s) directly, without opening any image.
  - View Detections from a csv...: load an image plus a previously-saved
    (or ROI-filtered) spots csv and browse it in the same z-slice viewer,
    without running any detection.

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

try:
  # lets files be dragged in from Finder/Explorer; plain tkinter can't do it.
  # Optional on purpose -- without it every screen still works via Browse...
  from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
  DND_FILES = TkinterDnD = None

import io
import logging
import os
import subprocess
import sys
import tempfile
import textwrap

import fish_quant_core as core


WINDOW_POS_ENV = "FISH_QUANT_WINDOW_POS"


def window_position():
  """Where this copy of the program should put its windows, as (x, y) screen
  pixels, or None to leave it to the window manager.

  Only a copy started by "Open a Second Window" gets one: the parent passes
  a cascaded position through the environment so the new run lands beside
  the one that opened it instead of straight on top of it.
  """
  try:
    x, y = (int(value) for value in os.environ.get(WINDOW_POS_ENV, "").split(","))
  except ValueError:
    return None
  return x, y


def place_window(window, position):
  """Move a tk window (including the matplotlib review window, which is one
  underneath) to `position`. Quietly does nothing on a backend or window
  manager that won't be told where to put things."""
  if not position:
    return
  try:
    window.wm_geometry(f"+{position[0]}+{position[1]}")
  except Exception:
    pass


def place_figure(fig, position):
  try:
    place_window(fig.canvas.manager.window, position)
  except Exception:
    pass   # non-Tk backend: no window to move


def _default_figsize(origin=None):
  """Size the review window to most of the actual screen, so images render
  as large as possible on whatever monitor is in use (falls back to a fixed
  size if the screen can't be queried for some reason).

  A copy that opens at an offset only has the screen from `origin` rightward
  and downward to play with, so it's sized against what's actually left --
  otherwise a cascaded window would hang off the edge of the display.
  """
  try:
    probe = tk.Tk()
    probe.withdraw()
    screen_w = probe.winfo_screenwidth()
    screen_h = probe.winfo_screenheight()
    probe.destroy()
    dpi = 100
    offset_x, offset_y = origin or (0, 0)
    available_w = max(screen_w - offset_x, 800)
    available_h = max(screen_h - offset_y, 600)
    floor_w, floor_h = (15, 8) if not origin else (10, 6)
    width_in = min(max(available_w * 0.92 / dpi, floor_w), 24)
    height_in = min(max(available_h * 0.85 / dpi, floor_h), 15)
    return (width_in, height_in)
  except Exception:
    return (16, 9)


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


TIFF_TYPES = [("TIFF images", "*.tif *.tiff"), ("All files", "*.*")]
ROI_TYPES = [("ImageJ ROI", "*.roi"), ("All files", "*.*")]
CSV_TYPES = [("CSV files", "*.csv"), ("All files", "*.*")]


def _as_path_list(paths):
  """askopenfilenames returns a tuple on most platforms but a single
  Tk-quoted string on some -- normalise both into a plain list."""
  if not paths:
    return []
  if isinstance(paths, str):
    root = tk._default_root
    if root is not None:
      return list(root.tk.splitlist(paths))
    return [paths]
  return list(paths)


_spawned = {"count": 0}   # how many copies this window has opened so far


def _cascade_position(parent):
  """Screen position for the next copy: down and right of this window, a
  step further along for each one opened, and never so far that its corner
  leaves the screen."""
  _spawned["count"] += 1
  step = 60 * _spawned["count"]
  x = parent.winfo_x() + step
  y = parent.winfo_y() + step
  max_x = max(parent.winfo_screenwidth() - 400, 0)
  max_y = max(parent.winfo_screenheight() - 300, 0)
  return min(max(x, 0), max_x), min(max(y, 0), max_y)


def launch_second_window(parent=None):
  """Start another, completely separate copy of this program.

  Nothing here is shared between runs -- each process gets its own windows,
  its own detections and its own session log -- so two sets of images can be
  worked through side by side. Same thing as running the program again in a
  second terminal, which also still works, except that the new copy is told
  where to put itself so it doesn't land on top of this one.
  """
  script = os.path.abspath(__file__)
  env = dict(os.environ)
  if parent is not None:
    try:
      x, y = _cascade_position(parent)
      env[WINDOW_POS_ENV] = f"{x},{y}"
    except Exception:
      env.pop(WINDOW_POS_ENV, None)   # can't read the screen: let the WM place it
  try:
    subprocess.Popen(
      [sys.executable, script],
      cwd=os.path.dirname(script) or None,
      env=env,
      # detach from this program's terminal, so quitting one (or Ctrl-C in
      # the terminal it was started from) doesn't take the other down
      start_new_session=True,
    )
  except Exception as exc:
    messagebox.showerror(
      "Could not open another window",
      f"{exc}\n\nYou can always start a second copy by hand: open another "
      f"terminal in the project folder and run the same command again.",
      parent=parent)


def _dropped_tiffs(data, widget):
  """Pull the TIFF paths out of a drop. The platform hands over one string
  with brace-quoted paths ("{/a/b (1).lif - c.tif} /d/e.tif"), which Tcl's
  own splitter unpacks correctly -- these file names are full of spaces and
  parentheses. Splitting goes through the dropped-on widget rather than
  tkinter's default-root global, which isn't guaranteed to point anywhere.
  Returns (tiff paths, how many other items were dropped)."""
  dropped = list(widget.tk.splitlist(data)) if isinstance(data, str) else list(data)
  tifs = [p for p in dropped if p.lower().endswith((".tif", ".tiff"))]
  return tifs, len(dropped) - len(tifs)


def _dnd_root():
  """A root window that accepts files dragged in from Finder/Explorer where
  that's available, and an ordinary one everywhere else. Returns
  (root, drag_and_drop_works)."""
  if TkinterDnD is not None:
    try:
      return TkinterDnD.Tk(), True
    except Exception:   # tkdnd present but not loadable on this machine
      pass
  return tk.Tk(), False


def ask_count(title, prompt, default=1, minimum=1, maximum=99):
  """Small modal asking for a whole number (how many tiffs / rois / csvs).
  Returns the number, or None if cancelled."""
  root = tk.Tk()
  root.title(title)
  root.resizable(False, False)

  result = {}
  var = tk.StringVar(value=str(default))

  tk.Label(root, text=prompt).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 4))
  entry = tk.Entry(root, textvariable=var, width=8)
  entry.grid(row=1, column=0, sticky="w", padx=14)
  entry.focus_set()
  entry.select_range(0, "end")

  def ok(_event=None):
    try:
      n = int(var.get())
    except ValueError:
      messagebox.showerror("Invalid number", "Please enter a whole number.", parent=root)
      return
    if not (minimum <= n <= maximum):
      messagebox.showerror("Invalid number", f"Please enter a number between {minimum} and {maximum}.", parent=root)
      return
    result["n"] = n
    root.destroy()

  def cancel():
    root.destroy()

  btns = tk.Frame(root)
  btns.grid(row=2, column=0, columnspan=2, pady=(12, 14))
  tk.Button(btns, text="OK", command=ok, width=8).pack(side="left", padx=6)
  tk.Button(btns, text="Cancel", command=cancel, width=8).pack(side="left", padx=6)
  root.bind("<Return>", ok)

  root.mainloop()
  return result.get("n")


def ask_files(title, count, filetypes, parent=None):
  """Ask for exactly `count` files in one multi-select dialog (hold Cmd/Ctrl
  or Shift to pick several), re-asking if the wrong number comes back.
  Returns a list of paths, or None if cancelled."""
  kwargs = {"filetypes": filetypes}
  if parent is not None:
    kwargs["parent"] = parent

  if count == 1:
    path = filedialog.askopenfilename(title=title, **kwargs)
    return [path] if path else None

  while True:
    paths = _as_path_list(filedialog.askopenfilenames(title=f"{title} — select {count}", **kwargs))
    if not paths:
      return None
    if len(paths) == count:
      return paths
    again = messagebox.askretrycancel(
      "Wrong number of files",
      f"You selected {len(paths)} file(s), but {count} were requested.\n\n"
      "Hold Cmd (Mac) or Ctrl (Windows) to select several files at once.\n\nTry again?",
      parent=parent,
    )
    if not again:
      return None


def pick_image_and_threshold():
  """First screen: analyze image(s), jump straight to filtering existing
  csv(s) with roi(s), or just view an existing csv's detections against an
  image.

  Analysis runs in one of two modes:
    "shared_roi" -- one or more tiffs (e.g. one channel each), reviewed in a
                    single window you can switch between, all filtered at
                    the end with one shared ROI.
    "multi_roi"  -- exactly one tiff, whose spots get split at the end into
                    one filtered csv per ROI.

  Returns a dict with a "mode" key ("analyze", "filter", "view", or
  missing/None if cancelled); "analyze" also carries "paths", "roi_mode"
  and "threshold"."""
  root, can_drop = _dnd_root()
  root.title("FISH-Quant Interactive")
  root.resizable(False, False)
  place_window(root, window_position())

  result = {}
  roi_mode_var = tk.StringVar(value="shared_roi")
  count_var = tk.StringVar(value="1")
  thr_var = tk.StringVar(value="1")
  files_label_var = tk.StringVar(value="Image file(s) (.tif) to analyze:")
  selected = []  # image paths, in the order they were picked

  tk.Label(root, text="Analysis mode:", font=("TkDefaultFont", 11, "bold")).grid(
    row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 2))

  def on_mode_change():
    if roi_mode_var.get() == "multi_roi":
      # this mode splits one image's spots per roi, so only one image
      del selected[1:]
      count_var.set("1")
      count_entry.configure(state="disabled")
      refresh_files()
    else:
      count_entry.configure(state="normal")

  tk.Radiobutton(
    root, text="Multiple (or 1) tiffs  →  1 ROI     (switch between images while detecting; one shared ROI at the end)",
    variable=roi_mode_var, value="shared_roi", command=on_mode_change, anchor="w", justify="left",
  ).grid(row=1, column=0, columnspan=3, sticky="w", padx=16)

  tk.Radiobutton(
    root, text="1 tiff  →  multiple ROIs     (one image, split into a separate filtered csv per ROI)",
    variable=roi_mode_var, value="multi_roi", command=on_mode_change, anchor="w", justify="left",
  ).grid(row=2, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 6))

  tk.Label(root, text="Number of tiff files to upload:").grid(row=3, column=0, sticky="w", padx=10)
  count_entry = tk.Entry(root, textvariable=count_var, width=8)
  count_entry.grid(row=3, column=1, sticky="w")

  tk.Label(root, textvariable=files_label_var).grid(
    row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))

  files_list = tk.Listbox(root, height=4, width=62)
  files_list.grid(row=5, column=0, columnspan=2, padx=(10, 0), pady=6, sticky="we")

  def refresh_files():
    files_list.delete(0, "end")
    for i, p in enumerate(selected):
      files_list.insert("end", f"{i + 1}. {os.path.basename(p)}")

  def on_drop(event):
    """Files dropped onto the box from Finder/Explorer. Dropping adds to
    what's already listed, so several tiffs can be dragged in a batch at a
    time; the count follows along by itself."""
    tifs, ignored = _dropped_tiffs(event.data, files_list)
    if not tifs:
      messagebox.showerror(
        "Not a TIFF image",
        "Only .tif / .tiff images can be analyzed. Drop the image files "
        "themselves, not a folder.", parent=root)
      return

    if roi_mode_var.get() == "multi_roi":
      selected[:] = tifs[-1:]           # this mode takes exactly one image
    else:
      selected.extend(p for p in tifs if p not in selected)
    count_var.set(str(len(selected)))
    refresh_files()

    if ignored:
      messagebox.showwarning(
        "Some files ignored",
        f"{ignored} dropped item(s) weren't .tif/.tiff images and were skipped.", parent=root)

  if can_drop:
    try:
      files_list.drop_target_register(DND_FILES)
      files_list.dnd_bind("<<Drop>>", on_drop)
      files_label_var.set("Image file(s) (.tif) — drag them onto the box below, or Browse...")
    except Exception:
      can_drop = False

  def browse():
    if roi_mode_var.get() == "multi_roi":
      n = 1
    else:
      try:
        n = int(count_var.get())
      except ValueError:
        messagebox.showerror("Invalid number", "Number of tiff files must be a whole number.", parent=root)
        return
      if not (1 <= n <= 99):
        messagebox.showerror("Invalid number", "Number of tiff files must be between 1 and 99.", parent=root)
        return

    paths = ask_files("Select image(s) to analyze", n, TIFF_TYPES, parent=root)
    if not paths:
      return
    selected[:] = paths
    count_var.set(str(len(selected)))
    refresh_files()

  tk.Button(root, text="Browse...", command=browse).grid(row=5, column=2, padx=10, pady=6)

  tk.Label(root, text="Starting threshold modifier:").grid(row=6, column=0, sticky="w", padx=10, pady=(6, 0))
  tk.Entry(root, textvariable=thr_var, width=10).grid(row=6, column=1, sticky="w", pady=(6, 0))

  def start():
    if not selected:
      messagebox.showerror("Missing file", "Please select image file(s) first.", parent=root)
      return
    if roi_mode_var.get() == "multi_roi" and len(selected) != 1:
      messagebox.showerror("Too many images",
                           "The '1 tiff → multiple ROIs' mode takes exactly one image.", parent=root)
      return
    try:
      thr = float(thr_var.get())
    except ValueError:
      messagebox.showerror("Invalid threshold", "Threshold modifier must be a number.", parent=root)
      return
    result["mode"] = "analyze"
    result["paths"] = list(selected)
    result["roi_mode"] = roi_mode_var.get()
    result["threshold"] = thr
    root.destroy()

  def go_filter_only():
    result["mode"] = "filter"
    root.destroy()

  def go_view_only():
    result["mode"] = "view"
    root.destroy()

  def cancel():
    root.destroy()

  tk.Label(root, text="— or —").grid(row=7, column=0, columnspan=3, pady=(10, 0))

  btn_frame = tk.Frame(root)
  btn_frame.grid(row=8, column=0, columnspan=3, pady=(14, 4))
  tk.Button(btn_frame, text="Start Analysis", command=start, width=16).pack(side="left", padx=6)
  tk.Button(btn_frame, text="Filter csv(s) with ROI(s)...", command=go_filter_only, width=24).pack(side="left", padx=6)

  btn_frame2 = tk.Frame(root)
  btn_frame2.grid(row=9, column=0, columnspan=3, pady=(4, 4))
  tk.Button(btn_frame2, text="View Detections from a csv...", command=go_view_only, width=26).pack(side="left", padx=6)
  tk.Button(btn_frame2, text="Cancel", command=cancel, width=10).pack(side="left", padx=6)

  btn_frame3 = tk.Frame(root)
  btn_frame3.grid(row=10, column=0, columnspan=3, pady=(4, 14))
  tk.Button(btn_frame3, text="Open a Second Window",
            command=lambda: launch_second_window(root), width=22).pack(side="left", padx=6)
  tk.Label(btn_frame3, text="(a separate run, for another set of images)",
           fg="#555555").pack(side="left", padx=(2, 6))

  on_mode_change()
  root.mainloop()
  return result


def _unique_path(path, used):
  """Keep two same-named inputs (e.g. rois with the same filename in
  different folders) from writing over each other's output."""
  candidate = path
  stem, ext = os.path.splitext(path)
  n = 2
  while candidate in used:
    candidate = f"{stem}_{n}{ext}"
    n += 1
  used.add(candidate)
  return candidate


def filter_csvs_with_rois(roi_paths, csv_paths):
  """Filter every csv by every roi. Returns one result dict per (csv, roi)
  pair: csv, roi, inside, total, output, error.

  With a single roi the output keeps the familiar <name>_filtered_ROI.csv
  name; with several, each output is named after the roi that produced it so
  the runs don't overwrite each other.
  """
  results = []
  used = set()
  spots_inside = 0
  csv_totals = {}   # by csv, so filtering one csv by several rois counts it once
  for csv_path in csv_paths:
    for roi_path in roi_paths:
      output_path = None
      if len(roi_paths) > 1:
        stem = os.path.splitext(os.path.basename(csv_path))[0]
        roi_stem = os.path.splitext(os.path.basename(roi_path))[0]
        output_path = _unique_path(
          os.path.join(os.path.dirname(csv_path), f"{stem}_filtered_{roi_stem}.csv"), used)
      try:
        total, inside, saved_to = core.filter_roi(roi_path, csv_path, output_path=output_path)
      except Exception as exc:
        results.append({"csv": csv_path, "roi": roi_path, "error": str(exc),
                        "inside": 0, "total": 0, "output": None})
        logging.info(f"ROI filter FAILED — ROI={os.path.basename(roi_path)} — CSV={csv_path}: {exc}")
        continue
      share = (100.0 * inside / total) if total else 0.0
      results.append({"csv": csv_path, "roi": roi_path, "error": None,
                      "inside": inside, "total": total, "output": saved_to})
      spots_inside += inside
      csv_totals[csv_path] = total
      logging.info(f"ROI filter: {inside} of {total} spots inside ({share:.1f}%) "
                   f"— ROI={os.path.basename(roi_path)} — saved to={saved_to}")
  if len(results) > 1:
    spots_total = sum(csv_totals.values())
    overall = (100.0 * spots_inside / spots_total) if spots_total else 0.0
    logging.info(f"ROI filter total: {spots_inside} of {spots_total} spots inside an ROI ({overall:.1f}%) "
                 f"over {len(csv_paths)} csv(s) × {len(roi_paths)} ROI(s)")
  return results


def roi_results_text(results):
  """Lay the outcomes out to be read rather than to fit on one line: each csv
  named once as a heading, its numbers indented underneath, and the shared
  output folder mentioned once at the end instead of on every row."""
  by_csv = {}
  for result in results:
    by_csv.setdefault(result["csv"], []).append(result)
  several_rois = len({result["roi"] for result in results}) > 1

  blocks = []
  for csv_path, rows in by_csv.items():
    lines = [os.path.basename(csv_path)]
    for row in rows:
      indent = "    "
      if several_rois:
        lines.append(f"    in {os.path.basename(row['roi'])}:")
        indent = "        "
      if row["error"]:
        lines.append(f"{indent}FAILED — {row['error']}")
        continue
      share = (100.0 * row["inside"] / row["total"]) if row["total"] else 0.0
      lines.append(f"{indent}{row['inside']:,} of {row['total']:,} spots inside  ({share:.1f}%)")
      # the output is the csv's own name plus a suffix, and that name is the
      # heading right above -- so only show the part that differs
      out_name = os.path.basename(row["output"])
      stem = os.path.splitext(os.path.basename(csv_path))[0]
      shown = "…" + out_name[len(stem):] if out_name.startswith(stem) else out_name
      lines.append(f"{indent}saved as  {shown}")
    blocks.append("\n".join(lines))

  text = "\n\n".join(blocks)

  done = [r for r in results if not r["error"]]
  if len(done) > 1:
    csv_totals = {r["csv"]: r["total"] for r in done}
    inside = sum(r["inside"] for r in done)
    total = sum(csv_totals.values())
    share = (100.0 * inside / total) if total else 0.0
    text += f"\n\n{'-' * 60}\nTotal:  {inside:,} of {total:,} spots inside an ROI  ({share:.1f}%)"

  folders = {os.path.dirname(r["output"]) for r in done}
  if len(folders) == 1:
    text += f"\n\nSaved in:\n    {folders.pop()}"
  return text


def show_results_window(title, text):
  """Show a block of results in a scrollable, monospaced, selectable window.
  A messagebox stretches itself to its longest line, which these file names
  turn into something unreadable."""
  root = tk.Tk()
  root.title(title)

  frame = tk.Frame(root)
  frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

  height = min(28, max(8, len(text.splitlines()) + 1))
  box = tk.Text(frame, wrap="none", width=96, height=height, font=("TkFixedFont",),
                borderwidth=1, relief="solid", padx=8, pady=8)
  yscroll = tk.Scrollbar(frame, orient="vertical", command=box.yview)
  xscroll = tk.Scrollbar(root, orient="horizontal", command=box.xview)
  box.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

  box.grid(row=0, column=0, sticky="nsew")
  yscroll.grid(row=0, column=1, sticky="ns")
  frame.rowconfigure(0, weight=1)
  frame.columnconfigure(0, weight=1)
  xscroll.pack(fill="x", padx=10)

  box.insert("1.0", text)
  box.configure(state="disabled")   # read-only, but still selectable to copy

  tk.Button(root, text="OK", command=root.destroy, width=10).pack(pady=(6, 10))
  root.bind("<Return>", lambda _event: root.destroy())
  root.mainloop()


def standalone_roi_filter():
  """Filter arbitrary spots csvs with arbitrary rois -- independent of any
  image currently open. Asks how many of each first: every csv picked is
  filtered by every roi picked, so both 1 roi × N csvs (one region, several
  channels) and N rois × 1 csv (several regions of one channel) work."""
  n_csv = ask_count("How many csv files?", "Number of spots csv files to filter:", default=1)
  if not n_csv:
    return

  n_roi = ask_count("How many ROI files?", "Number of ROI files to filter them with:", default=1)
  if not n_roi:
    return

  csv_paths = ask_files("Select spots csv to filter", n_csv, CSV_TYPES)
  if not csv_paths:
    return

  roi_paths = ask_files("Select ROI file", n_roi, ROI_TYPES)
  if not roi_paths:
    return

  results = filter_csvs_with_rois(roi_paths, csv_paths)
  show_results_window(
    "ROI filtering complete",
    f"Filtered {len(csv_paths)} csv file(s) with {len(roi_paths)} ROI file(s).\n\n"
    + roi_results_text(results))


def view_csv_detections():
  """Load an image and a previously-saved (or ROI-filtered) spots csv, and
  open the z-slice/brightness/LUT viewer with those spots overlaid --
  no detection is (re-)run."""
  image_path = filedialog.askopenfilename(
    title="Select image the csv's spots belong to",
    filetypes=TIFF_TYPES,
  )
  if not image_path:
    return

  csv_path = filedialog.askopenfilename(
    title="Select spots csv to view",
    filetypes=CSV_TYPES,
  )
  if not csv_path:
    return

  try:
    all_spots = core.load_spots_csv(csv_path)
  except Exception as exc:
    messagebox.showerror("Could not load csv", f"{csv_path}\n\n{exc}")
    return

  print(f"Loading {image_path} ...")
  image_raw = core.load_image(image_path)
  interactive_analysis([{"path": image_path, "image": image_raw, "spots": all_spots}], view_only=True)


def _spot_marker_size(spot_radius, voxel_size):
  """Width and height, in pixels, of the circle drawn around a detection.

  spot_radius is the physical radius in nm and voxel_size the nm each pixel
  covers, so radius / voxel is that radius in pixels -- double it and the
  drawn circle is exactly as wide as the spot it marks. Both are (z, y, x).
  """
  width = 2.0 * spot_radius[2] / voxel_size[2]
  height = 2.0 * spot_radius[1] / voxel_size[1]
  return max(width, 1.0), max(height, 1.0)


def _coarse_threshold_note(image_raw, auto_threshold, used_threshold, mod_min=0.05, mod_max=2.0):
  """Explain a modifier change that does nothing.

  bigfish LoG-filters an integer image in integer space, so the detection
  cutoff is effectively floor(threshold): whole bands of modifier values give
  byte-identical results, and on images that only occupy a sliver of the
  16-bit range (auto threshold of ~1-4 rather than hundreds) those bands are
  wider than the slider steps. Returns "" when the modifier is fine-grained
  enough to behave continuously, which is the normal case.
  """
  if image_raw.dtype.kind not in "ui" or auto_threshold <= 0:
    return ""
  if 1.0 / auto_threshold < 0.05:   # one whole number is a <0.05 nudge: fine
    return ""

  cutoff = float(np.floor(used_threshold))
  hints = []
  if (cutoff + 1) / auto_threshold <= mod_max:
    hints.append(f"≥{(cutoff + 1) / auto_threshold:.2f} for fewer")
  if cutoff / auto_threshold > mod_min:
    hints.append(f"<{cutoff / auto_threshold:.2f} for more")
  where = ", ".join(hints) if hints else "outside this slider's range"
  return (f"this image only spans {int(image_raw.min())}–{int(image_raw.max())} of the 16-bit range, so the cutoff"
          f" moves in whole numbers: the count won't budge until the modifier is {where}")


def _short_name(name, width):
  """Trim a filename to `width` characters, favouring the tail -- that's
  where the channel/sample suffixes that tell these files apart live."""
  if len(name) <= width:
    return name
  head = max(1, (width - 3) // 3)
  return f"{name[:head]}...{name[-(width - 3 - head):]}"


def interactive_analysis(images, initial_modifier=1.0, view_only=False):
  """Threshold + z-slice review window for one or more images.

  `images` is a list of dicts, one per image, with keys:
    "path"  -- source file, used for titles and for naming the saved csv
    "image" -- the raw (z, y, x) array
    "spots" -- optional (N, 3) array to open with (e.g. loaded from a csv)
               instead of starting empty

  With more than one image an "Image" panel appears on the right and you can
  switch between them at any time: each image keeps its own spots, threshold
  modifier, spot radius / voxel size, z-slice and brightness window, so a
  channel you've already dialled in stays exactly as you left it.

  view_only=True hides the detection controls (threshold modifier, spot
  radius, voxel size, Regular/Dense Detect) and shows a single Close
  button -- used for browsing an existing csv's spots, not detecting new ones.

  Returns the state dict: state["entries"] holds the per-image results
  (all_spots / thr_auto / modifier / spot_radius / voxel_size) and
  state["finished"] says whether Finish & Save was clicked.
  """
  entries = []
  for item in images:
    img = item["image"]
    # sane starting brightness window, derived from the image itself
    p95, p995 = np.percentile(img, [95, 99.5])
    vmin0 = max(1, int(round(p95)))
    vmax0 = max(vmin0 + 1, int(round(p995)))
    spots = item.get("spots")
    zmax = img.shape[0] - 1
    entries.append({
      "path": item.get("path", ""),
      "name": os.path.basename(item.get("path", "")) or "image",
      "image": img,
      "all_spots": spots if spots is not None else np.empty((0, 3)),
      "thr_auto": None,
      "modifier": initial_modifier,
      "last_method": None,        # detection to repeat when the threshold moves
      "detected_modifier": None,  # modifier the last detection was attempted at
      "spot_radius": core.DEFAULT_SPOT_RADIUS,
      "voxel_size": core.DEFAULT_VOXEL_SIZE,
      "zmax": zmax,
      "img_max": max(2, int(img.max())),
      "z": zmax // 2,
      "vmin": vmin0,
      "vmax": vmax0,
      "radius_xy": f"{core.DEFAULT_SPOT_RADIUS[2]:g}",
      "radius_z": f"{core.DEFAULT_SPOT_RADIUS[0]:g}",
      "voxel_xy": f"{core.DEFAULT_VOXEL_SIZE[2]:g}",
      "voxel_z": f"{core.DEFAULT_VOXEL_SIZE[0]:g}",
      "status": None,
    })

  state = {"entries": entries, "index": 0, "finished": False}
  multi = len(entries) > 1
  # set while widgets are being repointed at another image, so their
  # callbacks don't redraw against a half-updated state
  syncing = {"busy": False}

  def cur():
    return state["entries"][state["index"]]

  def default_status(entry):
    if view_only:
      return f"Viewing {len(entry['all_spots'])} spots loaded from csv"
    return ("Set a threshold modifier and click 'Regular Detect' or 'Dense Detect' to start"
            " — after that, changing the modifier re-runs that same detection automatically")

  first = entries[0]

  position = window_position()
  fig, (ax_raw, ax_ovl) = plt.subplots(1, 2, figsize=_default_figsize(position), sharex=True, sharey=True)
  window_title = "FISH-Quant Interactive — viewing csv" if view_only else "FISH-Quant Interactive — detection review"
  if multi:
    window_title += f" ({len(entries)} images)"
  fig.canvas.manager.set_window_title(window_title)
  place_figure(fig, position)   # keep a second copy clear of the first
  bottom_margin = 0.20 if view_only else 0.32
  # top leaves a header strip for the image name and up to three status lines
  # (the panel titles ride just above the axes, and a square image keeps the
  # axes box full height, so this has to clear the tallest case); the right
  # edge stops short of the LUT panel to leave room for the ▶ arrow
  plt.subplots_adjust(bottom=bottom_margin, top=0.87, right=0.845 if multi else 0.86)

  ax_raw.axis("off")
  ax_ovl.axis("off")

  im_raw = ax_raw.imshow(first["image"][first["z"]], cmap="gray", vmin=first["vmin"], vmax=first["vmax"])
  im_ovl = ax_ovl.imshow(first["image"][first["z"]], cmap="gray", vmin=first["vmin"], vmax=first["vmax"])
  # detections are circled at the physical size of the spot (radius ÷ voxel
  # size) and measured in data units rather than screen points, so a circle
  # keeps covering the same patch of image -- and the same spot -- however far
  # you zoom in with the toolbar
  spot_markers = EllipseCollection(
    widths=np.empty(0), heights=np.empty(0), angles=0, units="xy",
    offsets=np.empty((0, 2)), offset_transform=ax_ovl.transData,
    facecolors="none", edgecolors="red", linewidths=1.2)
  ax_ovl.add_collection(spot_markers, autolim=False)
  ax_raw.set_title(f"raw — z={first['z']}")
  ax_ovl.set_title("no detection run yet")

  # header strip, stacked in one left-aligned column so nothing can collide
  # sideways however long a file name or a status message gets:
  #   line 1 -- which image you're looking at (◀ ▶ step through them)
  #   line 2+ -- what the tool is doing / what the last detection found
  image_label = fig.text(0.012, 0.995, "", ha="left", va="top", fontsize=10.5, fontweight="bold")
  status = fig.text(0.012, 0.962, "", ha="left", va="top", fontsize=8.5, linespacing=1.25)

  def set_status(text, max_lines=3):
    """Wrap the status to the window width and cap how many lines it can
    take, so a long message can't run off the top or into the panel titles."""
    width = max(60, int(fig.get_size_inches()[0] * 11))
    lines = []
    for paragraph in text.splitlines() or [""]:
      lines.extend(textwrap.wrap(paragraph, width=width) or [""])
    if len(lines) > max_lines:
      lines = lines[:max_lines - 1] + [lines[max_lines - 1][:width - 1] + "…"]
    status.set_text("\n".join(lines))

  set_status(default_status(first))

  # LUT (lookup table) picker, à la Image > Lookup Tables in Fiji/ImageJ --
  # changes how raw intensities are colored, applied to both panels
  ax_lut = fig.add_axes([0.89, 0.40, 0.10, 0.50])
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
      # slider.valmin/valmax rather than the arguments: the z and brightness
      # sliders get re-ranged when you switch to a differently-sized image
      val = min(max(val, slider.valmin), slider.valmax)
      guard["busy"] = True
      slider.set_val(val)
      guard["busy"] = False
      box.set_val(f"{val:g}")

    slider.on_changed(on_slider_change)
    box.on_submit(on_box_submit)
    nudge_targets.append((box, slider, nudge_step))
    return slider, box

  if view_only:
    z_y, vmin_y, vmax_y = 0.15, 0.115, 0.08
  else:
    z_y, thr_y, vmin_y, vmax_y = 0.27, 0.235, 0.20, 0.165

  z_slider, _z_box = add_precise_slider(z_y, "z-slice", 0, first["zmax"], first["z"], valstep=1, nudge_step=1)
  vmin_slider, _vmin_box = add_precise_slider(vmin_y, "brightness min", 0, first["img_max"], first["vmin"], valstep=1, nudge_step=1)
  vmax_slider, _vmax_box = add_precise_slider(vmax_y, "brightness max", 1, first["img_max"], first["vmax"], valstep=1, nudge_step=1)
  if not view_only:
    thr_slider, _thr_box = add_precise_slider(thr_y, "threshold modifier", 0.05, 2.0, initial_modifier, nudge_step=0.01)

  # things to do once a slider has been *settled* on a new value (as opposed to
  # dragged through one) -- the auto re-detect below hangs off these
  settled_hooks = []

  def on_key_press(event):
    # "enter" means a value was typed into one of the boxes and accepted (the
    # box's own handler has already pushed it to the slider by now)
    if event.key not in ("up", "down", "enter"):
      return
    if event.key in ("up", "down"):
      direction = 1 if event.key == "up" else -1
      for box, slider, step in nudge_targets:
        if box.capturekeystrokes:
          new_val = min(max(slider.val + direction * step, slider.valmin), slider.valmax)
          slider.set_val(new_val)
          box.set_val(f"{new_val:g}")
          break
    for hook in settled_hooks:
      hook()

  def on_button_release(_event):
    # fires when a slider drag ends, rather than on every value the drag
    # passes through -- detection is far too slow to run mid-drag
    for hook in settled_hooks:
      hook()

  fig.canvas.mpl_connect("key_press_event", on_key_press)
  fig.canvas.mpl_connect("button_release_event", on_button_release)

  if not view_only:
    # spot_radius and voxel_size (nm) -- xy and z are edited separately since
    # bigfish expects (z, y, x); text boxes rather than sliders since these
    # are typed, not dragged
    default_radius_z, default_radius_y, default_radius_x = core.DEFAULT_SPOT_RADIUS
    default_voxel_z, default_voxel_y, default_voxel_x = core.DEFAULT_VOXEL_SIZE

    ax_radius_xy = fig.add_axes([0.30, 0.075, 0.12, 0.035])
    radius_xy_box = TextBox(ax_radius_xy, "spot radius xy (nm)   ", initial=str(default_radius_x))

    ax_radius_z = fig.add_axes([0.68, 0.075, 0.12, 0.035])
    radius_z_box = TextBox(ax_radius_z, "spot radius z (nm)   ", initial=str(default_radius_z))

    ax_voxel_xy = fig.add_axes([0.30, 0.115, 0.12, 0.035])
    voxel_xy_box = TextBox(ax_voxel_xy, "voxel size xy (nm)   ", initial=str(default_voxel_x))

    ax_voxel_z = fig.add_axes([0.68, 0.115, 0.12, 0.035])
    voxel_z_box = TextBox(ax_voxel_z, "voxel size z (nm)   ", initial=str(default_voxel_z))

  def redraw(_=None):
    if syncing["busy"]:
      return
    e = cur()
    image_raw = e["image"]
    z = min(int(round(z_slider.val)), e["zmax"])
    im_raw.set_data(image_raw[z])
    im_ovl.set_data(image_raw[z])
    im_raw.set_clim(vmin_slider.val, vmax_slider.val)
    im_ovl.set_clim(vmin_slider.val, vmax_slider.val)
    # images in one session can differ in xy size, so keep the drawn extent
    # tied to whichever one is currently showing
    height, width = image_raw.shape[1:]
    im_raw.set_extent((-0.5, width - 0.5, height - 0.5, -0.5))
    im_ovl.set_extent((-0.5, width - 0.5, height - 0.5, -0.5))

    all_spots = e["all_spots"]
    if len(all_spots):
      zr = np.round(all_spots[:, 0]).astype(int)
      on = all_spots[zr == z]
    else:
      on = np.empty((0, 3))
    spot_markers.set_offsets(on[:, [2, 1]] if len(on) else np.empty((0, 2)))
    # one width/height for the whole collection -- it's cycled over the
    # offsets, so this stays cheap with tens of thousands of spots
    width, height = _spot_marker_size(e["spot_radius"], e["voxel_size"])
    spot_markers.set_widths(np.array([width]))
    spot_markers.set_heights(np.array([height]))
    ax_raw.set_title(f"raw — z={z}")
    ax_ovl.set_title(f"detections — {len(on)} on this plane / {len(all_spots)} total")
    fig.canvas.draw_idle()

  z_slider.on_changed(redraw)
  vmin_slider.on_changed(redraw)
  vmax_slider.on_changed(redraw)

  def save_current():
    """Stash the widget values into the image they belong to, so switching
    away and back doesn't lose them."""
    e = cur()
    e["z"] = int(round(z_slider.val))
    e["vmin"] = vmin_slider.val
    e["vmax"] = vmax_slider.val
    e["status"] = status.get_text()
    if not view_only:
      e["modifier"] = thr_slider.val
      e["radius_xy"] = radius_xy_box.text
      e["radius_z"] = radius_z_box.text
      e["voxel_xy"] = voxel_xy_box.text
      e["voxel_z"] = voxel_z_box.text

  def _rerange(slider, valmin, valmax, val):
    slider.valmin = valmin
    slider.valmax = valmax
    slider.ax.set_xlim(valmin, valmax)
    slider.set_val(min(max(val, valmin), valmax))

  def apply_entry():
    """Point every widget at the currently-selected image."""
    e = cur()
    syncing["busy"] = True
    try:
      _rerange(z_slider, 0, e["zmax"], e["z"])
      _rerange(vmin_slider, 0, e["img_max"], e["vmin"])
      _rerange(vmax_slider, 1, e["img_max"], e["vmax"])
      if not view_only:
        thr_slider.set_val(e["modifier"])
        radius_xy_box.set_val(e["radius_xy"])
        radius_z_box.set_val(e["radius_z"])
        voxel_xy_box.set_val(e["voxel_xy"])
        voxel_z_box.set_val(e["voxel_z"])
    finally:
      syncing["busy"] = False

    height, width = e["image"].shape[1:]
    ax_raw.set_xlim(-0.5, width - 0.5)
    ax_raw.set_ylim(height - 0.5, -0.5)
    shown_name = _short_name(e["name"], 70)   # long enough to tell channels apart
    if multi:
      image_label.set_text(f"Image {state['index'] + 1} of {len(entries)} — {shown_name}")
    else:
      image_label.set_text(shown_name)
    set_status(e["status"] or default_status(e))
    redraw()

  if multi:
    # ◀ ▶ at the left and right edges of the window step through the loaded
    # images (wrapping around); each one keeps its own spots and settings, so
    # you can go back and forth between channels while working
    ax_prev = fig.add_axes([0.012, 0.47, 0.028, 0.10])
    prev_btn = Button(ax_prev, "◀")
    prev_btn.label.set_fontsize(16)

    ax_next = fig.add_axes([0.855, 0.47, 0.028, 0.10])
    next_btn = Button(ax_next, "▶")
    next_btn.label.set_fontsize(16)

    def step_image(delta):
      save_current()
      state["index"] = (state["index"] + delta) % len(state["entries"])
      apply_entry()

    prev_btn.on_clicked(lambda _event: step_image(-1))
    next_btn.on_clicked(lambda _event: step_image(1))

  if view_only:
    ax_close = fig.add_axes([0.37, 0.02, 0.16, 0.045])
    close_btn = Button(ax_close, "Close")

    def close(_event):
      state["finished"] = False
      plt.close(fig)

    close_btn.on_clicked(close)

  else:
    ax_regular = fig.add_axes([0.10, 0.02, 0.16, 0.045])
    regular_btn = Button(ax_regular, "Regular Detect")

    ax_dense = fig.add_axes([0.28, 0.02, 0.16, 0.045])
    dense_btn = Button(ax_dense, "Dense Detect")

    ax_finish = fig.add_axes([0.46, 0.02, 0.16, 0.045])
    finish_btn = Button(ax_finish, "Finish & Save")

    ax_cancel = fig.add_axes([0.64, 0.02, 0.16, 0.045])
    cancel_btn = Button(ax_cancel, "Cancel")

    def read_positive(box, label):
      val = float(box.text)
      if val <= 0:
        raise ValueError(f"{label} must be a positive number")
      return val

    DETECT_METHODS = {
      "regular detection": (core.detect_spots, ""),
      "dense detection": (core.dense_detect_spots,
                          " this decomposes dense/clustered regions and can take several minutes"),
    }
    detecting = {"busy": False}   # detection blocks the window; don't stack runs

    def run_detection(method_label, auto=False):
      # the window is frozen for as long as detection takes, so anything that
      # arrives meanwhile (another click, a queued auto re-run) is dropped
      if detecting["busy"]:
        return
      detecting["busy"] = True
      try:
        detect_fn, running_note = DETECT_METHODS[method_label]
        try:
          radius_xy = read_positive(radius_xy_box, "spot radius xy")
          radius_z = read_positive(radius_z_box, "spot radius z")
          voxel_xy = read_positive(voxel_xy_box, "voxel size xy")
          voxel_z = read_positive(voxel_z_box, "voxel size z")
        except ValueError as exc:
          set_status(f"{exc} (nm). Fix it and try again.")
          fig.canvas.draw_idle()
          return
        spot_radius = (radius_z, radius_xy, radius_xy)
        voxel_size = (voxel_z, voxel_xy, voxel_xy)

        entry = cur()
        image_raw = entry["image"]

        modifier = thr_slider.val
        # recorded before running, so a detection that fails isn't retried
        # over and over by the auto re-run below
        entry["detected_modifier"] = modifier

        lead = "Threshold modifier changed — re-running" if auto else "Running"
        set_status(f"{lead} {method_label} on the full stack...{running_note}")
        fig.canvas.draw()
        fig.canvas.flush_events()

        try:
          all_spots, thr_auto = detect_fn(image_raw, modifier, voxel_size=voxel_size, spot_radius=spot_radius)
        except Exception as exc:
          set_status(f"Detection failed with spot radius {spot_radius} / voxel size {voxel_size} "
                     f"(radius likely too small for this voxel size): {exc}")
          fig.canvas.draw_idle()
          return
        entry["all_spots"] = all_spots
        entry["thr_auto"] = thr_auto
        entry["modifier"] = modifier
        entry["spot_radius"] = spot_radius
        entry["voxel_size"] = voxel_size
        entry["last_method"] = method_label   # what an auto re-run will repeat

        used = thr_auto * modifier
        # one compact line per topic -- the full breakdown goes to the log
        coarse = _coarse_threshold_note(image_raw, thr_auto, used)
        set_status(
          f"[{method_label}]  auto threshold={thr_auto:.4g} × modifier={modifier:.3f}"
          f"  →  threshold used={used:.4g}   •   {len(all_spots)} spots found\n"
          f"spot radius (z,y,x)=({radius_z:g}, {radius_xy:g}, {radius_xy:g}) nm"
          f"    voxel size (z,y,x)=({voxel_z:g}, {voxel_xy:g}, {voxel_xy:g}) nm"
          + (f"\n{coarse}" if coarse else "")
        )
        logging.info(f"\n Image: {entry['path'] or entry['name']} \n Parameters: spot radius (z,y,x)={spot_radius} \n voxel size (z,y,x)={voxel_size} \n threshold modifier={modifier:.3f} \n Threshold used={used:.4g} \n total spots={len(all_spots)} \n method={method_label}\n original threshold={thr_auto:.4g}\n brightness window=({vmin_slider.val:g}, {vmax_slider.val:g})")
        redraw()
      finally:
        detecting["busy"] = False

    def run_regular(_event):
      run_detection("regular detection")

    def run_dense(_event):
      run_detection("dense detection")

    def rerun_on_threshold_change():
      """Moving the threshold modifier re-runs whichever detection was last
      used on this image -- seeing what the new threshold does is the whole
      point of the slider. Only fires once a value has been settled on (slider
      let go, or typed/nudged and accepted), never for the values a drag
      passes through, and only after that image has been detected on once."""
      entry = cur()
      if syncing["busy"] or detecting["busy"] or entry["last_method"] is None:
        return
      if entry["detected_modifier"] is not None and abs(thr_slider.val - entry["detected_modifier"]) < 1e-9:
        return
      run_detection(entry["last_method"], auto=True)

    settled_hooks.append(rerun_on_threshold_change)

    def finish(_event):
      save_current()
      if not any(len(e["all_spots"]) for e in state["entries"]):
        set_status("Run detection at least once before finishing.")
        fig.canvas.draw_idle()
        return
      empty = [e["name"] for e in state["entries"] if not len(e["all_spots"])]
      if empty and not messagebox.askyesno(
        "Some images have no detections",
        "No detection has been run (or nothing was found) for:\n\n  "
        + "\n  ".join(empty)
        + "\n\nFinish anyway? These images will be skipped when saving.",
      ):
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

  apply_entry()   # initial sync: draws any preloaded spots too
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


def save_spots_for_entries(entries):
  """Save each image's detections to its own csv. A single image keeps the
  familiar Save As dialog; several images share one output folder and are
  named after the tiff they came from. Returns a list of (entry, csv_path)."""
  detected = [e for e in entries if len(e["all_spots"])]
  if not detected:
    return []

  if len(detected) == 1:
    entry = detected[0]
    csv_path = save_csv_dialog(entry["path"], entry["all_spots"])
    if not csv_path:
      return []
    logging.info(f"Saved {len(entry['all_spots'])} spots to {csv_path}")
    return [(entry, csv_path)]

  out_dir = filedialog.askdirectory(
    title=f"Choose a folder to save {len(detected)} spots csv files into",
    initialdir=os.path.dirname(detected[0]["path"]) or ".",
  )
  if not out_dir:
    return []

  planned = []
  used = set()
  for entry in detected:
    stem = os.path.splitext(os.path.basename(entry["path"]))[0]
    planned.append((entry, _unique_path(os.path.join(out_dir, f"{stem}_spots.csv"), used)))

  clashes = [p for _, p in planned if os.path.exists(p)]
  if clashes and not messagebox.askyesno(
    "Overwrite existing files?",
    f"{len(clashes)} file(s) in that folder will be overwritten:\n\n  "
    + "\n  ".join(os.path.basename(p) for p in clashes)
    + "\n\nContinue?",
  ):
    return []

  saved = []
  for entry, csv_path in planned:
    core.save_spots_csv(entry["all_spots"], csv_path)
    logging.info(f"Saved {len(entry['all_spots'])} spots to {csv_path}")
    saved.append((entry, csv_path))
  return saved


def offer_shared_roi_filter(csv_paths):
  """End of the 'multiple (or 1) tiffs → 1 ROI' mode: one ROI file, applied
  to every csv that was just saved."""
  if not csv_paths:
    return

  names = "\n  ".join(os.path.basename(p) for p in csv_paths)
  if not messagebox.askyesno(
    "Filter with ROI?",
    f"Spots saved to:\n\n  {names}\n\nFilter all of them with one ROI now?",
  ):
    return

  roi_path = filedialog.askopenfilename(
    title="Select the ROI file to filter every csv with",
    filetypes=ROI_TYPES,
  )
  if not roi_path:
    return

  results = filter_csvs_with_rois([roi_path], csv_paths)
  show_results_window(
    "ROI filtering complete",
    f"ROI:  {os.path.basename(roi_path)}\n{' ' * 6}{os.path.dirname(roi_path)}\n\n"
    + roi_results_text(results))


def offer_multi_roi_filter(csv_path):
  """End of the '1 tiff → multiple ROIs' mode: split this one image's spots
  into a separate filtered csv per ROI."""
  if not messagebox.askyesno(
    "Filter with ROIs?",
    f"Spots saved to:\n{csv_path}\n\nSplit these spots into one filtered csv per ROI now?",
  ):
    return

  n_roi = ask_count("How many ROI files?",
                    "Number of ROI files to filter this csv with\n(one filtered csv is written per ROI):",
                    default=2)
  if not n_roi:
    return

  roi_paths = ask_files("Select ROI file", n_roi, ROI_TYPES)
  if not roi_paths:
    return

  results = filter_csvs_with_rois(roi_paths, [csv_path])
  show_results_window(
    "ROI filtering complete",
    f"Split one csv across {len(roi_paths)} ROI file(s).\n\n" + roi_results_text(results))


def open_session_log(log_data):
  """Show what happened this session in a text editor. It is deliberately
  never written to disk -- Save As from the editor to keep a copy."""
  if not log_data.strip():
    return

  if os.name == 'nt':  # Windows
    # Passing text directly to Notepad via command line is tricky,
    # so we use a temp file that Notepad treats as a separate stream.
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w') as f:
      f.write(log_data)
      temp_path = f.name

    # Open notepad. If they click Save, it defaults to "Save As"
    subprocess.Popen(['notepad.exe', temp_path])

  else:  # macOS / Linux
    # Use 'open -t' on Mac to open a temporary stream in TextEdit
    process = subprocess.Popen(['open', '-f', '-t'], stdin=subprocess.PIPE, text=True)
    process.communicate(input=log_data)


def main():
  log_buffer = io.StringIO()
  logging.basicConfig(stream=log_buffer, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
  choice = pick_image_and_threshold()
  mode = choice.get("mode")

  if mode == "filter":
    standalone_roi_filter()
    # the spot counts per ROI only exist in the log, so show it here too --
    # not just at the end of a full analysis session
    open_session_log(log_buffer.getvalue())
    log_buffer.close()
    return

  if mode == "view":
    view_csv_detections()
    return

  if mode != "analyze":
    print("No image selected. Exiting.")
    return

  image_paths = choice["paths"]
  roi_mode = choice.get("roi_mode", "shared_roi")
  initial_modifier = choice["threshold"]

  images = []
  for image_path in image_paths:
    print(f"Loading {image_path} ...")
    images.append({"path": image_path, "image": core.load_image(image_path)})

  state = interactive_analysis(images, initial_modifier)
  if not state.get("finished"):
    print("Cancelled before saving.")
    return

  saved = save_spots_for_entries(state["entries"])
  if not saved:
    print("Save cancelled.")
    return
  for entry, csv_path in saved:
    print(f"Saved {len(entry['all_spots'])} spots to {csv_path}")

  csv_paths = [csv_path for _, csv_path in saved]
  if roi_mode == "multi_roi":
    offer_multi_roi_filter(csv_paths[0])
  else:
    offer_shared_roi_filter(csv_paths)

  open_session_log(log_buffer.getvalue())
  log_buffer.close()


if __name__ == "__main__":
  main()
