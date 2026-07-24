# ThorFP ROI Tools

Quality-control and ROI re-extraction utilities for ThorLabs fiber photometry
(FIP) recordings stored as raw 16-bit binary movies.

The workflow is two steps:

1. **`ThorFP_ROI_QA.py`** — visually check that the existing ROIs line up with
   the recorded field of view.
2. **`ThorFP_ROI_reextraction.py`** — if the ROIs are off, draw new circular
   ROIs on the average image and re-extract the ROI time courses from the raw
   movies.

---

## Data layout

Both scripts expect a session folder containing a `fib` subfolder with the raw
movies and the original ROI files:

```
<session_folder>/
└── fib/
    ├── FIP_RawG_*        # green signal movie   (470 nm)
    ├── FIP_RawR_*        # red signal movie
    ├── FIP_RawIso_*      # isosbestic movie     (415 nm, green control)
    ├── FIP_ROIsG-Iso_*   # original green ROIs (shared by G and Iso)
    └── FIP_ROIsR_*       # original red ROIs
```

Movies are raw binary, `uint16`, `frame_width × frame_height` pixels per frame
with no header (default `200 × 200`). ROI files are CSVs with `RoiIndex`, `X`,
`Y` columns describing polygon vertices.

---

## Scripts

### `ThorFP_ROI_QA.py`

Loads the average of a frame range for the green and red channels and overlays
the existing ROI polygons, so you can confirm the ROIs match the movie before
trusting any downstream time courses.

Key points:

- **Orientation handling.** ROI and movie coordinate conventions can differ.
  `ORIENTATION` (`"none"`, `"transpose"`, `"flip_y"`, `"flip_x"`) lets you pick
  the transform that makes the ROIs land on the fibers. The current setting is
  shown in the figure title.
- **Automatic brightness.** The display range is set from image percentiles
  (`VMIN_PCT` / `VMAX_PCT`), so hot or saturated pixels no longer force manual
  `vmax` tuning.

example image:


<img width="800" height="400" alt="Screenshot 2026-07-24 at 12 40 36" src="https://github.com/user-attachments/assets/36535769-21d7-4983-a392-b481f3e9c134" />

  

### `ThorFP_ROI_reextraction.py`

Interactive tool to redraw circular ROIs and re-extract time courses (mean
pixel value inside each ROI) from the raw movies.

Workflow:

1. Shows the average image of the green signal movie (`FIP_RawG_`).
2. **Draw circular ROIs** by click-drag (click = center, drag = radius).
   - `u` — undo the last ROI
   - `Enter` — finish drawing
3. Time courses are computed from the raw movies and saved as CSVs.

Key points:

- **Green extracts both channels.** For `CHANNEL = "G"`, the same ROIs are
  applied to both the signal movie (`FIP_RawG_`) and the isosbestic movie
  (`FIP_RawIso_`). For `CHANNEL = "R"`, only `FIP_RawR_` is used.
- **Consistent orientation.** The same `ORIENTATION` transform is applied to the
  display image and to every movie frame, so the drawn ROIs always match the
  extracted pixels. Keep `ORIENTATION` identical to the value that lined up in
  the QA script.
- **Configurable output folder.** Set `output_folder` to save the results
  anywhere; leave it as `None` to save next to the movies (in `fib`).
- **Timestamped outputs.** ROI and time-course files from a single run share the
  same date/time in their names, making them easy to pair.
- **Redraw or reuse.** With `DRAW_NEW = False`, the most recent re-extracted ROI
  file is loaded instead of drawing again.
- **Efficient reading.** Movies are memory-mapped and read in chunks, so long
  recordings do not need to fit in memory.
- **Overview plot.** The average image with ROIs plus the time courses, colored
  by channel (G = green, Iso = blue, R = red).

---

## Configuration

Edit the settings block near the top of each script:

| Setting | Meaning |
| --- | --- |
| `session_folder` | Path to the recording session (contains `fib/`). |
| `output_folder` | Where to save outputs (re-extraction script). `None` → save in `fib`. |
| `CHANNEL` | `"G"` (green + isosbestic) or `"R"` (red). |
| `ORIENTATION` | Coordinate transform: `"none"`, `"transpose"`, `"flip_y"`, `"flip_x"`. |
| `START_FRAME` / `END_FRAME` | Frame range used to build the average image. |
| `FRAME_WIDTH` / `FRAME_HEIGHT` | Frame dimensions in pixels. |
| `VMIN_PCT` / `VMAX_PCT` | Percentiles for automatic display brightness. |
| `DRAW_NEW` | Re-extraction only: draw new ROIs (`True`) or load the latest saved ones (`False`). |

---

## Output files

The re-extraction script writes files prefixed with `reextracted_`. The date and
time reflect when the re-extraction was run, and are shared between the ROI file
and its time courses.

For `CHANNEL = "G"`:

```
reextracted_FIP_ROIsG-Iso_<YYYY-MM-DDTHH_MM_SS>.csv   # ROIs (shared by G and Iso)
reextracted_TS_FLIR_G_<YYYY-MM-DDTHH_MM_SS>.csv       # green signal time courses
reextracted_TS_FLIR_Iso_<YYYY-MM-DDTHH_MM_SS>.csv     # isosbestic time courses
```

For `CHANNEL = "R"`:

```
reextracted_FIP_ROIsR_<YYYY-MM-DDTHH_MM_SS>.csv       # ROIs
reextracted_TS_FLIR_R_<YYYY-MM-DDTHH_MM_SS>.csv       # red signal time courses
```

Time-course CSVs are indexed by frame, with one column per ROI. ROI CSVs store
each circle as `cx`, `cy`, `r` (center in display coordinates, radius in pixels).

---

## Requirements

- Python 3.8+
- numpy
- pandas
- matplotlib

```bash
pip install numpy pandas matplotlib
```

---

## Usage

```bash
python ThorFP_ROI_QA.py
python ThorFP_ROI_reextraction.py
```

example image:


<img width="800" height="400" alt="Screenshot 2026-07-24 at 12 32 41" src="https://github.com/user-attachments/assets/48956b4e-6bf1-453e-92f4-9c3af8ca3d22" />



### Interactive backend (important for re-extraction)

The ROI drawing GUI needs an **interactive matplotlib backend** (e.g. Qt), not
the inline one. The script checks the backend and stops with an explanatory
message if it is non-interactive.

- **Spyder:** Tools → Preferences → IPython console → Graphics → Graphics
  backend → set to `Qt` (or `Automatic`), then restart the kernel. Alternatively,
  run the file in an external system terminal.
- **Local VS Code / plain terminal:** works out of the box.
- **Code Ocean:** the interactive GUI runs only in an Ubuntu Desktop cloud
  workstation (or locally). Headless batch runs, the VS Code cloud workstation
  terminal, and inline notebook backends cannot open the drawing window. On
  Code Ocean, set `output_folder` to a writable location such as `/results`
  (the `/data` mount is read-only).

---

## Suggested workflow

1. Run `ThorFP_ROI_QA.py` and check the ROI/movie alignment. Adjust
   `ORIENTATION` until the ROIs sit on the fibers.
2. If the original ROIs are misplaced, run `ThorFP_ROI_reextraction.py` with the
   same `ORIENTATION`, draw fresh circular ROIs, and re-extract the time courses.
