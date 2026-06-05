# Dense Optical Flow Dataset Exporter — Implementation Plan
_2026-04-20_

> **HISTORICAL — workstream killed 2026-05-08.** The HDF5 dataset
> exporter described here was deprioritized when the CV deliverable
> pivoted to direct metric (mm) leaflet displacement via stereo
> calibration + triangulation. See
> `docs/plans/2026-05-08-stereo-calibration-design.md` for the
> active design. Camera-angle references were updated from "30°" to
> "19.3°" for consistency with the as-built geometry, but
> implementation steps below are no longer the active plan.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. See `2026-04-20-flow-export-design.md` for background.

**Goal:** Ship a CLI tool at `tools/flow_export.py` that converts a valve MP4 into an HDF5 dataset (`session.h5` + optional `flow.h5` sidecar) for handoff to Dr. Lee or a downstream researcher.

**Prerequisite:** Tomorrow's data collection (videos with actual valve motion from both 0° and 19.3° Basler cameras). Phase 0 validation runs against one of those.

**Tech stack:** Python 3.11+, OpenCV, NumPy, h5py (new dep), pytest.

**Branch:** `feature/flow-export` (off `feature/optical-flow`).

---

## Task 0: Phase 0 validation spike (run first, after data is in)

**Goal:** Prove the donut-ROI Farneback signal actually tracks valve motion before investing in the full exporter. Cheap (~30 min of coding, ~5 min of running).

**Files:**
- New: `tools/flow_validate.py` (throwaway script)

**Steps:**
1. Load one MP4 and its matching CSV from `outputs/`.
2. For each frame pair, run Farneback (new params: winsize=21, poly_n=7, poly_sigma=1.5, OPTFLOW_FARNEBACK_GAUSSIAN) inside a donut ROI derived from `config/valve_calibration.json`.
3. Compute per-frame mean flow magnitude inside the donut.
4. Align frame timestamps to CSV `elapsed` column, join.
5. Plot mean flow magnitude vs Arduino FLOW channel, compute Pearson r².
6. Report r² in the terminal.

**Gate:** r² ≥ 0.5 → proceed to Task 1. r² < 0.5 → stop. Either the donut ROI is wrong, the scene is dominated by out-of-plane motion, or we need to pivot to threshold-based orifice segmentation (PRD §5.4).

**Do not commit** this script — it's an experimental spike. Delete or .gitignore it after the gate decision.

---

## Task 1: Create `tools/_flow_io.py` — shared I/O helpers

**Files:**
- New: `tools/_flow_io.py`

**Functions:**

```python
def load_calibration(calib_path: Path) -> dict | None:
    """Load valve_calibration.json. Returns None if path does not exist.

    Schema matches tools/calibrate_valve.py output:
        {"valve_center": [cx, cy], "valve_radius": r, "reference_points": [...]}
    """

def build_donut_mask(
    height: int,
    width: int,
    center: tuple[int, int],
    radius: int,
    inner_frac: float = 0.7,
    outer_frac: float = 1.3,
) -> np.ndarray:
    """Return uint8 (H, W) mask, 255 inside donut annulus, 0 elsewhere.
    Inner radius = radius * inner_frac, outer = radius * outer_frac.
    """

def build_roi_crop_bbox(
    center: tuple[int, int],
    radius: int,
    frame_shape: tuple[int, int],
    outer_frac: float = 1.3,
    pad_px: int = 20,
) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) bbox for cropping full-frame to ROI.
    Clipped to frame bounds.
    """

def load_session_dataset(h5_path: Path) -> dict:
    """Load exported session.h5 into a dict convenience view.
    Keys: frames, masks, timestamps, contours (list-per-frame), attrs.
    Used by tests and the 5-minute downstream snippet.
    """
```

**Tests this enables:** mask geometry correctness, calibration-absent path, loader roundtrip.

---

## Task 2: Create `tools/flow_export.py` — core pipeline (no file output yet)

**Files:**
- New: `tools/flow_export.py`

**Functions:**

