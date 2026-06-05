# Backup Slides — Stereo Calibration / Triangulation Math + Tracking Algorithm

Hidden Q&A slides. Notation follows Laurence et al. (2022),
*Benchtop characterization of the tricuspid valve leaflet pre-strains*
(Appendix A): pixel coordinates `(p, q)`, world coordinates
`(x, y, z)`, camera subscripts `c ∈ {1, 2}`, marker superscript `I`.

Source-of-truth code:
- `tools/stereo_calibrate.py`, `tools/triangulate.py` (math)
- `tools/track_intersections.py` (algorithm)

---

## SLIDE 1 — Stereo calibration & triangulation: equations

**Pinhole projection (per camera `c`, per 3D point `(x, y, z)` in
calibration-object coordinates):**

$$
\begin{aligned}
\begin{bmatrix} x_c \\ y_c \\ z_c \end{bmatrix} &= R_c \begin{bmatrix} x \\ y \\ z \end{bmatrix} + t_c
\qquad
(x'_c,\; y'_c) = \left(\tfrac{x_c}{z_c},\; \tfrac{y_c}{z_c}\right) \\[4pt]
r^2 &= x'_c{}^2 + y'_c{}^2 \\
x''_c &= x'_c\,(1 + k_{1,c}\, r^2) + 2 p_{1,c}\,x'_c y'_c + p_{2,c}\,(r^2 + 2 x'_c{}^2) \\
y''_c &= y'_c\,(1 + k_{1,c}\, r^2) + p_{1,c}\,(r^2 + 2 y'_c{}^2) + 2 p_{2,c}\,x'_c y'_c \\[4pt]
p_c &= f_c\, x''_c + c_{x,c}, \qquad q_c = f_c\, y''_c + c_{y,c}
\end{aligned}
$$

**Calibration objective** — for `N ≥ 6` non-coplanar markers per
camera, minimize total reprojection error (analog of Laurence A.2):

$$
\min_{\,K_c,\; \mathbf{d}_c,\; R_c,\; t_c}\;
\sum_{I=1}^{N}
\left\lVert
\begin{bmatrix} p_c^{\,I} \\ q_c^{\,I} \end{bmatrix}_{\text{observed}}
-
\begin{bmatrix} p_c^{\,I} \\ q_c^{\,I} \end{bmatrix}_{\text{projected}}
\right\rVert_2^{\,2}
$$

**Triangulation** — given matched pixels `(p_1^I, q_1^I)`,
`(p_2^I, q_2^I)` and projection matrices `P_c = K_c [R_c \mid t_c]`,
solve for `(x^I, y^I, z^I)` from the linear system (analog of A.3):

$$
\begin{bmatrix}
p_1^{\,I}\,P_{1,3}^\top - P_{1,1}^\top \\
q_1^{\,I}\,P_{1,3}^\top - P_{1,2}^\top \\
p_2^{\,I}\,P_{2,3}^\top - P_{2,1}^\top \\
q_2^{\,I}\,P_{2,3}^\top - P_{2,2}^\top
\end{bmatrix}
\begin{bmatrix} x^I \\ y^I \\ z^I \\ 1 \end{bmatrix} = \mathbf{0}
\qquad (\text{SVD, smallest-singular-value solution})
$$

**Variables**

| Symbol | Meaning |
|---|---|
| `(x, y, z)` | 3D point in calibration-object frame (mm) |
| `(p_c, q_c)` | pixel coordinates in camera `c ∈ {1, 2}` |
| `R_c, t_c` | rotation (3×3) and translation (3×1), object → camera |
| `K_c = diag(f_c, f_c, 1) + c_c` | intrinsic matrix; `f_c` focal length (px), `(c_{x,c}, c_{y,c})` principal point |
| `\mathbf{d}_c = (k_{1,c}, p_{1,c}, p_{2,c})` | distortion: 1 radial + 2 tangential |
| `P_c = K_c [R_c \mid t_c]` | 3×4 projection matrix |
| `P_{c,j}^\top` | `j`-th row of `P_c` (`j = 1, 2, 3`) |
| `N` | number of CAD-known markers (41 painted dots) |
| `I` | marker index (`I = 1, …, N`) |

