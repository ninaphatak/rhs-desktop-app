"""Plot per-marker stereo triangulation error for water vs analog calibration.

Reads the validation block from each stereo_calib_<fluid>.json and renders a
presentation-quality two-panel bar chart of 3D triangulation error (mm) per
marker, one panel per fluid, with median line, max-marker callout, and stats.

Output: outputs/calibration_error_per_marker.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
CALIB_DIR = REPO / "outputs" / "calib"
OUT_PATH = REPO / "outputs" / "calibration_error_per_marker.png"

FLUIDS = {
    "water": {
        "color": "#1f77b4",
        "edge": "#10446e",
        "label": "Water  (refractive index n ≈ 1.333)",
    },
    "analog": {
        "color": "#d97706",
        "edge": "#8a4a04",
        "label": "35% Glycerin Blood Analog  (n ≈ 1.385)",
    },
}

GOOD_THRESHOLD_MM = 0.5  # "sub-millimeter" target guide


def load_errors(fluid: str) -> dict[int, float]:
    path = CALIB_DIR / f"stereo_calib_{fluid}.json"
    data = json.loads(path.read_text())
    pm = data["validation"]["triangulation_error_mm"]["per_marker"]
    return {int(k): float(v) for k, v in pm.items()}


def color_for_value(v: float, base: str) -> str:
    """Slightly fade bars that are well below the threshold for visual weight."""
    return base


def draw_panel(ax, fluid: str, errs: dict[int, float], marker_ids: list[int], ymax: float) -> None:
    meta = FLUIDS[fluid]
    vals = np.array([errs.get(m, np.nan) for m in marker_ids])
    x = np.arange(len(marker_ids))

    bars = ax.bar(
        x,
        vals,
        width=0.78,
        color=meta["color"],
        edgecolor=meta["edge"],
        linewidth=0.6,
        zorder=3,
    )

    # highlight worst marker in a darker shade
    worst = int(np.nanargmax(vals))
    bars[worst].set_color(meta["edge"])

    median = float(np.nanmedian(vals))
    mean = float(np.nanmean(vals))
    mx = float(np.nanmax(vals))

    # median line
    ax.axhline(median, color=meta["edge"], linestyle="--", linewidth=1.4, alpha=0.9, zorder=2)
    ax.text(
        len(marker_ids) - 0.5,
        median,
        f"  median = {median:.3f} mm",
        color=meta["edge"],
        va="center",
        ha="left",
        fontsize=10,
        fontweight="bold",
    )

    # max callout — nudge sideways if the worst marker is near a plot edge
    n_markers = len(marker_ids)
    if x[worst] < 3:
        text_x = x[worst] + 3.0
        ha = "left"
    elif x[worst] > n_markers - 4:
        text_x = x[worst] - 3.0
        ha = "right"
    else:
        text_x = x[worst]
        ha = "center"
    ax.annotate(
        f"worst marker: ID {marker_ids[worst]}\n{mx:.3f} mm",
        xy=(x[worst], mx),
        xytext=(text_x, mx + ymax * 0.18),
        ha=ha,
        fontsize=9.5,
        color=meta["edge"],
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=meta["edge"], lw=1.0),
    )

    # stats box in top-right of panel
    n = int(np.sum(~np.isnan(vals)))
    sub_mm_frac = float(np.sum(vals < 1.0)) / n if n else 0.0
    stats = (
        f"n = {n} markers\n"
        f"median  {median:.3f} mm\n"
        f"mean    {mean:.3f} mm\n"
        f"max     {mx:.3f} mm\n"
        f"{int(round(sub_mm_frac*100))}% sub-millimeter"
    )
    ax.text(
        0.985,
        0.96,
        stats,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9.5,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor=meta["edge"], linewidth=1.2),
    )

    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in marker_ids], fontsize=8.5)
    ax.set_ylabel("3D triangulation\nerror (mm)", fontsize=11, fontweight="bold")
    ax.set_title(meta["label"], fontsize=12.5, fontweight="bold", color=meta["edge"], loc="left", pad=8)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.35)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, ymax)
    ax.margins(x=0.005)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def main() -> None:
    errs = {f: load_errors(f) for f in FLUIDS}
    marker_ids = sorted(set().union(*[e.keys() for e in errs.values()]))
    all_vals = np.concatenate([np.array(list(e.values())) for e in errs.values()])
    ymax = float(np.nanmax(all_vals)) * 1.35

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 1, figsize=(15, 8.5), dpi=150, sharex=True)
    fig.suptitle(
        "Stereo Calibration Accuracy — 3D Triangulation Error per Calibration Marker",
        fontsize=15.5,
        fontweight="bold",
        y=0.985,
    )
    fig.text(
        0.5,
        0.945,
        "Single-view DLT calibration  ·  38 markers common to both cameras",
        ha="center",
        va="top",
        fontsize=10.5,
        style="italic",
        color="#444444",
    )

    for ax, fluid in zip(axes, FLUIDS):
        draw_panel(ax, fluid, errs[fluid], marker_ids, ymax)

    axes[-1].set_xlabel("Calibration Marker ID", fontsize=11.5, fontweight="bold")

    fig.text(
        0.5,
        0.01,
        "Error = ||triangulated_xyz − CAD_xyz||",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color="#666666",
    )

    plt.tight_layout(rect=(0, 0.025, 1, 0.93))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
