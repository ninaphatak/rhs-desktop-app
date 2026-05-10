"""Dual-camera dense optical flow explorer in metric (mm) units.

Side-by-side display of cam0 and cam1 with directional flow overlays.
Each pane shows its frame tinted by flow direction (hue) and magnitude
(opacity), with magnitude expressed in millimetres of in-plane motion
per frame.

Direction-to-color anchors (image-space compass; "north" = up on screen,
applied independently per camera):
  - Red    -> flow heading north (up)
  - Yellow -> flow heading 30 deg counter-clockwise from east (ENE)
  - Cyan   -> flow heading east (right)
  Other directions interpolate linearly between adjacent anchors around
  the full circle (red wraps back to cyan the long way for the
  south-west arc).

Opacity-to-magnitude:
  - At |flow| <= --threshold mm/frame the overlay is fully transparent.
  - Above threshold opacity grows linearly to a cap at --max-mag mm/frame.
  - At |flow| >= --max-mag the overlay reaches its peak alpha (0.85), so
    anatomy stays faintly visible even where motion is fastest.

Pixel-flow magnitudes are converted to mm using a per-pixel scale field
derived once at startup from the stereo calibration. Each camera's
pixel ray is back-projected onto the z=0 plane of the calibration-object
frame (= the valve plane), and the local mm-per-pixel is the average
distance moved on that plane when stepping +1 px in u or v.

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

# BGR anchor colors (OpenCV channel order).
COLOR_CYAN   = np.array([255, 255,   0], dtype=np.float32)  # east, theta = 0 deg
COLOR_YELLOW = np.array([  0, 255, 255], dtype=np.float32)  # 30 deg CCW of east
COLOR_RED    = np.array([  0,   0, 255], dtype=np.float32)  # north, theta = 90 deg


def _build_direction_lut() -> np.ndarray:
    """360-entry BGR LUT mapping flow angle (degrees) to anchor color.

    Anchors (math convention, 0 deg = +x = east, 90 deg = +y_inverted = north):
        0   -> cyan
        30  -> yellow
        90  -> red
        90..360 -> red interpolated back to cyan the long way around

    Returns float32 array of shape (360, 3).
    """
    lut = np.zeros((360, 3), dtype=np.float32)
    for theta in range(360):
        if theta < 30:
            t = theta / 30.0
            lut[theta] = (1 - t) * COLOR_CYAN + t * COLOR_YELLOW
        elif theta < 90:
            t = (theta - 30) / 60.0
            lut[theta] = (1 - t) * COLOR_YELLOW + t * COLOR_RED
        else:
            t = (theta - 90) / 270.0
            lut[theta] = (1 - t) * COLOR_RED + t * COLOR_CYAN
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


def compute_mm_per_px_field(
    K: np.ndarray,
    dist: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    image_size_wh: tuple[int, int],
) -> np.ndarray:
    """Per-pixel mm/px scale, evaluated on the z=0 plane of the object frame.

    For each pixel (u, v) we back-project the undistorted ray into the
    calibration-object coordinate frame, intersect it with the z=0 plane
    (the valve plane), and take the average of the two displacements
    incurred by stepping +1 px in u and +1 px in v on that plane.

    Pixels whose rays do not hit the z=0 plane in front of the camera
    (parallel rays or back-facing geometry) are assigned scale 0 so they
    drop below threshold during overlay rendering.

    Returns a (H, W) float32 array of mm-per-pixel values.
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

    P_base = P[:H, :W]
    P_u1 = P[:H, 1:W + 1]
    P_v1 = P[1:H + 1, :W]

    du = np.linalg.norm(P_u1 - P_base, axis=2)
    dv = np.linalg.norm(P_v1 - P_base, axis=2)
    scale = 0.5 * (du + dv)

    valid_cell = V[:H, :W] & V[:H, 1:W + 1] & V[1:H + 1, :W]
    scale = np.where(valid_cell, scale, 0.0)
    return scale.astype(np.float32)


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
    mm_per_px: np.ndarray,
    threshold_mm: float,
    max_mag_mm: float,
) -> np.ndarray:
    """Tint `frame` by flow direction (hue) and metric magnitude (opacity).

    `flow` is the raw per-frame pixel displacement field from Farneback;
    `mm_per_px` is the precomputed scale field for this camera. Pixels
    with |flow| (in mm/frame) below threshold stay untinted. Above
    threshold, opacity grows linearly to PEAK_ALPHA at max_mag_mm.
    """
    fx = flow[..., 0]
    fy = flow[..., 1]
    mag_px = np.sqrt(fx * fx + fy * fy)
    mag_mm = mag_px * mm_per_px

    # Image-space compass: y grows downward, so negate fy before atan2 so that
    # an upward flow vector (negative dy) gets theta = +90 deg = north.
    theta_deg = np.degrees(np.arctan2(-fy, fx)) % 360.0
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


def draw_direction_legend(img: np.ndarray) -> None:
    """Draw the three anchor arrows in the bottom-left corner of `img`.

    Arrow geometry matches the direction-color mapping:
      - Red    -> straight up    (north,  theta = 90 deg)
      - Yellow -> up-and-right   (theta = 30 deg, 30 deg CCW of east)
      - Cyan   -> straight right (east,   theta =  0 deg)

    All three share an origin so the user can read the angles directly off
    the legend. Drawn with a black outline so it stays legible against any
    background.
    """
    h = img.shape[0]
    arrow_len = 45
    margin_x = 60
    margin_y = 60
    cx, cy = margin_x, h - margin_y

    anchors = [
        (0.0,  COLOR_CYAN),    # east
        (30.0, COLOR_YELLOW),  # 30 deg CCW of east
        (90.0, COLOR_RED),     # north
    ]
    for theta_deg, color in anchors:
        theta = np.deg2rad(theta_deg)
        tip = (
            int(round(cx + arrow_len * np.cos(theta))),
            int(round(cy - arrow_len * np.sin(theta))),  # negate: image y grows down
        )
        # Black outline first, then the colored arrow on top.
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

    print("Computing per-pixel mm/px scale fields (one-time)...")
    scale0 = compute_mm_per_px_field(
        calib["cam0"]["K"], calib["cam0"]["dist"],
        calib["cam0"]["rvec"], calib["cam0"]["tvec"], image_size,
    )
    scale1 = compute_mm_per_px_field(
        calib["cam1"]["K"], calib["cam1"]["dist"],
        calib["cam1"]["rvec"], calib["cam1"]["tvec"], image_size,
    )
    print(
        f"  cam0 mm/px: median={np.median(scale0[scale0 > 0]):.5f}  "
        f"min={scale0[scale0 > 0].min():.5f}  max={scale0.max():.5f}"
    )
    print(
        f"  cam1 mm/px: median={np.median(scale1[scale1 > 0]):.5f}  "
        f"min={scale1[scale1 > 0].min():.5f}  max={scale1.max():.5f}"
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
                curr0, flow0, scale0, args.threshold, args.max_mag,
            )
            overlay1 = render_directional_overlay(
                curr1, flow1, scale1, args.threshold, args.max_mag,
            )

            draw_overlay(overlay0, "cam0", frame_num, total_frames, args.threshold, args.max_mag)
            draw_overlay(overlay1, "cam1", frame_num, total_frames, args.threshold, args.max_mag)
            draw_direction_legend(overlay0)
            draw_direction_legend(overlay1)

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
