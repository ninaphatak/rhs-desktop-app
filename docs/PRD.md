# PRD: RHS Monitor — Product Requirements & Design

## 1. Product Overview

RHS Monitor is a PySide6 desktop application for the Right Heart Simulator — a benchtop cardiovascular training device that simulates post-Fontan hemodynamics relevant to Hypoplastic Left Heart Syndrome (HLHS). The app provides real-time sensor monitoring, data recording, visualization, and computer vision-based leaflet boundary tracking for tricuspid valve assessment.

## 2. Users

- **Nina's 5 non-technical groupmates** — need zero-terminal UX; machines set up manually
- **Dr. Lee (lab PI/sponsor)** — may use the app for research if the project succeeds
- **Instructors** — Dr. McKee (BIEN 175B course), Dr. Lee (lab PI)

## 3. Core Features

### 3.1 Arduino Sensor Monitoring
- Real-time plotting of P1, P2, Flow Rate, Heart Rate, VT1, VT2, AT1
- 31250 baud serial, read-only, 7 space-separated fields
- Rolling deque buffers (5-second window at 30Hz = maxlen 150)
- pyqtgraph for real-time plotting

### 3.2 Data Recording
- On-demand CSV recording with t=0 reset on Record click
- User-selected file path
- Columns: timestamp, elapsed, P1, P2, flow_rate, heart_rate, VT1, VT2, AT1, plus CV columns when tracking is active

### 3.3 Data Visualization
- Time-series plots (in-app)
- Trial comparison
- P2-P1 diverging bar charts with configurable aggregation (mean/median/max/min)

### 3.4 Dual Camera Feed
- Two Basler ace 2 a2A1920-160umBAS cameras displayed simultaneously
- 0° direct view (primary tracking camera) + 19.3° offset view (was 30° design intent, but as-built tilt is 19.33° per CAD)
- Both camera positions are fixed — valve appears at same pixel location every session

### 3.5 Leaflet Tracking (CV Pipeline)

> **Pivot 2026-05-08:** The CV deliverable is now **metric (millimeter)
> leaflet displacement** via stereo calibration + triangulation, not
> pixel displacement. Dr. Lee made this a hard requirement after
> meeting. See `docs/plans/2026-05-08-stereo-calibration-design.md`
> for the active workstream.
>
> The dense-Farneback + point-annotator pixel-mode pipeline (§6, §7)
> still exists as a **single-camera validation pipeline** for sanity
> checks against optical-flow accuracy, but is no longer the headline
> deliverable. The earlier sparse-LK and polygon-IoU framings in §5–§6
> below are historical context for design rationale; the active CV
> design is in the stereo-calibration plan doc.

- Primary deliverable: per-frame metric XYZ leaflet displacement (mm)
  from triangulated stereo annotations
- Supporting validation: pixel-mode point annotator + cycle CV from
  phase labels (single camera)
- Calibration: per-fluid (water + 35% glycerin analog), single-view
  DLT-style with effective-pinhole refraction model
- See `docs/plans/2026-05-08-stereo-calibration-design.md` for the
  current design

## 4. Hardware Specifications

| Component | Spec |
|-----------|------|
| Arduino | 31250 baud, read-only, 7-field output |
| Cameras | 2× Basler ace 2 a2A1920-160umBAS |
| Resolution | 1920×1200, monochrome (sensor capable of 60 fps; recorded at 30 fps) |
| Camera positions | 0° direct + 19.3° offset (as-built tilt 19.33° per CAD, 18.30° per calibration 2026-05-08; originally 30° in design but mounting compromised the angle). FIXED positions |
| Camera lens | Edmund Optics #33-304, 16mm UC Series, C-mount, EPP=10.68 mm (from front vertex of first lens element, into lens). Same lens on both cameras. See `lens _specsheet.pdf` + `lens_drawing.pdf` |
| Camera sync | Free-run (NOT hardware-triggered). Workaround for stereo: software timestamp matching via `grabResult.GetTimeStamp()`. Hardware sync via Basler GPIO pins is the eventual fix but deferred |
| Recording format | Lossless FFV1 in AVI container (was H.264/MP4 — reverted 2026-05-08 to remove inter-frame compression artifacts that bias optical flow analysis) |
| Valve | White silicone tricuspid, 3 leaflets, underwater |
| Valve behavior | Leaflets bow outward (toward camera) when open |
| Visual conditions | Bubbles on surface, uneven underwater lighting |
| Temperature sensors | Dallas sensors (VT1, VT2, AT1), cached reads every ~500ms |

