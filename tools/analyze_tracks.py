"""Per-point + aggregate metrics on a multi-point intersection-tracking CSV.

Reads a `.tracks.csv` produced by `tools/track_intersections.py` and
computes:

  Per-point (healthy samples only):
    - n_healthy: number of healthy frames for this point
    - peak_displacement_mm: max 3D displacement from this point's frame-0 origin
    - peak_frame_idx: frame index where the peak occurred
    - path_length_mm: cumulative 3D path length across healthy frames

  Aggregate (across all points):
    - mean displacement per frame (healthy points only)
    - dominant cycle period in seconds, via FFT of the per-frame mean
      displacement signal (numpy-only, no scipy dep)

Outputs:
    <input>.metrics.csv             always written: per-point + one aggregate row
    Plots:
      default: displayed in interactive matplotlib windows (close to continue)
      with --save: also written to
        <input>.tracks.png           combined plot
        <input>.tracks_per_point.png grid plot (one subplot per point)

Usage:
    python tools/analyze_tracks.py TRACKS_CSV [--fps 30] [--healthy-only] [--save]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._tracks import TrackSample, color_mpl_for_point, read_tracks


def per_point_metrics(samples: list[TrackSample]) -> dict[int, dict]:
    """Return {point_id: {n_healthy, peak_displacement_mm, peak_frame_idx, path_length_mm}}."""
    by_point: dict[int, list[TrackSample]] = defaultdict(list)
    for s in samples:
        by_point[s.point_id].append(s)
    out: dict[int, dict] = {}
    for pid, rows in by_point.items():
        rows.sort(key=lambda r: r.frame_idx)
        healthy = [r for r in rows if r.healthy]
        if not healthy:
            out[pid] = {"n_healthy": 0, "peak_displacement_mm": 0.0,
                        "peak_frame_idx": -1, "path_length_mm": 0.0}
            continue
        peak_row = max(healthy, key=lambda r: r.displacement_mm)
        path_len = 0.0
        for a, b in zip(healthy[:-1], healthy[1:]):
            d = np.array([b.x_mm - a.x_mm, b.y_mm - a.y_mm, b.z_mm - a.z_mm])
            path_len += float(np.linalg.norm(d))
        out[pid] = {
            "n_healthy": len(healthy),
            "peak_displacement_mm": float(peak_row.displacement_mm),
            "peak_frame_idx": int(peak_row.frame_idx),
            "path_length_mm": path_len,
        }
    return out


def aggregate_displacement_signal(samples: list[TrackSample]) -> tuple[np.ndarray, np.ndarray]:
    """Return (frame_indices_sorted, mean_displacement_mm_per_frame).

    Mean is taken over healthy samples only; frames with zero healthy
    samples are skipped.
    """
    by_frame: dict[int, list[float]] = defaultdict(list)
    for s in samples:
        if s.healthy:
            by_frame[s.frame_idx].append(s.displacement_mm)
    if not by_frame:
        return np.array([], dtype=int), np.array([], dtype=float)
    frames = np.array(sorted(by_frame.keys()))
    means = np.array([float(np.mean(by_frame[f])) for f in frames])
    return frames, means


def dominant_cycle_period_s(frames: np.ndarray, means: np.ndarray,
                             fps: float) -> float | None:
    """Estimate the dominant cycle period (s) by picking the largest peak
    of the FFT of the (zero-mean) mean-displacement signal.

    Returns None if the signal is too short or has no clear peak.
    """
    if len(frames) < 16:
        return None
    # Interpolate onto a uniform grid in case some frames are missing.
    full = np.arange(int(frames[0]), int(frames[-1]) + 1)
    if len(full) < 16:
        return None
    means_full = np.interp(full, frames, means)
    centered = means_full - means_full.mean()
    spec = np.fft.rfft(centered)
    freqs = np.fft.rfftfreq(len(centered), d=1.0 / fps)
    # Ignore DC and very low frequencies (< 0.3 Hz = period > 3.3 s).
    # Also ignore very high frequencies (> 5 Hz).
    mask = (freqs >= 0.3) & (freqs <= 5.0)
    if not mask.any():
        return None
    mags = np.abs(spec)
    mags[~mask] = 0.0
    if mags.max() <= 0:
        return None
    peak_idx = int(np.argmax(mags))
    peak_freq = float(freqs[peak_idx])
    if peak_freq <= 0:
        return None
    return 1.0 / peak_freq


def _healthy_segments(rows: list[TrackSample], fps: float) -> list[tuple[list[float], list[float]]]:
    """Split a per-point row list into (time, displacement) segments broken at lost samples."""
    rows = sorted(rows, key=lambda r: r.frame_idx)
    segments: list[tuple[list[float], list[float]]] = []
    seg_t: list[float] = []
    seg_d: list[float] = []
    for r in rows:
        if r.healthy:
            seg_t.append(r.frame_idx / fps)
            seg_d.append(r.displacement_mm)
        else:
            if seg_t:
                segments.append((seg_t, seg_d))
                seg_t, seg_d = [], []
    if seg_t:
        segments.append((seg_t, seg_d))
    return segments


def _stayed_healthy_ids(samples: list[TrackSample]) -> set[int]:
    """Return the set of point_ids that have NO healthy=False row anywhere."""
    lost = {s.point_id for s in samples if not s.healthy}
    all_ids = {s.point_id for s in samples}
    return all_ids - lost


def _build_combined_plot(samples: list[TrackSample], fps: float, title: str):
    """One axis, one colored line per point — for cross-point comparison."""
    import matplotlib.pyplot as plt

    by_point: dict[int, list[TrackSample]] = defaultdict(list)
    for s in samples:
        by_point[s.point_id].append(s)

    fig, ax = plt.subplots(figsize=(11, 5))
    for pid in sorted(by_point.keys()):
        color = color_mpl_for_point(pid)
        labelled = False
        for seg_t, seg_d in _healthy_segments(by_point[pid], fps):
            ax.plot(seg_t, seg_d, color=color, linewidth=0.9,
                    label=(f"pt{pid}" if not labelled else None))
            labelled = True

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("3D displacement from each point's frame-0 origin (mm)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    handles, labels = ax.get_legend_handles_labels()
    if 0 < len(labels) <= 24:
        ax.legend(handles, labels, loc="upper right", fontsize=7, ncol=2)
    fig.tight_layout()
    return fig


def _build_per_point_plot(samples: list[TrackSample], fps: float, title: str):
    """Grid of subplots, one per point. Shared x and y axes."""
    import math

    import matplotlib.pyplot as plt

    by_point: dict[int, list[TrackSample]] = defaultdict(list)
    for s in samples:
        by_point[s.point_id].append(s)
    point_ids = sorted(by_point.keys())
    n = len(point_ids)
    if n == 0:
        return None

    # Grid: up to 4 columns, rows as needed
    ncols = min(4, n)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols,
                              figsize=(3.2 * ncols, 2.0 * nrows + 0.6),
                              sharex=True, sharey=True, squeeze=False)

    # Compute shared y-axis range
    max_disp = 0.0
    for pid in point_ids:
        for r in by_point[pid]:
            if r.healthy:
                max_disp = max(max_disp, r.displacement_mm)
    ymax = max_disp * 1.05 if max_disp > 0 else 1.0

    for i, pid in enumerate(point_ids):
        ax = axes[i // ncols][i % ncols]
        rows = by_point[pid]
        healthy_rows = [r for r in rows if r.healthy]
        color = color_mpl_for_point(pid)
        for seg_t, seg_d in _healthy_segments(rows, fps):
            ax.plot(seg_t, seg_d, color=color, linewidth=1.0)
        if healthy_rows:
            peak = max(healthy_rows, key=lambda r: r.displacement_mm)
            ax.plot(peak.frame_idx / fps, peak.displacement_mm, "o",
                    color=color, markersize=4)
            ax.set_title(f"pt{pid}  peak={peak.displacement_mm:.2f} mm @ frame {peak.frame_idx}",
                         fontsize=8)
        else:
            ax.set_title(f"pt{pid}  (no healthy frames)", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0, ymax)

    # Hide unused cells
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    # Shared axis labels on the outer edges only
    for row in range(nrows):
        axes[row][0].set_ylabel("disp (mm)", fontsize=8)
    for col in range(ncols):
        axes[nrows - 1][col].set_xlabel("Time (s)", fontsize=8)

    fig.suptitle(title, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tracks_csv", type=Path,
                    help="Output of tools/track_intersections.py")
    ap.add_argument("--fps", type=float, default=30.0,
                    help="Recording frame rate (default 30; matches recorder)")
    ap.add_argument("--metrics-output", type=Path, default=None,
                    help="Per-point metrics CSV (default: <input>.metrics.csv)")
    ap.add_argument("--healthy-only", action="store_true",
                    help="Only plot points whose tracks never went lost. The metrics "
                         "CSV still contains every point (including lost ones) so you "
                         "can see what was filtered out.")
    ap.add_argument("--save", action="store_true",
                    help="Save plots to PNG (default paths: <input>.tracks.png and "
                         "<input>.tracks_per_point.png) in addition to displaying them.")
    ap.add_argument("--plot-output", type=Path, default=None,
                    help="Combined plot PNG path when --save is set (overrides default)")
    ap.add_argument("--per-point-plot-output", type=Path, default=None,
                    help="Per-point grid plot PNG path when --save is set (overrides default)")
    ap.add_argument("--no-display", action="store_true",
                    help="Don't pop interactive windows (useful with --save when running headless)")
    args = ap.parse_args()

    samples = read_tracks(args.tracks_csv)
    if not samples:
        print(f"No samples in {args.tracks_csv}"); sys.exit(1)
    print(f"Loaded {len(samples)} samples from {args.tracks_csv}")

    per_pt = per_point_metrics(samples)
    print(f"\nPer-point metrics ({len(per_pt)} points):")
    for pid in sorted(per_pt.keys()):
        m = per_pt[pid]
        print(f"  pt{pid:2d}  healthy={m['n_healthy']:4d}  "
              f"peak={m['peak_displacement_mm']:6.3f} mm @ frame {m['peak_frame_idx']:4d}  "
              f"path_length={m['path_length_mm']:7.3f} mm")

    frames, means = aggregate_displacement_signal(samples)
    period_s = dominant_cycle_period_s(frames, means, args.fps) if len(frames) else None
    n_total_frames = int(frames[-1] - frames[0] + 1) if len(frames) else 0
    print(f"\nAggregate (mean displacement across healthy points):")
    if len(frames):
        print(f"  spans frames {int(frames[0])}..{int(frames[-1])}  "
              f"({n_total_frames / args.fps:.2f} s)")
        print(f"  mean displacement: {float(means.mean()):.3f} mm  "
              f"peak {float(means.max()):.3f} mm")
    print(f"  dominant cycle period: {period_s:.3f} s" if period_s else
          "  dominant cycle period: (signal too short or no clear peak)")

    metrics_out = args.metrics_output or args.tracks_csv.with_suffix(".metrics.csv")
    with open(metrics_out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["point_id", "n_healthy", "peak_displacement_mm",
                    "peak_frame_idx", "path_length_mm"])
        for pid in sorted(per_pt.keys()):
            m = per_pt[pid]
            w.writerow([pid, m["n_healthy"],
                        f"{m['peak_displacement_mm']:.4f}",
                        m["peak_frame_idx"],
                        f"{m['path_length_mm']:.4f}"])
        # Aggregate row: point_id=-1 sentinel
        agg_mean = float(means.mean()) if len(means) else 0.0
        agg_peak = float(means.max()) if len(means) else 0.0
        agg_period = period_s if period_s else ""
        w.writerow(["AGGREGATE", int(len(frames)),
                    f"{agg_peak:.4f}", "",
                    f"period_s={agg_period}" if agg_period else "period_s=NA"])

    print(f"\nWrote {metrics_out}")

    # Plot stage — filter to surviving points if --healthy-only.
    plot_samples = samples
    if args.healthy_only:
        kept = _stayed_healthy_ids(samples)
        dropped = {s.point_id for s in samples} - kept
        plot_samples = [s for s in samples if s.point_id in kept]
        suffix = f" — healthy-only ({len(kept)} of {len(kept) + len(dropped)} points)"
        if dropped:
            print(f"\n--healthy-only: hiding {len(dropped)} point(s) that went lost: "
                  f"{sorted(dropped)}")
    else:
        suffix = ""

    if not args.no_display:
        import matplotlib
        # Let matplotlib pick the default interactive backend
    elif args.save:
        import matplotlib
        matplotlib.use("Agg")

    title_combined = f"Per-point intersection-tracking displacement — {args.tracks_csv.stem}{suffix}"
    title_grid = f"Per-point displacement (each in its own axis) — {args.tracks_csv.stem}{suffix}"
    fig_combined = _build_combined_plot(plot_samples, args.fps, title_combined)
    fig_grid = _build_per_point_plot(plot_samples, args.fps, title_grid)

    if args.save:
        plot_out = args.plot_output or args.tracks_csv.with_suffix(".tracks.png")
        per_point_out = (args.per_point_plot_output
                         or args.tracks_csv.with_suffix(".tracks_per_point.png"))
        fig_combined.savefig(plot_out, dpi=120)
        if fig_grid is not None:
            fig_grid.savefig(per_point_out, dpi=120)
        print(f"Wrote {plot_out}")
        if fig_grid is not None:
            print(f"Wrote {per_point_out}")

    if not args.no_display:
        import matplotlib.pyplot as plt
        plt.show(block=True)
    else:
        import matplotlib.pyplot as plt
        plt.close(fig_combined)
        if fig_grid is not None:
            plt.close(fig_grid)


if __name__ == "__main__":
    main()
