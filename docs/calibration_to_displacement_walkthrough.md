# Calibration → Metric Displacement: Full Mathematical Walkthrough

Chronological, equation-by-equation walkthrough of the entire pipeline,
written for lab-meeting Q&A prep. Equations match the actual tool code,
not the idealized textbook version.

**Source-of-truth code:**
- `tools/stereo_calibrate.py` — camera model, calibration, validation
- `tools/pick_track_seeds.py` — landmark seeding
- `tools/track_intersections.py` — LK + NCC-anchor tracker
- `tools/triangulate.py` — undistortion + DLT triangulation + displacement
- `tools/analyze_metric.py` / `tools/analyze_tracks.py` — cycle metrics

> **Framing point — say this precisely or you will get caught.**
> The pipeline is **not** "optical flow → displacement." Lucas–Kanade
> optical flow is used **only as a per-frame search prior**. The actual
> position measurement every frame is a **normalized cross-correlation
> match against a frozen frame-0 template**, followed by stereo
> triangulation. If you claim "we track the leaflet with optical flow,"
> the first question is "doesn't LK drift?" — and that question is the
> entire reason the tracker is built this way.

---

## Stage 0 — Coordinate frame and the calibration object

Everything is expressed in the **calibration-object frame**: origin at
the center of the top face, +z out of the top face (direction of flow),
right-handed. CAD gives the true 3D position $X_i=(X,Y,Z)_i$ in **mm**
of all 41 painted dots (`markers.csv`).

Because all geometry enters in mm, every downstream number comes out in
mm with no extra scaling — that is why metric output is "free" once
calibration is correct.

The dots sit at 5 z-depths (cylinder rings at z = −11.76, −7.84, −3.92,
plus two top-face rings at z = 0, plus the center point at the origin).
**This non-coplanarity is load-bearing** — see Stage 3.

---

## Stage 1 — Capture

`record_calibration.py` (object) and `record_valve.py` (valve runs)
record **two independent AVIs** (lossless FFV1) plus a **timestamp
sidecar** per camera: one row per frame, `frame_index, system_time_s`,
where the time is `grabResult.GetTimeStamp()`.

Key fact: **the cameras are not hardware-triggered.** They free-run at
~30 fps and drift relative to each other. The timestamps are what let us
correct that later (Stage 7). Deliberate deferral, not an oversight.

---

## Stage 2 — 2D↔3D correspondences (`stereo_calibrate.py`)

One frame is extracted per camera's calibration video. Dots are
auto-detected:

1. Threshold: pixels with intensity `< 80` → binary mask.
2. Morphological open (5×5 ellipse) to kill speckle.
3. `SimpleBlobDetector` filtered by area (30–1200 px²) and circularity
   (≥ 0.4).

The operator manually assigns a CAD `marker_id ∈ [1,41]` to each blob
(or `--load` / `--edit` to reuse/repair). Output per camera: a map
$\{\text{marker\_id} \rightarrow (u,v)\}$ pairing pixel observations to
known 3D points.

Manual ID assignment is done **once** — these dots are *identified, not
tracked*, which is why fiducials on the *object* are fine even though
fiducials on the *valve* are banned (ID drift).

---

## Stage 3 — Single-view camera calibration (`calibrate_camera`)

### The camera model

**Extrinsics** (world → camera), rotation stored as a Rodrigues vector
$r$ so $R = \exp([r]_\times)\in SO(3)$:

$$X_c = R\,X + t$$

**Perspective division** to normalized image coordinates:

$$x = X_c/Z_c,\qquad y = Y_c/Z_c$$

**Brown–Conrady distortion** with $r^2 = x^2+y^2$. Here $k_2=k_3=0$
(fixed), so only $k_1$ (radial) and $p_1,p_2$ (tangential) are free:

$$
\begin{aligned}
x_d &= x\,(1 + k_1 r^2) + 2p_1 x y + p_2 (r^2 + 2x^2)\\
y_d &= y\,(1 + k_1 r^2) + p_1 (r^2 + 2y^2) + 2p_2 x y
\end{aligned}
$$

**Intrinsics** $K$ map to pixels:

$$
\begin{bmatrix}u\\ v\\ 1\end{bmatrix}=K\begin{bmatrix}x_d\\ y_d\\ 1\end{bmatrix},\qquad
K=\begin{bmatrix}f_x&0&c_x\\0&f_y&c_y\\0&0&1\end{bmatrix}
$$

### The focal-length seed and the refraction story

$K$ is **initialized**, not blindly optimized:

$$f_{\text{px}} = \frac{f_{\text{lens}}}{p}\cdot n
= \frac{16\,\text{mm}}{0.00345\,\text{mm/px}}\cdot n,
\qquad c_x=\tfrac{w}{2},\ c_y=\tfrac{h}{2}$$

