"""
Draw circular ROIs on an average image and extract ROI time courses
(mean pixel value inside each ROI) from the original 16-bit binary movie.

Workflow:
    1. Show the average image of one channel.
    2. Click-drag to draw circular ROIs (click = center, drag = radius).
       Keys:  u = undo last ROI,  Enter = finish drawing.
    3. Time courses are computed from the raw movie and plotted / saved.

NOTE on orientation:
    ROIs are drawn on the *oriented* (display) image. The SAME orientation
    transform is applied to every movie frame before averaging inside the
    mask, so the ROI and the pixels always match. Keep ORIENTATION identical
    to the value that made the overlay script line up ("transpose" here).

NOTE on backend:
    This needs an interactive matplotlib backend (e.g. TkAgg / QtAgg), not
    the inline one. Run it as a normal .py file from a terminal.
"""

import glob
import os
import re
from datetime import datetime
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Circle

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
FRAME_WIDTH = 200
FRAME_HEIGHT = 200
DTYPE = np.uint16
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT * np.dtype(DTYPE).itemsize

# Frame range used to build the average image for ROI drawing.
START_FRAME = 50
END_FRAME = 150

# Channel to process: "G" or "R".
CHANNEL = "G"

# Orientation transform (must match the working overlay script).
#   "none" / "transpose" / "flip_y" / "flip_x"
ORIENTATION = "transpose"

# Auto-brightness percentiles for the display.
VMIN_PCT = 1.0
VMAX_PCT = 99.5

# Chunk size (frames) for reading the movie when computing time courses.
CHUNK = 2000

# If a saved ROI CSV already exists, load it instead of drawing again.
DRAW_NEW = True

# ----------------------------------------------------------------------
# File paths
# ----------------------------------------------------------------------
# Input session folder (movie, original ROI files live in <session_folder>\fib).
session_folder = r""
fib = os.path.join(session_folder, "fib")

# Output folder for the saved files (ROI CSV + time-course CSV).
# If specified, files are saved there. If left as None (or ""), files are
# saved in the original folder (fib), next to the movie.
# Example: output_folder = r"S:\KentaHagihara_InternalTransfer\reextracted_results"
output_folder = r""

# Fall back to the original folder when no output folder is specified.
save_dir = output_folder if output_folder else fib
os.makedirs(save_dir, exist_ok=True)

# Channel token used for the ROI file name: "G-Iso" for green, "R" for red.
CH_TOKEN = "G-Iso" if CHANNEL == "G" else "R"

# Movies to extract from, as (token, filename pattern).
# Green recordings have a signal movie (G, 470 nm) AND an isosbestic movie
# (Iso, 415 nm); both are extracted with the same ROIs. Red has only R.
if CHANNEL == "G":
    extract_specs = [("G", "FIP_RawG_*"), ("Iso", "FIP_RawIso_*")]
    draw_pattern = "FIP_RawG_*"        # draw ROIs on the green signal image
else:
    extract_specs = [("R", "FIP_RawR_*")]
    draw_pattern = "FIP_RawR_*"

# Movie used to build the average image for ROI drawing.
draw_movie = glob.glob(os.path.join(fib, draw_pattern))[0]

# Resolve each extraction movie to a concrete file.
extract_targets = []
for tok, pat in extract_specs:
    matches = glob.glob(os.path.join(fib, pat))
    if not matches:
        raise FileNotFoundError(f"No movie matching '{pat}' in {fib}")
    extract_targets.append((tok, matches[0]))

# Corresponding original ROI file (e.g. FIP_ROIsG-Iso_* / FIP_ROIsR_*).
roi_src_file = glob.glob(os.path.join(fib, f"FIP_ROIs{CH_TOKEN}_*"))[0]

# Matches a timestamp like 2026-07-21T11_55_53 inside a file name.
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}")

