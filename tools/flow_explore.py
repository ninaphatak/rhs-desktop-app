"""Dense optical flow explorer for valve camera footage.

Side-by-side display:
  - Left:  original frame tinted by flow direction and magnitude. Hue encodes
           the flow vector's compass direction; opacity encodes magnitude.
  - Right: pure binary motion mask (white where moving, black elsewhere).

Direction-to-color anchors (image-space compass; "north" = up on screen):
  - Red    -> flow heading north (up)
  - Yellow -> flow heading 30 deg counter-clockwise from east (ENE)
  - Cyan   -> flow heading east (right)
  Other directions interpolate linearly between adjacent anchors around the
  full circle (red wraps back to cyan the long way for the south-west arc).

Opacity-to-magnitude:
  - At |flow| <= --threshold px/frame the overlay is fully transparent.
  - Above threshold opacity grows linearly to a cap at --max-mag px/frame.
  - At |flow| >= --max-mag the overlay reaches its peak alpha (0.85), so
    anatomy stays faintly visible even where motion is fastest.

Threshold is the same control used by the dataset exporter
(`tools/flow_export.py`); --max-mag only affects this visualization.

Usage:
    python tools/flow_explore.py path/to/valve_recording.mp4
    python tools/flow_explore.py path/to/valve_recording.mp4 --threshold 2.0
    python tools/flow_explore.py path/to/valve_recording.mp4 --max-mag 6.0
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._flow_params import FARNEBACK_PARAMS


DEFAULT_THRESHOLD_PX = 3.0  # scaled for 30 fps recordings (design doc cited 1.5 at 60 fps)
DEFAULT_MAX_MAG_PX = 10.0   # magnitude at which overlay opacity saturates
DEFAULT_CONTRAST = 1.25     # gain applied around mid-gray (128) before Farneback
PEAK_ALPHA = 0.85           # max blend weight on the colored overlay

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


def apply_contrast(gray: np.ndarray, factor: float) -> np.ndarray:
    """Linearly scale grayscale pixel values around 128 by `factor`.

    factor=1.0 is a no-op; factor=1.25 stretches the dynamic range by 25%.
    Result is clipped to [0, 255] and returned as uint8.
    """
    if factor == 1.0:
        return gray
    out = (gray.astype(np.float32) - 128.0) * factor + 128.0
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def compute_motion_mask(flow: np.ndarray, threshold_px: float) -> np.ndarray:
    """Binary motion mask: 255 where |flow| >= threshold, 0 elsewhere."""
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return ((mag >= threshold_px) * 255).astype(np.uint8)


def render_directional_overlay(
    frame: np.ndarray,
    flow: np.ndarray,
    threshold_px: float,
    max_mag_px: float,
) -> np.ndarray:
    """Tint `frame` by flow direction (hue) and magnitude (opacity).

    Pixels with |flow| < threshold_px stay untinted. Pixels above threshold
    receive a per-pixel BGR color (looked up from the direction LUT) blended
    over the source frame with alpha proportional to magnitude, clipped at
    max_mag_px and capped at PEAK_ALPHA.
    """
    fx = flow[..., 0]
    fy = flow[..., 1]
    mag = np.sqrt(fx * fx + fy * fy)

    # Image-space compass: y grows downward, so negate fy before atan2 so that
    # an upward flow vector (negative dy) gets theta = +90 deg = north.
    theta_deg = np.degrees(np.arctan2(-fy, fx)) % 360.0
    theta_idx = theta_deg.astype(np.int32) % 360
    color = DIRECTION_LUT[theta_idx]  # (H, W, 3) float32, BGR

    above = mag >= threshold_px
    span = max(max_mag_px - threshold_px, 1e-6)
    alpha = np.clip((mag - threshold_px) / span, 0.0, 1.0) * PEAK_ALPHA
    alpha = np.where(above, alpha, 0.0).astype(np.float32)
    alpha3 = alpha[..., None]

    out = frame.astype(np.float32) * (1.0 - alpha3) + color * alpha3
    return np.clip(out, 0.0, 255.0).astype(np.uint8)


def draw_overlay(
    img: np.ndarray,
    frame_num: int,
    total_frames: int,
    threshold_px: float,
    max_mag_px: float,
) -> None:
    """Frame counter + thresholds in top-left corner."""
    cv2.putText(
        img, f"Frame {frame_num}/{total_frames}", (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
    )
    cv2.putText(
        img, f"thr={threshold_px:.2f}  max={max_mag_px:.2f} px/frame", (10, 60),
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Path to recorded valve video")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD_PX,
        help=f"Motion magnitude threshold in px/frame (default {DEFAULT_THRESHOLD_PX})",
    )
    parser.add_argument(
        "--max-mag", type=float, default=DEFAULT_MAX_MAG_PX,
        help=(
            "Magnitude at which overlay opacity saturates, in px/frame "
            f"(default {DEFAULT_MAX_MAG_PX})"
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

    if not args.video.exists():
        print(f"File not found: {args.video}")
        sys.exit(1)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"Cannot open video: {args.video}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ret, prev_frame = cap.read()
    if not ret:
        print("Cannot read first frame")
        sys.exit(1)

    prev_gray = apply_contrast(cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY), args.contrast)
    frame_num = 1
    paused = False

    print(
        f"Controls: SPACE=play/pause  RIGHT=step  q=quit  "
        f"(threshold={args.threshold} max={args.max_mag} px/frame  "
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
            ret, curr_frame = cap.read()
            if not ret:
                print(f"End of video at frame {frame_num}")
                paused = True
                continue

            curr_gray = apply_contrast(
                cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY), args.contrast,
            )

            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None, **FARNEBACK_PARAMS,
            )

            mask = compute_motion_mask(flow, args.threshold)
            overlay = render_directional_overlay(
                curr_frame, flow, args.threshold, args.max_mag,
            )
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

            draw_overlay(overlay, frame_num, total_frames, args.threshold, args.max_mag)
            draw_overlay(mask_bgr, frame_num, total_frames, args.threshold, args.max_mag)
            draw_direction_legend(overlay)

            combined = np.hstack([overlay, mask_bgr])
            cv2.imshow("Dense Optical Flow Explorer", combined)

            prev_gray = curr_gray
            frame_num += 1

        if not paused:
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = True

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