$n$ is the **fluid refractive index** (water 1.333, blood analog
1.385). This is the entire refraction handling — "Approach A, effective
pinhole." We calibrate *underwater, through the acrylic, in final
mounting*. A flat refracting interface scales apparent magnification by
≈ $n$; seeding $f$ with that factor and calibrating in situ lets the
fitted intrinsics + distortion **absorb** the refraction. We do **not**
ray-trace Snell's law (Approach B, deferred). Price: a separate
calibration per fluid.

### The optimization

`cv2.calibrateCamera` runs Levenberg–Marquardt to minimize total
**reprojection error** over all $N$ correspondences:

$$\min_{K,\,d,\,R,\,t}\ \sum_{i=1}^{N}
\big\lVert m_i - \pi(K,d,R,t;\,X_i)\big\rVert^2$$

where $m_i$ is the observed pixel, $\pi(\cdot)$ is the full projection
above. Reported number is the RMS:

$$\text{RMS}=\sqrt{\tfrac{1}{N}\sum_i\lVert m_i-\hat m_i\rVert^2}
\quad(\text{cam0}=3.23\text{ px, cam1}=3.63\text{ px, water run})$$

### Why single-view, and why we lock parameters

Zhang's standard method needs many views of a planar target at
different poses. **Our object is fixed** — it is machined to occupy the
valve's displacement volume and cannot be moved or rotated. So we have
*one* image per camera.

- **Single-view PnP-with-intrinsics works here only because the markers
  are non-coplanar** (the cylinder stack spans 5 z-depths). A planar
  dot pattern in one view would be degenerate; the depth spread makes
  the calibration observable.
- One view still under-constrains the full model. Focal length, object
  distance, and radial distortion mutually compensate in a single image
  (the focal/depth ambiguity). Let everything float and the optimizer
  drives RMS down by corrupting the *extrinsics*: projection looks
  great, camera position is wrong, triangulation is biased.
- So we fix what we physically know: `CALIB_FIX_FOCAL_LENGTH` (lens
  spec × $n$), `CALIB_FIX_PRINCIPAL_POINT` (image center),
  `CALIB_FIX_K2 | CALIB_FIX_K3` (zero high-order radial terms). Only
  $k_1, p_1, p_2$ and the 6 extrinsic DOF fit. Empirically the best of
  5 variants tested: 0.154 mm median triangulation error.

---

## Stage 4 — Calibration validation (two independent checks)

**(a) 3D triangulation residual.** Triangulate every marker seen by
both cameras (Stage 8 math) and compare to CAD truth:

$$e_i = \lVert \hat X_i - X_i^{\text{CAD}}\rVert,
\qquad \text{report median, mean, max}$$

Pass if median < 5 mm. Water run: median **0.154 mm**, max 0.431 mm
over 38 markers. This is the **noise floor of the whole pipeline** —
quote it.

**(b) Camera-position cross-check vs CAD.** Calibrated optical center
in world coordinates:

$$C = -R^{\top} t$$

CAD predicts the entrance pupil from the lens datasheet:

$$C_{\text{CAD}} = \text{front\_face} - 10.68\,\text{mm}\cdot \hat a,
\qquad \hat a = \frac{\text{axis\_intersect}-\text{front\_face}}
{\lVert\text{axis\_intersect}-\text{front\_face}\rVert}$$

Discrepancy $\lVert C - C_{\text{CAD}}\rVert$ must be < 15 mm
(mounting tolerance + residual refraction). Got 10.80 / 8.19 mm;
recovered tilt 18.30° vs 19.33° CAD.

This check proves the extrinsics are **physical**, not merely that
reprojection is small — that distinction is exactly the Stage 3 trap.
Lead with this if challenged on single-view.

Output: `outputs/calib/stereo_calib_<fluid>.json` holding
$K, d, r, t$ per camera.

---

## Stage 5 — Seed picking on the valve (`pick_track_seeds.py`)

Scrub to a clean reference frame (typically fully-closed valve). Click
the **same physical landmark** in cam0 and cam1. The frame of the first
click becomes the **anchor frame** (frame 0 of tracking). Output JSON:
per point, $(u_0,v_0)$ and $(u_1,v_1)$ at the anchor.

---

## Stage 6 — Per-frame tracking: LK + NCC-anchor hybrid (`track_intersections.py`)

The heart of "from optical flow." For every frame $n$, every point,
**each camera independently**:

### Step 1 — Lucas–Kanade as a motion prior

LK assumes brightness constancy and locally constant motion in a window
$W$. For displacement $\delta$:

$$\min_{\delta}\sum_{x\in W}
\big[I_{n}(x+\delta)-I_{n-1}(x)\big]^2$$