## 5. Approaches Evaluated and Rejected

### 5.1 Manual Dot Tracking (Fiducial Markers)
**What:** User clicks on black dots drawn on valve surface, algorithm tracks them frame-to-frame using nearest-neighbor matching.
**Why rejected:** ID assignment drift. When dots move fast between frames, the algorithm assigns the wrong ID — a dot that moved far is matched to a different dot that's now closer. At 180 BPM (3° per frame), dots jump significantly between frames. Also, dots give sparse information — 2-3 points can't capture spatial displacement patterns.

### 5.2 Spiderweb Pattern + HoughLinesP
**What:** Draw intersecting lines on valve surface, detect lines with HoughLinesP, compute intersection points as trackable nodes. Each node has structural identity (defined by which two lines created it), eliminating the ID assignment problem.
**Why rejected after visual inspection:** Bubble coverage is far worse than assumed — dozens of bubbles on the leaflet surface generate false edges that HoughLinesP would detect. Leaflets undergo extreme 3D deformation (bowing toward camera), which means straight lines drawn on the surface would appear curved in the image. HoughLinesP only detects straight lines. Additionally, uneven underwater lighting creates mid-tone gradients that complicate edge detection.

### 5.3 Deep Learning / CNN Segmentation
**What:** Train a U-Net or similar on annotated valve frames to segment the orifice boundary.
**Why rejected:** No dedicated GPU available. CPU inference on 1920×1200 frames would cap at ~20-30fps even with a lightweight model. Colab free tier has limited GPU time and frequent disconnects. Training requires 100-200 annotated frames. The effort/complexity is disproportionate to the problem — the leaflet boundary already has high contrast that simpler methods can exploit.

### 5.4 Pure Threshold Segmentation (Orifice Tracking)
**What:** Binary threshold within a user-defined ROI to segment the dark orifice, extract the contour, measure area per frame.
**Why partially rejected:** Threshold reliably captures ~85-90% of the orifice boundary — the dark core. However, at the three commissure tips (where adjacent leaflets meet), the gap between leaflets is gray, not dark. The leaflets have separated but the space isn't deep enough to appear black. Threshold contour stops short of the true leaflet boundary at these tips by ~10-15%.

**Experimental evidence:** Tested on two static frames (open and closed valve, 0° camera). Binary threshold at 110 with Gaussian blur (11,11) within circular ROI: open valve detected 39,656px² area with clean contour along the dark core, but commissure tips were not captured. Canny edge detection confirmed the real leaflet edges exist at the tips — threshold just can't reach them.

### 5.5 Threshold + Commissure Tip Anchors (Hybrid)
**What:** Threshold for the dark core + 3 user-placed anchor points at commissure tips. For each tip, find nearby contour points, draw filled triangles from contour to tip on the binary mask, re-extract contour.
**Why deprioritized:** The triangle extension geometry was fragile — base width selection, perpendicular projection, search radius all needed tuning. Multiple iterations (v1-v6) improved it but the contour at the tips still had visible straight-line artifacts from the triangle edges. Works but adds complexity for marginal benefit over the optical flow approach.

