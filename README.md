# Visual FISH-Quant

An interactive tool for detecting and reviewing smFISH spots in microscope
images, with a simple point-and-click interface (no coding required to use
it, only to install it).

This guide assumes you are starting from a completely empty computer —
no Python, no Git, nothing. Follow it top to bottom.

---

## 1. Install Python

You need Python installed before anything else.

### Windows

1. Go to https://www.python.org/downloads/ in your browser.
2. Click the big yellow "Download Python" button.
3. Open the downloaded file (it will be named something like
   `python-3.x.x-amd64.exe`).
4. **Important:** on the very first installer screen, check the box at the
   bottom that says **"Add python.exe to PATH"**. If you skip this, nothing
   later in this guide will work.
5. Click "Install Now" and let it finish.
6. Open the **Command Prompt** app (press the Windows key, type `cmd`,
   press Enter).
7. Type the following and press Enter:
   ```
   python --version
   ```
   You should see something like `Python 3.13.0`. If instead you see an
   error like `'python' is not recognized`, restart your computer and try
   again — the PATH change needs a restart to take effect.

### macOS

1. Go to https://www.python.org/downloads/ in your browser.
2. Click the button to download the macOS installer (a `.pkg` file).
3. Open the downloaded file and click through the installer (defaults are
   fine).
4. Open the **Terminal** app (press Cmd+Space, type `Terminal`, press
   Enter).
5. Type the following and press Enter:
   ```
   python3 --version
   ```
   You should see something like `Python 3.13.0`.

From here on, whenever this guide says `python`, Mac users should type
`python3` instead (Windows users can use `python` as written).

---

## 2. Get the code onto your computer

You do **not** need to install Git for this — the simplest way is to
download a ZIP file directly from GitHub.

1. Go to https://github.com/jmo7728/Visual_FISH_QUANT in your browser.
2. Click the green **"Code"** button, then click **"Download ZIP"**.
3. Find the downloaded ZIP file (usually in your Downloads folder) and
   unzip it (on Windows: right-click → "Extract All"; on Mac: double-click
   it).
4. You should now have a folder named `Visual_FISH_QUANT-main` (or similar).
   Move it somewhere you'll remember, e.g. your Desktop.

**Prefer using Git instead?** If you'd rather use Git (useful if the
project gets updated later and you want to pull new changes easily):

1. Install Git from https://git-scm.com/downloads and click through the
   installer with default options.
2. Open Command Prompt (Windows) or Terminal (Mac).
3. Run:
   ```
   git clone https://github.com/jmo7728/Visual_FISH_QUANT.git
   ```
4. This creates a `Visual_FISH_QUANT` folder with the code in it.

Either way, the rest of this guide assumes you have a folder containing
`fish_quant_gui.py` on your computer.

---

## 3. Open a terminal in that folder

- **Windows:** open the folder in File Explorer, click in the address bar
  at the top, type `cmd`, and press Enter. A Command Prompt will open
  already inside that folder.
- **macOS:** open the folder in Finder, right-click inside it (or
  Ctrl-click), and look for "New Terminal at Folder" (if you don't see
  this option, open Terminal normally and type `cd ` followed by dragging
  the folder into the Terminal window, then press Enter).

Confirm you're in the right place by typing:
```
dir
```
(Windows) or
```
ls
```
(Mac), and pressing Enter. You should see `fish_quant_gui.py` listed.

---

## 4. Install the required packages

This project uses a tool called **pipenv** to install everything it needs
(image processing, spot detection, and GUI libraries) in one isolated
step, without affecting anything else on your computer.

1. Install pipenv:
   ```
   python -m pip install pipenv
   ```
2. Install this project's dependencies:
   ```
   python -m pipenv install
   ```
   This will download and install a number of packages. **It can take
   several minutes** (some of the libraries, like napari and scikit-image,
   are large) — this is normal, just let it run.

If step 2 fails with a message about not finding a matching Python
version, run this instead, which tells pipenv to just use whatever Python
you already have:
```
python -m pipenv install --python python
```
(macOS: use `python3 -m pipenv install --python python3`)

---

## 5. Run the app

From that same terminal window, in that same folder, run:
```
python -m pipenv run python fish_quant_gui.py
```
(macOS: `python3 -m pipenv run python3 fish_quant_gui.py`)

A small window should pop up asking you to pick an image file. You're in.

**Every time you want to run it again later:** open a terminal in the
project folder (step 3) and run the command from this step again. You do
not need to repeat step 4 unless you re-download the project.

---

## 6. Using the app

