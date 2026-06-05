"""Plot pressure, flow, and leaflet displacement vs time, stacked.

Three panels on a shared time axis (like legacy/plots/view_csv.py):
    1. P2 (mmHg)
    2. Flow rate (mL/s)
    3. Displacement (mm), one line per tracked point

Lets you eyeball whether the displacement trace has the same shape as
the pressure / flow traces as you ramp the input.

Usage:
    python tools/analyze_pressure_vs_tracks.py PRESSURE_CSV TRACKS_CSV \\
        [--cam0-timestamps CAM0.timestamps.csv] [--fps 30] \\
        [--time-offset SECONDS] [--no-show]

Writes <tracks>.pressure_vs_disp.png next to the tracks CSV.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._tracks import TrackSample, color_mpl_for_point, read_tracks


def _load_cam0_times(ts_path: Path | None, n_frames_hint: int, fps: float) -> np.ndarray:
    if ts_path is None or not ts_path.exists():
        return np.arange(n_frames_hint) / fps
    df = pd.read_csv(ts_path)
    t = df["system_time_s"].to_numpy(dtype=float)
    return t - t[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pressure_csv", type=Path)
    ap.add_argument("tracks_csv", type=Path)
    ap.add_argument("--cam0-timestamps", type=Path, default=None)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--time-offset", type=float, default=0.0,
                    help="Seconds to add to track time to align with pressure t=0.")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    if not args.pressure_csv.exists():
        print(f"Pressure CSV not found: {args.pressure_csv}"); sys.exit(1)
    if not args.tracks_csv.exists():
        print(f"Tracks CSV not found: {args.tracks_csv}"); sys.exit(1)

    df = pd.read_csv(args.pressure_csv)
    t_p = df["Time (s)"].to_numpy(dtype=float)
    p2 = df["Pressure 2 (mmHg)"].to_numpy(dtype=float)
    flow = df["Flow Rate (mL/s)"].to_numpy(dtype=float)
    print(f"Pressure: {len(df)} samples, {t_p[-1]:.2f} s")

    samples = read_tracks(args.tracks_csv)
    if not samples:
        print(f"No track samples in {args.tracks_csv}"); sys.exit(1)
    by_point: dict[int, list[TrackSample]] = defaultdict(list)
    for s in samples:
        by_point[s.point_id].append(s)
    for pid in by_point:
        by_point[pid].sort(key=lambda r: r.frame_idx)
    point_ids = sorted(by_point.keys())
    n_frames_hint = max(s.frame_idx for s in samples) + 1
    cam0_t = _load_cam0_times(args.cam0_timestamps, n_frames_hint, args.fps)
    print(f"Tracks: {len(samples)} samples, {len(point_ids)} point(s) {point_ids}, "
          f"video span = {cam0_t[-1] - cam0_t[0]:.2f} s")

    fig, (ax_p, ax_f, ax_d) = plt.subplots(3, 1, figsize=(12, 8), sharex=True)

    ax_p.plot(t_p, p2, color="black", lw=0.9)
    ax_p.set_ylabel("P2 (mmHg)")
    ax_p.set_title("Ventricle pressure")
    ax_p.grid(alpha=0.3)

    ax_f.plot(t_p, flow, color="tab:blue", lw=0.9)
    ax_f.set_ylabel("Flow (mL/s)")
    ax_f.set_title("Flow rate")
    ax_f.grid(alpha=0.3)

    for pid in point_ids:
        rows = by_point[pid]
        frame_idx = np.array([r.frame_idx for r in rows])
        t = cam0_t[np.clip(frame_idx, 0, len(cam0_t) - 1)] + args.time_offset
        d = np.array([r.displacement_mm for r in rows], dtype=float)
        h = np.array([r.healthy for r in rows], dtype=bool)
        d_masked = d.copy(); d_masked[~h] = np.nan
        ax_d.plot(t, d_masked, color=color_mpl_for_point(pid), lw=0.9,
                  label=f"pt{pid}")
    ax_d.set_ylabel("Displacement (mm)")
    ax_d.set_xlabel("Time (s)")
    ax_d.set_title("Leaflet displacement")
    ax_d.grid(alpha=0.3)
    if len(point_ids) > 1:
        ax_d.legend(loc="upper left", fontsize=9)

    fig.tight_layout()
    out_path = args.tracks_csv.with_name(args.tracks_csv.name + ".pressure_vs_disp.png")
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")

    # ---- Per-axis displacement components (dx, dy, dz) ----
    fig2, (ax_x, ax_y, ax_z) = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    for pid in point_ids:
        rows = by_point[pid]
        frame_idx = np.array([r.frame_idx for r in rows])
        t = cam0_t[np.clip(frame_idx, 0, len(cam0_t) - 1)] + args.time_offset
        h = np.array([r.healthy for r in rows], dtype=bool)
        dx = np.array([r.dx_mm for r in rows], dtype=float); dx[~h] = np.nan
        dy = np.array([r.dy_mm for r in rows], dtype=float); dy[~h] = np.nan
        dz = np.array([r.dz_mm for r in rows], dtype=float); dz[~h] = np.nan
        color = color_mpl_for_point(pid)
        label = f"pt{pid}" if len(point_ids) > 1 else None
        ax_x.plot(t, dx, color=color, lw=0.9, label=label)
        ax_y.plot(t, dy, color=color, lw=0.9, label=label)
        ax_z.plot(t, dz, color=color, lw=0.9, label=label)
    for ax, lbl in ((ax_x, "dx (mm)"), (ax_y, "dy (mm)"), (ax_z, "dz (mm)")):
        ax.axhline(0, color="gray", lw=0.6, alpha=0.5)
        ax.set_ylabel(lbl)
        ax.grid(alpha=0.3)
    ax_x.set_title("Leaflet displacement — X component (in-plane)")
    ax_y.set_title("Leaflet displacement — Y component (in-plane)")
    ax_z.set_title("Leaflet displacement — Z component (axial, +z = flow direction)")
    ax_z.set_xlabel("Time (s)")
    if len(point_ids) > 1:
        ax_x.legend(loc="upper left", fontsize=9)
    fig2.tight_layout()
    comp_path = args.tracks_csv.with_name(args.tracks_csv.name + ".disp_components.png")
    fig2.savefig(comp_path, dpi=150)
    print(f"Wrote {comp_path}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