**Why fixed `f_c` and `(c_{x,c}, c_{y,c})`:** single-view non-coplanar
calibration is under-determined if all intrinsics are free. We set
`f_c = (16\text{ mm} / 0.00345\text{ mm·px}^{-1}) \cdot n_{\text{fluid}}`
(lens spec × refractive index of working fluid, `n_{\text{water}} =
1.333`, `n_{\text{analog}} = 1.385`) and `(c_{x,c}, c_{y,c}) =`
image center. Only `\mathbf{d}_c` (3 params) and `(R_c, t_c)` (6 params)
are free per camera.

**Why effective pinhole, not Snell ray tracing:** calibration is done
underwater in the final mounting, so the fitted `(K_c, \mathbf{d}_c)`
absorbs the fixed acrylic + fluid refraction. Validated on water:
median 3D triangulation residual **0.154 mm**, max **0.431 mm** over
38 markers (cf. Laurence 0.24 mm).

---

## SLIDE 2 — Calibration & triangulation procedure (separate slide)

1. **Record** a single dual-camera frame of the CAD calibration object
   submerged in the working fluid (`tools/record_calibration.py`).
2. **Detect** dark dots per camera: threshold + morphological opening
   + `SimpleBlobDetector` → blob centroids `(p_c^I, q_c^I)`.
3. **Assign** marker IDs `I` to detected blobs by manual click
   (resumable via `--load` / `--edit`).
4. **Solve** per camera via `cv2.calibrateCamera` with the constraints
   above → `(K_c, \mathbf{d}_c, R_c, t_c)`.
5. **Validate** against three independent checks:
   - reprojection RMS per camera (water: 3.23 px, 3.63 px),
   - 3D residual vs CAD per marker (water: median 0.154 mm),
   - recovered camera optical center vs CAD entrance-pupil position
     (water: 10.80 mm / 8.19 mm discrepancy, tolerance 15 mm).
6. **Save** to `outputs/calib/stereo_calib_<fluid>.json`. One JSON per fluid.
7. **Per recording**, annotate a landmark in both cameras every frame,
   align cam2 to cam1 frame times by linear interpolation on
   `grabResult.GetTimeStamp()`, then triangulate
   (`cv2.triangulatePoints`) → `(x^I, y^I, z^I)(t)` in mm.

---

## SLIDE 3 — Tracking algorithm (formal notation)

**Algorithm 1: Hybrid Lucas-Kanade + Frame-0 NCC Anchor Tracker**

```
Input:  dual-camera video frames {F_c^t}, c ∈ {1, 2}, t = 0, …, T−1
        seed pixel (p_c^0, q_c^0) per camera, clicked at t = 0
        patch size w, search radii r_LK, r_FB
        thresholds τ_FB (px), τ_NCC (corr.)
Output: per-frame (p_c^t, q_c^t) for t = 1, …, T−1 and healthy^t

# Initialize the frame-0 anchor template (never updated)
1.  for c ∈ {1, 2}:
2.     T_c ← w × w patch of F_c^0 centered at (p_c^0, q_c^0)

# Track each frame
3.  for t = 1, …, T−1:
4.     for c ∈ {1, 2}:
           # (a) Lucas-Kanade as search prior, with FB consistency check
5.         (p̂, q̂) ← LK_forward (F_c^{t−1}, F_c^t,  (p_c^{t−1}, q_c^{t−1}))
6.         (p̌, q̌) ← LK_backward(F_c^t,    F_c^{t−1}, (p̂, q̂))
7.         ε_FB ← ‖(p̌, q̌) − (p_c^{t−1}, q_c^{t−1})‖_2

8.         if ε_FB ≤ τ_FB:
9.            (p̄, q̄) ← (p̂, q̂);          r ← r_LK
10.        else:
11.           (p̄, q̄) ← (p_c^{t−1}, q_c^{t−1}); r ← r_FB

           # (b) NCC search against frame-0 anchor (the actual decision)
12.        S ← (2r + 1) × (2r + 1) NCC map of F_c^t vs T_c, centered at (p̄, q̄)
              with NCC(u, v) =
                Σ (F_c^t(u, v) − F̄)(T_c − T̄)
                ─────────────────────────────────────────
                √( Σ(F_c^t − F̄)² · Σ(T_c − T̄)² )
13.        (u*, v*) ← argmax_{(u,v) ∈ S}  NCC(u, v)
14.        ρ_c     ← NCC(u*, v*)
15.        (Δu, Δv) ← parabolic_subpixel(S, (u*, v*))      # |·| ≤ 0.5 px
16.        (p_c^t, q_c^t) ← (u* + Δu, v* + Δv)

       # (c) Health gate — lose loudly, never recover silently
17.    if ρ_1 < τ_NCC or ρ_2 < τ_NCC:
18.       healthy^t ← False;       (p_c^{t'}, q_c^{t'}) ← (p_c^t, q_c^t) for all t' > t
19.       break
20.    else:
21.       healthy^t ← True

22. return  { (p_c^t, q_c^t, healthy^t) }_{t, c}
```

