# Dense Optical Flow Dataset Exporter — Design Doc
_2026-04-20_

## Problem

The CV pipeline was originally scoped as sparse Lucas-Kanade tracking on leaflet boundary points, with `src/core/leaflet_tracker.py` as the integration target. The LK prototype (`tools/leaflet_flow_test.py`) did not produce reliable tracks on actual valve footage — points drift or lose lock through the open/close cycle, consistent with the textureless white silicone surface and bubble noise described in PRD §5.6.

Meanwhile, Farneback dense flow (`tools/flow_explore.py`) qualitatively captures leaflet motion well in HSV visualization. The project does not need a real-time in-app tracker to succeed — what Dr. Lee (sponsor) can use is a **structured per-frame optical flow dataset** that another researcher can annotate, train a CNN on, or analyze further. This reframes the CV deliverable from "in-app measurement" to "handoff-ready dataset."

## Goal

A standalone CLI tool that ingests an MP4 valve recording from either Basler camera and produces a self-contained HDF5 dataset file plus an optional dense-flow sidecar. Schema is self-describing; a downstream user with `pip install h5py numpy` can read frame 500 and its motion contours in five lines of Python.

## Non-goals

- Not integrating into `src/core/` as a live tracker. If the pipeline proves useful, integration is a future task.
- No stereo reconstruction, no metric (mm) conversion, no depth estimation.
- No parameter tuning UI — Farneback params are hardcoded for reproducibility in the core exporter. Parameter *sensitivity* is analyzed separately in the validation phase (see §Reconstruction Validation below).
- No trained ML model. The annotation set produced in validation is input to a future downstream model, not one we train here.

## Reconstruction validation (added after exporter ships)

The exporter alone produces a dataset. To make the senior design deliverable a proper research contribution — rather than just "a data pipeline" — we add a parameter-sensitivity study that validates the pipeline recovers observable valve motion.

**"Reconstruction" here means motion reconstruction, not 3D geometry reconstruction.** Specifically:

1. **Temporal reconstruction**: flow-derived "valve open-ness" (mean flow magnitude in donut ROI, or total motion-mask area per frame) vs the Arduino FLOW sensor signal. No annotation needed — Arduino CSV is the ground truth. Metric: Pearson r, peak-timing offset in ms.
2. **Spatial reconstruction**: for a small hand-annotated frame set (target 30-50 frames spanning open/closed/transition phases), compare flow-derived leaflet contours against hand-drawn leaflet boundaries. Metrics: IoU per frame, centroid distance, contour-to-contour mean distance.

**Parameter sweep design:** 2-3 parameters, 3 values each, 9-27 total runs. Primary candidates: `winsize ∈ {15, 21, 31}`, `flow_threshold_px ∈ {1.0, 1.5, 2.0}`, `donut_outer_frac ∈ {1.2, 1.3, 1.4}`. Each parameter set gets re-exported (same MP4, different HDF5) and metrics computed. Output: a heatmap of IoU and Arduino-correlation across the parameter grid, plus time-series overlays for the winning setting.

**Annotation tooling:** Lightweight custom tool (`tools/annotate_leaflets.py`) that steps through frames, lets the user draw polygon leaflet boundaries with click-to-add-vertex + enter-to-close, saves to a sidecar JSON next to the HDF5. Avoid CVAT/Label Studio — overkill for 30-50 frames, adds install/hosting friction. Expect ~1 min per annotated frame.

**Why this matters for the project framing:** Without validation, the pitch is "I built a data pipeline." With it, the pitch is "I validated an optical flow pipeline for tricuspid valve motion tracking, with parameter-sensitivity analysis and hand-annotated ground truth." That's a legitimate undergrad research deliverable. It is also what a downstream CNN trainer would need anyway (an annotated set is the training data).

## Key design decisions

### 1. Dense flow at the boundary, not the surface
PRD §5.6 rejected dense flow on the uniform leaflet surface (no texture → no signal). That rejection stands. The pipeline runs Farneback on a **donut ROI** around the orifice boundary — where the bright leaflet meets the dark opening — not on the leaflet interior. The flow Farneback reports *inside* the interior is regularization-propagated hallucination and will be masked out before any downstream use.

### 2. Fixed absolute-magnitude threshold
`flow_explore.py` uses `cv2.normalize(..., NORM_MINMAX)` which rescales per-frame. That's fine for visualization and wrong for datasets — the same threshold means different motion at peak vs. quiet frames. The exporter saves raw float32 flow fields. The binary motion mask is derived with a fixed absolute threshold (default **1.5 px/frame**; range 1.0–2.0 is the working zone based on expected 60fps leaflet kinematics).

### 3. Frames in the core dataset; flow in a sidecar
Per-frame float32 flow at 1920×1200 is ~18 MB/frame → ~1 GB for 60s. It's also the **least reusable** artifact — annotation tools want frames, ML researchers recompute flow with their own params. Core `session.h5` holds grayscale frames + masks + contours + metadata (~500 MB compressed). Optional `flow.h5` sidecar holds the dense flow arrays. Users who only want to annotate skip the sidecar.

### 4. Hardcode Farneback params with a recorded revision
Exposing params as CLI flags means mixed exports with non-comparable magnitudes. Params are fixed in code and stamped into HDF5 root attributes for auditability. Based on CV review of the current scene (textureless leaflet, bubbles, 60fps):

| Param | Current in `flow_explore.py` | New in exporter |
|---|---|---|
| `winsize` | 15 | **21** |
| `poly_n` | 5 | **7** |
| `poly_sigma` | 1.2 | **1.5** |
| `flags` | 0 | **OPTFLOW_FARNEBACK_GAUSSIAN** |

