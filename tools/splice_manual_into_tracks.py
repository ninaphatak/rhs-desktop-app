"""Splice manually-annotated points into a master tracks.csv.

For each manually-annotated point, reads its stereo annotations CSV
(sparse: only frames you labeled), triangulates each labeled frame into
3D mm using the supplied calibration, linearly interpolates 3D position
+ pixel coords between labeled frames, and replaces that point_id's
rows in the master tracks.csv produced by tools/track_intersections.py.

Outside the labeled range (frame < first labeled or frame > last labeled
for that point), the master row is kept unchanged — so auto-tracked
frames before the failure region are preserved. Spliced rows are written
with healthy=1, ncc=1.0, fb_err=0.0.

Displacement (dx, dy, dz, displacement_mm) is computed relative to the
existing per-point origin from the master CSV (the first frame's
healthy x_mm,y_mm,z_mm for that point), so the spliced trajectory uses
the same reference as the auto-tracked points.

Phase is taken directly on labeled frames and nearest-neighbored on
interpolated frames.

Usage:
    python tools/splice_manual_into_tracks.py MASTER_TRACKS_CSV \\
        --calib outputs/calib/stereo_calib_water.json \\
        --point 6 point6.stereo_annotations.csv \\
        --point 7 point7.stereo_annotations.csv \\
        [--cam0-timestamps CAM0.timestamps.csv] \\
        [--cam1-timestamps CAM1.timestamps.csv] \\
        [--output MERGED.tracks.csv]

The output is in the same schema as track_intersections.py's output and
can be fed directly into tools/analyze_tracks.py and
tools/playback_tracks.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._tracks import TrackSample, read_tracks, write_tracks
from tools.annotate_stereo_point import read_stereo_csv
from tools.triangulate import (
    interpolate_pixel_at_time,
    load_calibration,
    load_timestamps,
    triangulate_point,
)


def _triangulate_labeled_frames(
    stereo_csv_path: Path,
    calib: dict,
    cam0_ts: dict[int, float] | None,
    cam1_ts: dict[int, float] | None,
) -> dict[int, tuple[float, float, float, float, float, float, float]]:
    """Triangulate every complete frame in the stereo CSV.

    Returns {frame_idx: (u0, v0, u1_corrected, v1_corrected, x_mm, y_mm, z_mm)}.
    The u1, v1 values returned are AFTER timestamp sync interpolation when
    timestamps are available — matching exactly what tools/triangulate.py does.
    """
    anns = read_stereo_csv(stereo_csv_path)
    complete = [a for a in anns if a.complete]
    if not complete:
        return {}

    cam1_anns = {a.frame_idx: (a.u1, a.v1) for a in complete}
    do_interp = cam0_ts is not None and cam1_ts is not None

    out: dict[int, tuple[float, float, float, float, float, float, float]] = {}
    for a in complete:
        u0, v0 = a.u0, a.v0
        if do_interp and a.frame_idx in cam0_ts:
            target_t = cam0_ts[a.frame_idx]
            u1, v1 = interpolate_pixel_at_time(cam1_anns, cam1_ts, target_t)
        else:
            u1, v1 = a.u1, a.v1
        xyz = triangulate_point(
            calib["cam0"]["K"], calib["cam0"]["dist"],
            calib["cam0"]["rvec"], calib["cam0"]["tvec"],
            calib["cam1"]["K"], calib["cam1"]["dist"],
            calib["cam1"]["rvec"], calib["cam1"]["tvec"],
            (u0, v0), (u1, v1),
        )
        out[a.frame_idx] = (float(u0), float(v0), float(u1), float(v1),
                            float(xyz[0]), float(xyz[1]), float(xyz[2]))
    return out


def _interpolate_at(
    labeled: dict[int, tuple[float, float, float, float, float, float, float]],
    sorted_frames: list[int],
    frame_idx: int,
) -> tuple[tuple[float, ...], bool] | None:
    """Linearly interpolate the labeled tuple at frame_idx.

    Returns (values, is_interpolated) or None if frame_idx is outside the
    labeled range. is_interpolated is False when frame_idx is itself a
    labeled frame.
    """
    if not sorted_frames:
        return None
    if frame_idx < sorted_frames[0] or frame_idx > sorted_frames[-1]:
        return None
    if frame_idx in labeled:
        return labeled[frame_idx], False
    # Binary-style search via filter (sorted_frames typically small enough)
    lo = max(f for f in sorted_frames if f < frame_idx)
    hi = min(f for f in sorted_frames if f > frame_idx)
    span = hi - lo
    t = (frame_idx - lo) / span if span else 0.0
    a = labeled[lo]
    b = labeled[hi]
    interp = tuple(a[i] + t * (b[i] - a[i]) for i in range(len(a)))
    return interp, True


def _nearest_phase(phases_by_frame: dict[int, str], frame_idx: int) -> str:
    if not phases_by_frame:
        return ""
    nearest = min(phases_by_frame.keys(), key=lambda f: abs(f - frame_idx))
    return phases_by_frame[nearest]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("master_tracks_csv", type=Path,
                    help="Master tracks CSV from tools/track_intersections.py")
    ap.add_argument("--calib", type=Path, required=True,
                    help="Stereo calibration JSON")
    ap.add_argument("--point", nargs=2, action="append",
                    metavar=("POINT_ID", "STEREO_CSV"), required=True,
                    help="Repeat per manually-labeled point: --point 6 point6.csv")
    ap.add_argument("--cam0-timestamps", type=Path, default=None,
                    help="cam0 timestamp sidecar (.timestamps.csv) for sync-correction "
                         "interpolation on cam1 pixels. Match what you'd pass to "
                         "tools/triangulate.py for an apples-to-apples merge.")
    ap.add_argument("--cam1-timestamps", type=Path, default=None,
                    help="cam1 timestamp sidecar")
    ap.add_argument("--output", type=Path, default=None,
                    help="Output CSV (default: <master>.spliced.csv)")
    args = ap.parse_args()

    if not args.master_tracks_csv.exists():
        print(f"Master tracks not found: {args.master_tracks_csv}"); sys.exit(1)
    if not args.calib.exists():
        print(f"Calibration not found: {args.calib}"); sys.exit(1)

    out_path = args.output if args.output else args.master_tracks_csv.with_suffix(".spliced.csv")
    calib = load_calibration(args.calib)
    cam0_ts = load_timestamps(args.cam0_timestamps) if args.cam0_timestamps else None
    cam1_ts = load_timestamps(args.cam1_timestamps) if args.cam1_timestamps else None
    sync_on = cam0_ts is not None and cam1_ts is not None
    print(f"Sync interpolation: {'ON' if sync_on else 'OFF (no timestamps supplied)'}")

    print(f"Reading master tracks: {args.master_tracks_csv}")
    master = read_tracks(args.master_tracks_csv)
    print(f"  {len(master)} rows across "
          f"{len({r.point_id for r in master})} points, "
          f"{len({r.frame_idx for r in master})} frames")

    # Per-point origin = first frame's healthy (x, y, z). The master tracker
    # references displacement to point's frame-0 position, so the spliced
    # trajectory uses the same origin for consistency.
    origin_xyz: dict[int, tuple[float, float, float]] = {}
    for r in master:
        if r.point_id in origin_xyz:
            continue
        if not r.healthy:
            continue
        origin_xyz[r.point_id] = (r.x_mm, r.y_mm, r.z_mm)

    # Build replacement map: (frame_idx, point_id) -> new TrackSample
    replacements: dict[tuple[int, int], TrackSample] = {}
    for pid_str, stereo_csv_str in args.point:
        pid = int(pid_str)
        stereo_csv = Path(stereo_csv_str)
        if not stereo_csv.exists():
            print(f"  point {pid}: stereo CSV not found: {stereo_csv}"); sys.exit(1)

        labeled = _triangulate_labeled_frames(stereo_csv, calib, cam0_ts, cam1_ts)
        if not labeled:
            print(f"  point {pid}: NO complete annotations in {stereo_csv}, skipping")
            continue

        phases = {}
        for a in read_stereo_csv(stereo_csv):
            if a.complete:
                phases[a.frame_idx] = a.phase

        sorted_frames = sorted(labeled.keys())
        first_lf, last_lf = sorted_frames[0], sorted_frames[-1]

        if pid not in origin_xyz:
            # No healthy auto-tracker row for this point — anchor manual trajectory
            # on its own first labeled frame.
            origin_xyz[pid] = labeled[first_lf][4:7]
            origin_source = "manual (no auto origin)"
        else:
            origin_source = "auto frame-0"
        ox, oy, oz = origin_xyz[pid]

        n_label = n_interp = 0
        # Iterate master rows for this point so we only emit frames that exist
        # in the master (no schema rows invented out of thin air).
        for r in master:
            if r.point_id != pid:
                continue
            if r.frame_idx < first_lf or r.frame_idx > last_lf:
                continue
            res = _interpolate_at(labeled, sorted_frames, r.frame_idx)
            if res is None:
                continue
            vals, is_interp = res
            u0, v0, u1, v1, x, y, z = vals
            dx, dy, dz = x - ox, y - oy, z - oz
            disp = float(np.sqrt(dx * dx + dy * dy + dz * dz))
            phase = phases.get(r.frame_idx) or _nearest_phase(phases, r.frame_idx)
            replacements[(r.frame_idx, pid)] = TrackSample(
                frame_idx=r.frame_idx, point_id=pid,
                u0=u0, v0=v0, u1=u1, v1=v1,
                x_mm=x, y_mm=y, z_mm=z,
                dx_mm=dx, dy_mm=dy, dz_mm=dz, displacement_mm=disp,
                fb_err_px_cam0=0.0, fb_err_px_cam1=0.0,
                ncc_cam0=1.0, ncc_cam1=1.0,
                healthy=True,
                phase=phase,
            )
            if is_interp:
                n_interp += 1
            else:
                n_label += 1
        print(f"  point {pid}: {len(labeled)} labeled frames -> "
              f"{n_label} replacements from labels + {n_interp} interpolated "
              f"(range frame {first_lf}..{last_lf}, origin={origin_source})")

    # Merge: master rows pass through, replacements override (frame, point) keys.
    merged = [replacements.get((r.frame_idx, r.point_id), r) for r in master]

    write_tracks(merged, out_path)
    n_replaced = len(replacements)
    print(f"\nWrote {len(merged)} rows ({n_replaced} replaced) to {out_path}")


if __name__ == "__main__":
    main()
