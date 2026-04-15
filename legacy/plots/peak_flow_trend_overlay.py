"""Overlay mean-peak-flow-per-lap curves from the two trend datasets.

Quick one-off script — not part of the app.
  python legacy/plots/peak_flow_trend_overlay.py
"""

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATASETS = [
    {
        "csv": "outputs/Flow-Resistance-90-0-90-Final-Draft.csv",
        "labels": {
            1: "90",
            2: "80",
            3: "70",
            4: "60",
            5: "50",
            6: "40",
            7: "30",
            8: "20",
            9: "10",
            10: "0",
        },
        "lap_filter": lambda ln: 1 <= ln <= 10,
        "name": "90 to 0",
        "color": "green",
        "trend_color": "darkgreen",
    },
    {
        "csv": "outputs/rhs_2026-04-12_15-33-42.csv",
        "labels": {i: str(60 - 5 * (i - 1)) for i in range(1, 14)},
        "lap_filter": lambda ln: 1 <= ln <= 13,
        "name": "60 to 0",
        "color": "purple",
        "trend_color": "indigo",
    },
]


def find_flow_peaks(flow: np.ndarray) -> np.ndarray:
    change_mask = np.concatenate(([True], flow[1:] != flow[:-1]))
    step_v = flow[change_mask]
    peaks = []
    for i in range(1, len(step_v) - 1):
        if step_v[i] > step_v[i - 1] and step_v[i] > step_v[i + 1]:
            peaks.append(step_v[i])
    return np.array(peaks)


def summarize(dataset: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (valve_angles, means, stds) for a dataset, sorted by angle."""
    df = pd.read_csv(dataset["csv"])
    if "Lap" not in df.columns or df["Lap"].nunique() < 2:
        print(f"{dataset['csv']}: needs a 'Lap' column with multiple laps.")
        sys.exit(1)

    lap_nums = [ln for ln in sorted(df["Lap"].unique()) if dataset["lap_filter"](ln)]
    angles, means, stds = [], [], []
    print(f"\n{dataset['name']} ({dataset['csv']}):")
    for ln in lap_nums:
        sub = df[df["Lap"] == ln]
        peaks = find_flow_peaks(sub["Flow Rate (mL/s)"].values)
        if len(peaks) == 0:
            print(f"  lap {ln} ({dataset['labels'].get(ln)} deg): no peaks — skipped")
            continue
        try:
            angle = float(dataset["labels"][ln])
        except (KeyError, ValueError):
            continue
        angles.append(angle)
        means.append(float(np.mean(peaks)))
        stds.append(float(np.std(peaks)))
        print(
            f"  {angle:.0f} deg: n={len(peaks)}, mean={means[-1]:.2f}, std={stds[-1]:.2f}"
        )

    order = np.argsort(angles)
    return np.array(angles)[order], np.array(means)[order], np.array(stds)[order]


def trend(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, str]:
    xx = np.linspace(x.min(), x.max(), 300)
    try:
        from scipy.interpolate import PchipInterpolator

        yy = PchipInterpolator(x, y)(xx)
        return xx, yy, "Trend"
    except Exception:
        return xx, np.interp(xx, x, y), "Trend (linear)"


def main() -> None:
    title = (
        input("Plot title (Enter for default): ").strip()
        or "Peak flow rate vs ball-valve angle (overlay)"
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    for ds in DATASETS:
        x, m, s = summarize(ds)
        if len(x) < 2:
            print(f"{ds['name']}: not enough points to fit.")
            continue
        ax.errorbar(
            x,
            m,
            yerr=s,
            fmt="o",
            color=ds["color"],
            ecolor="gray",
            capsize=5,
            markersize=8,
            label=f"{ds['name']} — mean peak ± STD",
        )
        xx, yy, fit_label = trend(x, m)
        ax.plot(
            xx,
            yy,
            "-",
            color=ds["trend_color"],
            alpha=0.8,
            label=f"{ds['name']} — {fit_label}",
        )

    ax.set_xlabel("Ball Valve (deg)")
    ax.set_ylabel("Mean Peak Flow Rate (mL/s)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.invert_xaxis()  # match original scripts: high angle on left
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
