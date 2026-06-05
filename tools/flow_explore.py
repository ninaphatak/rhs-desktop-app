"""Dual-camera dense optical flow explorer in metric (mm) units.

Side-by-side display of cam0 and cam1 with directional flow overlays.
Each pane shows its frame tinted by flow direction (object-frame axis
color) and magnitude (opacity), with magnitude expressed in millimetres
of in-plane motion per frame.

Direction-to-color anchors (calibration-object frame; same physical
direction maps to the same color in BOTH cameras):
  - Red     -> motion along +x of the calibration object frame
  - Green   -> motion along +y
  - Cyan    -> motion along -x
  - Magenta -> motion along -y
  Other directions interpolate linearly between adjacent anchors around
  the full circle.

Motion along +/- z is invisible by construction: pixel flow from a
single camera is projected onto the z=0 plane of the object frame to
recover metric units, which collapses any out-of-plane component.

Opacity-to-magnitude:
  - At |flow| <= --threshold mm/frame the overlay is fully transparent.
  - Above threshold opacity grows linearly to a cap at --max-mag mm/frame.
  - At |flow| >= --max-mag the overlay reaches its peak alpha (0.85), so
    anatomy stays faintly visible even where motion is fastest.

Per-pixel object-frame Jacobian (precomputed once per camera at startup):
each camera's pixel ray is back-projected onto the z=0 plane of the
calibration-object frame. The 2x2 Jacobian at each pixel maps image-space
flow (du, dv) directly to object-frame in-plane displacement (dx, dy)
in mm. Per frame we apply the Jacobian, then read magnitude and angle
in the object frame.

Pairing is naive frame-N matching across both videos. This is a
visualization tool; precise temporal sync correction lives in
tools/triangulate.py.

Usage:
    python tools/flow_explore.py VIDEO_CAM0 VIDEO_CAM1 --calib CALIB_JSON
    python tools/flow_explore.py V0 V1 --calib outputs/calib/stereo_calib_water.json --threshold 1.5
    python tools/flow_explore.py V0 V1 --calib C.json --max-mag 5.0
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._flow_params import FARNEBACK_PARAMS


DEFAULT_THRESHOLD_MM = 1.0   # minimum 1 mm/frame motion to register on overlay
DEFAULT_MAX_MAG_MM = 3.0     # mm/frame at which overlay opacity saturates
DEFAULT_CONTRAST = 1.25      # gain applied around mid-gray (128) before Farneback
PEAK_ALPHA = 0.85            # max blend weight on the colored overlay

# BGR anchor colors (OpenCV channel order), tied to object-frame xy axes.
COLOR_RED     = np.array([  0,   0, 255], dtype=np.float32)  # +x, theta =   0 deg
COLOR_GREEN   = np.array([  0, 255,   0], dtype=np.float32)  # +y, theta =  90 deg
COLOR_CYAN    = np.array([255, 255,   0], dtype=np.float32)  # -x, theta = 180 deg
COLOR_MAGENTA = np.array([255,   0, 255], dtype=np.float32)  # -y, theta = 270 deg


def _build_direction_lut() -> np.ndarray:
    """360-entry BGR LUT mapping object-frame xy angle to axis-color.

    Anchors: 0 deg -> +x (red), 90 deg -> +y (green), 180 deg -> -x (cyan),
    270 deg -> -y (magenta), wrapping back to red at 360. Linear blend
    between consecutive anchors.

    Returns float32 array of shape (360, 3).
    """
    lut = np.zeros((360, 3), dtype=np.float32)
    anchors = [
        (0,   COLOR_RED),
        (90,  COLOR_GREEN),
        (180, COLOR_CYAN),
        (270, COLOR_MAGENTA),
        (360, COLOR_RED),
    ]
    for i in range(len(anchors) - 1):
        a_deg, a_color = anchors[i]
        b_deg, b_color = anchors[i + 1]
        span = b_deg - a_deg
        for theta in range(a_deg, b_deg):
            t = (theta - a_deg) / span
            lut[theta] = (1 - t) * a_color + t * b_color
    return lut


DIRECTION_LUT = _build_direction_lut()


def load_calibration(path: Path) -> dict:
    """Load the JSON written by tools/stereo_calibrate.py.

    Returns a dict with key 'image_size_wh' plus 'cam0' and 'cam1', each
    holding K, dist, rvec, tvec as float64 numpy arrays.
    """
    d = json.loads(path.read_text())
    out: dict = {"image_size_wh": tuple(d["image_size_wh"])}
    for cam in ("cam0", "cam1"):
        out[cam] = {
            "K": np.array(d[cam]["K"], dtype=np.float64),
            "dist": np.array(d[cam]["dist"], dtype=np.float64),
            "rvec": np.array(d[cam]["rvec"], dtype=np.float64),
            "tvec": np.array(d[cam]["tvec"], dtype=np.float64),
        }
    return out


def compute_pixel_jacobian(
    K: np.ndarray,
    dist: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    image_size_wh: tuple[int, int],
) -> np.ndarray:
    """Per-pixel Jacobian mapping image-flow (du, dv) to object-frame (dx, dy).

    For each pixel (u, v) we back-project the undistorted ray into the
    calibration-object coordinate frame, intersect with the z=0 plane (the
    valve plane), and finite-difference the back-projection in u and v to
    get the columns of the Jacobian. Applying this 2x2 matrix to a
    pixel-flow vector yields the in-plane object-frame displacement in mm.

    Pixels whose rays do not hit the z=0 plane in front of the camera
    (parallel rays or back-facing geometry) get a zero Jacobian so they
    fall below the magnitude threshold during overlay rendering.

    Returns a (H, W, 2, 2) float32 array. J[v, u, :, 0] is the object-xy
    displacement per +1 px in u; J[v, u, :, 1] is per +1 px in v.
    """
    W, H = image_size_wh

    # Sample at every integer pixel plus an extra row+col to take diffs.
    us, vs = np.meshgrid(np.arange(W + 1), np.arange(H + 1))
    grid = np.stack([us.ravel(), vs.ravel()], axis=-1).astype(np.float32)

    # Undistort to normalized camera coords (z=1 plane in camera frame).
    und = cv2.undistortPoints(grid.reshape(-1, 1, 2), K, dist).reshape(-1, 2)
    d_cam = np.concatenate([und, np.ones((und.shape[0], 1), dtype=und.dtype)], axis=1)

    # Pose stored as object -> camera: p_cam = R @ p_obj + t.
    R, _ = cv2.Rodrigues(rvec)
    Rt = R.T
    C_obj = (-Rt @ tvec.reshape(3, 1)).ravel()       # camera origin in object frame
    D_obj = (Rt @ d_cam.T).T                         # ray directions in object frame

    # Intersect with z=0 plane: C_obj.z + lambda * D_obj.z = 0
    with np.errstate(divide="ignore", invalid="ignore"):
        lam = -C_obj[2] / D_obj[:, 2]
    P_obj = C_obj.reshape(1, 3) + lam[:, None] * D_obj
    valid = np.isfinite(lam) & (lam > 0)

    P = P_obj.reshape(H + 1, W + 1, 3)
    V = valid.reshape(H + 1, W + 1)

    P_base = P[:H, :W, :2]            # only xy components (z is 0 by construction)
    P_u1   = P[:H, 1:W + 1, :2]
    P_v1   = P[1:H + 1, :W, :2]

    e_u = P_u1 - P_base               # (H, W, 2): obj-xy displacement per +1 px in u
    e_v = P_v1 - P_base               # (H, W, 2): obj-xy displacement per +1 px in v

    # Stack into J such that J @ (du, dv) = du * e_u + dv * e_v  (in obj xy).
    J = np.stack([e_u, e_v], axis=-1)  # (H, W, 2, 2)

    valid_cell = V[:H, :W] & V[:H, 1:W + 1] & V[1:H + 1, :W]
    J = np.where(valid_cell[..., None, None], J, 0.0)
    return J.astype(np.float32)


def project_axis_screen_directions(
    K: np.ndarray,
    dist: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Screen-space unit vectors for object-frame +x and +y at the origin.

    Projects the object-frame origin and a 10 mm offset along +x and +y
    onto the image plane via cv2.projectPoints, then normalises the
    pixel-space difference vectors. Used to draw a per-camera axis legend
    that points in the actual on-screen direction of each axis.
    """
    delta = 10.0  # mm; far enough to swamp pixel quantisation but still in-plane
    points = np.array([
        [0.0,  0.0,  0.0],
        [delta, 0.0, 0.0],
        [0.0,  delta, 0.0],
    ], dtype=np.float64).reshape(-1, 1, 3)

    img_pts, _ = cv2.projectPoints(points, rvec, tvec, K, dist)
    img_pts = img_pts.reshape(-1, 2)

    p0 = img_pts[0]
    vx = img_pts[1] - p0
    vy = img_pts[2] - p0
    vx = vx / (np.linalg.norm(vx) + 1e-9)
    vy = vy / (np.linalg.norm(vy) + 1e-9)
    return vx, vy