- The first window lets you either:
  - **Start Analysis**: pick your `.tif` image(s) and a starting threshold
    modifier, then click through to the main review window.
    THIS IMAGE MUST BE IN 16-bit! Adjust via FIJI Image>Type>16-bit.
    Pick one of the two **analysis modes** at the top of this window first:
    - **Multiple (or 1) tiffs → 1 ROI**: type how many tiff files you want
      to upload, click **Browse...** and select exactly that many (hold
      Cmd on Mac / Ctrl on Windows to select several at once), **or drag
      the `.tif` files straight from Finder/Explorer onto the file box** —
      dropping adds to whatever is already listed, so you can drag them in
      one at a time or in batches, and the count keeps itself up to date.
      Anything dropped that isn't a `.tif`/`.tiff` is skipped. All of them
      open in one review window that you can switch between, and at the
      end every image's detections are filtered with the *same single* ROI
      — the usual case when the images are channels of one worm.
    - **1 tiff → multiple ROIs**: one image, exactly as before, except the
      ROI step at the end asks how many ROI files you want to upload and
      writes one filtered csv per ROI — the usual case when you want to
      count spots in several regions of the same image.
  - **Filter csv(s) with ROI(s)...**: skip straight to filtering existing
    spots csvs against ROI files, without opening any image. It asks how
    many csvs and how many ROIs you want to upload, then filters every csv
    with every ROI (so 1 ROI × several csvs and several ROIs × 1 csv both
    work).
  - **View Detections from a csv...**: pick a `.tif` image and a
    previously-saved (or ROI-filtered) spots csv, and browse those spots
    in the same z-slice/brightness/LUT viewer — no detection is run, this
    is just for checking a csv you already have against the image it
    came from.
  - **Open a Second Window**: starts another, completely separate copy of
    the program, so you can work through two different sets of images at
    the same time — each copy has its own detections, its own saved csvs
    and its own session log, and neither can disturb the other. The new
    copy opens down and to the right of the one that launched it (a
    little further along each time, so several stay distinguishable)
    rather than landing on top of it, and its review window is sized to
    the screen space left from that corner. Use it as
    many times as you like. (Running the same
    `pipenv run python fish_quant_gui.py` command again in another
    terminal does exactly the same thing.) Closing one copy leaves the
    others running.
- In the main review window:
  - The name of the image you're looking at is always shown in bold at the
    **top left** of the window (as `Image 2 of 3 — <file name>` when you
    loaded several), so you can tell at a glance which one is on screen.
  - If you loaded more than one tiff, a **◀** and a **▶** button appear at
    the left and right edges of the window — click them to step through
    your images (they wrap around, so ▶ on the last one goes back to the
    first). Each image remembers its own detected spots, threshold
    modifier, spot radius, voxel size, z-slice and brightness window, so
    you can go back and forth between channels and nothing you already
    dialed in is lost. Detection always runs on whichever image is
    currently on screen.
  - Every slider (**z-slice**, **threshold modifier**, **brightness
    min/max**) has a box next to it where you can type an exact value
    (press Enter), or click into that box and use the ↑/↓ arrow keys to
    nudge it by a small step.
  - Drag or type the **z-slice** control to page through the image and
    check detected spots (red circles) against the raw image.
  - The red circles are drawn at the **physical size of a spot** — the
    spot radius divided by the voxel size, i.e. how many pixels across
    the spot you're looking for actually is — so raising the spot radius
    (or lowering the voxel size) draws bigger circles. They're measured
    against the image rather than the screen, so when you zoom in with
    the magnifier in the toolbar the circles zoom with the image and keep
    ringing the same pixels. At full-image view they'll look like small
    dots; zoom in to judge whether a detection really covers a punctum.
  - Adjust **spot radius (xy/z, nm)** and **voxel size (xy/z, nm)** if
    spots are being detected as too small, too large, or not at all —
    voxel size should match your microscope's actual pixel size, and
    spot radius is roughly how big a real spot is physically.
  - Adjust the **threshold modifier** slider (0.05–2.0), then click one
    of:
    - **Regular Detect** — standard spot detection, fast (seconds to
      ~1 minute depending on image size).
    - **Dense Detect** — same detection, followed by decomposing
      dense/overlapping spot clusters into individual spots. This can
      take several minutes, especially at low/permissive thresholds
      that produce a lot of raw spots — the window will look frozen
      while it runs, that's expected. It's worth dialing in a threshold
      with Regular Detect first before trying Dense Detect.
  - **After that first click, changing the threshold modifier re-runs
    that same detection by itself** — whichever of Regular/Dense you used
    last on the image you're looking at. It only re-runs once you've
    settled on a value (let go of the slider, or typed one in the box and
    pressed Enter, or nudged it with ↑/↓), never for the values the
    slider passes through while you drag it, so you can drag freely and
    it will detect once when you let go. Bear in mind that if the last
    thing you ran was **Dense Detect**, every change re-runs the slow
    dense decomposition — dial the threshold in with Regular Detect
    first, then finish with one Dense Detect.
  - Each image remembers its own last-used method, so switching to an
    image you haven't detected on yet won't start anything until you
    click one of the buttons for it.
  - Use the **brightness min/max** sliders to make dim spots visible.
  - Use the **LUT** panel on the right to change how the image is
    colored (similar to Image > Lookup Tables in Fiji/ImageJ).
  - Click **Finish & Save** when you're happy with the detection, then
    choose where to save the resulting csv of spot coordinates. With
    several images loaded you instead pick one folder, and each image gets
    its own `<image name>_spots.csv` in it (any image you never ran
    detection on is skipped, after a warning).
  - You'll then be asked if you want to filter those spots with ROI(s) —
    you can do this immediately, or skip it and do it later from the first
    screen. What you're asked for depends on the mode you chose:
    - **Multiple (or 1) tiffs → 1 ROI**: one ROI file, applied to every
      csv that was just saved.
    - **1 tiff → multiple ROIs**: how many ROI files to upload, then that
      many files — each one produces its own
      `<image name>_spots_filtered_<roi name>.csv`.
  - Once that **Start Analysis** session finishes, a text editor window
    opens automatically (Notepad on Windows, TextEdit on Mac) with a
    timestamped log of everything that happened — the parameters used for
    each detection run (spot radius, voxel size, threshold modifier,
    threshold used, method, spot count) and the result of any ROI
    filtering you did. **This log is not saved anywhere by itself** — if
    you want to keep it, use Save/Save As in that editor window before
    closing it. The log also opens after **"Filter csv(s) with ROI(s)..."**
    from the first screen, since the per-ROI spot counts are recorded
    there. It does not appear for "View Detections from a csv...", which
    changes nothing.
  - The log is kept short on purpose: a parameter block for each
    detection you ran (image, spot radius, voxel size, threshold modifier,
    threshold used, spot count, method, brightness window), one line for
    each csv saved, and one line per ROI giving how many of the spots fell
    inside it and where the filtered csv went — plus a one-line total when
    a run covers more than one csv/ROI pair. Those ROI counts are the
    numbers you want for quantification, so use Save/Save As in the editor
    window if you need to keep them.