### 5.6 Dense Optical Flow on Leaflet Surface
**What:** Farneback dense optical flow across the entire valve to compute displacement field.
**Why rejected for production:** Leaflet surface is uniform white silicone with no texture. Optical flow requires local intensity variation to compute displacement — a patch of uniform intensity produces near-zero eigenvalues in the structure tensor, meaning flow cannot be determined (see Lucas-Kanade eigenvalue condition, §2.4 of Wu "Optical Flow and Motion Analysis"). Bubbles provide some texture but may move independently of the leaflet surface.

**Note:** Dense flow (Farneback) IS being used for exploration/visualization to identify trackable regions. It is not suitable for production tracking.

## 6. CV Pipeline Design: Sparse Optical Flow on Leaflet Boundary

### 6.1 Core Concept
Points placed along the leaflet boundary (where bright leaflet transitions to dark opening) are tracked frame-to-frame using Lucas-Kanade pyramidal optical flow. The leaflet boundary has the strongest intensity gradient in the frame (~150-220 leaflet intensity → ~7-80 opening intensity), producing well-conditioned flow estimates.

**Why boundary points work for LK:** The reliability of Lucas-Kanade depends on the eigenvalues of the structure tensor A^T W^2 A within the search window. Points on a curved intensity edge have two large eigenvalues, meaning flow is uniquely determined. The leaflet boundary is curved, so most points along it satisfy this condition. (Reference: Wu, "Optical Flow and Motion Analysis," §2.4.)

### 6.2 Camera Selection
- **0° direct-view camera** is the primary tracking camera. Looks directly into the valve opening — bimodal intensity distribution (dark orifice vs bright leaflets), minimal foreshortening of the boundary.
- **19.3° offset camera** can also track boundary points (boundary is still visible) but with more noise due to mid-tone shadows from the viewing angle.
- **Stereo (stretch goal):** With both cameras calibrated, tracked boundary points can be triangulated in 3D for metric displacement. Requires underwater stereo calibration through water/acrylic interface (refraction invalidates standard calibration).

### 6.3 Fixed Camera/Valve Positions
Camera positions and valve housing position are fixed across sessions — the valve appears at the same pixel location (within ~2px) every recording. This means:
- ROI is a one-time calibration value, saved to config
- Closed-valve boundary positions (reference) are one-time calibration values
- No per-session manual setup required once calibration is done

### 6.4 Algorithm

```
INITIALIZATION (first frame or loaded from config):
    - ROI: circular mask around valve housing
    - Initial points: N points along the leaflet boundary
      (placement strategy TBD after exploration — manual, auto-detect, or hybrid)

PER-FRAME TRACKING:
    cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, prev_points, None, **lk_params)
    → new_points, status, error
    → Filter lost points (status == 0) and high-error points
    → Compute per-point displacement from initial positions
    → Compute orifice area = polygon area of tracked points
    → Draw overlay on camera feed
```

### 6.5 OpenCV Functions

```python
# Core tracking
cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, prev_pts, None, **lk_params)
    # lk_params:
    #   winSize=(21, 21)       — search window, default 21
    #   maxLevel=3             — pyramid levels
    #   criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)

# Exploration (dense flow visualization, NOT for production)
cv2.calcOpticalFlowFarneback(prev, curr, None, 0.5, 3, 15, 3, 5, 1.2, 0)

# Initialization: auto-detect boundary via threshold
cv2.GaussianBlur(frame, (11, 11), 0)
cv2.threshold(masked, thresh, 255, cv2.THRESH_BINARY_INV)
cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Initialization: find good tracking points
cv2.goodFeaturesToTrack(gray, maxCorners, qualityLevel, minDistance, mask)

# Measurements
cv2.contourArea(np.array(tracked_points))   # polygon area
cv2.moments(contour)                         # centroid

# Visualization
cv2.circle(frame, point, radius, color, thickness)
cv2.polylines(frame, [points], isClosed=True, color, 2)
cv2.arrowedLine(frame, pt_initial, pt_current, color, 1)
cv2.cartToPolar(flow[..., 0], flow[..., 1])  # for flow visualization
```

