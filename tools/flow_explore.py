"""Dual-camera 3D-displacement explorer via dense stereo + optical flow.

For each pane (one stereo pipeline per camera as "left"), we:
  1. Stereo-rectify both cameras using the saved calibration.
  2. Run cv2.StereoSGBM each frame to get a dense disparity, then
     cv2.reprojectImageTo3D for a per-pixel 3D position field in the
     rectified-left camera frame.
  3. Compute Farneback flow on the rectified-left grayscale.
  4. For each pixel: 3D position at t, bilinearly sample 3D position at
     t+1 using the flowed coordinate, subtract -> 3D displacement vector
     (in rectified-left frame).
  5. Rotate that vector into the calibration-object frame so the same
     physical world direction maps to the same color in both panes.
  6. Color by "normal-map" convention so a unit vector aligned with an
     object-frame axis shows as a vivid axis color:
        +x -> light red       -x -> dark teal
        +y -> light green     -y -> dark purple
        +z -> light blue      -z -> dark olive
     Specifically BGR = 255 * 0.5 * (unit_displacement_obj + 1), with the
     channels mapped (B,G,R) <- (z,y,x).

Opacity-to-magnitude:
  - At ||displacement|| <= --threshold mm/frame the overlay is fully
    transparent.
  - Above threshold opacity grows linearly to a cap at --max-mag mm/frame.
  - At ||displacement|| >= --max-mag the overlay reaches PEAK_ALPHA
    (0.85), so anatomy stays faintly visible.

Rectified view: each pane shows the rectified left frame for that
pipeline (cam0 in pane A, cam1 in pane B). Rectification is a
homography that aligns epipolar lines horizontally; with our ~73 mm
baseline and 19 deg tilt the warp is visible but not destructive.

Performance: SGBM at full 1920x1200 with the disparity range our
baseline implies (~2000 px) is impractical. We pass a smaller
newImageSize to cv2.stereoRectify (default 960x600) so the rectified
focal length and disparity range scale down too. Use --rect-width /
--rect-height / --num-disp to adjust.

Quality caveat: stereo matching needs texture, just like Farneback
does. The leaflet interior is textureless, so SGBM will hallucinate
disparity there via its smoothness prior (same failure mode the
CLAUDE.md doc warns about for dense flow on the leaflet surface).
Edges, the orifice boundary, and surrounding anatomy should be
reasonable.

Usage:
    python tools/flow_explore.py VIDEO_CAM0 VIDEO_CAM1 --calib CALIB_JSON
    python tools/flow_explore.py V0 V1 --calib outputs/calib/stereo_calib_water.json
    python tools/flow_explore.py V0 V1 --calib C.json --downsample 2 --rect-focal 1500
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._flow_params import FARNEBACK_PARAMS


DEFAULT_THRESHOLD_MM = 1.0
DEFAULT_MAX_MAG_MM = 3.0
DEFAULT_CONTRAST = 1.25
PEAK_ALPHA = 0.85

DEFAULT_DOWNSAMPLE = 4
DEFAULT_RECT_FOCAL = 800.0     # rectified focal in px; chosen so max disparity fits in image width
# At downsample=4 the working size is 480x300. With our 73 mm baseline
# and rect_focal=800, the disparity window 160..415 px brackets depths
# of roughly 141..456 mm (the cam-to-valve distance is ~210-220 mm, so
# this is comfortable). Startup print shows the actual depth range
# covered; tune via --rect-focal / --min-disp / --num-disp.
DEFAULT_NUM_DISPARITIES = 256  # must be multiple of 16
DEFAULT_MIN_DISPARITY = 160
DEFAULT_BLOCK_SIZE = 5

# Axis swatch colors (BGR) shown in the legend; correspond to the
# normal-map convention BGR <- (z, y, x) at unit ±axis.
LEGEND_SWATCHES = [
    ("+x",  (128, 128, 255)),  # light red
    ("-x",  (128, 128,   0)),  # dark teal
    ("+y",  (128, 255, 128)),  # light green
    ("-y",  (128,   0, 128)),  # dark purple
    ("+z",  (255, 128, 128)),  # light blue
    ("-z",  (  0, 128, 128)),  # dark olive
]


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


def relative_pose(R_left: np.ndarray, t_left: np.ndarray,
                  R_right: np.ndarray, t_right: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pose of right camera in left camera's frame.

    Given p_camL = R_left @ p_obj + t_left and p_camR = R_right @ p_obj + t_right,
    returns (R_rel, T_rel) such that p_camR = R_rel @ p_camL + T_rel.
    """
    R_rel = R_right @ R_left.T
    T_rel = t_right - R_rel @ t_left
    return R_rel, T_rel