```python
FARNEBACK_PARAMS = dict(
    pyr_scale=0.5, levels=3, winsize=21,
    iterations=3, poly_n=7, poly_sigma=1.5,
    flags=cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
)
CLAHE_CLIP = 2.0
CLAHE_TILE = (8, 8)
MORPH_CLOSE_KERNEL = (7, 7)
MORPH_OPEN_KERNEL = (3, 3)
MIN_CONTOUR_AREA = 500

def preprocess_frame(gray: np.ndarray, clahe: cv2.CLAHE) -> np.ndarray:
    """Apply CLAHE to normalize underwater lighting."""

def compute_farneback_flow(prev: np.ndarray, curr: np.ndarray) -> np.ndarray:
    """Run Farneback with FARNEBACK_PARAMS. Returns (H, W, 2) float32."""

def compute_motion_mask_and_contours(
    flow: np.ndarray,
    threshold_px: float,
    donut_mask: np.ndarray | None,
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Abs-threshold flow magnitude, AND with donut mask, morph clean,
    findContours, filter by MIN_CONTOUR_AREA, keep top 3 by area.
    Returns (mask, contours_list).
    """
```

All params hardcoded at module level. No CLI yet.

---

## Task 3: Add export loop + HDF5 writer to `tools/flow_export.py`

**Files:**
- Modify: `tools/flow_export.py`

**Function:**

```python
def export_video(
    video_path: Path,
    output_path: Path,
    camera_id: str,
    threshold_px: float,
    calib: dict | None,
    write_flow_sidecar: bool,
) -> int:
    """Main export loop.

    1. Open VideoCapture, get fps and frame dims.
    2. Build donut_mask from calib (or None if calib missing — warn).
    3. Compute roi_crop_bbox from calib (or use full frame).
    4. Open session.h5 for writing; set root attrs.
    5. Preallocate datasets with chunk shape (1, h, w) etc.
    6. If write_flow_sidecar: open flow.h5 alongside.
    7. Loop over frame pairs:
         - read curr, convert to gray, CLAHE, crop to ROI
         - Farneback(prev, curr) → flow
         - motion mask + contours
         - append frame/mask/timestamp to session.h5
         - write contour group for frame_<i:05d>
         - if sidecar: append flow to flow.h5
    8. Close files. Return number of frame pairs written.
    """
```

Preallocation note: HDF5 resizable datasets (`maxshape=(None, h, w)`) are simpler than two-pass pre-count. Use `dataset.resize((i+1, h, w))` then write.

---

## Task 4: CLI wrapper + argparse

**Files:**
- Modify: `tools/flow_export.py` — add `main()`

**CLI:**

```
python tools/flow_export.py <video_path> --camera {0deg,19_3deg} [options]

Positional:
  video_path                    Path to input MP4

Required:
  --camera {0deg,19_3deg}         Which camera produced the video

Options:
  --output PATH                 Output .h5 path. Default: <video_stem>_session.h5
  --threshold FLOAT             Motion mask threshold in px/frame. Default: 1.5
  --calib PATH                  Calibration JSON. Default: config/valve_calibration.json
  --with-flow                   Also write flow.h5 sidecar (adds ~1 GB per 60s)
  --no-calib                    Skip ROI masking; process full frame.
```

`--camera` is required because there's no reliable way to infer from the video file.

---

## Task 5: Tests — `tests/test_flow_export.py`

**Files:**
- New: `tests/test_flow_export.py`

**Test cases:**

1. **`test_absolute_threshold_produces_correct_mask`**
   Build synthetic flow `(H, W, 2)` with known magnitudes (values at exactly 0.5, 1.5, 3.0 px). Assert mask is 0/255 exactly where magnitude ≥ threshold.

2. **`test_donut_mask_geometry`**
   Build a 200×200 donut mask with center (100,100), radius 50, inner_frac=0.7, outer_frac=1.3. Assert center pixel is 0, pixel at radius 50 is 255, pixel at corner is 0, pixel at radius 80 is 0.

3. **`test_export_roundtrip_on_synthetic_mp4`**
   Write a synthetic 20-frame MP4 to `tmp_path` with `cv2.VideoWriter`. Call `export_video` with a synthetic calib dict. Open the resulting `session.h5` and assert: `/frames` shape is `(19, h, w)`, root attrs include `camera_id`, `fps`, `flow_threshold_px`, `farneback_params`. `/meta/timestamp_s` length matches `/frames`.