### 6.6 Parameters

| Parameter | Default | Range | Notes |
|-----------|---------|-------|-------|
| threshold_value | 110 | 60-180 | For auto-init boundary detection. Orifice ~7-80, leaflets ~150-220 |
| blur_kernel | (11,11) | (3,3)-(31,31) odd | Suppresses bubble edge noise |
| lk_winSize | (21,21) | (11,11)-(41,41) odd | LK search window |
| lk_maxLevel | 3 | 1-5 | Pyramid levels for handling larger motion |
| n_points | 30 | 10-60 | Number of boundary points to track |
| error_threshold | TBD | — | Max LK error before marking point as lost |
| roi_center | Fixed per camera | — | One-time calibration |
| roi_radius | Fixed per camera | — | One-time calibration |

### 6.7 Measurements Produced

**Per frame:**
- Tracked point positions: N × (x, y)
- Per-point displacement from initial position: N × (dx, dy)
- Mean and max displacement magnitude
- Orifice area: polygon area of tracked points (byproduct)
- Number of tracked vs lost points

**Per cardiac cycle (using Arduino BPM for cycle boundaries):**
- Peak displacement per leaflet edge
- Residual displacement at valve closure
- Displacement trajectory through cycle
- Leaflet symmetry — do all 3 edges displace equally

### 6.8 Lost Point Handling
TBD after exploration. Options under consideration:
- Mark as lost, stop tracking (simplest)
- Re-detect locally using goodFeaturesToTrack in small window
- Periodic drift correction by re-running threshold and snapping to boundary
- Re-initialize all points if >50% lost

### 6.9 Key Deliverable
Synchronized time-series plot: mean leaflet boundary displacement overlaid with P1-P2 pressure differential from Arduino. Demonstrates end-to-end integration (camera CV + sensor data on same time axis).

## 7. Exploration Phase

### Current Step
`tools/flow_explore.py` — Dense Farneback optical flow visualization on recorded AVI. Four-panel display: raw frame, flow magnitude, flow direction (HSV), flow arrows. Purpose: identify which pixels are reliably trackable before committing to a tracking strategy.

### Questions to Answer from Exploration
1. Does the leaflet boundary light up as the strongest flow region? (Expected: yes)
2. Do bubbles create significant flow noise on the leaflet surface? (Determines whether auto-init threshold will be noisy)
3. Is the valve housing truly zero-flow? (Confirms fixed position assumption)
4. How large is frame-to-frame displacement at 60fps? (Validates LK parameter choices)
5. Are the commissure tips trackable via flow? (The gray-gap problem may or may not affect LK)
6. Is there visible flow difference between 0° and 19.3° camera views?

### Next Steps (after exploration)
1. Decide point initialization strategy
2. Build `tools/leaflet_flow_test.py` — interactive sparse LK prototype on video
3. Integrate into main app as `src/core/leaflet_tracker.py`

## 8. Phase 2 — Stereo Tracking (NOW PRIMARY DELIVERABLE)

> **Promoted from stretch goal to primary deliverable on 2026-05-08.**
> See `docs/plans/2026-05-08-stereo-calibration-design.md` for the
> full design.

Track a single anatomical leaflet landmark in both 0° and 19.3° cameras.
With stereo calibration, triangulate per-frame → metric (mm) leaflet
displacement.

**Calibration approach:** single-view DLT-style on a fixed
(non-moveable) 3D-printed calibration object that occupies the valve
displacement volume. Underwater + acrylic refraction is absorbed into
the fitted intrinsics ("effective pinhole," Approach A). Per-fluid
calibration: separate JSON files for water and the 35% glycerin blood
analog.

**Sync workaround:** software timestamp matching (cameras are not
hardware-triggered).

**Pipeline:** `record_calibration.py` → `stereo_calibrate.py` →
`annotate_stereo_point.py` → `triangulate.py` → `analyze_metric.py`.
All offline tools in `tools/`; the app stays a read-only sensor
monitor.

