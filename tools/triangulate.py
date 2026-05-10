"""Triangulate a stereo-annotated landmark trajectory into 3D millimeters.

Consumes a stereo annotation CSV (one row per frame: frame_idx, u0, v0,
u1, v1, phase) plus a stereo calibration JSON, and outputs a per-frame
3D position in the calibration-object frame plus the metric displacement
vector from the first labeled frame.

Usage:
    python tools/triangulate.py STEREO_CSV CALIB_JSON [--output OUT_CSV]

Output CSV columns:
    frame_idx, x_mm, y_mm, z_mm, displacement_mm, dx_mm, dy_mm, dz_mm, phase
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def load_calibration(path: Path) -> dict:
    """Load the JSON written by tools/stereo_calibrate.py."""
    d = json.loads(path.read_text())
    out = {}
    for cam in ("cam0", "cam1"):
        out[cam] = {
            "K": np.array(d[cam]["K"], dtype=np.float64),
            "dist": np.array(d[cam]["dist"], dtype=np.float64),
            "rvec": np.array(d[cam]["rvec"], dtype=np.float64),
            "tvec": np.array(d[cam]["tvec"], dtype=np.float64),
        }
    return out


def load_stereo_annotations(path: Path) -> list[dict]:
    """Load per-frame stereo annotations."""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "frame_idx": int(r["frame_idx"]),
                "u0": float(r["u0"]), "v0": float(r["v0"]),
                "u1": float(r["u1"]), "v1": float(r["v1"]),
                "phase": r.get("phase", "").strip(),
            })
    return rows


def load_timestamps(path: Path) -> dict[int, float]:
    """Load a record_calibration.py timestamp sidecar. Returns frame_index -> system_time_s."""
    out: dict[int, float] = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            out[int(r["frame_index"])] = float(r["system_time_s"])
    return out


def interpolate_pixel_at_time(
    annotations_by_frame: dict[int, tuple[float, float]],
    times_by_frame: dict[int, float],
    target_time: float,
) -> tuple[float, float]:
    """Linearly interpolate (u, v) at target_time given annotated frames + their times.

    annotations_by_frame[frame_idx] = (u, v)
    times_by_frame[frame_idx]       = system_time_s
    Falls back to the nearest annotated frame if target_time is outside the range
    (no extrapolation).
    """
    annotated = sorted(annotations_by_frame.keys(),
                       key=lambda f: times_by_frame.get(f, float("inf")))
    if not annotated:
        raise ValueError("no annotations to interpolate")
    # Locate target_time in the sorted-by-time annotated frames
    times = [times_by_frame[f] for f in annotated]
    # Out-of-range: clamp to nearest endpoint (no extrapolation)
    if target_time <= times[0]:
        return annotations_by_frame[annotated[0]]
    if target_time >= times[-1]:
        return annotations_by_frame[annotated[-1]]
    # Find bracketing frames
    for i in range(1, len(annotated)):
        t_curr = times[i]
        if t_curr >= target_time:
            f_prev, f_curr = annotated[i - 1], annotated[i]
            t_prev = times[i - 1]
            alpha = (target_time - t_prev) / (t_curr - t_prev) if t_curr != t_prev else 0.0
            uv_prev = annotations_by_frame[f_prev]
            uv_curr = annotations_by_frame[f_curr]
            return (uv_prev[0] + alpha * (uv_curr[0] - uv_prev[0]),
                    uv_prev[1] + alpha * (uv_curr[1] - uv_prev[1]))
    return annotations_by_frame[annotated[-1]]


def triangulate_point(
    K0, dist0, rvec0, tvec0,
    K1, dist1, rvec1, tvec1,
    uv0, uv1,
) -> np.ndarray:
    """Triangulate one 3D point (mm, in the calibration-object frame)."""
    pts0 = cv2.undistortPoints(np.array([[uv0]], dtype=np.float32), K0, dist0, P=K0)
    pts1 = cv2.undistortPoints(np.array([[uv1]], dtype=np.float32), K1, dist1, P=K1)
    R0, _ = cv2.Rodrigues(rvec0)
    R1, _ = cv2.Rodrigues(rvec1)
    P0 = K0 @ np.hstack([R0, tvec0.reshape(3, 1)])
    P1 = K1 @ np.hstack([R1, tvec1.reshape(3, 1)])
    pt_4d = cv2.triangulatePoints(P0, P1, pts0[0].T, pts1[0].T)
    return (pt_4d[:3] / pt_4d[3]).ravel()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stereo_csv", type=Path,
                    help="Stereo annotations CSV with frame_idx, u0, v0, u1, v1, phase")
    ap.add_argument("calib_json", type=Path,
                    help="Calibration JSON from tools/stereo_calibrate.py")
    ap.add_argument("--output", type=Path, default=None,
                    help="Output CSV path (default: <stereo_csv>.triangulated.csv)")
    ap.add_argument("--cam0-timestamps", type=Path, default=None,
                    help="cam0 timestamp sidecar CSV from record_calibration.py. "
                         "If both --cam0-timestamps and --cam1-timestamps are provided, "
                         "cam1 pixel positions are linearly interpolated to align with cam0 "
                         "frame times (corrects for free-running camera sync skew).")
    ap.add_argument("--cam1-timestamps", type=Path, default=None,
                    help="cam1 timestamp sidecar CSV (paired with --cam0-timestamps).")
    args = ap.parse_args()

    print(f"Loading calibration from {args.calib_json}")
    calib = load_calibration(args.calib_json)
    print(f"Loading stereo annotations from {args.stereo_csv}")
    annotations = load_stereo_annotations(args.stereo_csv)
    print(f"  {len(annotations)} stereo-labeled frames")
    if not annotations:
        print("No annotations to process")
        sys.exit(1)

    # ---- Optional temporal interpolation for sync correction ----
    do_interp = args.cam0_timestamps is not None and args.cam1_timestamps is not None
    if do_interp:
        print(f"Loading timestamps for sync interpolation:")
        cam0_times = load_timestamps(args.cam0_timestamps)
        cam1_times = load_timestamps(args.cam1_timestamps)
        print(f"  cam0: {len(cam0_times)} frames, cam1: {len(cam1_times)} frames")
        # Build cam1 annotation map (frame_idx -> uv1) from the stereo CSV
        cam1_anns = {r["frame_idx"]: (r["u1"], r["v1"]) for r in annotations}
        # Stats: how big are the time offsets we're correcting?
        offsets_ms = [(cam1_times.get(r["frame_idx"], 0) - cam0_times.get(r["frame_idx"], 0)) * 1000
                      for r in annotations
                      if r["frame_idx"] in cam0_times and r["frame_idx"] in cam1_times]
        if offsets_ms:
            offs = np.array(offsets_ms)
            print(f"  raw cam1-cam0 offset on annotated frames: mean={offs.mean():.2f}ms  "
                  f"abs median={np.median(np.abs(offs)):.2f}ms  abs max={np.max(np.abs(offs)):.2f}ms")
            print(f"  => applying linear temporal interpolation on cam1 to align with cam0 times")
    else:
        print("(no timestamps provided; using naive frame-N pairing — sync residual NOT corrected)")

    # Triangulate every frame
    points_3d = []
    for r in annotations:
        if do_interp and r["frame_idx"] in cam0_times:
            target_t = cam0_times[r["frame_idx"]]
            uv1_corrected = interpolate_pixel_at_time(cam1_anns, cam1_times, target_t)
        else:
            uv1_corrected = (r["u1"], r["v1"])
        xyz = triangulate_point(
            calib["cam0"]["K"], calib["cam0"]["dist"],
            calib["cam0"]["rvec"], calib["cam0"]["tvec"],
            calib["cam1"]["K"], calib["cam1"]["dist"],
            calib["cam1"]["rvec"], calib["cam1"]["tvec"],
            (r["u0"], r["v0"]), uv1_corrected,
        )
        points_3d.append(xyz)
    points_3d = np.array(points_3d)

    # Displacement vectors from the FIRST labeled frame
    origin = points_3d[0]
    deltas = points_3d - origin
    distances = np.linalg.norm(deltas, axis=1)

    # Write output
    out_path = args.output or args.stereo_csv.with_suffix(".triangulated.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_idx", "x_mm", "y_mm", "z_mm",
                    "displacement_mm", "dx_mm", "dy_mm", "dz_mm", "phase"])
        for r, xyz, d, dist in zip(annotations, points_3d, deltas, distances):
            w.writerow([r["frame_idx"],
                        f"{xyz[0]:.4f}", f"{xyz[1]:.4f}", f"{xyz[2]:.4f}",
                        f"{dist:.4f}", f"{d[0]:.4f}", f"{d[1]:.4f}", f"{d[2]:.4f}",
                        r["phase"]])

    # Quick summary
    print(f"\n3D trajectory summary:")
    print(f"  origin (first labeled frame): ({origin[0]:.2f}, {origin[1]:.2f}, {origin[2]:.2f}) mm")
    print(f"  displacement range: {distances.min():.3f} to {distances.max():.3f} mm")
    print(f"  median displacement: {np.median(distances):.3f} mm")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
