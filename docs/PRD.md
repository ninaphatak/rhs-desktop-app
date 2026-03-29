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
- 0° direct view (primary tracking camera) + 30° offset view
- Both camera positions are fixed — valve appears at same pixel location every session

### 3.5 Leaflet Boundary Tracking (CV Pipeline)
- Sparse Lucas-Kanade optical flow on points along leaflet boundaries
- Primary measurement: leaflet displacement
- Secondary measurement: orifice area (polygon of tracked points)
- See §6 for full design

## 4. Hardware Specifications

| Component | Spec |
|-----------|------|
| Arduino | 31250 baud, read-only, 7-field output |
| Cameras | 2× Basler ace 2 a2A1920-160umBAS |
| Resolution | 1920×1200 @ 60fps, monochrome |
| Camera positions | 0° direct + 30° offset, FIXED positions |
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
- **30° offset camera** can also track boundary points (boundary is still visible) but with more noise due to mid-tone shadows from the viewing angle.
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
6. Is there visible flow difference between 0° and 30° camera views?

### Next Steps (after exploration)
1. Decide point initialization strategy
2. Build `tools/leaflet_flow_test.py` — interactive sparse LK prototype on video
3. Integrate into main app as `src/core/leaflet_tracker.py`

## 8. Phase 2 — Stereo Tracking (Stretch Goal)

Track boundary points in both 0° and 30° cameras. With stereo calibration, triangulate each point in 3D → metric leaflet displacement.

**Calibration challenge:** Standard stereo calibration assumes light travels in straight lines. Underwater, light refracts at the water-acrylic interface. Options:
- In-situ calibration: submerge checkerboard, calibrate with refraction baked into the model
- RIM (Refractive Index Matching): glycerol-water mixtures to match acrylic refractive index (adds complexity)
- Calibrate intrinsics in air, extrinsics submerged

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
| Dense flow exploration | 🔨 In Progress | `tools/flow_explore.py` — needs recorded AVI |
| Leaflet tracker | ⬜ Not Started | `src/core/leaflet_tracker.py` — after exploration |
| Leaflet tracking UI | ⬜ Not Started | Point overlay, displacement plots |
| Stereo calibration | ⬜ Not Started | Phase 2 stretch goal |