## 9. Regulatory Context

The RHS does not meet the FDA Section 201(h) medical device definition — it is purely educational with no patient contact. ViVitro Pulse Duplicator is a comparable non-regulated precedent. IEC 62304, 21 CFR Part 11, ASTM E2208 referenced as voluntary best practices.

## 10. Validation Strategy

- **CV repeatability:** Run the same cardiac cycle recording multiple times, compare tracked displacements
- **Controllability:** One-way ANOVA across different BPM settings
- Simple, defensible statistical methods preferred over complex automated analysis

## 11. What NOT to Build (with rationale)

| Item | Rationale |
|------|-----------|
| Dense optical flow on leaflet surface | Uniform white silicone has no texture — near-zero eigenvalues, unreliable flow |
| Deep learning / CNN | No GPU, Colab adds complexity, unnecessary given boundary contrast |
| Dot tracking / fiducial markers | ID assignment drift between frames |
| Spiderweb / HoughLinesP | Bubble noise + 3D deformation break line detection |
| Bidirectional Arduino control | Requires firmware modification |
| Standalone executable | PyInstaller/cx_Freeze — out of scope |
| MapAnything integration | Deferred |
| CI/CD pipeline | Deferred |
| HDF5 dataset exporter (`tools/flow_export.py`) | Killed 2026-05-08 — downstream-researcher / CNN-on-flow-data path no longer prioritized; metric displacement is the deliverable directly |
| Refractive ray tracing (Snell's law modeling) | Deferred — only revisit if effective-pinhole (Approach A) validation residuals are unacceptable |
| Hardware camera trigger sync | Deferred — using software timestamp matching as workaround. Eventual right fix via Basler GPIO pins, not this iteration |

## 12. Build State

| Module | Status | Notes |
|--------|--------|-------|
| Serial reader | ✅ Done | Reads 7 fields at 31250 baud |
| Graph panel | ✅ Done | Real-time P1/P2/Flow/HR plots |
| Camera panel | ✅ Done | Dual Basler feeds displayed |
| Control bar | ✅ Done | Connect/disconnect, record, port selection |
| Data recorder | ✅ Done | CSV recording with t=0 reset |
| Run logger | ✅ Done | Run quality logging |
| Plot dialog | ✅ Done | In-app visualization |
| Mock data | ✅ Done | Arduino + camera mocks |
| Setup scripts | ✅ Done | setup.sh/bat, run.sh/bat, hash-check for deps |
| Dense flow exploration | ✅ Done | `tools/flow_explore.py` — direction-encoded color overlay (red=N, yellow=ENE, cyan=E), magnitude-encoded opacity, `--max-mag` and `--contrast` knobs, direction legend in bottom-left |
| Annotation CSV I/O module | ✅ Done | `tools/_annotations.py` — `Annotation` dataclass + CSV read/write + malformed-phase rejection |
| Shared Farneback params | ✅ Done | `tools/_flow_params.py` — hoisted for reuse by analyzer |
| Point + phase annotator | ✅ Done | `tools/annotate_point.py` — manual landmark + per-frame phase label, OpenCV GUI. See `docs/plans/2026-05-04-point-annotator-design.md` and `2026-05-04-point-annotator-plan.md` |
| Annotation playback | ✅ Done | `tools/playback_annotations.py` — overlay + arrow + trail; per-frame length readout in HUD; `--save` renders MP4; `--plot` saves displacement-vs-time figure to `outputs/`; auto-loops between first/last annotated frame |
| Cycle CV analyzer (Mode A) | ✅ Done | `tools/analyze_annotations.py` — cycle detection from phase labels, per-cycle period + peak displacement, CV across cycles (pixel mode) |
| Flow vs manual error (Mode B) | ✅ Done | `tools/analyze_annotations.py --video` — Farneback dense flow at annotated points, median + p95 error vs manual displacement (pixel mode) |
| Lossless FFV1/AVI recording | ✅ Done | `src/core/basler_camera.py` + `src/ui/main_window.py` — reverted from H.264/MP4 to lossless intra-only FFV1 in AVI container; threading model + lock pattern preserved |
| Standalone calibration capture | ✅ Done | `tools/record_calibration.py` — dual-camera capture without GUI; CLI: `python tools/record_calibration.py <fluid_label> [--duration N]`; outputs `calib_<label>_<ts>_camN.avi` |
| Stereo calibration tool | ✅ Done | `tools/stereo_calibrate.py` — single-view calibration per camera with manual dot-ID assignment, interactive editor (`--edit`), load/save correspondences (`--load`) for resumability, k1+tangential distortion model with fixed focal length and principal point, full validation report (reprojection RMS + 3D triangulation error vs CAD + camera-position cross-check) |
| First water calibration validated | ✅ Done | `outputs/calib/stereo_calib_water.json` — 0.154mm median 3D error, 0.431mm max, EPP discrepancies <11mm, cam1 tilt agrees with CAD to within 1° (18.30° vs 19.33°) |
| Stereo annotator | ✅ Done | `tools/annotate_stereo_point.py` — dual-camera side-by-side single-landmark labeler with auto-fit display scale; output stereo CSV `(frame_idx, u0, v0, u1, v1, phase)`; auto-resumes from prior CSV |
| Triangulation | ✅ Done | `tools/triangulate.py` — stereo CSV + calibration JSON → per-frame XYZ in mm + displacement vector from first labeled frame |
| Metric cycle analyzer | ✅ Done | `tools/analyze_metric.py` — cycle period (ms), 3D path length (mm), peak 3D displacement (mm) + mean/std/CV across cycles |
| Analog calibration | ⬜ Pending | Awaiting lab session with the 35% glycerin analog fluid; same `tools/stereo_calibrate.py` consumes it |
| Software sync correction | ⬜ Pending | Timestamp-matching preprocessor that aligns the two valve videos before stereo annotation. Per-frame timestamps already logged by `record_calibration.py` (and presumably the GUI valve recordings); no consumer yet |
| Leaflet tracker (in-app) | ❌ Killed | CV work stays offline in `tools/`; `src/core/leaflet_tracker.py` removed from roadmap |
| Polygon annotator | ❌ Killed | `tools/annotate_leaflets.py` superseded by `tools/annotate_point.py` |
| Cycle-period FFT helpers | ❌ Killed | Cycle metrics derived from phase labels in `tools/analyze_annotations.py`, not FFT |
| HDF5 dataset exporter | ❌ Killed 2026-05-08 | `tools/flow_export.py` removed from roadmap. Downstream-researcher / CNN-on-flow-data path no longer prioritized in favor of direct metric displacement |
| Param sweep | ❌ Killed 2026-05-08 | Was tied to dataset exporter; subsumed by stereo calibration + validation |
| Validation report (pixel pipeline) | ❌ Killed 2026-05-08 | Subsumed by metric calibration's built-in validation report (reprojection + 3D triangulation error vs CAD) |

**Validation framing (current, see `docs/plans/2026-05-08-stereo-calibration-design.md`):** the CV deliverable is per-frame **metric (mm) leaflet displacement** computed by triangulating a manually-labeled landmark across both cameras using a stereo calibration fitted from a fixed 3D-printed calibration object. Stereo calibration is validated by (1) reprojection error per camera, (2) per-marker 3D triangulation error vs. known CAD positions, (3) cross-check against teammate-supplied scalar camera-to-marker distances. Pixel-mode point annotator + cycle CV (`docs/plans/2026-05-04-point-annotator-design.md`) is retained as a single-camera validation step but is no longer the primary deliverable. Earlier framings (polygon IoU, cycle-period FFT, motion-mask area, HDF5 dataset for downstream researcher) are all superseded.