CLAHE (`clipLimit=2.0, tileGridSize=(8,8)`) is applied before flow to normalize uneven underwater lighting.

### 5. Mask cleanup pipeline
Raw thresholded mask fragments badly because of bubble drift. Pipeline:
`threshold → close(7x7) → open(3x3) → min_contour_area=500px² → keep top 3 contours`.

### 6. HDF5 format, single file per video, per camera
`h5py` is the de-facto scientific Python format for large numerical arrays. Self-describing (`h5ls session.h5` prints schema), per-frame chunking gives random access with compression, and the library has been stable for 15+ years. One file per input video keeps the handoff atomic.

### 7. Both cameras supported via the same tool
The 0° and 30° cameras are both producing recordings in the April data collection session. The exporter handles either — `camera_id` is a required CLI arg and gets stamped into the `.h5` attrs. No per-camera code branches.

## Data schema

### Core file: `session.h5`

**Root attributes (global metadata):**
- `camera_id` (str): `"0deg"` or `"30deg"`
- `fps` (float): source video frame rate
- `frame_height`, `frame_width` (int): full-frame dimensions before ROI crop
- `roi_crop_bbox` (int[4]): (x, y, w, h) applied to each frame
- `valve_center` (int[2]): from `tools/calibrate_valve.py` output (in full-frame coords)
- `valve_radius` (int): pixels
- `donut_inner_frac` (float): inner radius multiplier relative to `valve_radius`
- `donut_outer_frac` (float): outer radius multiplier
- `farneback_params` (str): JSON-encoded `{pyr_scale, levels, winsize, iterations, poly_n, poly_sigma, flags}`
- `flow_threshold_px` (float): absolute magnitude threshold
- `preprocess` (str): JSON-encoded `{clahe_clip, clahe_tile}`
- `morph` (str): JSON-encoded `{close_kernel, open_kernel, min_contour_area}`
- `source_video` (str): absolute path of input
- `script_version` (str): git SHA of producing script
- `created_utc` (str): ISO 8601

**Datasets:**

| Path | Shape | dtype | Chunks | Compression |
|---|---|---|---|---|
| `/frames` | (T, h, w) | uint8 | (1, h, w) | gzip-4 |
| `/masks` | (T, h, w) | uint8 | (1, h, w) | gzip-4 |
| `/meta/frame_index` | (T,) | int32 | — | — |
| `/meta/timestamp_s` | (T,) | float64 | — | — |
| `/contours/frame_<i:05d>/contour_<j>` | (N_ij, 2) | int32 | — | — |

`T = N_frames − 1` (flow needs pairs). Dimensions `h, w` are the ROI-cropped values, not full-frame. Frame indices are 0-based pair indices (pair `i` is source frames `i` and `i+1`).

### Sidecar: `flow.h5`

| Path | Shape | dtype | Chunks | Compression |
|---|---|---|---|---|
| `/flow` | (T, h, w, 2) | float32 | (1, h, w, 2) | lzf |

Root attributes mirror `session.h5` so the sidecar is standalone.

### Downstream quickstart (to be copied into `tools/README_DATASET.md`)

```python
import h5py, numpy as np
with h5py.File("session.h5", "r") as f:
    print(dict(f.attrs))                          # global metadata
    frame = f["frames"][500]                      # (h, w) uint8
    mask  = f["masks"][500]                       # (h, w) uint8
    ts    = f["meta/timestamp_s"][500]
    contours = [f[f"contours/frame_00500/{k}"][:] # list of (N_j, 2) int32
                for k in f["contours/frame_00500"]]
```

## Files changed

**New (core exporter):**
- `tools/flow_export.py` — CLI entry point
- `tools/_flow_io.py` — shared I/O helpers (loader used by tests and downstream users)
- `tools/README_DATASET.md` — handoff README
- `tests/test_flow_export.py` — pytest tests

**New (validation phase):**
- `tools/annotate_leaflets.py` — lightweight polygon annotator, saves per-frame JSON
- `tools/param_sweep.py` — batch-run `flow_export` across a parameter grid, compute metrics, write summary CSV
- `tools/validation_report.py` — generate IoU/correlation heatmap + time-series overlays
- `docs/validation_results.md` — one-page results writeup for Dr. Lee

**Modified:**
- `environment.yml` — add `h5py`
- `CLAUDE.md` — CV pipeline description updated to reflect the pivot
- `docs/PRD.md` — §5.6 caveat ("dense flow on boundary, not surface") and new §7 "Dataset Export Pipeline"

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Out-of-plane leaflet bowing shows up as near-zero 2D flow; dataset misses the dominant real motion | Phase 0 sanity check: correlate donut-ROI mean flow magnitude against Arduino FLOW channel on one recording. Gate the rest of the build on r² ≥ 0.5. |
| Bubble drift (2–5 px/frame during jet events) creates false positives in mask | Morphological close+open + min-area 500 + keep-top-3 contours filters most. Remaining noise is visible in the mask and a downstream user can post-process. |
| HDF5 contour-group-per-frame is awkward API | Documented in quickstart snippet. Alternative (ragged VLen dataset) is less readable. If it becomes a problem, we add a `contours_concat + contour_offsets` view in a later revision. |
| Farneback param tuning drift if CV review wants adjustments | Params in HDF5 attrs. Bumping params = new export; old datasets are self-identifying via attrs. |

## Open questions (to resolve after tomorrow's data collection)

- Are the 30° recordings usable for the same pipeline, or does the viewing angle require a different donut ROI?
- What's the typical valve cycle length in the collected data — does 60s / 3600 frames still hold as a size-budget assumption?
- Does the Phase 0 sanity check (flow vs Arduino FLOW) pass? If not, pivot to threshold-based orifice segmentation (PRD §5.4) instead of flow.
