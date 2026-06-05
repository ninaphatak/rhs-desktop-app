# CV Pipeline & Optical-Flow Technical Primer

> **Audience:** an incoming student (bright high-schooler / early undergrad) who will pick up the computer-vision (CV) side of the Right Heart Simulator (RHS) project. This is your technical reference. It assumes you can read a little Python and remember some geometry and trig; it does **not** assume you have ever done computer vision before. Every CV term is defined the first time it appears, and again in the [Glossary](#5-glossary).
>
> **Where this fits in the handoff set:** doc 01 is the big project tour, doc 02 is the app/architecture. This doc (03) is the CV deep-dive.

---

## 0. Orientation: what problem are we even solving?

The RHS is a benchtop heart-valve simulator. A white silicone **tricuspid valve** (three leaflets) sits underwater and opens/closes as a solenoid pumps fluid through it, mimicking a post-Fontan heart. Two Basler cameras watch the valve through an acrylic window — one looking nearly straight on (the "0°" camera) and one tilted (the "19.3°" camera).

The headline question Dr. Lee wants answered is:

> **How far, in millimeters, does a point on a leaflet move during a heartbeat?**

That word **millimeters** is the whole ballgame. Anyone can measure motion in *pixels*, but pixels are meaningless without scale — and underwater, through acrylic, with a tilted camera, the scale changes across the image. Converting pixel motion into a real physical distance (millimeters in 3D space) is exactly what the CV pipeline does. This is called **metric** measurement ("metric" = real-world units, here mm).

> **One-sentence summary of the whole pipeline:** record the valve from two angles → figure out exactly where each camera is and how it distorts the image (**calibration**) → click the same leaflet landmark in both camera views → use the two viewing rays to find where they cross in 3D (**triangulation**) → measure how that 3D point moves over time.

---

## 1. The big picture: from dual-camera video to metric (mm) displacement

The CV work is **offline** — none of it runs inside the live GUI app. It is a set of standalone command-line scripts in the `tools/` directory. You run them by hand, in order, on recorded video files.

### 1.1 The pipeline at a glance

There are **two recording tracks** that feed one analysis chain. The trick is that they are recorded *separately*:

```
                       ┌─────────────────────────────┐
  RECORD THE           │ record_calibration.py       │   films the calibration
  CALIBRATION OBJECT   │  → calib_<fluid>_*_cam0.avi │   object (a fixed, known
  (a known 3D ruler)   │  → calib_<fluid>_*_cam1.avi │   3D shape) underwater
                       └──────────────┬──────────────┘
                                      ▼
                       ┌─────────────────────────────┐
                       │ stereo_calibrate.py         │   solves "where are the
                       │  → stereo_calib_<fluid>.json│   cameras + how do they
                       └──────────────┬──────────────┘   distort?"  (one-time
                                      │                    per fluid)
                                      │   (the calibration JSON)
                                      │
  RECORD THE VALVE     ┌──────────────┴──────────────┐
  (the actual          │ annotate_stereo_point.py    │   a HUMAN clicks the same
  experiment)          │  (run on the VALVE video)   │   leaflet landmark in cam0
   valve_cam0.avi ────►│  → *.stereo_annotations.csv │   and cam1, every frame,
   valve_cam1.avi ────►│                             │   tagging the cardiac phase
                       └──────────────┬──────────────┘
                                      ▼
                       ┌─────────────────────────────┐
                       │ triangulate.py              │   2 pixel clicks per frame
                       │  → *.triangulated.csv       │   → one 3D point (mm) + a
                       │   (x_mm,y_mm,z_mm,disp_mm…) │   displacement from frame 0
                       └──────────────┬──────────────┘
                                      ▼
                       ┌─────────────────────────────┐
                       │ analyze_metric.py           │   per-cardiac-cycle metrics
                       │  → *.metric.json            │   in mm: period, path length,
                       │   (period, path length,     │   peak displacement, and their
                       │    peak disp + their CVs)   │   reproducibility (CV)
                       └─────────────────────────────┘
```

**Why two separate recordings?** The **calibration object** is a fixed 3D-printed shape with dots at precisely known positions — think of it as a 3D ruler. You film it once (per fluid) to learn the cameras' geometry. Then you swap it out, put the real valve in, and film *that*. Both videos go through the same calibration, but they are different clips. `stereo_calibrate.py` (which reads the calibration-object clip) and `annotate_stereo_point.py` (which reads the valve clip) are two parallel branches that meet at `triangulate.py`.

### 1.2 The five stages in plain language

| Stage | Tool | What goes in | What comes out | One-line job |
|------:|------|--------------|----------------|--------------|
| 1 | `record_calibration.py` | (live cameras) | `calib_<fluid>_*_cam{0,1}.avi` + sidecars | Film the known 3D "ruler" underwater. |
| 2 | `stereo_calibrate.py` | the two calib AVIs + `markers.csv` | `stereo_calib_<fluid>.json` | Learn where each camera is and how it distorts. |
| 3 | `annotate_stereo_point.py` | the two **valve** AVIs | `*.stereo_annotations.csv` | Human clicks the same leaflet point in both views, per frame, + phase. |
| 4 | `triangulate.py` | the annotations CSV + the calib JSON | `*.triangulated.csv` | Turn 2 clicks/frame into one 3D point in mm + displacement. |
| 5 | `analyze_metric.py` | the triangulated CSV | `*.metric.json` | Per-heartbeat metrics in mm and their reproducibility. |

### 1.3 Important real-world wrinkles you must know

These are facts about *this specific rig* that shape everything:

- **The cameras are not synchronized in hardware.** They "free-run" — each grabs frames on its own clock, so cam0 frame 100 and cam1 frame 100 were *not* taken at exactly the same instant. To fix this, every recording writes a sidecar `*.avi.timestamps.csv` listing each frame's hardware timestamp. `triangulate.py` can use those timestamps to *interpolate* cam1's pixel position to match cam0's frame time (see [§3.6](#36-fixing-free-running-camera-skew-the-sync-step)). If you forget to pass the timestamp files, it falls back to naive "frame N pairs with frame N" and prints a warning.
- **The video codec is MJPG, not the "lossless FFV1" the older docs claim.** The valve recordings are saved as **MJPG/AVI** (Motion JPEG) at quality `-q:v 2` — "visually lossless" but technically lossy. The key property for us: MJPG is **intra-frame only** (each frame is compressed by itself, like a folder of JPEGs). That matters because the *reason* H.264/MP4 was abandoned was that its *inter*-frame compression invents motion between frames and biases optical flow. MJPG does not do that, so it is safe for flow. (Only `record_calibration.py` still uses true lossless FFV1.)
- **There is one calibration per fluid.** Water (refractive index `n ≈ 1.333`) and the 35% glycerin blood analog (`n ≈ 1.385`) bend light differently, so each needs its own calibration JSON: `stereo_calib_water.json` and `stereo_calib_analog.json`. Both exist and are validated.

---

## 2. Optical flow, explained from scratch

You will hear "optical flow" constantly on this project. Here is what it actually means, grounded in the real code.

### 2.1 The core idea

Take two consecutive video frames. **Optical flow** is the estimate of *which way, and how far, each piece of the image moved* from the first frame to the second. The output is a little arrow (a 2D vector, `(du, dv)` in pixels) telling you "the stuff that was here is now over there."

There are two flavors, and the difference is the single most important CV concept on this project:

- **Dense** optical flow computes an arrow for **every pixel**.
- **Sparse** optical flow computes an arrow for only a **handful of chosen points**.

This codebase uses *both*, for different purposes, and the failure of sparse flow on this valve is a genuine teaching moment.

### 2.2 The brightness-constancy assumption (why flow can work at all)

All optical flow rests on one assumption: **a physical point keeps the same brightness as it moves.** If a speck of texture was gray value 120 in frame 1, it is still ≈120 in frame 2, just at a new location.

Write the image intensity as `I(x, y, t)`. If a point moves by `(u, v)` between frames and keeps its brightness:

```
I(x + u, y + v, t + 1) = I(x, y, t)
```

Do a first-order Taylor expansion (treat `u, v` as small) and you get the **optical-flow constraint equation**:

```
I_x · u  +  I_y · v  +  I_t  =  0
```

where `I_x, I_y` are the image's spatial gradients (how fast brightness changes left↔right and up↔down) and `I_t` is the temporal change (how much that pixel's brightness changed between the two frames).

