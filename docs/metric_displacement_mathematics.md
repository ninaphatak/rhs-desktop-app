# The Mathematics of Metric Leaflet Displacement

**A self-contained derivation.**

This document derives every mathematical step that turns two raw camera
videos into a per-frame leaflet displacement in millimeters. It assumes
multivariable calculus, linear algebra, least squares, and undergraduate
optics, but **no computer-vision background** — every CV concept
(homogeneous coordinates, epipolar geometry, optical flow, the structure
tensor) is derived here rather than cited.

It supersedes `docs/calibration_to_displacement_walkthrough.md` (the
lighter code-oriented version). It does **not** replace
`docs/backup_slides_math_and_algorithm.md`, which is a hand-built Q&A
deck in Laurence et al. (2022) notation.

Pipeline at a glance:

> two videos of a known calibration object → **camera calibration**
> (recover each camera's lens + pose) → click a leaflet landmark →
> **track it in every frame** (optical-flow-primed template matching) →
> **triangulate** the two 2-D tracks into one 3-D point per frame →
> **displacement** = distance of that point from its starting position
> → **cycle metrics**.

---

## Notation

| Symbol | Meaning |
|---|---|
| $X=(X,Y,Z)^\top$ | a 3-D point, in the calibration-object frame, millimeters |
| $\tilde X=(X,Y,Z,1)^\top$ | the same point in **homogeneous** coordinates (§1.2) |
| $m=(u,v)^\top$ | a pixel location in an image |
| $\tilde m=(u,v,1)^\top$ | that pixel in homogeneous coordinates |
| $R\in SO(3)$ | a $3\times3$ rotation matrix (orthonormal, $\det=+1$) |
| $t\in\mathbb{R}^3$ | a translation vector |
| $r\in\mathbb{R}^3$ | the 3-parameter (axis–angle) form of $R$ (§2.2) |
| $K$ | the $3\times3$ intrinsic (calibration) matrix (§1.3) |
| $f$ | focal length; $f_{\text{mm}}$ in mm, $f$ in pixels |
| $p$ | sensor pixel pitch, $0.00345$ mm/pixel |
| $n$ | refractive index of the working fluid |
| $I(x,y,t)$ | image intensity at pixel $(x,y)$, frame $t$ |
| subscripts $0,1$ | quantities for camera 0 and camera 1 |
| $\lVert\cdot\rVert$ | Euclidean ($\ell_2$) norm |

---

# Part I — The Camera Model

Everything downstream rests on one equation: how a 3-D point in the
world becomes a pixel. We build it in four pieces — rigid motion,
projection, refraction, lens distortion — then assemble the whole.

## 1.1 The pinhole projection (similar triangles)

Idealize a camera as a single point (the optical center $O$) and an
image plane a distance $f$ behind it. Put the origin of a *camera-frame*
coordinate system at $O$, with the $Z$ axis along the optical axis. A
scene point at camera-frame coordinates $(X_c,Y_c,Z_c)$ casts a ray
through $O$; by **similar triangles** the ray crosses the image plane at

$$
x \;=\; f\,\frac{X_c}{Z_c}, \qquad
y \;=\; f\,\frac{Y_c}{Z_c}. \tag{1}
$$

This is the entire geometric content of a camera. The division by $Z_c$
— *perspective division* — is the only nonlinearity, and it is the
reason a single image cannot recover depth (any point along a ray
projects to the same pixel). Stereo (Part IV) exists precisely to undo
this division.

## 1.2 Homogeneous coordinates — why we use them

Equation (1) is nonlinear (a division). Projective ("homogeneous")
coordinates make it *linear*, which is what lets us use linear algebra
(matrix factorization, SVD) for calibration and triangulation.

The device: represent a 2-D point $(x,y)$ by **any** 3-vector
$(sx,\,sy,\,s)^\top$, $s\neq0$; represent a 3-D point $(X,Y,Z)$ by any
4-vector $(sX,sY,sZ,s)^\top$. Two homogeneous vectors that differ only
by a nonzero scalar denote the same geometric point. To read a
homogeneous result back as a real point, **divide by the last
coordinate** (this *is* the perspective division of Eq. 1, deferred to
the end). With this convention Eq. (1) becomes the linear statement

$$
\underbrace{\begin{pmatrix} \lambda x\\ \lambda y\\ \lambda\end{pmatrix}}_{\lambda\,\tilde m}
=
\begin{pmatrix} f&0&0&0\\ 0&f&0&0\\ 0&0&1&0\end{pmatrix}
\begin{pmatrix} X_c\\ Y_c\\ Z_c\\ 1\end{pmatrix},
\qquad \lambda=Z_c. \tag{2}
$$

The unknown scale $\lambda$ is the depth we threw away; recovering it is
exactly triangulation.

## 1.3 Intrinsics: from metric image plane to pixels

Equation (1) gives a position on the image plane in millimeters. A
sensor reports **pixels**. Three things intervene: the pixel pitch $p$
converts mm→pixels ($f = f_{\text{mm}}/p$, dimensionless "pixels"); the
pixel origin is a corner, not the optical axis, so we add the
**principal point** $(c_x,c_y)$ (the pixel where the optical axis pierces
the sensor); and in general the two axes could be non-square or skewed.
Collect these into the **intrinsic matrix**

$$
K=\begin{pmatrix} f_x & \gamma & c_x\\ 0 & f_y & c_y\\ 0 & 0 & 1\end{pmatrix}.
$$

- $f_x,f_y$: focal length in horizontal/vertical pixels. Our sensor has
  square pixels and we enforce $f_x=f_y=f$.
- $\gamma$: axis skew. Physically negligible for a machined sensor; set
  $\gamma=0$.
- $(c_x,c_y)$: principal point. We **fix** it at the image center
  $(w/2,h/2)$ — see §3.4 for the rigorous reason.

So $K$ contributes, in principle, 5 numbers, of which we fit **zero**
(all fixed or constrained). That fact is the backbone of the
single-view argument in §3.

## 1.4 Extrinsics: the world frame → camera frame

Scene points are measured in the **calibration-object frame** (origin at
the center of the object's top face, $+z$ along the flow direction; this
is the frame in which the CAD coordinates and, ultimately, the
displacement live). A point $X$ in that frame relates to its
camera-frame coordinates by a rigid-body transform — a rotation then a
translation:

$$
X_c \;=\; R\,X + t. \tag{3}
$$

$R$ (3 numbers, §2.2) is the camera's orientation; $t$ is built from its
position. The camera's optical center $C$ in world coordinates is the
point that maps to the camera-frame origin, $0=RC+t$, hence

$$
\boxed{\,C=-R^{\top}t\,}\qquad(\text{used in the §4 cross-check}). \tag{4}
$$

(We used $R^{-1}=R^{\top}$, true for any rotation matrix.)

## 1.5 Refraction through the flat acrylic window — *why $f$ scales by $n$*

The camera sits in air; the calibration object and valve sit in water
($n\approx1.333$) or the glycerin blood analog ($n\approx1.385$), behind
a flat acrylic port. Light bends at the flat fluid/air interface. We do
**not** ray-trace this (Snell's law, "Approach B," is deferred). Instead
we show that, to first order, refraction is mathematically equivalent to
**multiplying the focal length by $n$**, and then we calibrate *in situ*
so the fit absorbs the residual.

Derivation (paraxial flat-interface apparent depth). Consider a point at
true perpendicular depth $D$ below a flat interface, fluid index $n$,
observer in air. A ray leaves the point at angle $\theta_2$ to the
normal (in fluid) and refracts to $\theta_1$ in air; Snell's law gives
$n\sin\theta_2=\sin\theta_1$. For a camera viewing a small object near
the optical axis, all angles are small, so $\sin\theta\approx\tan\theta$.
Tracing two nearby rays back into air, they appear to emanate not from
depth $D$ but from the **apparent depth**

$$
D' \;=\; \frac{D}{n}. \tag{5}
$$

(This is the everyday "a pool looks shallower than it is" result; for
$n=1.333$, $D'\approx0.75\,D$.) Now feed the apparent depth into the
projection (Eq. 1). The image size of an object is governed by the
magnification $f/Z$. Replacing the true depth $Z$ by the apparent depth
$Z/n$:

$$
\text{magnification} \;=\; \frac{f}{Z/n} \;=\; \frac{(n f)}{Z}.
$$

So an **effective focal length** $f_{\text{eff}} = n\,f$, used with the
*true* geometric depth $Z$, reproduces exactly what the camera records.
That is the entire justification for seeding

$$
f \;=\; \frac{f_{\text{mm}}}{p}\,n
\;=\;\frac{16\ \text{mm}}{0.00345\ \text{mm/px}}\;n. \tag{6}
$$

**Honest caveat to state aloud.** Eq. (5) is paraxial (first order in
ray angle). Off-axis rays bend more than the linear law predicts; the
flat interface also introduces a mild *radial* aberration. We do not
correct these analytically — instead we calibrate **through the actual
port, underwater, in the final mounting**, and let the distortion
coefficients (§1.6) fitted from real data soak up the residual. This is
the "effective pinhole" assumption, and it is validated empirically in
§4 (0.154 mm median 3-D error). It is also why **each fluid needs its
own calibration**: $n$ differs, so $f_{\text{eff}}$ and the residual
aberration differ.

## 1.6 Lens distortion (Brown–Conrady)

A real lens is not an ideal pinhole. Two physical defects matter:

- **Radial distortion** — a real lens bends rays slightly more or less
  than $f\tan\theta$ the farther they are from the axis (a
  rotationally symmetric effect of spherical lens surfaces). Modeled as
  an even polynomial in radius.
- **Tangential distortion** — the lens elements are not perfectly
  centered/parallel to the sensor (decentering), breaking radial
  symmetry slightly.

Let $(x,y)$ be the *ideal* normalized image coordinates (Eq. 1 with
$f=1$), and $\rho^2=x^2+y^2$. The Brown–Conrady model maps them to the
**distorted** coordinates actually seen:

$$
\begin{aligned}
x_d &= x\,\underbrace{(1+k_1\rho^2+k_2\rho^4+k_3\rho^6)}_{\text{radial}}
      \;+\; \underbrace{2p_1xy + p_2(\rho^2+2x^2)}_{\text{tangential}},\\[4pt]
y_d &= y\,(1+k_1\rho^2+k_2\rho^4+k_3\rho^6)
      \;+\; p_1(\rho^2+2y^2) + 2p_2xy.
\end{aligned}\tag{7}
$$

We keep **$k_1$ (one radial term) and $p_1,p_2$ (tangential)** and force
$k_2=k_3=0$. Reason (made rigorous in §3.4): with a single view there
are too few constraints to identify high-order radial terms separately
from focal length and depth; freeing them lets the optimizer fit
*noise*, which corrupts the camera pose. $k_1,p_1,p_2$ are the
physically dominant, identifiable terms here.

## 1.7 The complete forward model

Composing §1.4 → §1.1 → §1.6 → §1.3, the full projection of a world
point $X$ to a pixel $m$ in camera $c$ is

$$
\boxed{\;
m \;=\; \pi\big(K_c,\,d_c,\,R_c,\,t_c;\,X\big)
\;}\tag{8}
$$

where the function $\pi$ is: (i) $X_c=R_cX+t_c$; (ii) normalize
$x=X_c/Z_c,\;y=Y_c/Z_c$; (iii) distort by Eq. (7) with coefficients
$d_c=(k_1,p_1,p_2)$; (iv) apply $K_c$. Calibration (Part II) is the
problem of finding $(K_c,d_c,R_c,t_c)$; triangulation (Part IV) inverts
$\pi$ jointly over two cameras.

---

# Part II — Camera Calibration

## 2.1 What we are solving and why it is least squares

We have the known 3-D positions $\{X_i\}$ of the painted dots on the
calibration object (from CAD, in mm) and their measured pixel positions
$\{m_i\}$ in one image from each camera. We seek the camera parameters
that best explain the data. "Best" = minimize the total squared
**reprojection error**, the gap between where the model says each dot
should land and where it actually landed:

$$
\boxed{\;
(\hat K,\hat d,\hat R,\hat t)
=\arg\min \sum_{i=1}^{N}
\big\lVert\, m_i-\pi(K,d,R,t;X_i)\,\big\rVert^2
\;}\tag{9}
$$

This is a **nonlinear least-squares** problem (nonlinear because $\pi$
contains the perspective division and the distortion polynomial).
Reported as a single number, the residual is the root-mean-square

$$
\text{RMS}=\sqrt{\tfrac1N\sum_i\lVert m_i-\hat m_i\rVert^2}
\quad(\text{water run: }3.23\text{ px (cam0)},\,3.63\text{ px (cam1)}).
\tag{10}
$$

## 2.2 Why rotation is only 3 numbers (axis–angle / Rodrigues)

A rotation matrix has 9 entries but only **3 degrees of freedom** (it
must satisfy $R^\top R=I$, 6 constraints). We parametrize it minimally
by a vector $r=\theta\,\hat k$ whose direction $\hat k$ is the rotation
axis and whose length $\theta$ is the rotation angle. Rodrigues'
formula reconstructs the matrix:

$$
R=I+\sin\theta\,[\hat k]_\times+(1-\cos\theta)\,[\hat k]_\times^{2},
\qquad
[\hat k]_\times=\begin{pmatrix}0&-\hat k_3&\hat k_2\\ \hat k_3&0&-\hat k_1\\ -\hat k_2&\hat k_1&0\end{pmatrix}.
\tag{11}
$$

This matters for the parameter count in §3.4: each camera's pose is
exactly $3\ (\text{rotation}) + 3\ (\text{translation}) = 6$ unknowns,
not 12.

## 2.3 How the minimization is performed (Levenberg–Marquardt)

Eq. (9) has no closed form. It is solved iteratively. Stack all
parameters into one vector $\beta$ and all residuals into
$\mathbf r(\beta)$ ($\mathbf r_i=m_i-\pi(\cdots)$). Let $J=\partial
\mathbf r/\partial\beta$ be the Jacobian. Two classical updates:

- **Gauss–Newton:** $\;\Delta\beta=-(J^\top J)^{-1}J^\top\mathbf r$ —
  fast near the optimum, unstable far from it.
- **Gradient descent:** $\;\Delta\beta=-\alpha\,J^\top\mathbf r$ —
  robust far away, slow near the optimum.

**Levenberg–Marquardt** interpolates between them with a damping
parameter $\mu\ge0$:

$$
\Delta\beta=-\big(J^\top J+\mu\,\mathrm{diag}(J^\top J)\big)^{-1}J^\top\mathbf r.
\tag{12}
$$

Large $\mu$ → gradient descent (safe); small $\mu$ → Gauss–Newton (fast).
$\mu$ is adapted each iteration: shrink it when a step reduces the error,
grow it when a step fails. The seed (Eq. 6 for $K$, a coarse pose) puts
the optimizer in the basin of the true solution. No probabilistic
content — this is deterministic numerical optimization.

---

# Part III — Why Single-View Calibration Is Legitimate

This is the part bioengineering reviewers will press hardest, because it
departs from the textbook (Zhang's) checkerboard method. The argument is
pure constraint-counting and a degeneracy analysis. Lead with it.

## 3.1 The constraint we cannot use

The standard method waves a planar checkerboard at many orientations.
Our calibration object **cannot move** — it is machined to occupy
exactly the volume the valve leaflets sweep, so it must be fixed in the
final geometry. We get **one image per camera**. Multi-view calibration
is therefore unavailable; we must show single-view suffices.

## 3.2 Degrees of freedom: equations vs unknowns

A fully general projective camera is a $3\times4$ matrix defined up to
scale: $12-1=11$ degrees of freedom. It decomposes (the "$KR\,|\,Rt$"
factorization) into $K$ (5) $+\,R$ (3) $+\,t$ (3) $= 11$. We then remove
unknowns by physics:

| Parameter group | General DOF | Ours | Why fixed |
|---|---|---|---|
| Focal length $f_x,f_y$ | 2 | **0** | known from lens spec × $n$ (Eq. 6) |
| Skew $\gamma$ | 1 | **0** | machined sensor, $\gamma=0$ |
| Principal point $c_x,c_y$ | 2 | **0** | fixed at image center (§3.4) |
| Rotation $R$ | 3 | 3 | unknown pose |
| Translation $t$ | 3 | 3 | unknown pose |
| Distortion $k_1,p_1,p_2$ | — | 3 | the identifiable lens terms |
| **Total free** | | **9** | |

Each visible marker supplies **two** scalar equations (its $u$ and its
$v$). The $19.3°$ camera sees ~31 dots, the $0°$ camera more; the water
calibration used 38 common markers. So we have on the order of
$2\times31\approx62$ to $2\times40\approx80$ equations for **9**
unknowns — a 7-to-9× over-determined system. The least-squares fit (Eq.
9) is well-posed and noise-averaging, not under-constrained.

## 3.3 Why the markers must be non-coplanar (the cylinder stack)

Over-determination alone is not enough; the equations must be
*independent*. If all dots lay in one plane, the point→pixel map would
collapse to a $3\times3$ **homography** (8 DOF) that *cannot be uniquely
factored* into intrinsics and extrinsics from one view — the classic
planar degeneracy. Our object defeats this on purpose: the dots sit at
**five distinct depths** (cylinder rings at $z=-11.76,\,-7.84,\,-3.92$
mm and two top-face rings at $z=0$, plus the center point). A 3-D
(non-coplanar) point set forces the full projective camera and makes
$(R,t)$ observable. This is *the* design reason the calibration target
is a stepped cylinder stack and not a printed flat pattern.

## 3.4 Why we still must fix $f$ and $(c_x,c_y)$ — the focal–depth ambiguity

Even non-coplanar, a single view has a near-degeneracy. For an object
spanning a small depth range about a mean distance $Z_0$, the projection
of Eq. (1) is $\approx f X/Z_0$. Scale focal length and the whole scene
distance together,

$$
(f,\;Z)\;\longmapsto\;(\alpha f,\;\alpha Z),
$$

and every predicted pixel $f X/Z$ is **unchanged**. A single camera
therefore cannot separate "long lens, far object" from "short lens,
near object" — focal length and overall depth/scale trade off almost
exactly. The depth spread of §3.3 only *weakly* breaks this (it pins
relative depths, not the global scale). If $f$ is left free it absorbs
this ambiguity by drifting, dragging $t$ (hence the camera position)
with it; reprojection still looks excellent while the recovered geometry
is wrong. We eliminate the ambiguity by **fixing $f$** to the
independently known optical value (Eq. 6) and **fixing the principal
point** at the image center (it is otherwise strongly correlated with
$t_x,t_y$). The high-order radial terms $k_2,k_3$ are zeroed for the
same reason — they mimic a focal-length change over the radius and would
re-introduce the ambiguity through the back door.

The take-away sentence for the room: *low reprojection error proves the
model fits the pixels; it does not prove the recovered camera pose is
physical. We pin the unobservable parameters to known optics so the
fit's freedom goes only into the genuinely unknown pose.*

---

# Part IV — Stereo Triangulation

## 4.1 The geometry: two rays, one point

Inverting one camera (§1.1) is impossible — perspective division lost
the depth. With **two** cameras whose calibrations are known, each
observed pixel back-projects to a 3-D *ray*; the scene point is where
the two rays meet. With real (noisy) data the rays are *skew* (do not
exactly intersect), so "meet" becomes a least-squares problem.

## 4.2 Removing distortion first

Triangulation is linear only for an ideal pinhole. So we first
**undistort**: numerically invert Eq. (7) to recover the ideal
$(x,y)$ from the measured $(x_d,y_d)$, then re-apply $K$ so the points
are expressed as if they came from a perfect pinhole with matrix $K$.
After this step each camera obeys the clean linear law

$$
\lambda_c\,\tilde m_c \;=\; P_c\,\tilde X,
\qquad
P_c \;=\; K_c\,[\,R_c \mid t_c\,]\ \ (3\times4). \tag{13}
$$

$P_c$ is the **projection matrix** of camera $c$ (its full forward model
as one matrix); $\lambda_c$ is the unknown depth.

## 4.3 The Direct Linear Transform (eliminating the unknown depths)

We want one equation in $\tilde X$ with $\lambda_c$ removed. Use the
fact that a vector crossed with a parallel vector is zero. From Eq.
(13), $P_c\tilde X=\lambda_c\tilde m_c$ is parallel to $\tilde m_c$, so

$$
\tilde m_c \times \big(P_c\,\tilde X\big)=0. \tag{14}
$$

Writing $\tilde m_c=(u_c,v_c,1)^\top$ and letting $P_c^{(k)}$ be the
$k$-th **row** of $P_c$, the cross product (14) expands to three scalar
equations, of which only **two are independent** (the three rows of a
cross-product matrix always have rank 2):

$$
\begin{aligned}
u_c\,\big(P_c^{(3)}\tilde X\big)-\big(P_c^{(1)}\tilde X\big)&=0,\\
v_c\,\big(P_c^{(3)}\tilde X\big)-\big(P_c^{(2)}\tilde X\big)&=0.
\end{aligned}\tag{15}
$$

Each camera contributes two such equations. Stacking both cameras:

$$
A\,\tilde X=0,\qquad
A=\begin{pmatrix}
u_0P_0^{(3)}-P_0^{(1)}\\
v_0P_0^{(3)}-P_0^{(2)}\\
u_1P_1^{(3)}-P_1^{(1)}\\
v_1P_1^{(3)}-P_1^{(2)}
\end{pmatrix}\in\mathbb{R}^{4\times4}. \tag{16}
$$

## 4.4 Solving $A\tilde X=0$ by SVD

With noise, $A$ has no exact nontrivial null vector, so we seek the
$\tilde X$ that comes closest, subject to a nondegeneracy constraint:

$$
\min_{\tilde X}\ \lVert A\,\tilde X\rVert^2
\quad\text{subject to}\quad \lVert\tilde X\rVert=1. \tag{17}
$$

By the **Rayleigh-quotient / singular value decomposition** theorem the
minimizer is the right singular vector of $A$ associated with its
smallest singular value. Take the SVD $A=U\Sigma V^\top$; $\tilde X$ is
the last column of $V$.

## 4.5 From homogeneous back to millimeters

$\tilde X=(\tilde X_1,\tilde X_2,\tilde X_3,\tilde X_4)^\top$ is defined
only up to scale; recover the physical point by the perspective division
deferred since §1.2:

$$
X=\Big(\tfrac{\tilde X_1}{\tilde X_4},\ \tfrac{\tilde X_2}{\tilde X_4},
\ \tfrac{\tilde X_3}{\tilde X_4}\Big)\ \text{mm}. \tag{18}
$$

Because the calibration $X_i$ were in millimeters in the
calibration-object frame, $X$ is automatically in **millimeters in that
same frame** — the metric output is a consequence of the calibration's
units, with no extra scale factor.

## 4.6 Algebraic vs geometric error — the honest footnote

Eq. (17) minimizes an *algebraic* residual $\lVert A\tilde X\rVert$, not
the *geometric* reprojection error one would get from re-imaging $X$.
The statistically optimal estimator (Hartley–Sturm "optimal
triangulation") minimizes the latter. We use the algebraic (DLT)
solution because (i) the inputs are sub-pixel and the geometry is wide
(a $0°$/$19.3°$ baseline), and (ii) the §4 calibration validation —
median $0.154$ mm, max $0.431$ mm over 38 markers — is itself an
end-to-end measurement of this exact triangulation on ground truth, so
the algebraic-vs-geometric gap is demonstrably far below the required
accuracy.

## 4.7 Calibration validation, restated as the two checks

1. **3-D residual.** Triangulate every common marker and compare to CAD:
   $e_i=\lVert\hat X_i-X_i^{\text{CAD}}\rVert$; require median $<5$ mm.
   This is the **noise floor of the entire pipeline** — every later
   number is at best this good.
2. **Camera-position cross-check.** From Eq. (4), $C=-R^\top t$.
   Independently, the lens datasheet predicts the entrance pupil (the
   optical point that *is* the projection center — the image of the
   aperture stop) at a fixed offset $10.68$ mm along the optical axis
   from the lens front face. Require $\lVert C-C_{\text{CAD}}\rVert<15$
   mm (mounting tolerance + residual refraction). Got $10.80$ / $8.19$
   mm; recovered tilt $18.30°$ vs CAD $19.33°$. **This check, not the
   reprojection RMS, is what proves the pose is physical** (§3.4).

---

# Part V — Tracking the Landmark in Every Frame

Triangulation needs the *same physical landmark's* pixel coordinates in
both cameras, in every frame. A human clicks it once (the **anchor
frame**, typically a fully closed valve). The math below finds it
automatically thereafter.

> **Stated precisely (do not let this be misheard):** optical flow is
> used **only as a per-frame search prior**. The position actually
> reported each frame is the peak of a normalized cross-correlation
> against the **frozen anchor-frame template**. The reason for this
> architecture is a drift argument (§5.4) that is itself mathematical.

## 5.1 Optical flow and the brightness-constancy equation

Assume a small image patch keeps its brightness as it moves:
$I(x,y,t)=I(x+\delta x,\,y+\delta y,\,t+\delta t)$. First-order Taylor
expansion and dividing by $\delta t$ gives the **optical flow
constraint equation**

$$
I_x\,u + I_y\,v + I_t \;=\; 0, \tag{19}
$$

where $(I_x,I_y)=\nabla I$ are spatial gradients, $I_t$ the temporal
gradient, and $(u,v)$ the unknown pixel velocity. Equation (19) is
**one scalar equation in two unknowns** — the **aperture problem**:
from a single pixel you can only recover the motion component along the
gradient (perpendicular to an edge); motion *along* an edge is
invisible. This is a fundamental obstruction, not an implementation
detail, and it dictates everything that follows.

## 5.2 Lucas–Kanade: resolve the aperture problem by a local window

Assume the flow $(u,v)$ is **constant over a small window $W$** around
the point. Then every pixel in $W$ gives one copy of Eq. (19); with many
pixels we have an over-determined linear system, solved by least
squares:

$$
\min_{(u,v)}\sum_{(x,y)\in W}\big(I_x u+I_y v+I_t\big)^2.
$$

Setting the gradient to zero gives the normal equations

$$
\underbrace{\begin{pmatrix}
\sum I_x^2 & \sum I_xI_y\\[2pt]
\sum I_xI_y & \sum I_y^2
\end{pmatrix}}_{\displaystyle G\ \text{(structure tensor)}}
\begin{pmatrix}u\\ v\end{pmatrix}
=-\begin{pmatrix}\sum I_xI_t\\[2pt]\sum I_yI_t\end{pmatrix}. \tag{20}
$$

$G=\sum_W\nabla I\,\nabla I^\top$ is the $2\times2$ **structure tensor**
(second-moment matrix). Its eigenvalues $\lambda_1\ge\lambda_2\ge0$
classify the local texture:

- $\lambda_1,\lambda_2$ both large → a **corner**: $G$ well-conditioned,
  $(u,v)$ uniquely recoverable.
- $\lambda_1\gg\lambda_2\approx0$ → an **edge**: $G$ singular, only the
  across-edge component is recoverable (the aperture problem in matrix
  form).
- both $\approx0$ → a **flat, textureless patch**: no information.

A minimum-eigenvalue threshold rejects ill-conditioned ($\lambda_2$ too
small) cases rather than returning a fabricated velocity. Large motions
violate the Taylor linearization, so the solve is done **coarse-to-fine
on an image pyramid** (downsampled copies): the displacement in pixels
halves at each coarser level until the linearization is valid, and the
estimate is refined back up to full resolution.

## 5.3 Forward–backward consistency (a self-check on the flow)

The flow is run **forward** (anchor→current frame), giving a predicted
point, then **backward** (current→previous). If the tracking is honest,
the round trip returns to the start; the discrepancy

$$
\varepsilon \;=\; \big\lVert\, p_{\text{prev}}-p_{\text{round-trip}}\,\big\rVert
\tag{21}
$$

is the **forward–backward error**. Small $\varepsilon$ ⇒ trust the flow
and search a small neighborhood; large $\varepsilon$ ⇒ distrust it,
revert to the previous position and search a large neighborhood (fast
or non-smooth motion, e.g. the leaflet snapping open). $\varepsilon$
gates *how far* we search, not the final answer.

## 5.4 Why the answer is template matching, not the flow — a drift argument

Naively, one could chain the flow frame to frame: $p_n=p_{n-1}+$ (flow
increment). Model each increment's error as a zero-mean random
perturbation $\eta_k$ with variance $\sigma^2$. Then

$$
p_N=p_0+\sum_{k=1}^{N}(\text{true step}+\eta_k)
\;\Rightarrow\;
\operatorname{Var}(p_N)=\sum_{k=1}^N\sigma^2=N\sigma^2.
$$

The positional uncertainty grows like $\sqrt{N}$ **without bound** — the
estimate *drifts*. (On this valve it does worse than drift: the leaflets
are low-texture white silicone with edge-like, deforming features, so
$G$ is near-singular and the per-step error is biased, not merely
noisy.) Cure: every frame, match against a **template extracted once
from the anchor frame and never updated**. Then each frame's error is
independent of the previous frame's:

$$
\operatorname{Var}(p_n)=\sigma^2 \quad\text{(constant in }n\text{)}.
$$

Bounded, not accumulating. The flow (§5.2) only chooses *where to
search*; the measurement is the template match (§5.5). This is the
single most important architectural decision in the tracker and the
justification is exactly the variance comparison above.

## 5.5 Normalized cross-correlation, and why it beats illumination changes

Let the fixed anchor template be the vector $T$ and a candidate patch at
shift $s$ be $S_s$ (pixels stacked into vectors). Define mean-subtracted
$\tilde T=T-\bar T$, $\tilde S_s=S_s-\bar S_s$. The **normalized
cross-correlation** score is

$$
\rho(s)=\frac{\tilde T\cdot\tilde S_s}
{\lVert\tilde T\rVert\,\lVert\tilde S_s\rVert}
=\cos\angle(\tilde T,\tilde S_s)\in[-1,1]. \tag{22}
$$

It is precisely the **Pearson correlation coefficient** between template
and patch — the cosine of the angle between the two mean-subtracted
intensity vectors. The reported landmark position is

$$
s^\star=\arg\max_s \rho(s).
$$

Crucially, $\rho$ is **invariant to any affine intensity change**
$S\mapsto aS+b$ with $a>0$: subtracting the mean kills the additive term
$b$ (brightness/bias), and dividing by the norm kills the multiplicative
term $a$ (contrast/gain). That is the formal reason this is robust to
the uneven, time-varying underwater lighting — a property pure flow
(which assumes brightness *constancy*, Eq. 19) does not have.

## 5.6 Sub-pixel localization by parabolic interpolation

$s^\star$ from §5.5 is integer-valued. Refine it by fitting a parabola
$q(\delta)=A\delta^2+B\delta+C$ through the three correlation scores at
the peak and its two neighbors, $\rho_{-1},\rho_{0},\rho_{+1}$ (done
independently along each image axis). Solving for the coefficients and
setting $q'(\delta)=0$ gives the vertex

$$
\delta^\star=-\frac{B}{2A}
=\frac12\cdot\frac{\rho_{-1}-\rho_{+1}}
{\rho_{-1}-2\rho_{0}+\rho_{+1}}, \tag{23}
$$

clamped to $[-\tfrac12,\tfrac12]$. The denominator is (twice) the
discrete second derivative — negative at a genuine peak, which is also
why a degenerate (flat) peak is rejected. This yields ≈0.1-pixel
localization without resampling the image.

## 5.7 Track-health gate

If the best correlation $\rho(s^\star)$ falls below a threshold
($\approx0.7$) in *either* camera, the landmark no longer resembles its
anchor appearance (occlusion, extreme deformation). The track is
declared **lost from that frame onward** and excluded from analysis. The
principle is statistical honesty: a forced match below the similarity
threshold is a fabricated coordinate; reporting "no data" is correct,
reporting a confident wrong displacement is not.

---

# Part VI — Temporal Synchronization

The two cameras free-run; they are **not** hardware-triggered, so
"frame $n$" of camera 0 and "frame $n$" of camera 1 are taken at
slightly different *times*. Each frame carries a hardware timestamp.

## 6.1 Why misalignment biases the 3-D point

Triangulation (Part IV) assumes both rays image the **same point at the
same instant**. Suppose the true landmark moves with velocity $V$ and
camera 1 lags camera 0 by $\Delta t$. Camera 0 images the point at
position $X$; camera 1 images it at $X+V\Delta t$. The two rays now
correspond to *different* physical points and intersect at a **phantom**
location whose error is, to first order,

$$
\lVert \text{bias}\rVert \;\approx\; \lVert V\rVert\,\Delta t
\quad(\text{the component not absorbed by the stereo geometry}).
$$

For a fast leaflet this is not negligible — it scales linearly with
leaflet speed.

## 6.2 The correction: linear interpolation in time

Let camera 0's frame $n$ occur at time $t_0(n)$. Bracket that instant by
camera 1's two nearest frames $a,b$ (times $t_1(a)\le t_0(n)\le
t_1(b)$). Linearly interpolate camera 1's tracked pixel position to the
common instant:

$$
\alpha=\frac{t_0(n)-t_1(a)}{t_1(b)-t_1(a)},\qquad
m_1^{\text{sync}} = m_1(a)+\alpha\big(m_1(b)-m_1(a)\big). \tag{24}
$$

(No extrapolation: instants outside the recorded range are clamped to
the nearest endpoint.) This reduces the timing error from first order
$O(\lVert V\rVert\,\Delta t)$ to the second-order interpolation residual
$O(\tfrac12\lVert a\rVert\,\Delta t^2)$, where $a$ is the landmark's
acceleration — i.e. the only remaining error is due to *curvature* of
the trajectory within one inter-frame interval, which is small. Hardware
GPIO sync would remove it entirely and is the eventual fix; this is the
deferred-but-quantified workaround.

---

# Part VII — Displacement and Cycle Metrics

## 7.1 Per-frame metric displacement

Triangulating the synced pixel pairs (Part IV) gives a 3-D position
$X^{(n)}$ for each frame $n$. Fix the **origin** as the anchor-frame
position $X^{(0)}$. The displacement vector and its magnitude are

$$
\Delta^{(n)}=X^{(n)}-X^{(0)}=(dx,dy,dz),\qquad
d^{(n)}=\big\lVert\Delta^{(n)}\big\rVert. \tag{25}
$$

Note a correctness subtlety worth stating: the **magnitude** $d^{(n)}$
is invariant to the choice of coordinate frame (a norm is unchanged by
rotation), so the headline displacement number does not depend on how
the calibration-object axes were drawn; only the **components**
$(dx,dy,dz)$ are frame-dependent.

## 7.2 Path length (and its sampling-rate caveat)

The 3-D distance the landmark travels over a cardiac cycle is
approximated by summing straight-line segments between consecutive
samples:

$$
L=\sum_{i}\big\lVert X^{(i+1)}-X^{(i)}\big\rVert
\;\le\;\int\big\lVert\dot X(t)\big\rVert\,dt
\;=\;\text{(true arc length)}. \tag{26}
$$

The inequality is exact and always in the same direction: a polygonal
(chord) approximation **systematically under-estimates** a curved path.
The bias is $O(\kappa^2\,\Delta s^2)$ in the local curvature $\kappa$
and the inter-sample spacing $\Delta s$, so it shrinks as frame rate
increases. State this honestly — it is the one place the metric has a
known sign of bias.

## 7.3 Peak displacement and reproducibility (CV)

Per cycle: peak excursion $d_{\max}=\max_i\lVert
X^{(i)}-X^{(0)}\rVert$, and period from the frame indices of the cycle
endpoints divided by frame rate. Across cycles, reproducibility is
summarized by the **coefficient of variation**

$$
\mathrm{CV}=\frac{\sigma}{\mu}, \tag{27}
$$

the dimensionless ratio of cycle-to-cycle standard deviation to mean. CV
(not the raw std) is used because it is scale-free and therefore
comparable across runs, fluids, and metrics — it is the run-quality
number for the simulator.

## 7.4 Cycle period by Fourier analysis (auto-tracked path)

When phase labels are not hand-annotated, the dominant cycle frequency
is read from the **discrete Fourier transform** of the mean-displacement
signal $x_n$ ($N$ samples at frame rate $f_s$):

$$
\hat x_k=\sum_{n=0}^{N-1}x_n\,e^{-2\pi i k n/N},\qquad
f_k=\frac{k}{N}\,f_s. \tag{28}
$$

The signal is mean-subtracted first (removes the DC bin), restricted to
the physiological band $0.3$–$5$ Hz (rejects slow drift and
high-frequency noise), and the period is $1/f_{k^\star}$ at the
largest-magnitude bin $k^\star$. The frequency resolution is
$\Delta f=f_s/N$ (longer recordings resolve the period more finely), and
the highest representable frequency is the Nyquist limit $f_s/2$; both
are worth stating if asked about the method's limits.

---

# Part VIII — End-to-End Error Budget

Why the depth direction is the hardest, in one formula. For an idealized
parallel stereo pair with baseline $B$, focal length $f$, and disparity
$d$, depth is $Z=fB/d$. Differentiating,

$$
\frac{\partial Z}{\partial d}=-\frac{fB}{d^2}=-\frac{Z^2}{fB}
\;\Longrightarrow\;
\sigma_Z\approx\frac{Z^2}{f\,B}\,\sigma_d. \tag{29}
$$

Depth uncertainty grows **quadratically with range** and **inversely
with baseline and focal length** — the standard reason stereo systems
want a wide baseline, a long lens, and a close target. Our geometry is
*converged* ($0°$ and $19.3°$), not parallel, so Eq. (29) is the
intuition rather than the exact expression, but the scaling explains the
design and the residual structure. Crucially, we do not have to
propagate Eq. (29) by hand: the §4.7 validation triangulates known CAD
points through the *actual* calibrated geometry and reports the true
end-to-end 3-D error directly.

| Error source | Magnitude | Folded into |
|---|---|---|
| Calibration 3-D residual (pipeline noise floor) | median **0.154 mm**, max 0.431 mm | every downstream number |
| Reprojection RMS | 3.23 px (cam0), 3.63 px (cam1) | the 0.154 mm above |
| Sub-pixel NCC localization | ≈ 0.1 px | the 0.154 mm above |
| Camera position vs CAD entrance pupil | 10.8 / 8.2 mm (tol. 15) | pose-physicality check |
| Inter-camera timing | reported per run (ms) | reduced to $O(\tfrac12 a\,\Delta t^2)$ by Eq. (24) |
| Path-length chord bias | $O(\kappa^2\Delta s^2)$, signed (under-estimate) | Eq. (26) |

---

# Appendix — The Five Questions, With the Equation That Answers Each

1. **"One image — how is that a valid calibration?"** Constraint count
   (§3.2): ~62–80 equations for 9 free unknowns, made independent by
   non-coplanar markers (§3.3, Eq. degeneracy), with $f$ and $(c_x,c_y)$
   fixed to kill the focal–depth ambiguity (§3.4). Validated by Eq. (9)
   residual *and* the independent pose check $C=-R^\top t$ (Eq. 4).
2. **"How is refraction handled without ray tracing?"** Eqs. (5)–(6):
   flat-interface apparent depth $D'=D/n$ ⇒ effective focal length
   $nf$; residual aberration absorbed by in-situ distortion fit (Eq. 7);
   per-fluid recalibration because $n$ differs.
3. **"Doesn't optical-flow tracking drift?"** §5.4: chained flow has
   $\operatorname{Var}\propto N$ (unbounded); anchored template
   matching (Eq. 22) has constant variance. Flow only sets the search
   window via the forward–backward error (Eq. 21).
4. **"The cameras aren't synchronized — bias?"** §6.1 quantifies the
   bias as $\lVert V\rVert\Delta t$; Eq. (24) interpolates it away to
   second order $O(\tfrac12 a\,\Delta t^2)$.
5. **"Why the linear (DLT) triangulation rather than the optimal
   estimator?"** §4.6: algebraic vs geometric error gap is provably
   below tolerance because the Eq. (9)/§4.7 validation measures the true
   end-to-end 3-D error (0.154 mm) on ground truth.

---

## References (APA 7th edition)

- Bradski, G. (2000). The OpenCV library. *Dr. Dobb's Journal of Software Tools, 25*(11), 120–125.
- Brown, D. C. (1971). Close-range camera calibration. *Photogrammetric Engineering, 37*(8), 855–866.
- Bouguet, J.-Y. (2001). *Pyramidal implementation of the affine Lucas–Kanade feature tracker: Description of the algorithm.* Intel Corporation, Microprocessor Research Labs.
- Conrady, A. E. (1919). Decentred lens-systems. *Monthly Notices of the Royal Astronomical Society, 79*(5), 384–390. https://doi.org/10.1093/mnras/79.5.384
- Hartley, R., & Zisserman, A. (2004). *Multiple view geometry in computer vision* (2nd ed.). Cambridge University Press. https://doi.org/10.1017/CBO9780511811685
- Hartley, R. I., & Sturm, P. (1997). Triangulation. *Computer Vision and Image Understanding, 68*(2), 146–157. https://doi.org/10.1006/cviu.1997.0547
- Kalal, Z., Mikolajczyk, K., & Matas, J. (2010). Forward-backward error: Automatic detection of tracking failures. In *Proceedings of the 20th International Conference on Pattern Recognition (ICPR)* (pp. 2756–2759). IEEE. https://doi.org/10.1109/ICPR.2010.675
- Lewis, J. P. (1995). Fast normalized cross-correlation. In *Vision Interface* (Vol. 10, pp. 120–123). Canadian Image Processing and Pattern Recognition Society.
- Lucas, B. D., & Kanade, T. (1981). An iterative image registration technique with an application to stereo vision. In *Proceedings of the 7th International Joint Conference on Artificial Intelligence (IJCAI)* (Vol. 2, pp. 674–679). Morgan Kaufmann.
- Shi, J., & Tomasi, C. (1994). Good features to track. In *Proceedings of IEEE Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 593–600). IEEE. https://doi.org/10.1109/CVPR.1994.323794
- Zhang, Z. (2000). A flexible new technique for camera calibration. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 22*(11), 1330–1334. https://doi.org/10.1109/34.888718
- Laurence, D. W., Ross, C. J., Hsu, M.-C., Mir, A., Burkhart, H. M., Holzapfel, G. A., & Lee, C.-H. (2022). Benchtop characterization of the tricuspid valve leaflet pre-strains. *Acta Biomaterialia, 152*, 321–334. https://doi.org/10.1016/j.actbio.2022.08.046

> ⚠️ The eleven method/implementation citations are reliable. For
> **Laurence et al. (2022)**, author list / year / title / journal are
> reliable, but **verify the volume, pages, and DOI against your own PDF
> copy** before presenting — those locator details should not be
> presented unchecked.

| Stage | Primary reference(s) |
|---|---|
| Pinhole + single-view calibration (Parts I–III) | Zhang (2000) |
| Lens distortion model (§1.6) | Brown (1971); Conrady (1919) |
| Lucas–Kanade flow + pyramid (§5.1–5.2) | Lucas & Kanade (1981); Bouguet (2001) |
| Structure-tensor / min-eigenvalue gate (§5.2) | Shi & Tomasi (1994) |
| Forward–backward error (§5.3) | Kalal et al. (2010) |
| Normalized cross-correlation (§5.5) | Lewis (1995) |
| DLT triangulation / SVD (Part IV) | Hartley & Zisserman (2004); Hartley & Sturm (1997) |
| Numerical implementation throughout | Bradski (2000) |
| Domain framing / notation | Laurence et al. (2022) |