def apply_contrast(gray: np.ndarray, factor: float) -> np.ndarray:
    """Linearly scale grayscale pixel values around 128 by `factor`.

    factor=1.0 is a no-op; factor=1.25 stretches the dynamic range by 25%.
    Result is clipped to [0, 255] and returned as uint8.
    """
    if factor == 1.0:
        return gray
    out = (gray.astype(np.float32) - 128.0) * factor + 128.0
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def render_directional_overlay(
    frame: np.ndarray,
    flow: np.ndarray,
    jacobian: np.ndarray,
    threshold_mm: float,
    max_mag_mm: float,
) -> np.ndarray:
    """Tint `frame` by object-frame flow direction and metric magnitude.

    `flow` is the raw per-frame pixel displacement field from Farneback;
    `jacobian` is the precomputed (H, W, 2, 2) per-pixel map from image
    flow to object-frame xy displacement. Pixels with |flow| (in mm/frame)
    below threshold stay untinted. Above threshold, opacity grows linearly
    to PEAK_ALPHA at max_mag_mm.
    """
    fu = flow[..., 0]
    fv = flow[..., 1]

    # Apply per-pixel Jacobian: (dx_obj, dy_obj) = J @ (du, dv).
    dx_obj = jacobian[..., 0, 0] * fu + jacobian[..., 0, 1] * fv
    dy_obj = jacobian[..., 1, 0] * fu + jacobian[..., 1, 1] * fv
    mag_mm = np.sqrt(dx_obj * dx_obj + dy_obj * dy_obj)

    # Object-frame angle: 0 deg = +x, 90 deg = +y, etc.
    theta_deg = np.degrees(np.arctan2(dy_obj, dx_obj)) % 360.0
    theta_idx = theta_deg.astype(np.int32) % 360
    color = DIRECTION_LUT[theta_idx]

    above = mag_mm >= threshold_mm
    span = max(max_mag_mm - threshold_mm, 1e-6)
    alpha = np.clip((mag_mm - threshold_mm) / span, 0.0, 1.0) * PEAK_ALPHA
    alpha = np.where(above, alpha, 0.0).astype(np.float32)
    alpha3 = alpha[..., None]

    out = frame.astype(np.float32) * (1.0 - alpha3) + color * alpha3
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def draw_overlay(
    img: np.ndarray,
    label: str,
    frame_num: int,
    total_frames: int,
    threshold_mm: float,
    max_mag_mm: float,
) -> None:
    """Camera label, frame counter, and threshold readout in top-left."""
    cv2.putText(
        img, label, (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
    )
    cv2.putText(
        img, f"Frame {frame_num}/{total_frames}", (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
    )
    cv2.putText(
        img, f"thr={threshold_mm:.2f}  max={max_mag_mm:.2f} mm/frame", (10, 90),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )


def draw_axis_legend(
    img: np.ndarray,
    axis_x_screen: np.ndarray,
    axis_y_screen: np.ndarray,
) -> None:
    """Draw object-frame +x/+y/-x/-y arrows in the bottom-left corner.

    Arrow directions are the screen-space projections of the object-frame
    axes for THIS camera, so the legend reflects how each axis appears
    from the current viewpoint. Colors match the direction LUT:
      - Red     -> +x
      - Green   -> +y
      - Cyan    -> -x
      - Magenta -> -y

    All four share an origin and are drawn with a black outline so the
    legend stays legible against any background.
    """
    h = img.shape[0]
    arrow_len = 45
    margin_x = 60
    margin_y = 60
    cx, cy = margin_x, h - margin_y

    anchors = [
        ( axis_x_screen, COLOR_RED),
        ( axis_y_screen, COLOR_GREEN),
        (-axis_x_screen, COLOR_CYAN),
        (-axis_y_screen, COLOR_MAGENTA),
    ]
    for direction, color in anchors:
        # direction is already in image pixel coords (y grows down), no negation.
        tip = (
            int(round(cx + arrow_len * float(direction[0]))),
            int(round(cy + arrow_len * float(direction[1]))),
        )
        cv2.arrowedLine(img, (cx, cy), tip, (0, 0, 0), 4, tipLength=0.3)
        cv2.arrowedLine(img, (cx, cy), tip, tuple(int(c) for c in color), 2, tipLength=0.3)


def open_video(path: Path) -> cv2.VideoCapture:
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"Cannot open video: {path}")
        sys.exit(1)
    return cap


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video_cam0", type=Path, help="Path to cam0 recording")
    parser.add_argument("video_cam1", type=Path, help="Path to cam1 recording")
    parser.add_argument(
        "--calib", type=Path, required=True,
        help="Path to stereo calibration JSON from tools/stereo_calibrate.py",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD_MM,
        help=f"Motion magnitude threshold in mm/frame (default {DEFAULT_THRESHOLD_MM})",
    )
    parser.add_argument(
        "--max-mag", type=float, default=DEFAULT_MAX_MAG_MM,
        help=(
            "Magnitude at which overlay opacity saturates, in mm/frame "
            f"(default {DEFAULT_MAX_MAG_MM})"
        ),
    )
    parser.add_argument(
        "--contrast", type=float, default=DEFAULT_CONTRAST,
        help=(
            "Contrast gain applied around mid-gray (128) on the grayscale "
            "frames before Farneback. 1.0 = no change, 1.25 = +25%% stretch "
            f"(default {DEFAULT_CONTRAST})"
        ),
    )
    args = parser.parse_args()

    if args.max_mag <= args.threshold:
        print(f"--max-mag ({args.max_mag}) must exceed --threshold ({args.threshold})")
        sys.exit(1)

    if not args.calib.exists():
        print(f"Calibration not found: {args.calib}")
        sys.exit(1)

    print(f"Loading calibration from {args.calib}")
    calib = load_calibration(args.calib)
    image_size = calib["image_size_wh"]
    print(f"  calibration image size: {image_size[0]}x{image_size[1]}")

    cap0 = open_video(args.video_cam0)
    cap1 = open_video(args.video_cam1)

    w0 = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    h0 = int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    h1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (w0, h0) != image_size or (w1, h1) != image_size:
        print(
            f"Video frame size mismatch: cam0={w0}x{h0}, cam1={w1}x{h1}, "
            f"calibration={image_size[0]}x{image_size[1]}"
        )
        sys.exit(1)

    print("Computing per-pixel object-frame Jacobians (one-time)...")
    jac0 = compute_pixel_jacobian(
        calib["cam0"]["K"], calib["cam0"]["dist"],
        calib["cam0"]["rvec"], calib["cam0"]["tvec"], image_size,
    )
    jac1 = compute_pixel_jacobian(
        calib["cam1"]["K"], calib["cam1"]["dist"],
        calib["cam1"]["rvec"], calib["cam1"]["tvec"], image_size,
    )
    # Diagnostic mm/px scale: sqrt of |det(J)| approximates mm-per-px area scale.
    for name, J in (("cam0", jac0), ("cam1", jac1)):
        det = np.abs(J[..., 0, 0] * J[..., 1, 1] - J[..., 0, 1] * J[..., 1, 0])
        scale = np.sqrt(det)
        valid = scale > 0
        if valid.any():
            print(
                f"  {name} mm/px (sqrt|det J|): median={np.median(scale[valid]):.5f}  "
                f"min={scale[valid].min():.5f}  max={scale.max():.5f}"
            )

    axes_screen0 = project_axis_screen_directions(
        calib["cam0"]["K"], calib["cam0"]["dist"],
        calib["cam0"]["rvec"], calib["cam0"]["tvec"],
    )
    axes_screen1 = project_axis_screen_directions(
        calib["cam1"]["K"], calib["cam1"]["dist"],
        calib["cam1"]["rvec"], calib["cam1"]["tvec"],
    )

    total_frames = min(
        int(cap0.get(cv2.CAP_PROP_FRAME_COUNT)),
        int(cap1.get(cv2.CAP_PROP_FRAME_COUNT)),
    )

    ret0, prev0 = cap0.read()
    ret1, prev1 = cap1.read()
    if not (ret0 and ret1):
        print("Cannot read first frames from one or both videos")
        sys.exit(1)

    prev_gray0 = apply_contrast(cv2.cvtColor(prev0, cv2.COLOR_BGR2GRAY), args.contrast)
    prev_gray1 = apply_contrast(cv2.cvtColor(prev1, cv2.COLOR_BGR2GRAY), args.contrast)

    frame_num = 1
    paused = False

    print(
        f"Controls: SPACE=play/pause  RIGHT=step  q=quit  "
        f"(threshold={args.threshold} max={args.max_mag} mm/frame  "
        f"contrast={args.contrast})"
    )

    while True:
        advance = False
        if not paused:
            advance = True
        else:
            key = cv2.waitKey(0) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = False
                continue
            elif key == 83 or key == ord('d'):  # RIGHT ARROW
                advance = True

        if advance:
            ret0, curr0 = cap0.read()
            ret1, curr1 = cap1.read()
            if not (ret0 and ret1):
                print(f"End of video at frame {frame_num}")
                paused = True
                continue

            curr_gray0 = apply_contrast(
                cv2.cvtColor(curr0, cv2.COLOR_BGR2GRAY), args.contrast,
            )
            curr_gray1 = apply_contrast(
                cv2.cvtColor(curr1, cv2.COLOR_BGR2GRAY), args.contrast,
            )

            flow0 = cv2.calcOpticalFlowFarneback(
                prev_gray0, curr_gray0, None, **FARNEBACK_PARAMS,
            )
            flow1 = cv2.calcOpticalFlowFarneback(
                prev_gray1, curr_gray1, None, **FARNEBACK_PARAMS,
            )

            overlay0 = render_directional_overlay(
                curr0, flow0, jac0, args.threshold, args.max_mag,
            )
            overlay1 = render_directional_overlay(
                curr1, flow1, jac1, args.threshold, args.max_mag,
            )

            draw_overlay(overlay0, "cam0", frame_num, total_frames, args.threshold, args.max_mag)
            draw_overlay(overlay1, "cam1", frame_num, total_frames, args.threshold, args.max_mag)
            draw_axis_legend(overlay0, axes_screen0[0], axes_screen0[1])
            draw_axis_legend(overlay1, axes_screen1[0], axes_screen1[1])

            combined = np.hstack([overlay0, overlay1])
            cv2.imshow("Dense Optical Flow Explorer (metric)", combined)

            prev_gray0 = curr_gray0
            prev_gray1 = curr_gray1
            frame_num += 1

        if not paused:
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = True

    cap0.release()
    cap1.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