**Stare at that equation.** It is *one* equation with *two* unknowns (`u` and `v`). You cannot solve one equation for two unknowns. This shortfall is not a bug — it is fundamental, and it has a name.

### 2.3 The aperture problem (the heart of the whole story)

Look at a long, straight, featureless edge through a small peephole (an "aperture"). Slide the edge. You can tell it moved *across* the edge (perpendicular), but you **cannot tell whether it also slid *along* the edge**, because every point on the edge looks identical to its neighbor. The motion along the edge is invisible.

That is the **aperture problem**: a local image window can only measure the component of motion *perpendicular to* an edge, never the component *along* it. Mathematically it is exactly the "one equation, two unknowns" problem above — the single constraint pins down motion in one direction and leaves the other free.

Corners and textured speckles escape the aperture problem because they have gradients in *two* different directions, giving you two independent equations. Edges and blank regions do not.

> **Hold onto this.** The white silicone valve is mostly blank surface and smooth edges. The aperture problem is precisely why automated point-tracking failed on it.

### 2.4 Sparse flow: Lucas-Kanade — and why plain LK failed here

**Lucas-Kanade (LK)** is the classic *sparse* method (`cv2.calcOpticalFlowPyrLK`). It picks a few specific points and asks, for each one, "where did *this* point go?" To make the one-equation-two-unknowns problem solvable, LK assumes that all pixels inside a small window around the point moved together, giving it many copies of the constraint equation — one per pixel in the window — which it solves by least squares. Stacking those leads to the **structure-tensor** normal equations:

```
G · δ = -b,    with   G = Σ_window ∇I (∇I)ᵀ    (a 2×2 matrix),
                       b = Σ_window ∇I · I_t
```

`G` is a 2×2 matrix built from the gradients in the window. The catch: `G` is only *invertible* (solvable) if the window has strong gradients in **two** different directions — i.e. if there is a corner or rich texture there. On a blank patch `G ≈ 0` (no gradients); on a straight edge `G` is near-singular (gradients all point one way). OpenCV guards against this with `minEigThreshold=1e-4` — it rejects a point if the smaller eigenvalue of `G` is too small, which is its way of detecting "this point is on an edge or a blank, I can't trust it."

**The prototype that failed:** `tools/leaflet_flow_test.py` was an LK tracker. For each frame it ran LK forward (prev→curr), then LK backward (curr→prev), and checked whether the point landed back where it started — a **forward-backward consistency check**. If the round-trip error exceeded `FB_ERROR_THRESHOLD = 1.0 px`, the point was flagged unreliable. Its parameters were `winSize=(21,21)`, `maxLevel=3`, `minEigThreshold=1e-4`.

It failed badly, and the reasons are exactly the optical-flow lesson:

1. **No texture to grab onto.** The leaflet is smooth, uniform **white silicone** with *no painted or inked features*. (We deliberately do **not** put fiducial dots on the valve — they drift in identity and confuse the tracker.) With no texture, the LK window has near-zero gradients → `G` is uninvertible → `minEigThreshold` rejections → meaningless flow.
2. **The aperture problem on the leaflet edges.** Where there *is* a feature, it is a smooth leaflet boundary — an edge. LK can only see motion across it, not along it, so a point sliding along the edge is tracked wrongly.
3. **Hostile conditions:** bubbles drifting on the surface, uneven underwater lighting, and a dark moving orifice all make the brightness-constancy assumption fail. Tracked points drift, the forward-backward error blows past 1.0 px, and the track is lost.

> **Standing project rule:** *Do not default to plain Lucas-Kanade for valve tracking.* `leaflet_flow_test.py` is kept in the repo only as a documented failure exhibit — do not extend it or copy its approach. (Memory: `feedback_lk_default.md`.)

