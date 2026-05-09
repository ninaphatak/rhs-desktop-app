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
    args = ap.parse_args()

    print(f"Loading calibration from {args.calib_json}")
    calib = load_calibration(args.calib_json)
    print(f"Loading stereo annotations from {args.stereo_csv}")
    annotations = load_stereo_annotations(args.stereo_csv)
    print(f"  {len(annotations)} stereo-labeled frames")
    if not annotations:
        print("No annotations to process")
        sys.exit(1)

    # Triangulate every frame
    points_3d = []
    for r in annotations:
        xyz = triangulate_point(
            calib["cam0"]["K"], calib["cam0"]["dist"],
            calib["cam0"]["rvec"], calib["cam0"]["tvec"],
            calib["cam1"]["K"], calib["cam1"]["dist"],
            calib["cam1"]["rvec"], calib["cam1"]["tvec"],
            (r["u0"], r["v0"]), (r["u1"], r["v1"]),
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