# Output names are built at run time so the timestamp reflects when the
# re-extraction was actually run. ROI and time-course files share the same
# timestamp (see __main__), making it easy to pair them.
def roi_out_path(when):
    """reextracted_<original ROI name with date/time replaced>.csv"""
    stamp = when.strftime("%Y-%m-%dT%H_%M_%S")
    stem, ext = os.path.splitext(os.path.basename(roi_src_file))
    if _TS_RE.search(stem):
        stem = _TS_RE.sub(stamp, stem)   # replace original date/time
    else:
        stem = f"{stem}_{stamp}"         # fallback: append if none found
    return os.path.join(save_dir, "reextracted_" + stem + ext)


def timecourse_out_path(token, when):
    """reextracted_TS_FLIR_<token>_<YYYY-MM-DDTHH_MM_SS>.csv"""
    stamp = when.strftime("%Y-%m-%dT%H_%M_%S")
    return os.path.join(save_dir, f"reextracted_TS_FLIR_{token}_{stamp}.csv")


# ----------------------------------------------------------------------
# Orientation helpers (frame-based, applied to both display and movie)
# ----------------------------------------------------------------------
def orient_frame(frame, mode=ORIENTATION):
    """Apply the orientation transform to a single 2D frame."""
    if mode == "none":
        return frame
    if mode == "transpose":
        return frame.T
    if mode == "flip_y":
        return frame[::-1, :]
    if mode == "flip_x":
        return frame[:, ::-1]
    raise ValueError(f"Unknown orientation mode: {mode}")


def orient_stack(stack, mode=ORIENTATION):
    """Apply the orientation transform to a 3D stack (n_frames, H, W)."""
    if mode == "none":
        return stack
    if mode == "transpose":
        return np.transpose(stack, (0, 2, 1))
    if mode == "flip_y":
        return stack[:, ::-1, :]
    if mode == "flip_x":
        return stack[:, :, ::-1]
    raise ValueError(f"Unknown orientation mode: {mode}")


# ----------------------------------------------------------------------
# I/O helpers
# ----------------------------------------------------------------------
def load_average_frame(video_file, start_frame, end_frame,
                       frame_size=FRAME_SIZE, dtype=DTYPE,
                       frame_width=FRAME_WIDTH, frame_height=FRAME_HEIGHT):
    """Average of frames [start_frame, end_frame). Returns a float64 image."""
    num_frames = end_frame - start_frame
    if num_frames <= 0:
        raise ValueError("Invalid frame range specified.")

    acc = np.zeros((frame_height, frame_width), dtype=np.float64)
    with open(video_file, "rb") as f:
        for i in range(start_frame, end_frame):
            f.seek(i * frame_size)
            buf = np.frombuffer(f.read(frame_size), dtype=dtype)
            if buf.size != frame_width * frame_height:
                raise ValueError(f"Reached end of file at frame {i}.")
            acc += buf.reshape((frame_height, frame_width))
    return acc / num_frames


def open_movie_stack(video_file, frame_width=FRAME_WIDTH,
                     frame_height=FRAME_HEIGHT, dtype=DTYPE):
    """Memory-map the whole movie as an oriented (n_frames, H, W) view."""
    raw = np.memmap(video_file, dtype=dtype, mode="r")
    px_per_frame = frame_width * frame_height
    n_frames = raw.size // px_per_frame
    stack = raw[:n_frames * px_per_frame].reshape(n_frames, frame_height, frame_width)
    return orient_stack(stack), n_frames


def auto_clim(frame, low=VMIN_PCT, high=VMAX_PCT):
    """Percentile-based display range, robust to hot/saturated pixels."""
    vmin, vmax = np.percentile(frame, [low, high])
    if vmax <= vmin:  # safeguard for flat images
        vmax = vmin + 1
    return vmin, vmax


# ----------------------------------------------------------------------
# Circular ROI mask
# ----------------------------------------------------------------------
def circle_mask(shape, cx, cy, r):
    """Boolean mask for a filled circle. cx = column (X), cy = row (Y)."""
    h, w = shape
    yy, xx = np.ogrid[:h, :w]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2