The fixes that came later (manual annotation, and the hybrid LK+NCC tracker in [§4](#4-the-experimental-tracks-workstream)) are both responses to this exact failure.

### 2.5 Dense flow: Farneback — what it does and its honest limits

**Farneback** is the *dense* method (`cv2.calcOpticalFlowFarneback`). Instead of tracking chosen points, it estimates a motion arrow for **every pixel at once**, fitting local quadratic ("polynomial expansion") models of the image and solving for the displacement field with a smoothness/regularization term that ties neighboring pixels together.

The project uses **one shared parameter set** so the visualizer and the validator never drift apart. From `tools/_flow_params.py`, verbatim:

```python
FARNEBACK_PARAMS = dict(
    pyr_scale=0.5,   # each pyramid level is half the size of the one below
    levels=3,        # 3-level image pyramid (handles bigger motions)
    winsize=15,      # 15×15 averaging window
    iterations=3,    # refinement iterations per level
    poly_n=5,        # neighborhood size for the polynomial fit
    poly_sigma=1.2,  # Gaussian smoothing of that fit
    flags=0,
)
```

Both `tools/flow_explore.py` (the visual explorer) and `tools/analyze_annotations.py` Mode B (the accuracy validator) import this exact dict.

> The `_flow_params.py` docstring still mentions an "eventual dataset-exporter target" (`winsize=21, poly_n=7, …`). That note is **stale** — the dataset exporter (`flow_export.py`) was killed. Ignore it.

**The honest limitation — the regularization trap.** Farneback's smoothness term is a double-edged sword. Where the image has real texture or a genuine moving edge, the arrows are trustworthy. But where the image is **blank** (the leaflet *interior*), Farneback has no real information, so its regularization just **smears the motion inward from the textured boundary and guesses.** Those interior arrows are *hallucinated* — they look smooth and convincing but are not measurements.

That is why the project rule is:

> **Dense flow at the orifice *boundary* is fine; dense flow on the leaflet *interior* is forbidden** — the interior values are regularization-propagated hallucination, not data.

**Heads-up — there is no literal "donut ROI" mask in the code.** Older design docs describe restricting dense flow to a "donut" (annulus) around the orifice boundary. That is a *design intent*, not implemented code. In `flow_explore.py`, Farneback runs on the *full frame*; the static, textureless interior is suppressed only by a **magnitude threshold** (default ~1.0 mm/frame) that hides slow/zero-motion pixels. So in practice only genuinely moving regions (boundary and edges) light up — but do not go hunting for a `donut_mask` variable; it does not exist.

### 2.6 How `flow_explore.py` turns dense flow into millimeters (and what it cannot see)

`flow_explore.py` is a dual-camera dense-flow *explorer* — a teaching/diagnostic visualizer, not a measurement tool. It is worth understanding because it shows both a clever idea and a hard limit:

- **Pixel flow → mm, per pixel.** Using the stereo calibration, it precomputes a per-pixel 2×2 **Jacobian** that converts a pixel-flow vector `(du, dv)` into an in-plane object-frame displacement `(dx, dy)` in mm, by back-projecting each pixel's ray onto the valve plane (`z = 0` in the calibration-object frame). It also prints a diagnostic mm-per-pixel scale at startup.
- **Direction → color, speed → opacity.** It tints each moving pixel by direction, anchored to the *object* axes so the same physical direction is the same color in both cameras: **Red = +x, Green = +y, Cyan = −x, Magenta = −y**, with opacity proportional to speed (transparent below threshold, ramping to ~0.85 alpha at `--max-mag`). (Note: CLAUDE.md's older "red=N, yellow=ENE, cyan=E" description is stale — the code is the source of truth.)
- **The hard limit — ±z is invisible by construction.** Because it projects *single-camera* flow onto the `z = 0` plane, any motion *toward or away from* the camera (along ±z, which is the flow direction) collapses to nothing. `flow_explore.py` is fundamentally a **2D** tool. For true 3D you *must* use the stereo triangulation pipeline ([§3](#3-the-stereo-calibration--triangulation-math)).

### 2.7 The human as the tiebreaker, and "is dense flow trustworthy?"

Because no automatic method is reliable on a blank leaflet, the actual ground-truth path puts a **human** in the loop: a person clicks the same anatomical landmark by eye on each frame (`annotate_point.py` for the single-camera validation track, `annotate_stereo_point.py` for the metric pipeline) and tags the cardiac **phase** (open / opening / closing / closed via keys 1/2/3/4).

The single-camera validation tool `analyze_annotations.py` then has two modes:

- **Mode A** (CSV only): detect complete cardiac cycles (the phase sequence `closed → opening → open → closing → closed`) and report per-cycle metrics — period, path length, peak displacement — plus their **coefficient of variation (CV = std/mean)**, the headline reproducibility number.
- **Mode B** (`--video`): the validation cross-check. It recomputes Farneback flow between consecutive labeled frames, samples the flow at the human's clicked point, and compares the *machine's* predicted displacement to the *human's* manual displacement, reporting `median_error_px` and `p95_error_px`. This literally answers: **"where a human can verify it, is dense flow accurate enough to trust?"**

> **Footgun:** Mode A's period and CV scale linearly with `--fps`. If you pass the wrong `--fps`, the numbers are silently wrong — the tool only *warns* if `--fps` disagrees with the video's reported FPS by more than 5%.

---

## 3. The stereo calibration & triangulation math

This section faithfully summarizes the two source-of-truth math docs — `docs/metric_displacement_mathematics.md` (the heavier, self-contained derivation) and `docs/calibration_to_displacement_walkthrough.md` (the code-oriented walkthrough) — and matches the actual code in `tools/stereo_calibrate.py` and `tools/triangulate.py`.

### 3.1 The pinhole camera model

A camera is modeled as an ideal **pinhole**: light from a 3D point passes through a single point (the optical center) onto the sensor. By similar triangles, a 3D point at `(X_c, Y_c, Z_c)` *in the camera's own coordinate frame* lands on the image at:

```
x = f · X_c / Z_c ,    y = f · Y_c / Z_c          (Eq. 1)
```

`f` is the focal length (here in pixel units). The division by `Z_c` (depth) is the **perspective division** — and it is the *only* nonlinear step, and the reason a single image throws away depth (near-and-small looks identical to far-and-big).

The full mapping from a 3D world point `X = (X, Y, Z)` to a pixel `(p, q)` has three parts:

**(a) Extrinsics — where the camera is.** Rotate and translate the world point into the camera's frame:

```
X_c = R · X + t                                    (Eq. 3)
```

`R` is a 3×3 rotation, `t` a 3-vector translation. Together `(R, t)` are the **extrinsics** (the camera's pose). The camera's optical center in world coordinates is:

```
C = −Rᵀ t                                          (Eq. 4)
```

This `C` is what gets cross-checked against CAD ([§3.5](#35-the-three-validation-checks)).

**(b) Lens distortion — the lens isn't a perfect pinhole.** Real lenses bend straight lines. We apply a small **Brown-Conrady** correction to the normalized coordinates `(x', y') = (X_c/Z_c, Y_c/Z_c)`, with `r² = x'² + y'²`:

```
x'' = x'(1 + k₁r²) + 2p₁x'y' + p₂(r² + 2x'²)
y'' = y'(1 + k₁r²) + p₁(r² + 2y'²) + 2p₂x'y'       (Eq. 7)
```

`k₁` is **radial** distortion (barrel/pincushion curvature); `p₁, p₂` are **tangential** distortion (slight lens-sensor misalignment). Higher radial terms `k₂, k₃` are forced to **zero** here (explained in [§3.4](#34-why-the-focal-length-and-principal-point-are-frozen)).

**(c) Intrinsics — sensor scale and center.** Finally map to pixels with the **camera matrix** `K`:

```
K = [[f, 0, cx],
     [0, f, cy],
     [0, 0,  1]]      p = f·x'' + cx ,  q = f·y'' + cy
```

`(cx, cy)` is the **principal point** — where the optical axis pierces the sensor, fixed here to the image center `(960, 600)` for a 1920×1200 sensor.

The whole chain is written compactly as the **forward projection** `m = π(K, d, R, t; X)` (Eq. 8), where `d = [k₁, p₁, p₂]` is the distortion and `m = (p, q)` is the predicted pixel.

### 3.2 Refraction and the "effective pinhole" trick

The cameras look through **acrylic and then fluid** at the submerged object. Light bends (**refracts**) at each interface, so a true pinhole model is wrong in principle. We do **not** ray-trace Snell's law (that is "Approach B," deferred). Instead we use **Approach A — the effective pinhole.**

The physics shortcut: for a flat interface, a paraxial (near-axis) ray makes a submerged object look **shallower** than it is by a factor of `n` (the refractive index) — the "the pool looks shallower than it is" effect. Apparent depth `D' = D / n` (Eq. 5). Feeding that into the magnification formula shows the recording behaves *as if* the focal length were multiplied by `n`. So the **effective focal length underwater is `n · f`**, and we seed the focal length as:

```
f_px = (f_lens / pixel_size) · n
     = (16.0 mm / 0.00345 mm/px) · n               (Eq. 6)
```

with `n_water = 1.333` and `n_analog = 1.385`. (Verified: `16/0.00345 × 1.333 = 6182.03`, exactly the `K[0][0]` in `stereo_calib_water.json`; `× 1.385 = 6423.19` for analog.)

**Honest caveat from the math doc:** Eq. 5 is only paraxial — off-axis rays bend more, and there is mild residual aberration. We do *not* correct this analytically. Instead we **calibrate underwater, through the real acrylic port, in the real fluid**, and let the fitted distortion terms soak up whatever the simple model misses. That is exactly why each fluid needs its own calibration. The lens is Edmund Optics **#33-304, 16 mm UC Series**, with entrance-pupil offset **EPP = 10.68 mm**. (An older CLAUDE.md note citing "#59-870 / EPP 24.42 mm" is **wrong/stale** — the code and both calib JSONs use 10.68 mm.)

### 3.3 Calibration: fitting the model to the dots

**The calibration object** is a fixed, 3D-printed stack of cylinders with 41 black dots (1.5 mm, painted with waterproof ink) at CAD-known 3D positions, listed in `markers.csv` as `(dX, dY, dZ)` in mm. The coordinate frame: **origin at the center of the top face, +z pointing up along the direction of fluid flow.** The dots sit at **five distinct z-depths** (z = −11.76, −7.84, −3.92, two rings at z = 0, and the center at the origin).

`stereo_calibrate.py` runs `cv2.calibrateCamera` *separately per camera*, fitting the model so that the projected dot positions match the clicked dot positions — i.e. minimizing the **reprojection error**:

```
(K̂, d̂, R̂, t̂) = argmin  Σ_i ‖ m_i,observed − π(K, d, R, t; X_i) ‖²     (Eq. 9)
```

over all dots `i`. The reported `reprojection_rms_px` is the root-mean-square of those pixel residuals. The solver is **Levenberg-Marquardt** (a standard nonlinear least-squares method that blends Gauss-Newton with gradient descent). The 3×3 rotation `R` is parameterized by a 3-number **Rodrigues** axis-angle vector `rvec` (a rotation has only 3 degrees of freedom, not 9), so each camera pose is just 6 unknowns.

### 3.4 Why the focal length and principal point are frozen

This is the subtlest and most important calibration decision, so it gets its own section.

Normally you calibrate by showing a checkerboard at *many* poses (Zhang's method). **We cannot** — the calibration object is fixed (it is designed to occupy the valve's displacement volume and cannot be moved or rotated). So we have only **one image per camera**. This is a **single-view, DLT-style** calibration.

A single view is *under-determined* if you let everything float. Two reasons, from the math doc:

1. **Focal-depth ambiguity.** The pinhole equation `x = f·X/Z` is unchanged if you scale `(f, Z) → (αf, αZ)`. A single camera *cannot* separate "long lens, far away" from "short lens, close up." If you leave `f` free, it will absorb this ambiguity — and silently drag the camera position `t` along with it. Reprojection error stays beautifully small while the recovered *geometry is physically wrong.* The higher radial terms `k₂, k₃` are zeroed for the same reason: they can mimic a focal-length change across the image and reintroduce the ambiguity.
2. **Planar degeneracy.** If all dots were coplanar, one view could only recover a homography, which cannot be uniquely factored into camera geometry. This is *the* reason the calibration object is a stepped **cylinder stack** giving **non-coplanar** dots at five depths — that depth spread is "load-bearing."

So `stereo_calibrate.py` fixes the under-determined parts and fits only the well-determined ones. The flags (`CALIB_FLAGS`):

```python
CALIB_FLAGS = (
    cv2.CALIB_USE_INTRINSIC_GUESS    # seed K from the lens·n matrix above
  | cv2.CALIB_FIX_FOCAL_LENGTH       # f frozen at the seed
  | cv2.CALIB_FIX_PRINCIPAL_POINT    # (cx, cy) frozen at image center
  | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3   # k2 = k3 = 0
)   # → only k1, p1, p2 (distortion) and (R, t) (pose) are actually fit
```

Degrees-of-freedom bookkeeping: a general projective camera has 11 DOF (K's 5 + pose's 6); we fix focal length, skew, and principal point, leaving **9 free** (3 distortion + 6 pose). With ~31–41 dots giving 2 equations each, the system is 7–9× over-determined — solidly constrained. This fixed-`f`, free-`k1/p1/p2` recipe was empirically the best of 5 variants tested.

> **The lesson the math doc hammers:** *low reprojection error proves the model fits the pixels; it does NOT prove the recovered camera pose is physical.* That is exactly why we add the independent CAD cross-check below.

### 3.5 The three validation checks

`stereo_calibrate.py` writes a `validation` block and gates on three checks:

1. **Reprojection RMS** (per camera): how well the fitted model reprojects the dots. *Water: cam0 = 3.23 px, cam1 = 3.63 px.*
2. **3D triangulation error vs CAD** (the real accuracy number): triangulate each dot from both cameras and compare to its known CSV position; `error = ‖X̂_i − X_i^CAD‖`. **Pass if median < 5.0 mm.** *Water achieved median 0.154 mm, max 0.431 mm over 38 dots* — sub-millimeter, the noise floor of the whole pipeline.
3. **Camera-position (EPP) cross-check** (proves the pose is *physical*, not just that pixels fit): compute the calibrated optical center `C = −Rᵀt` and compare to the CAD-predicted entrance pupil `C_CAD = front_face − 10.68 mm · axis_outward`. **Pass if `‖C − C_CAD‖ < 15 mm`.** *Water: cam0 10.80 mm, cam1 8.19 mm — both pass.* It also recovered cam1's tilt as 18.30° vs the CAD 19.33° (agreement within ~1°).

**Both fluids are calibrated and pass:**

| Fluid | n | Frame | 3D median / max | Reproj RMS (cam0/cam1) | EPP discrepancy (cam0/cam1) |
|-------|------|------:|-----------------|------------------------|-----------------------------|
| Water | 1.333 | 65 | 0.154 / 0.431 mm | 3.23 / 3.63 px | 10.80 / 8.19 mm |
| Analog (glycerin) | 1.385 | 69 | 0.131 / 0.500 mm | 3.11 / 3.83 px | **14.42** / 11.53 mm |

> **Caveat:** the analog cam0 EPP discrepancy (14.42 mm) is *only just inside* the 15 mm tolerance. Flag this if you ever recalibrate the blood analog.

### 3.6 Triangulation: two rays, one 3D point

Now the payoff. The valve clip is annotated: for each frame you have a pixel `(p, q)₀` in cam0 and `(p, q)₁` in cam1, both clicking the *same* physical leaflet landmark.

**Why two views give 3D:** a single camera only knows the *direction* (a ray) from its optical center through the clicked pixel — the point is somewhere along that ray, but you can't tell how far. With **two** cameras at known, different poses, each gives a ray. Two rays in space cross at one point — and that crossing **is** the 3D position. (Because of pixel noise the rays don't perfectly meet, so we take the best least-squares intersection.)

`triangulate_point()` in `triangulate.py` does exactly this:

```python
pts0 = cv2.undistortPoints([[uv0]], K0, dist0, P=K0)   # remove lens distortion first
pts1 = cv2.undistortPoints([[uv1]], K1, dist1, P=K1)
R0, _ = cv2.Rodrigues(rvec0); R1, _ = cv2.Rodrigues(rvec1)
P0 = K0 @ [R0 | t0];  P1 = K1 @ [R1 | t1]              # 3×4 projection matrices
pt_4d = cv2.triangulatePoints(P0, P1, pts0, pts1)      # homogeneous (4 numbers)
XYZ_mm = pt_4d[:3] / pt_4d[3]                           # dehomogenize → (X, Y, Z) in mm
```

Step by step:

1. **Undistort first.** Apply each camera's `(k₁, p₁, p₂)` to map the clicked pixel back to where an ideal pinhole would have put it. This makes the next step a clean *linear* problem.
2. **Build the projection matrix** `P = K [R | t]` (3×4) for each camera. `R` comes from `rvec` via Rodrigues.
3. **Solve the linear triangulation (DLT).** Each camera's relation `λ_c m̃_c = P_c X̃` can be rewritten so the unknown depth `λ_c` drops out, giving two equations per camera:

   ```
   [ p₀·P₀,₃ − P₀,₁ ]
   [ q₀·P₀,₃ − P₀,₂ ]  ·  [X, Y, Z, 1]ᵀ  =  0
   [ p₁·P₁,₃ − P₁,₁ ]
   [ q₁·P₁,₃ − P₁,₂ ]
   ```

   Stack the four rows into a 4×4 matrix `A` and solve `min ‖A X̃‖` subject to `‖X̃‖ = 1` via **SVD** (the answer is the singular vector with the smallest singular value).
4. **Dehomogenize:** divide the first three coordinates by the fourth → `(X, Y, Z)` in millimeters, automatically, because the calibration was in mm.

> Footnote from the math doc: DLT minimizes *algebraic* error, not the geometrically optimal (Hartley-Sturm) error. That is fine here — the inputs are sub-pixel and the measured end-to-end 3D error (0.154 mm) is far below what we need.

### 3.7 Fixing free-running camera skew (the sync step)

Because the cameras free-run, cam0's frame `n` and cam1's frame `n` were grabbed at slightly different *times*. Triangulation assumes "same point, same instant," so a time offset injects an error proportional to `(leaflet speed) × (time offset)`.

If you pass both `--cam0-timestamps` and `--cam1-timestamps`, `triangulate.py` corrects this by **linearly interpolating** cam1's pixel position to cam0's frame time. With `α = (t₀(n) − t₁(a)) / (t₁(b) − t₁(a))`:

```
uv1_sync = uv1(a) + α · (uv1(b) − uv1(a))
```

(`interpolate_pixel_at_time()` clamps to the nearest endpoint outside the range — no extrapolation.) This reduces the timing error from first-order to second-order (curvature within one inter-frame interval). **Always pass the timestamp sidecars** when you have them.

### 3.8 From 3D points to displacement and cycle metrics

`triangulate.py` then computes, for each frame, the **displacement** from the first labeled frame:

```
Δ⁽ⁿ⁾ = X⁽ⁿ⁾ − X⁽⁰⁾  = (dx, dy, dz),    d⁽ⁿ⁾ = ‖Δ⁽ⁿ⁾‖     (Eq. 25)
```

and writes `frame_idx, x_mm, y_mm, z_mm, displacement_mm, dx_mm, dy_mm, dz_mm, phase`.

`analyze_metric.py` then detects each complete cardiac cycle (`closed → opening → open → closing → closed`) and reports, per cycle:

- **`cycle_period_ms`** = `(frame span / fps) × 1000`
- **`path_length_mm`** = `Σ ‖X_{i+1} − X_i‖` (sum of segment lengths). *Honest bias:* this chord-sum is a **systematic under-estimate** of the true curved arc length; the error shrinks as frame rate rises. It is the one metric with a known sign of bias.
- **`peak_displacement_mm`** = `max ‖X_i − X_0‖` over the cycle

and aggregates each as mean, std, and **CV = std/mean** — the scale-free reproducibility number. (A cycle that doesn't pass cleanly through the full phase sequence is excluded; mislabeled or missing phases yield zero complete cycles and a hard exit — so annotate phases carefully.)

### 3.9 A note on stereo geometry and accuracy

For an idealized parallel stereo pair, depth uncertainty goes as `σ_Z ≈ (Z²/fB)·σ_d` (Eq. 29) — it grows *quadratically* with range and *inversely* with baseline `B` and focal length `f`. The intuition: stereo wants a **wide baseline, long lens, close target**. Our geometry is *converged* (0° and 19.3° cameras pointing at the same close target), so Eq. 29 is only intuition, not exact — which is why we don't propagate it by hand and instead *measure* true end-to-end error directly (the 0.154 mm number in [§3.5](#35-the-three-validation-checks)).

---

## 4. The experimental "tracks" workstream

There is a **second, parallel CV pipeline** in `tools/` that the older docs (CLAUDE.md, PRD) do **not** describe. As of this handoff it is **uncommitted** (all files show as untracked in git) — but it *works*, has passing tests, and produced real artifacts. An incoming student should know it exists, what it does, and where it is headed.

### 4.1 What it is

The headline pipeline ([§3](#3-the-stereo-calibration--triangulation-math)) tracks **one** landmark, labeled **by hand** every frame. The tracks workstream **automates** that and **scales to N points**: it automatically tracks *multiple* natural leaflet "intersection" corners over time across both cameras, triangulates each into 3D mm per frame, and analyzes/visualizes them (even correlating against Arduino pressure). It is the logical successor to the single-point annotator. Crucially, it **reuses the committed stereo machinery** — every tracks script imports `load_calibration`, `load_timestamps`, `interpolate_pixel_at_time`, and `triangulate_point` from the committed `triangulate.py`, and uses the same `stereo_calib_<fluid>.json`.

### 4.2 The tracker algorithm: hybrid LK + frozen-frame-0 NCC anchor

This is the technical heart, and it is the *direct answer* to why plain LK failed ([§2.4](#24-sparse-flow-lucas-kanade--and-why-plain-lk-failed-here)). The tracker (`track_intersections.py`) is **NOT** pure LK. Per point, per camera, per frame (`hybrid_step`):

1. **LK as a search *prior*, not the answer.** Run forward+backward LK from the previous frame. If the forward-backward residual ≤ `--fb-threshold` (default 1.0 px), trust LK's prediction and search a tight ±`--lk-search` window (default 10 px). Otherwise fall back to the previous position with a wide ±`--fallback-search` window (default 30 px) — wide enough to survive a fast leaflet snap-open.
2. **NCC against a frozen frame-0 template is the actual measurement.** Search that window with **normalized cross-correlation** (`cv2.matchTemplate`, `TM_CCOEFF_NORMED`) against the patch extracted at **frame 0 and never updated**. The NCC peak (refined to sub-pixel by a parabolic fit) is the reported position.
3. **Health gate — lose loudly, never recover silently.** If either camera's NCC peak score < `--ncc-threshold` (default 0.7), the track is marked `healthy=False` from that frame onward and carries the last good position. No silent recovery.

**Why this beats plain LK** (the drift argument, from the math doc): chained frame-to-frame flow *accumulates* error — variance grows like `N` (so spread grows like `√N`), unbounded. On the textureless valve it does worse (near-singular structure tensor + biased error). Matching against a template that is **extracted once and never updated** means error does **not** accumulate — variance stays constant. NCC is also formally *invariant to affine intensity changes* (`S → aS + b`): subtracting the mean kills the brightness offset `b`, dividing by the norm kills the gain `a`. That is the precise mathematical reason it survives the uneven underwater lighting that pure brightness-constancy flow cannot.

```
NCC(s) = Σ(T − T̄)(S_s − S̄_s) / √( Σ(T − T̄)² · Σ(S_s − S̄_s)² )  ∈ [−1, 1]
```

> **Reconciling with "do not track valve dots":** CLAUDE.md forbids *fiducial-dot* tracking on the valve because dot identity drifts. This tracker is different — it tracks *natural* intersection corners and re-anchors every frame to the immutable frame-0 template. The frozen-anchor NCC **is** the deliberate ID-drift mitigation. It does not violate the spirit of that rule, but the docs have not been updated to say so yet.

### 4.3 The supporting tools and data flow

```
record_valve.py --dual           → cam0/cam1 .avi + .timestamps.csv   [committed]
pick_track_seeds.py               → <cam0>.track_seeds.json (anchor frame + N points)
track_intersections.py            → <seeds>.tracks.csv  (long: one row per frame×point)
   --seeds … --calib stereo_calib_<fluid>.json [--camN-timestamps …]
   ├── analyze_tracks.py            → per-point peak/path-length + FFT cycle period + plots
   ├── playback_tracks.py           → dual-cam overlay video (--save MP4)
   ├── analyze_pressure_vs_tracks.py→ stacked P2 / Flow / displacement vs time PNGs
   └── splice_manual_into_tracks.py → repairs lost tracks with sparse manual labels
```

- `_tracks.py` — the shared headless spine: the `TrackSample` dataclass, the 19-column CSV schema, validated read/write, and a 20-color per-point palette so a point keeps its color across picker, playback, and plots. **Mature and unit-tested.**
- `analyze_tracks.py` derives cycle period by **FFT** (dominant frequency in a 0.3–5 Hz band over *healthy* frames) — different from `analyze_metric.py`, which derives period from manual *phase labels*. Two upstream paths, two period methods.
- `annotate_stereo_point.py` (the one *modified* tracked file) was retrofitted with `--step N` sparse labeling, a `--output` path, and yellow/red carry-forward markers, specifically to feed `splice_manual_into_tracks.py` as a manual-correction tool for tracks that go lost.

### 4.4 Status, tests, and cautions

- **It is real and works.** `tests/test_tracking.py` passes **17/17** (covers `_tracks.py` I/O and the tracker primitives, including an anti-drift regression test and a loss-detection test). Real `.tracks.csv` and 8-point `.spliced.tracks.csv` artifacts exist from multiple recordings.
- **What is NOT tested:** the tracker's `main()` orchestration, all the GUI tools (picker/playback/annotator), `analyze_*`, the plot scripts, and especially `splice_manual_into_tracks.py`'s interpolation/origin logic (the trickiest, most fragile piece).
- **It is parameter-sensitive.** `--ncc-threshold` (0.7) is the make-or-break knob: too high → tracks go lost during deformation; too low → they drift. `--fallback-search` (30) exists for snap-open. There is no quantitative ground-truth validation of the defaults — only the synthetic regression test and visual playback.
- **`analyze_pressure_vs_tracks.py` is exploratory.** It eyeballs Arduino P2/Flow against displacement, but CLAUDE.md/MEMORY are explicit that **Arduino flow is NOT a sanctioned validation gate** (it measures volumetric flow *upstream* in a different cross-section — not the same physical quantity as leaflet motion). Treat its plots as exploration, not validation.

### 4.5 Where it is headed (and a rejected detour)

The tracks workstream is the path from "one hand-labeled point" toward "many auto-tracked points, full 3D leaflet motion." Before extending it, the project convention says you must write a `docs/plans/<date>-tracking-design.md`, commit it on a correctly-named branch, and reconcile it with CLAUDE.md.

**A dead end you should not resurrect:** on 2026-05-10 the author briefly tried a completely different "true 3D" approach — per-pane **dense stereo** (rectify both cameras, `cv2.StereoSGBM` disparity → `reprojectImageTo3D`, then Farneback flow sampled at the 3D field). It was only smoke-tested on synthetic frames and **reverted the same day**. The author chose the sparse hybrid-LK+NCC tracker instead. (Dense flow on the leaflet interior is also on the "do not build" list — see [§2.5](#25-dense-flow-farneback--what-it-does-and-its-honest-limits).) Do not assume dense stereo flow works here; it was rejected.

> **Branch-name heads-up:** the current branch is `feature/flow-export`, but `flow_export.py` was **killed** and does not exist on disk; the dense-flow framing the branch is named for is dead. The real work on this branch is the metric stereo pipeline + this tracks pivot. Don't go looking for `flow_export.py`.

---

## 5. Glossary

Terms are defined in the specific way they are used on this project.

- **Aperture problem** — Through a small local window, you can only measure the component of motion *perpendicular* to an edge, never *along* it. Mathematically: the optical-flow constraint is one equation in two unknowns. This is *the* reason plain LK fails on the smooth leaflet. ([§2.3](#23-the-aperture-problem-the-heart-of-the-whole-story))

- **Baseline** — The distance between the two cameras' optical centers. A wider baseline gives better depth accuracy. Ours is small/converged (0° and 19.3° on a close target), so depth precision relies on the long focal length and sub-pixel accuracy instead.

- **Brightness constancy** — The assumption underpinning all optical flow: a physical point keeps the same brightness as it moves between frames. Bubbles and uneven lighting break it, which is why NCC (intensity-invariant) beats raw flow here. ([§2.2](#22-the-brightness-constancy-assumption-why-flow-can-work-at-all))

- **Calibration** — The process of solving for a camera's intrinsics, distortion, and pose by matching projected known-3D points to their observed pixel positions. Here it is **single-view** (one frame per camera) because the calibration object can't move. ([§3.3](#33-calibration-fitting-the-model-to-the-dots))

- **Calibration object** — A fixed 3D-printed cylinder stack with 41 ink dots at CAD-known mm positions (`markers.csv`), designed to occupy the valve's volume. A "3D ruler." Its dots span five depths (non-coplanar) so a single view can constrain the full camera geometry.

- **Camera matrix `K` (intrinsics)** — The 3×3 matrix `[[f,0,cx],[0,f,cy],[0,0,1]]` that maps a direction in the camera frame to a pixel. `f` = focal length in pixels; `(cx, cy)` = principal point. ([§3.1](#31-the-pinhole-camera-model))

- **Coefficient of variation (CV)** — `std / mean`, a scale-free measure of spread. The headline *reproducibility* number for cycle metrics (smaller = more consistent heartbeats). ([§3.8](#38-from-3d-points-to-displacement-and-cycle-metrics))

- **Dense optical flow (Farneback)** — Estimates a motion arrow for *every* pixel (`cv2.calcOpticalFlowFarneback`). Trustworthy on textured/edge regions; **hallucinates** on the blank leaflet interior via its smoothness term. ([§2.5](#25-dense-flow-farneback--what-it-does-and-its-honest-limits))

- **DLT (Direct Linear Transform)** — The linear method used to triangulate a 3D point from two pixel observations: stack the per-camera constraints into a matrix and solve with SVD. Minimizes algebraic error; good enough here. ([§3.6](#36-triangulation-two-rays-one-3d-point))

- **Distortion (Brown-Conrady)** — Lens deviation from the ideal pinhole. `k₁` = radial (curved lines), `p₁, p₂` = tangential (lens-sensor tilt). We fit `k₁, p₁, p₂` and force `k₂ = k₃ = 0`. ([§3.1](#31-the-pinhole-camera-model))

- **EPP / entrance pupil & EPP cross-check** — The entrance pupil is the effective optical center of the lens; for #33-304 it sits **10.68 mm** behind the front face. The cross-check compares the *calibrated* camera center `C = −Rᵀt` to the *CAD-predicted* entrance pupil; passing (< 15 mm) proves the recovered pose is physically real, not just numerically fitted. ([§3.5](#35-the-three-validation-checks))

- **Effective pinhole (Approach A)** — Handling refraction not by ray-tracing Snell's law, but by calibrating underwater through the real port and letting the fitted focal length (`n·f`) and distortion absorb the bending. Why each fluid needs its own calibration. ([§3.2](#32-refraction-and-the-effective-pinhole-trick))

- **Epipolar geometry** — The geometric relationship between two views of the same scene: a point in one image must lie on a line (the *epipolar line*) in the other. It is the foundation of stereo correspondence. Here it is implicit — we triangulate from manually/automatically matched points rather than searching along epipolar lines explicitly.

- **Extrinsics `(R, t)`** — The camera's *pose*: rotation `R` and translation `t` that move world points into the camera frame (`X_c = R X + t`). The optical center is `C = −Rᵀt`. The main thing calibration solves here. ([§3.1](#31-the-pinhole-camera-model))

- **Farneback** — See *Dense optical flow*.

- **Focal-depth ambiguity** — In a single view, scaling `(f, Z) → (αf, αZ)` leaves predicted pixels unchanged, so a lone camera can't separate focal length from depth. Why we *freeze* the focal length. ([§3.4](#34-why-the-focal-length-and-principal-point-are-frozen))

- **Forward-backward (FB) consistency** — Track forward then backward; a good point lands back on itself. The round-trip distance is a reliability check (LK prototype: threshold 1.0 px; the hybrid tracker uses it to choose its search window). ([§2.4](#24-sparse-flow-lucas-kanade--and-why-plain-lk-failed-here), [§4.2](#42-the-tracker-algorithm-hybrid-lk--frozen-frame-0-ncc-anchor))

- **Jacobian (in `flow_explore.py`)** — A per-pixel 2×2 matrix that converts a pixel-flow vector into an in-plane object displacement in mm, by back-projecting the ray onto the `z = 0` valve plane. ([§2.6](#26-how-flow_explorepy-turns-dense-flow-into-millimeters-and-what-it-cannot-see))

- **Lucas-Kanade (LK)** — See *Sparse optical flow*.

- **MJPG (Motion JPEG)** — The recording codec for valve clips: each frame is JPEG-compressed *independently* (intra-frame only). "Visually lossless" at `-q:v 2`, and safe for optical flow because it invents no inter-frame motion (unlike the abandoned H.264). ([§1.3](#13-important-real-world-wrinkles-you-must-know))

- **NCC (Normalized Cross-Correlation)** — A template-matching score in `[−1, 1]` that is invariant to affine intensity change (brightness/gain). In the hybrid tracker it is matched against a *frozen frame-0* template, which makes tracking drift-free by construction. ([§4.2](#42-the-tracker-algorithm-hybrid-lk--frozen-frame-0-ncc-anchor))

- **Optical flow** — The estimated per-pixel (dense) or per-point (sparse) motion between two frames. ([§2.1](#21-the-core-idea))

- **Pinhole model** — The idealized camera where all light passes through one point; gives `x = f·X/Z` (perspective projection). ([§3.1](#31-the-pinhole-camera-model))

- **Principal point `(cx, cy)`** — Where the optical axis pierces the sensor; frozen to image center `(960, 600)` here. ([§3.1](#31-the-pinhole-camera-model))

- **Projection matrix `P`** — The 3×4 matrix `P = K [R | t]` that maps a 3D world point directly to a pixel (up to scale). Built per camera in `triangulate.py`. ([§3.6](#36-triangulation-two-rays-one-3d-point))

- **Refraction / refractive index `n`** — Light bends at the acrylic/fluid interfaces; `n` quantifies how much (water 1.333, glycerin analog 1.385). Handled via the effective-pinhole trick and per-fluid calibration. ([§3.2](#32-refraction-and-the-effective-pinhole-trick))

- **Reprojection error** — After fitting, project the known 3D dots back to pixels and measure the residual; the RMS is `reprojection_rms_px`. Low reprojection error proves the model *fits the pixels* — but **not** that the pose is physical (hence the EPP cross-check). ([§3.5](#35-the-three-validation-checks))

- **Rodrigues vector `rvec`** — A compact 3-number axis-angle encoding of a rotation; `cv2.Rodrigues` expands it to a 3×3 `R`. A rotation has only 3 DOF. ([§3.3](#33-calibration-fitting-the-model-to-the-dots))

- **Sparse optical flow (Lucas-Kanade)** — Tracks a few chosen points (`cv2.calcOpticalFlowPyrLK`), each needing a locally distinctive (corner-like) pattern. Fails on the textureless silicone leaflet — the project's central failure lesson. ([§2.4](#24-sparse-flow-lucas-kanade--and-why-plain-lk-failed-here))

- **Structure tensor `G`** — The 2×2 matrix `Σ ∇I∇Iᵀ` whose invertibility (both eigenvalues large) tells LK whether a window is trackable. Near-singular on edges and blanks. ([§2.4](#24-sparse-flow-lucas-kanade--and-why-plain-lk-failed-here))

- **SVD (Singular Value Decomposition)** — The linear-algebra tool used to solve the homogeneous triangulation system `min ‖A X̃‖` (answer = smallest-singular-value vector). ([§3.6](#36-triangulation-two-rays-one-3d-point))

- **Timestamp sidecar (`*.avi.timestamps.csv`)** — Per-frame `frame_index, system_time_s, hw_timestamp_ticks` written at recording time. Used to correct the free-running cameras' temporal skew before triangulation. ([§1.3](#13-important-real-world-wrinkles-you-must-know), [§3.7](#37-fixing-free-running-camera-skew-the-sync-step))

- **Triangulation** — Recovering a 3D point as the (least-squares) intersection of the two rays from two calibrated cameras through the same matched pixel. The step that produces millimeters. ([§3.6](#36-triangulation-two-rays-one-3d-point))

---

## Appendix: quick reference

**Run order (metric pipeline):** `record_calibration.py` → `stereo_calibrate.py` → `annotate_stereo_point.py` (on the valve clip) → `triangulate.py` (pass the timestamp sidecars!) → `analyze_metric.py`.

**Source-of-truth files:**
- Math (committed): `tools/stereo_calibrate.py`, `tools/triangulate.py`
- Math docs (currently untracked — read these first): `docs/metric_displacement_mathematics.md` (primary), `docs/calibration_to_displacement_walkthrough.md` (code-oriented), `docs/backup_slides_math_and_algorithm.md` (Q&A slide deck)
- Optical flow: `tools/_flow_params.py` (shared Farneback dict), `tools/flow_explore.py` (dense explorer), `tools/leaflet_flow_test.py` (the LK *failure exhibit* — do not extend)
- Tracks workstream (untracked): `tools/track_intersections.py`, `tools/_tracks.py`, `tools/pick_track_seeds.py`, `tools/playback_tracks.py`, `tools/analyze_tracks.py`, `tools/splice_manual_into_tracks.py`; `tests/test_tracking.py` (17 pass)

**Calibration constants (in `stereo_calibrate.py`):** lens #33-304 16 mm, EPP 10.68 mm, pixel 0.00345 mm, `f_px = (16/0.00345)·n` → 6182.03 (water) / 6423.19 (analog). Fits only `k₁, p₁, p₂` + pose; freezes `f`, principal point, and `k₂ = k₃ = 0`. Gates: 3D error median < 5 mm, EPP discrepancy < 15 mm.

**The one thing to remember:** *Low reprojection error means the model fits the pixels — not that the geometry is real.* That is why we freeze the focal length and add the independent CAD cross-check, and why "we track with optical flow" is the wrong description of the tracker (flow is only a search prior; the measurement is NCC against a frozen frame-0 template).