---
## Running Program after setup

- **If you have already finished doing setup/installation, follow these instructions!** 
- **Open Terminal**
- **`cd {path_to_program_where_installed}`**
- **`pipenv shell`**
- **`pipenv install`**
- **`pipenv run python fish_quant_gui.py`**
---
## Troubleshooting

- **`'python' is not recognized as an internal or external command`**
  (Windows): Python wasn't added to PATH during install. Re-run the
  Python installer, choose "Modify", and make sure "Add python.exe to
  PATH" is checked. Restart Command Prompt afterward.
- **`command not found: python3`** (Mac): reinstall Python from
  python.org (not just via Xcode Command Line Tools).
- **Install seems stuck or very slow**: this is expected the first time —
  the dependency list is large (~100 packages including scientific
  imaging libraries). Give it 5-10 minutes on a normal internet
  connection before assuming something is wrong.
- **A window flashes and immediately closes / nothing happens**: run the
  app from the terminal (as in step 5) rather than double-clicking the
  `.py` file, so you can actually see any error message that gets
  printed.
- **`ModuleNotFoundError: No module named 'tkinter'`** (Linux only):
  install it with your package manager, e.g.
  `sudo apt install python3-tk` on Ubuntu/Debian.
- **Dragging tiffs onto the file box does nothing**: drag-and-drop comes
  from the `tkinterdnd2` package. If you set the project up before that
  was added, run `python -m pipenv install` again to pick it up (the
  label above the box will read "drag them onto the box below" once it's
  working). The app deliberately still runs without it — you just use
  **Browse...** instead.
- **Crash right at the end of a Start Analysis session, mentioning `open`**
  (Linux only): the session-log viewer uses the `open` command to launch
  a text editor, which is a macOS-only tool and normally isn't installed
  on Linux. This happens after your csv has already been saved, so your
  results aren't lost — you just won't get the automatic log window on
  Linux for now.
- **Changing the threshold modifier doesn't change the spot count** (even
  by a big step like 0.20): this is the image's dynamic range, not the
  slider. bigfish filters a 16-bit image in whole numbers, so the cutoff
  it applies is really the *integer part* of "threshold used". On an
  image whose pixel values only span a sliver of the 16-bit range — some
  of these smFISH tiffs only reach 29–59 counts out of 65535 — the auto
  threshold comes out around 1–4, so a 0.20 change in the modifier moves
  the threshold by well under 1 and lands on the same integer cutoff:
  identical spots, identical count. When this is the case the status area
  says so after each detection, and tells you the modifier values that
  *will* move it, e.g.:
  > this image only spans 0–41 of the 16-bit range, so the cutoff moves
  > in whole numbers: the count won't budge until the modifier is ≥1.55
  > for fewer, <0.77 for more

  Jump straight to one of those values instead of nudging. The real fix
  is upstream: export/rescale the images so they use the full 16-bit
  range (in Fiji, Image > Adjust > Brightness/Contrast then Apply, or
  multiply by a constant with Process > Math > Multiply). An image that
  spans thousands of counts gives an auto threshold in the hundreds,
  where the modifier behaves smoothly.
- **Status bar says "Detection failed with spot radius ... voxel size ..."**:
  the spot radius is too small relative to the voxel size you entered
  (roughly, radius ÷ voxel size needs to be comfortably above ~0.3).
  Increase the spot radius or decrease the voxel size and try again.
- **Dense Detect seems to hang**: it can genuinely take several minutes,
  especially with a low threshold modifier producing lots of raw spots.
  There's no progress bar — give it time, or lower the number of raw
  spots first by tuning the threshold with Regular Detect.
