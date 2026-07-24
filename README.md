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
  - **Start Analysis**: pick a `.tif` image and a starting threshold
    modifier, then click through to the main review window.
    THIS IMAGE MUST BE IN 16-bit! Adjust via FIJI Image>Type>16-bit.
  - **Filter a csv with an ROI...**: skip straight to filtering an
    existing spots csv against an ROI file, without opening any image.
  - **View Detections from a csv...**: pick a `.tif` image and a
    previously-saved (or ROI-filtered) spots csv, and browse those spots
    in the same z-slice/brightness/LUT viewer — no detection is run, this
    is just for checking a csv you already have against the image it
    came from.
- In the main review window:
  - Every slider (**z-slice**, **threshold modifier**, **brightness
    min/max**) has a box next to it where you can type an exact value
    (press Enter), or click into that box and use the ↑/↓ arrow keys to
    nudge it by a small step.
  - Drag or type the **z-slice** control to page through the image and
    check detected spots (red circles) against the raw image.
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
  - Use the **brightness min/max** sliders to make dim spots visible.
  - Use the **LUT** panel on the right to change how the image is
    colored (similar to Image > Lookup Tables in Fiji/ImageJ).
  - Click **Finish & Save** when you're happy with the detection, then
    choose where to save the resulting csv of spot coordinates.
  - You'll then be asked if you want to filter those spots with an ROI
    file — you can do this immediately, or skip it and do it later from
    the first screen.
  - Once that **Start Analysis** session finishes, a text editor window
    opens automatically (Notepad on Windows, TextEdit on Mac) with a
    timestamped log of everything that happened — the parameters used for
    each detection run (spot radius, voxel size, threshold modifier,
    threshold used, method, spot count) and the result of any ROI
    filtering you did. **This log is not saved anywhere by itself** — if
    you want to keep it, use Save/Save As in that editor window before
    closing it. This log window only appears after a full Start Analysis
    session; it doesn't show up when you only use "Filter a csv with an
    ROI..." or "View Detections from a csv..." from the first screen.

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
- **Crash right at the end of a Start Analysis session, mentioning `open`**
  (Linux only): the session-log viewer uses the `open` command to launch
  a text editor, which is a macOS-only tool and normally isn't installed
  on Linux. This happens after your csv has already been saved, so your
  results aren't lost — you just won't get the automatic log window on
  Linux for now.
- **Status bar says "Detection failed with spot radius ... voxel size ..."**:
  the spot radius is too small relative to the voxel size you entered
  (roughly, radius ÷ voxel size needs to be comfortably above ~0.3).
  Increase the spot radius or decrease the voxel size and try again.
- **Dense Detect seems to hang**: it can genuinely take several minutes,
  especially with a low threshold modifier producing lots of raw spots.
  There's no progress bar — give it time, or lower the number of raw
  spots first by tuning the threshold with Regular Detect.