# ----------------------------------------------------------------------
# Interactive circle drawer
# ----------------------------------------------------------------------
class CircleROIDrawer:
    """Click-drag to draw circular ROIs. u = undo, Enter = finish."""

    def __init__(self, ax):
        self.ax = ax
        self.canvas = ax.figure.canvas
        self.rois = []          # list of (cx, cy, r)
        self.patches = []       # permanent Circle patches
        self.labels = []        # text labels
        self.center = None      # center of the ROI being drawn
        self.preview = None     # live preview circle

        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("motion_notify_event", self.on_move)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("key_press_event", self.on_key)

    def on_press(self, event):
        # Only start on a left click inside the image axes.
        if event.inaxes != self.ax or event.button != 1:
            return
        self.center = (event.xdata, event.ydata)
        self.preview = Circle(self.center, 0.0, fill=False,
                              edgecolor="yellow", lw=1.5, linestyle="--")
        self.ax.add_patch(self.preview)
        self.canvas.draw_idle()

    def on_move(self, event):
        if self.center is None or event.inaxes != self.ax:
            return
        r = np.hypot(event.xdata - self.center[0], event.ydata - self.center[1])
        self.preview.set_radius(r)
        self.canvas.draw_idle()

    def on_release(self, event):
        if self.center is None:
            return
        cx, cy = self.center
        if event.inaxes == self.ax and event.xdata is not None:
            r = np.hypot(event.xdata - cx, event.ydata - cy)
        else:
            r = self.preview.get_radius()

        # Remove the dashed preview.
        self.preview.remove()
        self.preview = None
        self.center = None

        if r < 1.0:  # ignore accidental tiny clicks
            self.canvas.draw_idle()
            return

        idx = len(self.rois)
        self.rois.append((cx, cy, r))
        patch = Circle((cx, cy), r, fill=False, edgecolor="red", lw=1.5)
        self.ax.add_patch(patch)
        self.patches.append(patch)
        label = self.ax.text(cx, cy, str(idx), color="red", ha="center",
                             va="center", fontsize=9, fontweight="bold")
        self.labels.append(label)
        self.canvas.draw_idle()

    def on_key(self, event):
        if event.key == "u":          # undo last ROI
            if self.rois:
                self.rois.pop()
                self.patches.pop().remove()
                self.labels.pop().remove()
                self.canvas.draw_idle()
        elif event.key in ("enter", "return"):
            plt.close(self.ax.figure)


def draw_rois(image):
    """Open the GUI and return a list of (cx, cy, r) ROIs.

    Uses a local event loop (start_event_loop) instead of relying on
    plt.show() to block. This is important inside IPython/Spyder, where
    plt.show() returns immediately and would otherwise skip drawing.
    Requires an interactive backend (e.g. Qt), NOT the inline one.
    """
    # Reject only truly non-interactive backends. Note that GUI backends
    # like qt5agg / qtagg / tkagg / wxagg contain "agg" in their name but
    # ARE interactive, so we must not filter on the substring "agg".
    non_interactive = {"agg", "pdf", "ps", "svg", "cairo", "template"}
    backend = matplotlib.get_backend().lower()
    if "inline" in backend or backend in non_interactive:
        raise RuntimeError(
            "Interactive drawing needs a GUI backend, but the current "
            f"backend is '{matplotlib.get_backend()}'.\n"
            "In Spyder: Tools > Preferences > IPython console > Graphics > "
            "Graphics backend > set to 'Qt' (or 'Automatic'), then restart "
            "the kernel. Or run this file in an external system terminal."
        )

    vmin, vmax = auto_clim(image)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(image, cmap="gray", vmin=vmin, vmax=vmax)
    ax.set_title("Drag to draw circular ROIs   |   u: undo   Enter: finish")
    drawer = CircleROIDrawer(ax)

    # Stop the local event loop when the window is closed (X button or Enter).
    fig.canvas.mpl_connect("close_event", lambda _e: fig.canvas.stop_event_loop())

    plt.show(block=False)          # display the window
    fig.canvas.draw_idle()
    fig.canvas.start_event_loop(timeout=0)  # block here until the window closes
    return drawer.rois


