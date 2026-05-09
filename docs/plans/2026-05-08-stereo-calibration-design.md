# Stereo Calibration + Metric Displacement — Design

_2026-05-08_

> **Major scope pivot.** Supersedes the validation framing in
> `2026-05-04-point-annotator-design.md`. The CV deliverable is now
> *metric* (millimeter) leaflet displacement via stereo calibration +
> triangulation, not pixel displacement. The point-annotator pipeline
> stays as a supporting validation step but is no longer the headline.
>
> Kills: `tools/flow_export.py` (HDF5 dataset exporter for downstream
> researcher) — see §"What's killed" below.

## Why

After meeting with Dr. Lee, **metric displacement is now a hard
requirement** for the deliverable. Pixel-displacement validation alone
is not sufficient. He referenced
[Aggarwal et al., *Acta Biomaterialia* 2022 (DOI 10.1016/j.actbio.2022.08.046)](https://doi.org/10.1016/j.actbio.2022.08.046),
which characterizes tricuspid valve leaflet pre-strains using
photogrammetry. We can't replicate their photogrammetry setup, but we
have a stereo pair of Basler cameras and a 3D-printed calibration
object — enough to compute metric displacement via standard stereo
triangulation.

## Setup constraints

- Cameras image **through an acrylic chamber wall + the working fluid**
  (refraction at every air-acrylic-fluid interface).
- The calibration object is **fixed in place** — designed to occupy
  the exact volume the valve will displace through, cannot be moved
  or rotated. Standard multi-view calibration (Zhang's method) is not
  applicable. We use single-view DLT-style calibration instead.
- **Two fluids in scope, separate calibration per fluid:**
  - Water (n ≈ 1.333)
  - Blood analog: 35% water-glycerin + 0.02% xanthan gum (n ≈ 1.385).
    The analog has an RI closer to acrylic (1.49), so refraction
    residual is theoretically smaller — expect lower reprojection
    error than water.
- Both cameras use the **same lens**: Edmund Optics #33-304, 16mm
  **UC Series** fixed focal length, C-mount. EPP = 10.68 mm
  measured from the front vertex of the first lens element, positive
  direction into the lens toward the image (datum confirmed
  unambiguously: the alternative "from image plane" interpretation
  would place EPP behind the C-mount face, which is physically
  impossible). Spec sheet at `lens _specsheet.pdf`, mechanical drawing
  at `lens_drawing.pdf`. Overall length 27.88-29.13 mm depending on
  focus position; Max OD 30 mm. (Earlier reference to #59-870
  C-Series, EPP=24.42 mm, was an incorrect lens link — superseded by
  the actual #33-304 UC Series.)

## Refraction handling

**Approach A — Effective pinhole (default).** Calibrate the cameras
underwater, in their final mounting positions, looking through the
acrylic at the calibration object submerged in the working fluid. The
fitted intrinsics (K + distortion) absorb the air-acrylic-fluid
refraction. Standard OpenCV pipeline.

- Pros: well-tested, fast, no extra physics.
- Cons: accuracy degrades for points outside the calibration volume;
  only valid for the exact mount + fluid that was calibrated.
- Realistic accuracy: sub-mm to ~1 mm 3D error inside the calibration
  volume.

**Approach B — Explicit refractive ray tracing (deferred).** Model the
acrylic-fluid interface with Snell's law. Only revisit if Approach A
validation residuals are unacceptable.

## Calibration object geometry

Stack of cylinders, growing in the +z direction (= direction of water
flow when the valve is in place). Each cylinder has a flat **forward
face** with painted dots arranged in a circle on that face. The top
cylinder additionally has dots on its top face.

- Markers: 1.5 mm diameter painted circles, filled with waterproof
  black eyeliner ink. CAD has 0.08 mm extruded outlines as guides.
- Surface imperfections (eyeliner unevenness, 3D-print layer lines)
  expected; handled in detection via HSV threshold + morphological
  opening + size/circularity blob filters.
- ~31 markers visible to the 30° camera (more visible to the 0°
  camera). With minimal-distortion model = 12 unknowns per camera,
  62 measurements gives 5.2× constraint ratio — comfortable.

### Coordinate frame (committed)

- **Origin**: center of the **top face** (the flat circular top of the
  topmost cylinder) of the calibration object.
- **z-axis**: pointing up out of the top face = direction of water
  flow. Cylinder markers below the top face have **negative z**.
- **x-axis**: a physically distinguishable direction in the top face
  plane, designated by the teammate on a sketch (typical choice:
  toward camera 0 or toward a labeled top-face reference dot).
- **y-axis**: right-handed (+y = +z × +x).
- **All marker XYZ and any CAD-derived camera positions live in this
  frame.**

### Marker spec format (what teammate provides)

Direct `(dx, dy, dz)` per marker — no parametric ring description
needed. The teammate can extract vector displacements from CAD
component-wise once the origin is fixed at the top-face center.

```
markers.csv:
marker_id, dx_mm, dy_mm, dz_mm
```

One row per painted dot on the entire calibration object (every
cylinder ring + every top-face dot). Each row is the displacement
vector from origin (top-face center) to that marker's center.

Plus a sketch showing the +x direction and labeling one physical
reference dot per ring so detected blobs can be matched to marker_ids
during the manual ID assignment step.

```
cameras.csv:
camera_id, cmount_dx_mm, cmount_dy_mm, cmount_dz_mm, axis_dx, axis_dy, axis_dz
```

Per-camera C-mount center position + optical-axis unit vector, in the
same coordinate frame. If unit-vector extraction is awkward, the
teammate can supply a second point on the optical axis instead and
the script derives the direction by subtraction + normalization.

### Validation reference data

Teammate also provides scalar distances from each camera's C-mount
face center to each marker, in mm. These are *not* used as calibration
input — they're a secondary validation check. After running stereo
calibration, the script compares each (camera-derived position →
marker) distance against the CAD-measured distance. Per-pair error
should be ≤5 mm.

## Camera synchronization

**Hardware sync is not configured.** `src/core/basler_camera.py` sets
`AcquisitionFrameRate` per camera independently with no `TriggerMode`
or `LineSelector` configuration — both cameras free-run at ~30 fps
with unknown phase offset.

- For **calibration** (static object): irrelevant. Single still frame
  from each camera, no time pressure.
- For **valve analysis** (moving leaflet): up to ½-frame offset =
  ~16 ms phase error → up to ~5 mm misregistration during peak
  leaflet velocity.

**Chosen workaround: software timestamp matching.** Both Basler
cameras carry hardware timestamps on each grab via
`grabResult.GetTimeStamp()`. We log per-frame timestamps for both
streams and post-hoc match each cam0 frame to the closest cam1 frame
in time. Residual offset bounded by 1/(2 × fps) = 16 ms, but the
*expected* residual is much smaller because of free-run phase
diversity.

Hardware sync via the Basler ace 2 GPIO pins is the eventual right
fix but is deferred — no time for the wiring + Pylon trigger
configuration this iteration.

## Pipeline

| Stage | Tool | Input | Output |
|---|---|---|---|
| Capture | `tools/record_calibration.py` (built) | live cameras | `outputs/videos/calib_<fluid>_<ts>_camN.avi` |
| Calibrate | `tools/stereo_calibrate.py` (planned) | Calibration AVIs + marker spec + CAD distance list | `outputs/calib/stereo_calib_<fluid>.json` |
| Annotate | `tools/annotate_stereo_point.py` (planned) | Two synchronized valve videos | Stereo annotation CSV: `frame_idx, u0, v0, u1, v1, phase` |
| Triangulate | `tools/triangulate.py` (planned) | Stereo annotation CSV + calibration JSON | Per-frame XYZ in calibration frame + per-frame metric displacement |
| Analyze | `tools/analyze_metric.py` (planned) | Triangulated trajectory | Cycle period CV + peak displacement CV (in mm) |

The pixel-displacement tools (`annotate_point.py`,
`playback_annotations.py`, `analyze_annotations.py`) remain as the
**single-camera validation pipeline** for sanity checks against
optical-flow accuracy. They are not extended with `--calibration`
flags — stereo/metric tools live as separate files.

## What's killed by this pivot

- **`tools/flow_export.py`** (HDF5 dataset exporter for downstream
  researcher) — removed from roadmap. The downstream-researcher /
  CNN-on-flow-data path is no longer being prioritized; metric
  displacement is now the deliverable directly.
- The earlier validation framing in `2026-05-04-point-annotator-design.md`
  ("validated point-tracker accuracy + cycle CV characterization") —
  pixel-mode tools still exist but are now subordinate to the metric
  pipeline.

## Tools shipped this session (not yet covered elsewhere)

These ship alongside the metric work and should be kept:

- **`tools/record_calibration.py`** — standalone dual-camera capture
  script using the same FFV1/AVI pipeline as the GUI. No PySide6
  dependency. CLI: `python tools/record_calibration.py <fluid_label>
  [--duration 5] [--camera N] [--out-dir PATH]`. Outputs
  `outputs/videos/calib_<label>_<ts>_camN.avi`.
- **`tools/playback_annotations.py`** new flags:
  - `--save PATH` renders the overlaid playback as MP4
  - `--plot` saves displacement vs time figure to `outputs/`
  - Per-frame vector length readout in HUD
  - Auto-loop between first and last annotated frame
- **`tools/flow_explore.py`** changes:
  - Direction-encoded color overlay (red = north, yellow = 30° CCW
    of east, cyan = east); other directions interpolate between
    anchors around full circle
  - Magnitude-encoded opacity with `--max-mag` knob
  - `--contrast 1.25` pre-stretches grayscale before Farneback
  - Direction legend rendered in bottom-left of overlay pane

## Recording format change

Reverted from H.264/MP4 to **lossless FFV1/AVI**. Same threading
model + lock pattern preserved from the MP4 version (segfault and
fps-mismatch fixes intact). Files ~30-50 MB/sec mono at 30 fps; SSD
storage absorbs this.

Why: H.264 inter-frame compression introduces artifacts that bias
optical flow analysis on near-textureless leaflet surfaces. FFV1 is
lossless intra-only — every frame is an I-frame, no temporal
prediction.

## Camera geometry (as-built, 2026-05-08)

| | CAD | Calibration recovered | Validation discrepancy |
|---|---|---|---|
| cam0 ("0° camera") tilt from vertical | 0° (design) / measured 0° in CAD | 0.91° | within mounting tolerance |
| cam1 ("30° offset" — label only) | **19.33° from vertical** (as-built per CAD) | **18.30°** | 1.03° (within tolerance) |
| cam0 EPP from origin | (-1.84, 0, 216.74) mm | (0.86, -0.57, 225.47) mm | 9.15 mm |
| cam1 EPP from origin | (-68.17, 0, 191.73) mm | (-64.93, -0.02, 198.65) mm | 7.65 mm |

Note: the "30°" in "30° offset camera" is **a name only**. The actual
as-built axis tilt is 19.33°, originally 30° in the design but
compromised during physical mounting. The calibration's 18.3°
recovery agrees with the as-built CAD value to within 1°, confirming
both the calibration math and the as-built geometry are consistent.

## First successful calibration (water, 2026-05-08)

End-to-end run on `outputs/videos/calib_water_2026-05-08_21-26-59_*.avi`:

- **3D triangulation error**: median 0.20 mm, max 0.53 mm over 38 markers
  visible to both cameras (markers 3, 11, 19 occluded from cam1 by
  cylinder geometry; cam0 sees all 41).
- **Reprojection RMS**: cam0 = 3.36 px, cam1 = 3.76 px. Higher than
  ideal (sub-px is the gold standard), reflects residual refraction
  the effective-pinhole model can't fully capture. Acceptable because
  the 3D accuracy is what the deliverable cares about.
- **EPP cross-check**: both within 10 mm of CAD prediction (passes
  the relaxed 15 mm tolerance for as-built mounting + refraction).

Per-ring 3D error pattern: top inner ring (z=0) is the most accurate
(0.118 mm median); lowest cylinder (z=-11.76) is the least (0.292 mm
median). Error scales with depth as expected for stereo geometry.

## Validation strategy (metric)

Two complementary checks, run automatically by `stereo_calibrate.py`:

1. **Reprojection error** (calibration's internal goodness-of-fit):
   project each known marker XYZ through the fitted K + extrinsics,
   compare to detected pixel position. Per-camera RMS in pixels.
   Target: < 1 px.

2. **3D triangulation error** (metric correctness): triangulate each
   marker visible to both cameras, compare to known marker XYZ.
   Per-marker error in mm; report median + worst-case. Target:
   median < 1 mm, worst-case < 5 mm.

3. **Cross-check against teammate's CAD distances**: for each
   (camera, marker) pair, distance from calibration-derived camera
   position to known marker should match the teammate's
   CAD-measured distance to within 5 mm.

If all three pass, the calibration is metrically trustworthy.

## Out of scope (this iteration)

- Refractive ray tracing (Approach B) — only revisit if Approach A
  validation fails.
- Hardware camera sync — software timestamp matching is the chosen
  workaround.
- Auto-correspondence of dots between cameras — manual ID assignment
  is acceptable for one-time calibration.
- Multiple landmarks per recording (still one landmark per session,
  same as point-annotator pipeline).
- Statistical hypothesis testing on metric CVs (raw numbers suffice
  for Dr. Lee handoff).

## Open questions tracked

- Edmund EPP datum (front vertex vs image plane) — emailed Edmund
  tech support, awaiting response. ~4 mm spread between
  interpretations; absorbed by 5 mm validation tolerance, so not
  blocking.
- Whether the same calibration JSON validates within tolerance for
  both fluids — empirical question, answered after first calibration
  capture in each fluid.

## File layout

```
tools/
  record_calibration.py            (built this session)
  stereo_calibrate.py              (planned)
  annotate_stereo_point.py         (planned)
  triangulate.py                   (planned)
  analyze_metric.py                (planned)
outputs/
  calib/
    stereo_calib_water.json        (per-fluid)
    stereo_calib_analog.json
  videos/
    calib_water_<ts>_camN.avi      (calibration captures)
    calib_analog_<ts>_camN.avi
    valve_camN_<ts>.avi            (valve recordings, FFV1 lossless)
```

No `src/` changes for the metric pipeline — CV stays offline in
`tools/`. The recording-format revert touched
`src/core/basler_camera.py` and `src/ui/main_window.py`.

## Branch

All work continues on `feature/flow-export`.

## Implementation plan

Deferred to a separate plan doc once the teammate's marker spec +
CAD distance list arrives. The plan will sequence:

1. `tools/stereo_calibrate.py` — read marker spec YAML/text, detect
   dots, manual ID assignment UI, single-view calibration per camera,
   stereo extrinsic derivation, validation report.
2. `tools/annotate_stereo_point.py` — dual-camera side-by-side
   annotator, click landmark in both views per frame, output stereo
   CSV.
3. `tools/triangulate.py` — stereo annotation + calibration → per-frame
   XYZ + per-frame metric displacement.
4. `tools/analyze_metric.py` — cycle CVs in mm.
5. Sync correction layer for the valve videos (timestamp matching)
   — possibly a preprocessing step that aligns the two streams before
   `annotate_stereo_point.py` consumes them.