Linearizing ($I_n(x+\delta)\approx I_n(x)+\nabla I^\top\delta$) gives
the normal equations

$$G\,\delta = -\,b,\qquad
G=\sum_{W}\nabla I\,\nabla I^{\top}\ (\text{2}\times\text{2 structure tensor}),
\qquad b=\sum_{W}\nabla I\,I_t$$

`minEigThreshold = 1e-4` rejects windows where the smaller eigenvalue
of $G$ is too small — the **aperture problem** guard (an edge with no
corner gives a rank-deficient $G$). A 4-level pyramid (`maxLevel=3`)
handles large inter-frame motion (leaflet snap-open).

**Forward–backward consistency:** track $p_{n-1}\!\to\!\hat p_n$
forward, then $\hat p_n\!\to\!\hat p_n'$ backward. FB residual:

$$\varepsilon = \lVert \hat p_n' - p_{n-1}\rVert$$

If $\varepsilon \le \tau_{fb}$ (default 1 px), LK is trusted and the NCC
search window is small (`±lk_search`). Else LK is distrusted: fall back
to the previous position with a **large** window (`±fallback_search`,
default ±30 px) to absorb fast / non-smooth motion.

### Step 2 — NCC against the frozen frame-0 anchor (the actual measurement)

LK output is **only the center of a search box**. The reported position
is the peak of normalized cross-correlation between search region $S$
and the **frame-0 template $T$, which is never updated**
(`cv2.matchTemplate`, `TM_CCOEFF_NORMED`):

$$\rho(p)=\frac{\displaystyle\sum_{x}
\big(T(x)-\bar T\big)\big(S(x+p)-\bar S_p\big)}
{\sqrt{\displaystyle\sum_{x}\big(T(x)-\bar T\big)^2\
\sum_{x}\big(S(x+p)-\bar S_p\big)^2}}\in[-1,1]$$

$$p^\* = \arg\max_p \rho(p)$$

**Why this design — key Q&A point.** Pure LK integrates frame-to-frame:
per-frame error accumulates into unbounded drift, and it fails outright
on the valve (low-texture white silicone, edge/aperture features,
deformation) — documented in the dead `leaflet_flow_test.py`. By
matching every frame against the *immutable frame-0 appearance*, error
does **not** accumulate: each frame is independently registered to
ground truth. LK only narrows where to search so NCC is fast and does
not lock onto a repeated texture elsewhere. Normalization (subtract
mean, divide by std) handles uneven underwater lighting.

### Step 3 — Sub-pixel parabolic refinement

Fit a parabola through the 3 NCC values straddling the integer peak,
per axis:

$$\delta = \frac{1}{2}\cdot
\frac{\rho_{-1}-\rho_{+1}}{\rho_{-1}-2\rho_0+\rho_{+1}}
\quad(\text{clamped to }[-0.5,0.5])$$

applied independently in row and column. Final $(u,v)$ = integer peak
+ $(\delta_c,\delta_r)$. Sub-pixel (~0.1 px) without upsampling.

### Step 4 — Health gating

If $\rho^\* < \tau_{ncc}$ (default 0.70) in **either** camera, the point
is marked **lost from this frame onward**: subsequent frames carry the
last healthy $(u,v)$ with `healthy=False`, **no recovery**. Once the
landmark is occluded or deformed past recognition, a forced match is a
fabricated number; flag it and let `analyze_tracks.py` exclude it.

---

## Stage 7 — Free-running sync correction (temporal interpolation)

cam0 frame $n$ and cam1 frame $n$ were **not captured at the same
instant**. Using the timestamp sidecars: cam0 frame $n$ has time
$t_0(n)$. Find the bracketing cam1 frames $a,b$ around $t_0(n)$ and
linearly interpolate cam1's tracked position:

$$\alpha=\frac{t_0(n)-t_1(a)}{t_1(b)-t_1(a)},\qquad
uv_1^{\text{sync}} = uv_1(a) + \alpha\big(uv_1(b)-uv_1(a)\big)$$

Outside the range it clamps (no extrapolation).

**Why it matters mathematically:** triangulation assumes both rays
image the *same physical point at the same time*. If the leaflet moved
during the inter-camera offset, the rays do not intersect at the true
point — you triangulate a phantom, and the error scales with leaflet
speed × time offset. The tool prints raw offset stats (mean/median/max
ms) so you can show the magnitude being corrected.

---

## Stage 8 — Stereo triangulation (`triangulate_point`)

Given synced $(u_0,v_0)$, $(u_1,v_1)$ and both calibrations:

**1. Undistort.** `cv2.undistortPoints(..., P=K)` numerically inverts
Brown–Conrady and re-projects with $K$, yielding pixels as if from an
ideal pinhole. Required so the next step is **linear**.