4. **`test_load_session_dataset_roundtrip`**
   After Task 5.3 creates the H5, call `load_session_dataset` and assert the loaded frames round-trip the written values.

5. **`test_missing_calibration_path`**
   Pass `calib=None` (and `--no-calib` analog). Assert `export_video` completes, root attr `donut_inner_frac` is absent or recorded as `null`.

Do NOT test Farneback's numerical output — trust OpenCV.

---

## Task 6: `environment.yml` + handoff README

**Files:**
- Modify: `environment.yml` — add `h5py` to dependencies
- New: `tools/README_DATASET.md`

**README structure (1 page, ~300 words):**
1. What this is (1 paragraph — valve recording, camera, date)
2. File inventory (`session.h5`, optional `flow.h5`, source MP4)
3. Install (`pip install h5py numpy`)
4. Schema table (copy-paste from design doc)
5. Quickstart snippet (10 lines)
6. Calibration note (where `valve_center`/`valve_radius` came from)
7. Params used (Farneback settings, threshold — from HDF5 attrs)
8. Known caveats (bubbles, leaflet bowing produces near-zero 2D flow)
9. Contact (Nina Phatak, date)

---

## Task 7: Run on real data; tune threshold

**After tomorrow's recordings are in:**

1. Run `tools/flow_export.py recording_0deg.mp4 --camera 0deg --with-flow`
2. Open `session.h5` in a REPL, visualize a few mid-cycle mask frames with matplotlib.
3. If mask is too sparse (missing leaflet motion): drop threshold to 1.0.
4. If mask is noisy with bubble speckle: raise to 2.0 or tighten `min_contour_area` to 800.
5. Commit final threshold as the default after one visual QA pass.
6. Repeat for 19.3° recording.
7. Zip up `session.h5 + flow.h5 + README_DATASET.md + source MP4` into a handoff folder for Dr. Lee.

---

## Task 9: Annotation tool — `tools/annotate_leaflets.py`

**Ships AFTER the core exporter is working and a dataset exists.**

**Files:**
- New: `tools/annotate_leaflets.py`

**Behavior:**
- CLI: `python tools/annotate_leaflets.py <session.h5> [--output leaflet_annotations.json]`
- Loads frames from the HDF5 dataset.
- Displays one frame at a time in an OpenCV window.
- Mouse: left-click adds a polygon vertex; `ENTER` closes the current polygon and starts a new one; `N` moves to next frame; `P` to previous; `U` undoes last vertex; `S` saves; `Q` quits.
- Sampling: by default, shows every Nth frame such that 30-50 frames span the video. User can override with `--every-n-frames`.
- Output JSON schema:
  ```json
  {
    "source_h5": "session.h5",
    "created_utc": "...",
    "annotations": {
      "00100": [[[x1,y1],[x2,y2],...], [[...]]],   // list of polygons per frame
      "00250": [...],
      ...
    }
  }
  ```
- Keep it under 200 lines. No external deps beyond `cv2, numpy, json`.

**Tests:** 1-2 cases. Construct a synthetic annotation dict and assert it round-trips through save/load. Do NOT test the GUI.

---

## Task 10: Parameter sweep — `tools/param_sweep.py`

**Files:**
- New: `tools/param_sweep.py`

**Behavior:**
- CLI: `python tools/param_sweep.py <video.mp4> --camera {0deg,19_3deg} --grid <grid.json>`
- `grid.json` schema:
  ```json
  {
    "winsize": [15, 21, 31],
    "flow_threshold_px": [1.0, 1.5, 2.0],
    "donut_outer_frac": [1.2, 1.3, 1.4]
  }
  ```
- For each parameter combination (Cartesian product, default 27 runs):
  - Re-runs the exporter with that parameter set.
  - Writes output to `sweeps/<param_hash>/session.h5`.
  - Computes metrics against annotations + Arduino CSV.
  - Appends a row to `sweeps/summary.csv`:
    `param_hash, winsize, threshold, donut_outer, mean_iou, arduino_pearson_r, median_centroid_err_px`
