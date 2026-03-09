# Design: Remove Flow Rate for Demo (fix/temp-remove-FR)

**Date:** 2026-03-08
**Branch:** fix/temp-remove-FR
**Status:** Approved

## Context

Flow Rate data from the Arduino serial stream is currently invalid. For demo purposes, flow rate is removed entirely from the UI and CSV output on this branch. The Arduino hardware is unchanged and still sends 7 fields — only the codebase is modified.

## Constraints

- `SERIAL_FIELDS` and `SERIAL_FIELD_COUNT` in `config.py` must remain unchanged (7-field parse protocol)
- Camera panel is not touched
- Changes are scoped to this branch only

## New Graph Layout

| | Col 0 | Col 1 |
|---|---|---|
| Row 0 | Pressure (unchanged) | Heart Rate (moved from row 1) |
| Row 1 | Temperature (colspan=2, full width) | |

## Files Changed

### `src/utils/config.py`
- Remove `"Flow Rate (mL/s)"` from `CSV_HEADERS` (6 columns instead of 7)
- `SERIAL_FIELDS` and `SERIAL_FIELD_COUNT` stay unchanged

### `src/core/data_recorder.py`
- In `record_row`, filter `"flow"` from the written row:
  `[data.get(f, 0.0) for f in SERIAL_FIELDS if f != "flow"]`

### `src/ui/graph_panel.py`
- Remove `_flow_plot` and `_flow_curve` from `_init_ui`
- Move HR widget to grid position `(0, 1)`
- Move Temperature widget to grid position `(1, 0, 1, 2)` (colspan=2)
- Remove `_flow_plot` from dark-background loop and `setXRange` loop
- Remove `_flow_curve.setData(...)` from `_refresh_curves`

### `src/ui/plot_dialog.py`
- Switch from 4-subplot (2×2) to 3-subplot layout using `GridSpec`
- Top row: Pressure (left) + Heart Rate (right)
- Bottom row: Temperature spanning full width
- Remove Flow Rate subplot entirely
