# Multi-CSV Flow CV Comparison Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone script that compares flow rate CV (peaks and troughs) across multiple recorded CSVs in a grouped bar chart.

**Architecture:** Single standalone script at `legacy/plots/compare_cv.py`. Reuses peak/trough detection and CV computation logic from `legacy/plots/view_csv.py` (copied, not imported — these are standalone legacy scripts). No tests required per project CLAUDE.md mock data rules (this is a legacy plotting script, not a core module).

**Tech Stack:** Python 3.11+, pandas, numpy, matplotlib

**Spec:** `docs/superpowers/specs/2026-04-13-compare-cv-design.md`

---

### Task 1: Create compare_cv.py with analysis functions

**Files:**
- Create: `legacy/plots/compare_cv.py`

- [ ] **Step 1: Create the file with imports and helper functions**

Copy `find_flow_peaks_and_troughs` and `compute_cv` from `legacy/plots/view_csv.py` (lines 92-163), then add folder input, CSV discovery, trial naming, per-CSV analysis, and the grouped bar chart.

```python
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def find_flow_peaks_and_troughs(
    t: pd.Series, flow: pd.Series
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Detect local max/min turning points in a step-function flow signal.

    Collapses consecutive duplicate values to find the underlying steps,
    then identifies where direction reverses (peak = higher than both
    neighbors, trough = lower than both neighbors among the step levels).
    """
    t_arr = t.values
    flow_arr = flow.values

    # Collapse consecutive duplicates to get step change points
    change_mask = np.concatenate(([True], flow_arr[1:] != flow_arr[:-1]))
    step_idx = np.where(change_mask)[0]
    step_t = t_arr[step_idx]
    step_v = flow_arr[step_idx]

    # Find all turning points among the step levels
    raw_peaks: list[tuple[float, float, int]] = []
    raw_troughs: list[tuple[float, float, int]] = []
    for i in range(1, len(step_v) - 1):
        if step_v[i] > step_v[i - 1] and step_v[i] > step_v[i + 1]:
            raw_peaks.append((step_t[i], step_v[i], i))
        elif step_v[i] < step_v[i - 1] and step_v[i] < step_v[i + 1]:
            raw_troughs.append((step_t[i], step_v[i], i))

    # Filter: a peak must be >10 mL/s above its nearest trough(s)
    peak_times: list[float] = []
    peak_vals: list[float] = []
    trough_times: list[float] = []
    trough_vals: list[float] = []
    trough_arr = np.array([v for _, v, _ in raw_troughs]) if raw_troughs else np.array([])
    trough_t_arr = np.array([t for t, _, _ in raw_troughs]) if raw_troughs else np.array([])

    for pt, pv, pi in raw_peaks:
        if len(trough_t_arr) == 0:
            peak_times.append(pt)
            peak_vals.append(pv)
            continue
        before = np.where(trough_t_arr < pt)[0]
        after = np.where(trough_t_arr > pt)[0]
        prev_tv = trough_arr[before[-1]] if len(before) else None
        next_tv = trough_arr[after[0]] if len(after) else None
        ok = True
        if prev_tv is not None and pv - prev_tv <= 10.0:
            ok = False
        if next_tv is not None and pv - next_tv <= 10.0:
            ok = False
        if ok:
            peak_times.append(pt)
            peak_vals.append(pv)

    # Keep only troughs that sit between accepted peaks
    if len(peak_times) >= 2:
        for tt, tv, ti in raw_troughs:
            if peak_times[0] <= tt <= peak_times[-1]:
                trough_times.append(tt)
                trough_vals.append(tv)
    else:
        trough_times = [t for t, _, _ in raw_troughs]
        trough_vals = [v for _, v, _ in raw_troughs]

    return (
        np.array(peak_times), np.array(peak_vals),
        np.array(trough_times), np.array(trough_vals),
    )


def compute_cv(values: np.ndarray) -> float:
    """Coefficient of variation (std / mean) as a percentage."""
    if len(values) == 0 or np.mean(values) == 0:
        return 0.0
    return (np.std(values) / np.mean(values)) * 100


def main() -> None:
    # --- Get folder path ---
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    else:
        folder = Path(input("Enter folder path containing CSVs: ").strip().strip('"'))

    if not folder.is_dir():
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    csv_files = sorted(folder.glob("*.csv"))
    if len(csv_files) < 2:
        print(f"Error: Need at least 2 CSV files, found {len(csv_files)} in '{folder}'.")
        sys.exit(1)

    print(f"\nFound {len(csv_files)} CSV files:")
    for i, f in enumerate(csv_files, 1):
        print(f"  {i}. {f.name}")

    # --- Trial naming ---
    name_input = input("\nName each trial? (y/N): ").strip().lower()
    if name_input == "y":
        trial_names: list[str] = []
        for i, f in enumerate(csv_files, 1):
            name = input(f"  Name for {f.name} (Enter for '{i}'): ").strip()
            trial_names.append(name if name else str(i))
    else:
        trial_names = [str(i) for i in range(1, len(csv_files) + 1)]

    # --- Analyze each CSV ---
    peak_cvs: list[float] = []
    trough_cvs: list[float] = []

    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        t = df["Time (s)"]
        flow = df["Flow Rate (mL/s)"]
        _, peak_vals, _, trough_vals = find_flow_peaks_and_troughs(t, flow)
        peak_cvs.append(compute_cv(peak_vals))
        trough_cvs.append(compute_cv(trough_vals))

    # --- Grouped bar chart ---
    x = np.arange(len(trial_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(8, len(trial_names) * 2), 6))
    bars_peak = ax.bar(x - width / 2, peak_cvs, width, label="Peaks CV", color="red", alpha=0.8)
    bars_trough = ax.bar(x + width / 2, trough_cvs, width, label="Troughs CV", color="blue", alpha=0.8)

    # Label bars with CV values
    for bar in bars_peak:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height, f"{height:.1f}%",
                ha="center", va="bottom", fontsize=9, fontweight="bold")
    for bar in bars_trough:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height, f"{height:.1f}%",
                ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xlabel("Trial")
    ax.set_ylabel("CV (%)")
    ax.set_title("Flow Rate CV Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(trial_names)
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script manually to verify it works**

Run with a folder containing at least 2 CSVs:
```bash
conda run -n rhs-app python legacy/plots/compare_cv.py outputs/
```
Expected: Interactive prompts, then a grouped bar chart window opens.

- [ ] **Step 3: Commit**

```bash
git add legacy/plots/compare_cv.py
git commit -m "add multi-CSV flow CV comparison bar chart tool"
```
