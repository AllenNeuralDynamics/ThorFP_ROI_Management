import glob
import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
FRAME_WIDTH = 200
FRAME_HEIGHT = 200
DTYPE = np.uint16
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT * np.dtype(DTYPE).itemsize

START_FRAME = 50
END_FRAME = 150

# --- Orientation of ROI coordinates relative to the movie -------------
# A mismatch between ROI and movie orientation is almost always due to a
# difference in coordinate conventions. Switch this setting until the
# ROIs land on the fluorescence spots.
#   "none"        : as-is (X -> column, Y -> row, origin = top-left),
#                   same as imshow's default
#   "transpose"   : transpose the image (row/column swapped in reshape)
#   "flip_y"      : flip ROI Y vertically (ROI origin was bottom-left)
#   "flip_x"      : flip ROI X horizontally
ORIENTATION = "transpose"   # try this first; if wrong, try "flip_y" etc.

# --- Auto brightness ---------------------------------------------------
# Percentile-based scaling: robust to outliers (hot/saturated pixels)
# and gives a reasonable contrast automatically.
VMIN_PCT = 1.0     # map the lowest 1% to black
VMAX_PCT = 99.5    # map the top 0.5% to white (handles saturated pixels)

# ----------------------------------------------------------------------
# File paths
# ----------------------------------------------------------------------
session_folder = r"S:\KentaHagihara_InternalTransfer\428-9-B_transfer\854147\2026_07_21"
fib = os.path.join(session_folder, "fib")

video_file_G = glob.glob(os.path.join(fib, "FIP_RawG_*"))[0]
video_file_R = glob.glob(os.path.join(fib, "FIP_RawR_*"))[0]
roi_file_G   = glob.glob(os.path.join(fib, "FIP_ROIsG-Iso_*"))[0]
roi_file_R   = glob.glob(os.path.join(fib, "FIP_ROIsR_*"))[0]

# ----------------------------------------------------------------------
# Functions
# ----------------------------------------------------------------------
def load_average_frame(video_file, start_frame, end_frame,
                       frame_size=FRAME_SIZE, dtype=DTYPE,
                       frame_width=FRAME_WIDTH, frame_height=FRAME_HEIGHT):
    """Average of frames [start_frame, end_frame). Returns float64 image."""
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

    # Return as float: no need to quantize back to uint16 for display,
    # it would only lose precision.
    return acc / num_frames


def apply_orientation(frame, df, mode=ORIENTATION,
                      w=FRAME_WIDTH, h=FRAME_HEIGHT):
    """Return (frame, x, y) adjusted so ROI coords match the image."""
    x = df["X"].to_numpy(dtype=float)
    y = df["Y"].to_numpy(dtype=float)
    if mode == "none":
        pass
    elif mode == "transpose":
        frame = frame.T
    elif mode == "flip_y":
        y = (h - 1) - y
    elif mode == "flip_x":
        x = (w - 1) - x
    else:
        raise ValueError(f"Unknown orientation mode: {mode}")
    return frame, x, y


def auto_clim(frame, low=VMIN_PCT, high=VMAX_PCT):
    """Percentile-based display range."""
    vmin, vmax = np.percentile(frame, [low, high])
    if vmax <= vmin:  # safeguard for flat images
        vmax = vmin + 1
    return vmin, vmax


def plot_channel(ax, frame, df_roi, title):
    frame_disp, x_all, y_all = apply_orientation(frame, df_roi)
    vmin, vmax = auto_clim(frame_disp)
    ax.imshow(frame_disp, cmap="gray", vmin=vmin, vmax=vmax)
    ax.set_title(f"{title} (vmin={vmin:.0f}, vmax={vmax:.0f})")

    df_adj = df_roi.copy()
    df_adj["Xp"], df_adj["Yp"] = x_all, y_all
    for roi_index, roi in df_adj.groupby("RoiIndex"):
        xs = roi["Xp"].tolist() + [roi["Xp"].iloc[0]]  # close the polygon
        ys = roi["Yp"].tolist() + [roi["Yp"].iloc[0]]
        ax.plot(xs, ys, marker="o", markersize=3, label=f"ROI {roi_index}")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_xlim(0, frame_disp.shape[1])
    ax.set_ylim(frame_disp.shape[0], 0)  # keep image orientation (origin top-left)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == "__main__":
    frame_G = load_average_frame(video_file_G, START_FRAME, END_FRAME)
    frame_R = load_average_frame(video_file_R, START_FRAME, END_FRAME)

    df_G = pd.read_csv(roi_file_G)
    df_R = pd.read_csv(roi_file_R)   # NOTE: original code used df_G here (bug)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    plot_channel(axes[0], frame_G, df_G,
                 f"Green Ch, Frame {START_FRAME}-{END_FRAME}")
    plot_channel(axes[1], frame_R, df_R,
                 f"Red Ch, Frame {START_FRAME}-{END_FRAME}")
    fig.suptitle(f"orientation = '{ORIENTATION}'")
    fig.tight_layout()
    plt.show()