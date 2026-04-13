# Multi-CSV Flow CV Comparison Tool

**Date:** 2026-04-13
**Location:** `legacy/plots/compare_cv.py`

## Purpose

Standalone script that compares flow rate consistency across multiple recorded trials. Given a folder of CSVs, it produces a grouped bar chart showing the coefficient of variation (CV) of detected peaks and troughs for each trial side by side.

## Behavior

1. **Input:** Folder path via CLI argument or interactive prompt.
2. **Discovery:** Finds all `*.csv` files in that folder, sorted alphabetically. Exits with an error message if fewer than 2 CSVs are found.
3. **Trial naming:** Prompts user to name each trial. If declined, defaults to `1, 2, 3...`.
4. **Analysis per CSV:**
   - Reads `Time (s)` and `Flow Rate (mL/s)` columns.
   - Runs peak/trough detection (same algorithm as `view_csv.py`: collapse consecutive duplicates into steps, find turning points, filter peaks >10 mL/s above adjacent troughs).
   - Computes CV = (std / mean) * 100 for peaks and troughs separately.
5. **Output:** A single matplotlib grouped bar chart.

## Chart Specification

- **X-axis label:** "Trial"
- **X-axis ticks:** One group per CSV, labeled with trial name
- **Y-axis label:** "CV (%)"
- **Y-axis range:** 0 to 100
- **Bars per group:** 2 — Peaks CV (red) and Troughs CV (blue)
- **Bar labels:** CV value displayed on top of each bar (e.g. "12.3%")
- **Legend:** "Peaks CV", "Troughs CV"
- **Title:** "Flow Rate CV Comparison"

## Functions (copied from view_csv.py)

- `find_flow_peaks_and_troughs(t, flow)` — returns peak/trough times and values
- `compute_cv(values)` — returns CV as percentage

## No time filtering

Uses full CSV data. No time range or lap filtering.

## Dependencies

pandas, numpy, matplotlib (all already in the conda env).