# ----------------------------------------------------------------------
# Time-course extraction
# ----------------------------------------------------------------------
def extract_timecourses(stack, n_frames, rois, shape, chunk=CHUNK):
    """Mean pixel value inside each circular ROI, per frame."""
    masks = [circle_mask(shape, cx, cy, r) for cx, cy, r in rois]
    n_rois = len(masks)
    out = np.zeros((n_frames, n_rois), dtype=np.float64)

    for start in range(0, n_frames, chunk):
        end = min(start + chunk, n_frames)
        block = np.asarray(stack[start:end], dtype=np.float64)  # load this chunk
        for j, m in enumerate(masks):
            out[start:end, j] = block[:, m].mean(axis=1)
    return out


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # --- Average image for ROI drawing (already oriented) --------------
    avg = orient_frame(load_average_frame(draw_movie, START_FRAME, END_FRAME))
    disp_shape = avg.shape  # (H, W) after orientation

    # --- Get ROIs: draw new ones or load the latest saved reextracted CSV ---
    # One timestamp for this run, shared by the ROI and time-course files.
    run_time = datetime.now()

    existing_rois = sorted(glob.glob(
        os.path.join(save_dir, f"reextracted_FIP_ROIs{CH_TOKEN}_*.csv")))

    if DRAW_NEW or not existing_rois:
        rois = draw_rois(avg)
        if not rois:
            raise SystemExit("No ROIs were drawn.")
        run_time = datetime.now()  # stamp reflects when drawing finished
        roi_csv_out = roi_out_path(run_time)
        pd.DataFrame(rois, columns=["cx", "cy", "r"]).to_csv(
            roi_csv_out, index_label="RoiIndex")
        print(f"Saved {len(rois)} ROIs -> {roi_csv_out}")
    else:
        roi_csv_out = existing_rois[-1]  # most recent reextracted ROI file
        df_roi = pd.read_csv(roi_csv_out)
        rois = list(df_roi[["cx", "cy", "r"]].itertuples(index=False, name=None))
        print(f"Loaded {len(rois)} ROIs <- {roi_csv_out}")

    # --- Extract time courses from every target movie ----------------
    # For green this covers both the G (signal) and Iso movies with the
    # same ROIs; for red it is just R.
    timecourses = {}  # token -> (n_frames, n_rois) array
    for token, movie_path in extract_targets:
        stack, n_frames = open_movie_stack(movie_path)
        print(f"[{token}] {os.path.basename(movie_path)}: {n_frames} frames, "
              f"computing {len(rois)} time course(s)...")
        tc = extract_timecourses(stack, n_frames, rois, disp_shape)
        timecourses[token] = tc

        # Save this channel's time courses (same timestamp as the ROI file).
        out_path = timecourse_out_path(token, run_time)
        cols = [f"ROI_{i}" for i in range(len(rois))]
        df_tc = pd.DataFrame(tc, columns=cols)
        df_tc.index.name = "Frame"
        df_tc.to_csv(out_path)
        print(f"[{token}] Saved time courses -> {out_path}")

    # --- Overview plot: image with ROIs + time courses ---------------
    # Per-channel line colors for the time-course plot.
    channel_colors = {"G": "green", "Iso": "blue", "R": "red"}

    fig, (ax_img, ax_tc) = plt.subplots(1, 2, figsize=(13, 6))

    vmin, vmax = auto_clim(avg)
    ax_img.imshow(avg, cmap="gray", vmin=vmin, vmax=vmax)
    ax_img.set_title(f"{CH_TOKEN} average ({os.path.basename(draw_movie)}) + ROIs")
    for i, (cx, cy, r) in enumerate(rois):
        ax_img.add_patch(Circle((cx, cy), r, fill=False, edgecolor="yellow", lw=1.5))
        ax_img.text(cx, cy, str(i), color="yellow", ha="center", va="center",
                    fontsize=9, fontweight="bold")

    for token, tc in timecourses.items():
        color = channel_colors.get(token)
        for i in range(len(rois)):
            ax_tc.plot(tc[:, i], lw=0.8, color=color, label=f"{token} ROI {i}")
    ax_tc.set_xlabel("Frame")
    ax_tc.set_ylabel("Mean intensity (a.u.)")
    ax_tc.set_title("ROI time courses")
    ax_tc.legend(fontsize=8)

    fig.tight_layout()
    # block=True keeps the window open when run from a plain terminal;
    # under Spyder/IPython the figure shows in the usual way.
    plt.show(block=True)