**2. Projection matrices** ($3\times4$):

$$P_0 = K_0\,[\,R_0\mid t_0\,],\qquad P_1 = K_1\,[\,R_1\mid t_1\,]$$

**3. Linear (DLT) triangulation.** For homogeneous world point
$\tilde X$, each view gives $\,\tilde m \times (P\tilde X)=0$ → 2
independent linear equations per camera. Stack into

$$A=\begin{bmatrix}
u_0\,P_0^{(3)} - P_0^{(1)}\\
v_0\,P_0^{(3)} - P_0^{(2)}\\
u_1\,P_1^{(3)} - P_1^{(1)}\\
v_1\,P_1^{(3)} - P_1^{(2)}
\end{bmatrix},\qquad A\,\tilde X = 0$$

($P^{(k)}$ = $k$-th row.) Solve by SVD: $\tilde X$ is the right
singular vector of the smallest singular value
(`cv2.triangulatePoints`).

**4. Dehomogenize:**

$$X_{\text{mm}} = \left(\frac{\tilde X_1}{\tilde X_4},\
\frac{\tilde X_2}{\tilde X_4},\ \frac{\tilde X_3}{\tilde X_4}\right)$$

in the calibration-object frame, in mm.

> "DLT minimizes algebraic not geometric error — biased?" Yes in
> general, but with sub-px inputs and a 0.15 mm calibration residual it
> is far below required accuracy, and the Stage 4(a) validation is
> itself an end-to-end test of exactly this triangulation.

---

## Stage 9 — Metric displacement

Origin = the point's anchor-frame 3D position $X^{(0)}$. Per frame:

$$\Delta^{(n)} = X^{(n)} - X^{(0)} = (dx, dy, dz),
\qquad d^{(n)} = \lVert \Delta^{(n)}\rVert_2$$

`displacement_mm` $= d^{(n)}$, written per (frame, point).

---

## Stage 10 — Cycle metrics

Two analyzers depending on the upstream path:

**`analyze_metric.py`** (manual stereo-annotation path, phase-labeled).
A cycle is one full pass `closed → opening → open → closing → closed`.
Per cycle:

- Period: $\big(\tfrac{n_{\text{last}}-n_{\text{first}}}{\text{fps}}\big)
  \times 1000$ ms
- 3D path length: $L=\sum_i \lVert X_{i+1}-X_i\rVert$
- Peak displacement: $\max_i \lVert X_i - X_0\rVert$

Aggregated as mean, std, and **CV = std/mean** across cycles (CV is the
run-quality / reproducibility metric).

**`analyze_tracks.py`** (optical-flow tracker path). Per point, over
healthy frames only: peak displacement, cumulative path length.
Aggregate: mean displacement across points per frame, then **dominant
cycle period via FFT** — zero-mean the signal, real FFT, restrict to a
0.3–5 Hz physiological band, pick the peak bin $f^\*$, period $=1/f^\*$.
(FFT here because the tracker output has no manual phase labels to
walk.)

---

## Accuracy budget (have this ready)

| Source | Magnitude |
|---|---|
| Calibration triangulation residual (noise floor) | median 0.154 mm, max 0.431 mm |
| Reprojection RMS | cam0 3.23 px, cam1 3.63 px |
| NCC sub-pixel localization | ~0.1 px |
| Camera-position vs CAD EPP | 10.8 / 8.2 mm (tolerance 15) |
| Sync residual | reported per-run in ms; corrected by interpolation |

---

## The five most likely questions, one-line answers

1. **"Single image — how can you calibrate?"** Non-coplanar markers
   (cylinder stack, 5 z-depths) make single-view PnP-with-intrinsics
   observable; we fix focal length and principal point (physically
   known) so the underdetermined DOF cannot corrupt extrinsics.
   Validated by 0.15 mm triangulation and an independent CAD-position
   cross-check.
2. **"How do you handle refraction?"** Effective-pinhole: calibrate in
   situ underwater, seed focal length with ×$n$, let intrinsics +
   distortion absorb it. No Snell ray tracing. Separate calibration per
   fluid.
3. **"Doesn't optical flow drift?"** LK is only the search prior; the
   measured position is NCC against a frozen frame-0 template, so error
   never integrates. FB residual gates LK trust; NCC threshold gates
   track health.
4. **"Cameras aren't synced — bias?"** Timestamp-based linear
   interpolation of cam1 pixels onto cam0 frame times before
   triangulation; raw offset reported per run. Hardware GPIO sync
   deferred.
5. **"Why DLT and not bundle / optimal triangulation?"** Sub-px inputs
   and 0.15 mm calibration residual put us well inside required
   accuracy; the calibration validation is itself an end-to-end test of
   this exact triangulation.