def apply_contrast(gray: np.ndarray, factor: float) -> np.ndarray:
    """Linearly scale grayscale pixel values around 128 by `factor`."""
    if factor == 1.0:
        return gray
    out = (gray.astype(np.float32) - 128.0) * factor + 128.0
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def bilinear_sample_xyz(xyz: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Bilinear sample of an (H, W, 3) field at fractional coords (xs, ys).

    Out-of-bounds samples are returned as NaN. NaN values in xyz
    propagate to outputs. Used to look up the 3D position at the flowed
    pixel coordinate.
    """
    H, W, _ = xyz.shape
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1

    in_bounds = (x0 >= 0) & (y0 >= 0) & (x1 < W) & (y1 < H)
    x0c = np.clip(x0, 0, W - 1)
    y0c = np.clip(y0, 0, H - 1)
    x1c = np.clip(x1, 0, W - 1)
    y1c = np.clip(y1, 0, H - 1)

    wx = (xs - x0).astype(np.float32)
    wy = (ys - y0).astype(np.float32)

    p00 = xyz[y0c, x0c]
    p10 = xyz[y0c, x1c]
    p01 = xyz[y1c, x0c]
    p11 = xyz[y1c, x1c]

    out = (
        p00 * ((1 - wx) * (1 - wy))[..., None] +
        p10 * (wx * (1 - wy))[..., None] +
        p01 * ((1 - wx) * wy)[..., None] +
        p11 * (wx * wy)[..., None]
    )
    out[~in_bounds] = np.nan
    return out


class StereoPipeline:
    """One stereo pipeline: rectify, disparity, 3D, flow, displacement.

    Construct with the calibration of "left" and "right" cameras (in the
    sense of stereoRectify). Per-frame .step() returns the rectified
    left frame and the per-pixel 3D displacement in the calibration
    object frame.
    """

    def __init__(
        self,
        K_left: np.ndarray, dist_left: np.ndarray,
        R_left: np.ndarray, t_left: np.ndarray,
        K_right: np.ndarray, dist_right: np.ndarray,
        R_right: np.ndarray, t_right: np.ndarray,
        image_size_wh: tuple[int, int],
        rect_size_wh: tuple[int, int],
        min_disparity: int,
        num_disparities: int,
        block_size: int,
        rect_focal: float,
    ) -> None:
        self.rect_size_wh = rect_size_wh

        R_rel, T_rel = relative_pose(R_left, t_left, R_right, t_right)
        baseline = float(np.linalg.norm(T_rel))

        # We use stereoRectify only for the rectifying rotations R1_rect, R2_rect.
        # The default P/Q it returns picks a focal that puts the disparity
        # window well outside any reasonable SGBM range for our long-focal
        # underwater setup, so we override P_left, P_right, Q with custom
        # matrices that share a chosen rectified focal length.
        rect = cv2.stereoRectify(
            K_left, dist_left, K_right, dist_right,
            image_size_wh, R_rel, T_rel.reshape(3, 1),
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0,
            newImageSize=rect_size_wh,
        )
        R1_rect, R2_rect, _, _, _, _, _ = rect

        f = float(rect_focal)
        cx = rect_size_wh[0] / 2.0
        cy = rect_size_wh[1] / 2.0
        # OpenCV stereoRectify convention: P_left[0,3]=0, P_right[0,3]=-f*B.
        P1 = np.array([[f, 0, cx,        0],
                       [0, f, cy,        0],
                       [0, 0,  1,        0]], dtype=np.float64)
        P2 = np.array([[f, 0, cx, -f * baseline],
                       [0, f, cy,        0],
                       [0, 0,  1,        0]], dtype=np.float64)
        # Disparity-to-depth Q matching OpenCV convention.
        Q = np.array([[1, 0, 0,         -cx],
                      [0, 1, 0,         -cy],
                      [0, 0, 0,           f],
                      [0, 0, -1.0/baseline, 0]], dtype=np.float64)
        self.R_rect_left = R1_rect
        self.P_left = P1
        self.Q = Q

        self.map_left_x, self.map_left_y = cv2.initUndistortRectifyMap(
            K_left, dist_left, R1_rect, P1, rect_size_wh, cv2.CV_32FC1,
        )
        self.map_right_x, self.map_right_y = cv2.initUndistortRectifyMap(
            K_right, dist_right, R2_rect, P2, rect_size_wh, cv2.CV_32FC1,
        )

        # NOTE: SGBM_3WAY mode has a known integer-overflow bug when
        # minDisparity > 0; standard SGBM mode is the safe choice here.
        self.stereo = cv2.StereoSGBM_create(
            minDisparity=min_disparity,
            numDisparities=num_disparities,
            blockSize=block_size,
            P1=8 * block_size ** 2,
            P2=32 * block_size ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
            mode=cv2.STEREO_SGBM_MODE_SGBM,
        )

        # Rotation chain: rectified-left frame -> original-left frame -> object frame.
        # For a vector v in rectified-left coords:
        #   v_origLeft = R_rect_left.T @ v
        #   v_obj      = R_left.T @ v_origLeft   (since p_camL = R_left @ p_obj + t_left)
        self.R_disp_to_obj = R_left.T @ R1_rect.T

        self.prev_gray: np.ndarray | None = None
        self.prev_xyz: np.ndarray | None = None

    def rectify_pair(self, frame_left: np.ndarray, frame_right: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rect_l = cv2.remap(frame_left, self.map_left_x, self.map_left_y, cv2.INTER_LINEAR)
        rect_r = cv2.remap(frame_right, self.map_right_x, self.map_right_y, cv2.INTER_LINEAR)
        return rect_l, rect_r

    def compute_xyz(self, rect_left_gray: np.ndarray, rect_right_gray: np.ndarray) -> np.ndarray:
        """Return (H, W, 3) array of 3D positions in rectified-left frame, NaN where invalid."""
        disp16 = self.stereo.compute(rect_left_gray, rect_right_gray)
        disp = disp16.astype(np.float32) / 16.0
        valid = disp > 0
        xyz = cv2.reprojectImageTo3D(disp, self.Q)
        xyz = np.where(valid[..., None], xyz, np.nan)
        return xyz

    def step(
        self,
        frame_left_color: np.ndarray,
        frame_right_color: np.ndarray,
        contrast: float,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Process one stereo pair.

        Returns (rectified_left_color, displacement_obj or None on first frame).
        displacement_obj has shape (H, W, 3) with NaN where any of:
        disparity invalid at t, disparity invalid at t+1, or flowed
        coordinate out of bounds.
        """
        rect_l_color, rect_r_color = self.rectify_pair(frame_left_color, frame_right_color)
        rect_l_gray = apply_contrast(cv2.cvtColor(rect_l_color, cv2.COLOR_BGR2GRAY), contrast)
        rect_r_gray = apply_contrast(cv2.cvtColor(rect_r_color, cv2.COLOR_BGR2GRAY), contrast)

        xyz = self.compute_xyz(rect_l_gray, rect_r_gray)

        if self.prev_gray is None:
            self.prev_gray = rect_l_gray
            self.prev_xyz = xyz
            return rect_l_color, None

        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, rect_l_gray, None, **FARNEBACK_PARAMS,
        )

        H, W = rect_l_gray.shape
        ys, xs = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
        new_xs = xs.astype(np.float32) + flow[..., 0]
        new_ys = ys.astype(np.float32) + flow[..., 1]
        new_xyz = bilinear_sample_xyz(xyz, new_xs, new_ys)

        displacement_rect = new_xyz - self.prev_xyz                        # (H, W, 3) in rect-left
        flat = displacement_rect.reshape(-1, 3).T                          # (3, N)
        displacement_obj = (self.R_disp_to_obj @ flat).T.reshape(H, W, 3)  # (H, W, 3) in obj frame

        self.prev_gray = rect_l_gray
        self.prev_xyz = xyz
        return rect_l_color, displacement_obj


