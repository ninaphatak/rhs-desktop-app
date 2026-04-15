"""Plot mean peak flow rate per lap with error bars and a trend line.

Quick one-off script — not part of the app.
Hardcoded for outputs/rhs_2026-04-12_15-33-42.csv (lap 1 = 60deg, -5deg per lap).
  python legacy/plots/peak_flow_trend2.py
"""

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HARDCODED_CSV = "outputs/rhs_2026-04-12_15-33-42.csv"
# Lap 1 = 60, each lap decrements by 5, stop at lap 13 = 0.
HARDCODED_LABELS = {i: str(60 - 5 * (i - 1)) for i in range(1, 14)}
MAX_LAP = 13


def find_flow_peaks(flow: np.ndarray) -> np.ndarray:
    """Return flow values at all local-max turning points (no amplitude gate)."""
    change_mask = np.concatenate(([True], flow[1:] != flow[:-1]))
    step_v = flow[change_mask]
    peaks = []
    for i in range(1, len(step_v) - 1):
        if step_v[i] > step_v[i - 1] and step_v[i] > step_v[i + 1]:
            peaks.append(step_v[i])
    return np.array(peaks)


def main() -> None:
    filepath = HARDCODED_CSV
    df = pd.read_csv(filepath)

    if "Lap" not in df.columns or df["Lap"].nunique() < 2:
        print("CSV must have a 'Lap' column with multiple laps.")
        sys.exit(1)

    lap_nums = [ln for ln in sorted(df["Lap"].unique()) if 1 <= ln <= MAX_LAP]
    labels: dict[int, str] = {
        ln: HARDCODED_LABELS.get(ln, f"Lap {ln}") for ln in lap_nums
    }

    means, stds, xs, used_labels = [], [], [], []
    for i, ln in enumerate(lap_nums):
        sub = df[df["Lap"] == ln]
        peaks = find_flow_peaks(sub["Flow Rate (mL/s)"].values)
        if len(peaks) == 0:
            print(f"  {labels[ln]}: no peaks detected — skipping")
            continue
        means.append(float(np.mean(peaks)))
        stds.append(float(np.std(peaks)))
        xs.append(i + 1)
        used_labels.append(labels[ln])
        print(
            f"  {labels[ln]}: n={len(peaks)}, mean={means[-1]:.2f}, std={stds[-1]:.2f}"
        )

    if len(xs) < 2:
        print("Need at least 2 laps with peaks to fit a curve.")
        sys.exit(1)

    xs_a = np.array(xs)
    means_a = np.array(means)
    stds_a = np.array(stds)

    xx = np.linspace(xs_a.min(), xs_a.max(), 300)
    try:
        from scipy.interpolate import PchipInterpolator

        yy = PchipInterpolator(xs_a, means_a)(xx)
        fit_label = "Trend"
    except Exception:
        yy = np.interp(xx, xs_a, means_a)
        fit_label = "Trend (linear)"

    title = (
        input("Plot title (Enter for filename): ").strip() or filepath.split("/")[-1]
    )

    _, ax = plt.subplots(figsize=(10, 6))
    ax.errorbar(
        xs_a,
        means_a,
        yerr=stds_a,
        fmt="o",
        color="green",
        ecolor="gray",
        capsize=5,
        markersize=8,
        label="Mean peak ± STD",
    )
    ax.plot(xx, yy, "b-", alpha=0.7, label=fit_label)
    ax.set_xticks(xs_a)
    ax.set_xticklabels(used_labels, rotation=20, ha="right")
    ax.set_ylabel("Mean Peak Flow Rate (mL/s)")
    ax.set_xlabel("Ball Valve (º)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