- Reuses `export_video` from `tools/flow_export.py` but accepts an override-params dict. This means Task 2 needs to accept an optional `params_override: dict | None` argument — adjust during Task 2 or add a thin wrapper here.

**Expected runtime:** 27 runs × 30-60s per run ≈ 15-30 min on a 60s input video. Acceptable.

**Tests:** parameter-grid expansion logic (turn grid.json into list of param dicts). Do NOT test the full sweep in pytest.

---

## Task 11: Metrics module — `tools/_metrics.py`

**Files:**
- New: `tools/_metrics.py` (shared between `param_sweep.py` and `validation_report.py`)

**Functions:**
```python
def polygon_iou(poly_a: np.ndarray, poly_b: np.ndarray, frame_shape: tuple[int, int]) -> float:
    """Rasterize both polygons into binary masks (via cv2.fillPoly), compute IoU."""

def centroid_distance(poly_a: np.ndarray, poly_b: np.ndarray) -> float:
    """Euclidean distance between polygon centroids (from cv2.moments)."""

def arduino_flow_correlation(
    flow_time_series: np.ndarray,
    flow_timestamps: np.ndarray,
    csv_path: Path,
) -> tuple[float, float]:
    """Interpolate Arduino FLOW onto flow timestamps, return (pearson_r, peak_offset_ms)."""
```

**Tests:** 3-5 cases. IoU on identical polygons = 1.0. IoU on disjoint polygons = 0.0. Centroid distance on known polygons. Correlation on synthetic in-phase / anti-phase signals.

---

## Task 12: Validation report — `tools/validation_report.py`

**Files:**
- New: `tools/validation_report.py`
- New: `docs/validation_results.md` (writeup)

**Behavior:**
- Reads `sweeps/summary.csv`.
- Produces three figures using matplotlib, saved to `sweeps/figures/`:
  1. Heatmap: mean IoU across parameter grid (2D projection, fix one param).
  2. Heatmap: Arduino Pearson r across parameter grid.
  3. Time-series overlay: flow-derived valve-open signal vs Arduino FLOW, for the winning parameter set.
- Writes `docs/validation_results.md`: 1 page. Sections: setup, parameter grid, winning settings, headline metrics, caveats, figures.

No tests. Pure scripting + plotting.

---

## Task 8: Docs

**Files:**
- Modify: `docs/PRD.md`
  - §5.6: add a note that dense flow on **the boundary** (donut ROI) is viable; the rejection applies to dense flow on the untextured **surface interior**.
  - Add new §7 "Dataset Export Pipeline" describing the exporter at the level of a user, not the implementer.
  - Update §12 build state table: mark leaflet_tracker as "deferred / superseded by dataset export", mark flow_export as shipped.
- Modify: `CLAUDE.md` — already updated in the same PR that ships this plan (see main commit).

---

## Build sequence summary

**Core exporter (weekend 1):**

| Phase | Tasks | Gate |
|---|---|---|
| 0 | Validation spike (Task 0) | r² ≥ 0.5 vs Arduino FLOW |
| 1 | `_flow_io.py` (Task 1) + core pipeline (Task 2) | Unit tests on synthetic flow pass |
| 2 | HDF5 writer (Task 3) + CLI (Task 4) | `session.h5` loads in REPL |
| 3 | Tests (Task 5) + env/README (Task 6) | `pytest tests/ -v` green |
| 4 | Real-data tuning (Task 7) | Visual QA on mask frames |

**Validation study (weekend 2, after core is stable and a dataset exists):**

| Phase | Tasks | Gate |
|---|---|---|
| 5 | Annotation tool (Task 9) | 30-50 frames annotated on one session |
| 6 | Metrics (Task 11) + param sweep (Task 10) | `sweeps/summary.csv` populated |
| 7 | Validation report (Task 12) | `docs/validation_results.md` + figures committed |
| 8 | Docs (Task 8) | PRD + CLAUDE.md reflect current state |

Each phase is one commit. Phases 5-7 are the deliverable that turns this from "data pipeline" into "validated optical flow pipeline" — the research framing for Dr. Lee.