def render_3d_overlay(
    frame: np.ndarray,
    displacement_obj: np.ndarray,
    threshold_mm: float,
    max_mag_mm: float,
) -> np.ndarray:
    """Color by 3D direction (normal-map style), opacity by metric magnitude.

    `displacement_obj` is (H, W, 3) in the calibration-object frame, with
    NaN where unavailable. Pixels with ||displacement|| < threshold_mm
    or any NaN component stay untinted.
    """
    valid = np.all(np.isfinite(displacement_obj), axis=2)
    safe_disp = np.where(valid[..., None], displacement_obj, 0.0)
    mag_mm = np.linalg.norm(safe_disp, axis=2)

    # Normal-map: BGR = 255 * 0.5 * (unit_direction + 1), with channel
    # ordering (B, G, R) <- (z, y, x).
    safe_mag = np.where(mag_mm > 0, mag_mm, 1.0)
    unit = safe_disp / safe_mag[..., None]
    color_bgr = np.stack([
        0.5 * (unit[..., 2] + 1.0) * 255.0,
        0.5 * (unit[..., 1] + 1.0) * 255.0,
        0.5 * (unit[..., 0] + 1.0) * 255.0,
    ], axis=-1)
    color_bgr = np.clip(color_bgr, 0.0, 255.0)

    above = mag_mm >= threshold_mm
    span = max(max_mag_mm - threshold_mm, 1e-6)
    alpha = np.clip((mag_mm - threshold_mm) / span, 0.0, 1.0) * PEAK_ALPHA
    alpha = np.where(above & valid, alpha, 0.0).astype(np.float32)
    alpha3 = alpha[..., None]

    out = frame.astype(np.float32) * (1.0 - alpha3) + color_bgr * alpha3
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
    cv2.putText(img, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(img, f"Frame {frame_num}/{total_frames}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(img, f"thr={threshold_mm:.2f}  max={max_mag_mm:.2f} mm/frame", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)


def draw_axis_swatches(img: np.ndarray) -> None:
    """Draw the 6 axis-color swatches in the bottom-left corner.

    Each swatch is a small filled rectangle plus its axis label, laid
    out in two columns (+x/-x, +y/-y, +z/-z).
    """
    h = img.shape[0]
    swatch_w = 28
    swatch_h = 18
    pad = 4
    margin_x = 10
    margin_y = 10
    cols = 2
    n_per_col = (len(LEGEND_SWATCHES) + cols - 1) // cols  # 3 rows

    block_h = n_per_col * (swatch_h + pad)
    base_y = h - margin_y - block_h
    for i, (label, color) in enumerate(LEGEND_SWATCHES):
        col = i % cols
        row = i // cols
        x0 = margin_x + col * 90
        y0 = base_y + row * (swatch_h + pad)
        x1 = x0 + swatch_w
        y1 = y0 + swatch_h
        cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 0), 1)
        cv2.putText(
            img, label, (x1 + 6, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA,
        )
        cv2.putText(
            img, label, (x1 + 6, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA,
        )


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
    parser.add_argument("--calib", type=Path, required=True,
                        help="Path to stereo calibration JSON from tools/stereo_calibrate.py")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_MM,
                        help=f"||displacement|| threshold in mm/frame (default {DEFAULT_THRESHOLD_MM})")
    parser.add_argument("--max-mag", type=float, default=DEFAULT_MAX_MAG_MM,
                        help=f"||displacement|| at which overlay opacity saturates, mm/frame "
                             f"(default {DEFAULT_MAX_MAG_MM})")
    parser.add_argument("--contrast", type=float, default=DEFAULT_CONTRAST,
                        help=f"Grayscale contrast gain around 128 (default {DEFAULT_CONTRAST})")
    parser.add_argument("--downsample", type=int, default=DEFAULT_DOWNSAMPLE,
                        help=f"Integer scale factor applied to inputs before stereo+flow "
                             f"(default {DEFAULT_DOWNSAMPLE}). Larger = faster + smaller "
                             f"disparities but coarser overlay.")
    parser.add_argument("--rect-focal", type=float, default=DEFAULT_RECT_FOCAL,
                        help=f"Override the rectified focal length, in px (default "
                             f"{DEFAULT_RECT_FOCAL}). Lower => smaller disparity range, "
                             f"coarser angular resolution.")
    parser.add_argument("--min-disp", type=int, default=DEFAULT_MIN_DISPARITY,
                        help=f"SGBM minDisparity (default {DEFAULT_MIN_DISPARITY})")
    parser.add_argument("--num-disp", type=int, default=DEFAULT_NUM_DISPARITIES,
                        help=f"SGBM numDisparities, multiple of 16 (default {DEFAULT_NUM_DISPARITIES})")
    parser.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE,
                        help=f"SGBM blockSize, odd (default {DEFAULT_BLOCK_SIZE})")
    args = parser.parse_args()

    if args.max_mag <= args.threshold:
        print(f"--max-mag ({args.max_mag}) must exceed --threshold ({args.threshold})")
        sys.exit(1)
    if args.num_disp % 16 != 0:
        print(f"--num-disp ({args.num_disp}) must be a multiple of 16")
        sys.exit(1)
    if args.block_size % 2 == 0:
        print(f"--block-size ({args.block_size}) must be odd")
        sys.exit(1)
    if args.downsample < 1:
        print(f"--downsample ({args.downsample}) must be >= 1")
        sys.exit(1)
    if not args.calib.exists():
        print(f"Calibration not found: {args.calib}")
        sys.exit(1)

    print(f"Loading calibration from {args.calib}")
    calib = load_calibration(args.calib)
    full_size = calib["image_size_wh"]
    s = args.downsample
    work_size = (full_size[0] // s, full_size[1] // s)
    rect_size = work_size  # rectified output matches the downsampled input
    print(f"  calibration image size: {full_size[0]}x{full_size[1]}")
    print(f"  downsample factor:      {s}x  =>  working size {work_size[0]}x{work_size[1]}")
    print(f"  SGBM: minDisp={args.min_disp}  numDisp={args.num_disp}  blockSize={args.block_size}")

    # Scale K to match the downsampled image; distortion coefficients are unitless.
    K_scale = np.diag([1.0 / s, 1.0 / s, 1.0])
    K0_s = K_scale @ calib["cam0"]["K"]
    K1_s = K_scale @ calib["cam1"]["K"]

    cap0 = open_video(args.video_cam0)
    cap1 = open_video(args.video_cam1)
    w0 = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    h0 = int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    h1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (w0, h0) != full_size or (w1, h1) != full_size:
        print(f"Video frame size mismatch: cam0={w0}x{h0}, cam1={w1}x{h1}, "
              f"calibration={full_size[0]}x{full_size[1]}")
        sys.exit(1)

    print("Building stereo pipelines (one per pane)...")
    R0, _ = cv2.Rodrigues(calib["cam0"]["rvec"])
    R1, _ = cv2.Rodrigues(calib["cam1"]["rvec"])
    t0 = calib["cam0"]["tvec"].reshape(3)
    t1 = calib["cam1"]["tvec"].reshape(3)

    pipe_A = StereoPipeline(
        K0_s, calib["cam0"]["dist"], R0, t0,
        K1_s, calib["cam1"]["dist"], R1, t1,
        work_size, rect_size, args.min_disp, args.num_disp, args.block_size,
        args.rect_focal,
    )
    pipe_B = StereoPipeline(
        K1_s, calib["cam1"]["dist"], R1, t1,
        K0_s, calib["cam0"]["dist"], R0, t0,
        work_size, rect_size, args.min_disp, args.num_disp, args.block_size,
        args.rect_focal,
    )

    # Tell the user what depth range the disparity window covers, so they
    # can adjust --min-disp / --num-disp if their scene depths fall outside.
    fx_rect = pipe_A.P_left[0, 0]
    baseline = abs(1.0 / pipe_A.Q[3, 2])
    d_lo = max(args.min_disp, 1)
    d_hi = args.min_disp + args.num_disp - 1
    depth_far = fx_rect * baseline / d_lo
    depth_near = fx_rect * baseline / d_hi
    print(f"  rectified focal: {fx_rect:.1f} px   baseline: {baseline:.2f} mm")
    print(
        f"  disparity window {args.min_disp}..{d_hi} px "
        f"=> depth range ~{depth_near:.1f}..{depth_far:.1f} mm "
        f"(valve plane is at obj z=0; cam tvec z is ~{abs(t0[2]):.0f} mm so "
        f"expect depths near that)"
    )

    total_frames = min(int(cap0.get(cv2.CAP_PROP_FRAME_COUNT)),
                       int(cap1.get(cv2.CAP_PROP_FRAME_COUNT)))

    frame_num = 0
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
            elif key == 83 or key == ord('d'):
                advance = True

        if advance:
            ret0, frame0_full = cap0.read()
            ret1, frame1_full = cap1.read()
            if not (ret0 and ret1):
                print(f"End of video at frame {frame_num}")
                paused = True
                continue
            frame_num += 1

            if s != 1:
                frame0 = cv2.resize(frame0_full, work_size, interpolation=cv2.INTER_AREA)
                frame1 = cv2.resize(frame1_full, work_size, interpolation=cv2.INTER_AREA)
            else:
                frame0 = frame0_full
                frame1 = frame1_full

            rect_A, disp_A = pipe_A.step(frame0, frame1, args.contrast)
            rect_B, disp_B = pipe_B.step(frame1, frame0, args.contrast)

            if disp_A is None or disp_B is None:
                # First frame: nothing to overlay yet, just show the rectified pair.
                pane_A = rect_A.copy()
                pane_B = rect_B.copy()
            else:
                pane_A = render_3d_overlay(rect_A, disp_A, args.threshold, args.max_mag)
                pane_B = render_3d_overlay(rect_B, disp_B, args.threshold, args.max_mag)

            draw_overlay(pane_A, "cam0 (rectified)", frame_num, total_frames,
                         args.threshold, args.max_mag)
            draw_overlay(pane_B, "cam1 (rectified)", frame_num, total_frames,
                         args.threshold, args.max_mag)
            draw_axis_swatches(pane_A)
            draw_axis_swatches(pane_B)

            combined = np.hstack([pane_A, pane_B])
            cv2.imshow("3D-displacement explorer (stereo + flow)", combined)

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