**Variables**

| Symbol | Meaning |
|---|---|
| `F_c^t` | grayscale frame at time `t` from camera `c` |
| `T_c` | frame-0 anchor template, `w × w` (never updated) |
| `(p_c^t, q_c^t)` | tracked pixel position |
| `ε_FB` | LK forward–backward residual (px) |
| `r_LK, r_FB` | NCC search half-widths when LK is trusted / not (5 px / 15 px) |
| `τ_FB` | FB residual threshold for trusting LK (1.0 px) |
| `τ_NCC` | NCC peak threshold for "still on target" (0.7) |
| `ρ_c` | peak NCC score for camera `c` this frame |
| `(Δu, Δv)` | sub-pixel offset from parabolic fit on NCC peak |

**Why hybrid:** Pure LK (`tools/leaflet_flow_test.py`) drifts because
patches deform with the leaflet and LK has no global reference. Pure
template-update NCC drifts for the same reason — any per-frame error
gets baked into the next template. Anchoring to `T_c = T_c(t=0)` is
**drift-free by construction**: at worst `ρ_c` collapses below `τ_NCC`
and the track is honestly marked lost.

**Settings** (`tools/track_intersections.py`): LK pyramid `maxLevel=3`,
`winSize=21×21`, `w = 21`, `τ_FB = 1.0` px, `τ_NCC = 0.7`,
`r_LK = 5` px, `r_FB = 15` px. NCC computed via
`cv2.matchTemplate(TM_CCOEFF_NORMED)`.

---

## SLIDE 4 — Tracking procedure (separate slide)

1. **Calibrate** stereo per fluid (Slide 2) → `stereo_calib_<fluid>.json`.
2. **Pick seeds** at a clean reference frame (e.g. fully closed valve)
   with `tools/pick_track_seeds.py`: click the same landmark in cam1
   and cam2 → `<recording>.track_seeds.json`. The anchor frame becomes `t = 0`.
3. **Track** with `tools/track_intersections.py`: runs Algorithm 1 per
   point per camera over all frames, writes
   `<recording>.tracks.csv` (one row per frame × point: `p_c^t, q_c^t`,
   `ε_FB`, `ρ_c`, `healthy^t`).
4. **Temporal align** cam2 to cam1 frame times by linear interpolation
   on `grabResult.GetTimeStamp()` (free-running cameras).
5. **Triangulate** each tracked point per frame (Slide 1 equation set)
   → `(x^I, y^I, z^I)(t)` in mm.
6. **Displacement**: `d^I(t) = ‖(x^I, y^I, z^I)(t) − (x^I, y^I, z^I)(0)‖_2`.
7. **Filter** on `healthy^t = True` in downstream analysis
   (`tools/analyze_tracks.py`); never trust silent drift.

---

## Cheat-sheet numbers (hide behind everything)

- Pinhole + 3-param distortion (`k_1, p_1, p_2`); `f_c, c_x, c_y` fixed.
- Underwater focal length: `f_c = (16\,\text{mm} / 0.00345\,\text{mm·px}^{-1}) \cdot n_{\text{fluid}}`.
- Water calibration: RMS 3.23 / 3.63 px; 3D residual median 0.154 mm, max 0.431 mm; EPP discrepancy 10.80 / 8.19 mm; tilt 18.30° vs CAD 19.33°.
- Tracker: `w = 21`, `τ_FB = 1.0` px, `τ_NCC = 0.7`, LK pyramid 3 levels.
