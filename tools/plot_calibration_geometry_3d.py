"""Render a 3D view of the calibration coordinate frame: the 41 calibration
markers on the calibration object plus both camera optical (EPP) positions.

Output: outputs/calibration_geometry_3d.png

View convention: viewer sits at the camera position (world +Z), looking
toward the object at the origin. So in the rendered plot:
    world +X is to the right on screen
    world +Y is up on screen
    world +Z is OUT of the page toward the viewer (cameras are foreground)
    world -Z is INTO the page (the direction of flow, away from cameras)
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers 3d projection)

REPO = Path(__file__).resolve().parents[1]
MARKERS_CSV = REPO / "markers.csv"
OUT_PATH = REPO / "outputs" / "calibration_geometry_3d.png"


def load_markers() -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    marker_ids: list[int] = []
    marker_xyz: list[tuple[float, float, float]] = []
    cams: dict[str, np.ndarray] = {}
    with MARKERS_CSV.open() as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            name = row[0]
            xyz = (float(row[1]), float(row[2]), float(row[3]))
            try:
                marker_ids.append(int(name))
                marker_xyz.append(xyz)
            except ValueError:
                cams[name] = np.array(xyz)
    return np.array(marker_ids), np.array(marker_xyz), cams


def to_mpl(world_xyz) -> np.ndarray:
    """Map world (X, Y, Z) → matplotlib (X, Z, Y)."""
    a = np.asarray(world_xyz, dtype=float)
    if a.ndim == 1:
        return np.array([a[0], a[2], a[1]])
    return np.column_stack([a[:, 0], a[:, 2], a[:, 1]])


def main() -> None:
    ids, mxyz, cams = load_markers()
    cam0 = cams["cam0"]
    cam1 = cams["cam1"]

    fig = plt.figure(figsize=(14, 10), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("white")
    ax.xaxis.pane.set_alpha(0.0)
    ax.yaxis.pane.set_alpha(0.05)
    ax.zaxis.pane.set_alpha(0.0)

    # ---- calibration markers, colored by z-depth ring ----
    z_to_color = {
        -11.76: "#08306b",
        -7.84: "#2171b5",
        -3.92: "#6baed6",
        0.0: "#c6dbef",
    }
    z_levels = sorted(set(mxyz[:, 2].round(2)))
    for z in z_levels:
        mask = np.isclose(mxyz[:, 2], z, atol=0.05)
        pts = mxyz[mask]
        pts_mpl = to_mpl(pts)
        ax.scatter(
            pts_mpl[:, 0], pts_mpl[:, 1], pts_mpl[:, 2],
            c=z_to_color.get(round(z, 2), "#444444"),
            s=60, edgecolors="white", linewidth=0.8,
            depthshade=False,
            label=f"markers @ z = {z:+.2f} mm  (n={mask.sum()})",
        )

    # ---- origin ----
    o = to_mpl([0, 0, 0])
    ax.scatter([o[0]], [o[1]], [o[2]], color="black", s=130, marker="o",
               depthshade=False, zorder=11, edgecolors="white", linewidth=1.2)
    origin_label_mpl = (45, 30, -30)
    ax.plot([0, origin_label_mpl[0]], [0, origin_label_mpl[1]], [0, origin_label_mpl[2]],
            color="#444444", linewidth=0.8, alpha=0.6)
    ax.text(*origin_label_mpl, "origin (0, 0, 0)",
            fontsize=10, fontweight="bold", color="black")

    # ---- cameras ----
    cam_specs = [
        ("cam0  (0° direct view)", cam0, "#7f3fbf", ( 18,   5,  18)),
        ("cam1  (19.3° tilted)",   cam1, "#c43f9e", (-30,   5,  18)),
    ]
    for name, pos, color, (dx, dy, dz) in cam_specs:
        p_mpl = to_mpl(pos)
        ax.scatter(p_mpl[0], p_mpl[1], p_mpl[2], color=color, marker="*",
                   s=500, edgecolors="black", linewidth=1.2, depthshade=False, zorder=11)
        # sight line from origin to camera
        ax.plot([0, p_mpl[0]], [0, p_mpl[1]], [0, p_mpl[2]],
                color=color, linestyle="--", linewidth=1.3, alpha=0.7)
        ax.text(p_mpl[0] + dx, p_mpl[1] + dy, p_mpl[2] + dz,
                f"{name}\n({pos[0]:+.2f}, {pos[1]:+.2f}, {pos[2]:+.2f}) mm",
                fontsize=10.5, fontweight="bold", color=color)

    # ---- styling ----
    # matplotlib X = world X (lateral), matplotlib Y = world Z (depth),
    # matplotlib Z = world Y (vertical). Labels reflect the WORLD frame.
    ax.set_xlabel("X (mm)  left ↔ right", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_ylabel("Z (mm)  forward (−Z) / back (+Z)", fontsize=11, fontweight="bold", labelpad=12)
    ax.set_zlabel("Y (mm)  up / down", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_title(
        "Calibration Coordinate Frame:\nMarker Positions and Camera Optical Centers (CAD)",
        fontsize=14, fontweight="bold", pad=18,
    )

    # extents in matplotlib coords
    ax.set_xlim(-80, 80)          # world X
    ax.set_ylim(-30, 240)         # world Z (cameras at ~+200)
    ax.set_zlim(-80, 80)          # world Y
    try:
        ax.set_box_aspect((1.0, 1.7, 1.0))
    except AttributeError:
        pass

    # View from the camera side (+Z) looking toward the origin. With
    # azim=112 the matplotlib Y axis (world Z) points OUT of the page
    # so cameras appear in the foreground. invert_xaxis() then flips the
    # mpl X axis on screen so world +X stays on the right (camera POV).
    ax.view_init(elev=20, azim=112)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9.5, framealpha=0.95, bbox_to_anchor=(-0.02, 0.92))

    plt.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
