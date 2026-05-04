"""Dense optical flow explorer for valve camera footage.

Side-by-side display:
  - Left:  original frame with a bright blue tint wherever motion is above
           the threshold (anatomy still visible underneath).
  - Right: pure binary motion mask (white where moving, black elsewhere).

Direction is discarded and sub-threshold motion is hidden, so an entire
moving leaflet glows uniformly. Threshold is the same control used by the
dataset exporter (`tools/flow_export.py`).

Usage:
    python tools/flow_explore.py path/to/valve_recording.avi
    python tools/flow_explore.py path/to/valve_recording.avi --threshold 2.0
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._flow_params import FARNEBACK_PARAMS


DEFAULT_THRESHOLD_PX = 3.0  # scaled for 30 fps recordings (design doc cited 1.5 at 60 fps)


def compute_motion_mask(flow: np.ndarray, threshold_px: float) -> np.ndarray:
    """Binary motion mask: 255 where |flow| >= threshold, 0 elsewhere.

    Uniform brightness above the threshold so an entire moving region glows
    at the same intensity, regardless of which pixels move fastest.
    """
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return ((mag >= threshold_px) * 255).astype(np.uint8)


def render_blue_overlay(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Original frame with bright blue tint where the motion mask is on.

    Anatomy stays visible underneath the tint (the camera is monochrome,
    so the green/red channels carry the original luminance).
    """
    blue = np.zeros_like(frame)
    blue[..., 0] = 255  # BGR: pure blue
    blended = cv2.addWeighted(frame, 0.4, blue, 0.8, 0)
    out = frame.copy()
    out[mask > 0] = blended[mask > 0]
    return out


def draw_overlay(
    img: np.ndarray,
    frame_num: int,
    total_frames: int,
    threshold_px: float,
) -> None:
    """Frame counter + active threshold in top-left corner."""
    cv2.putText(
        img, f"Frame {frame_num}/{total_frames}", (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
    )
    cv2.putText(
        img, f"thr={threshold_px:.2f} px/frame", (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Path to recorded valve video")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD_PX,
        help=f"Motion magnitude threshold in px/frame (default {DEFAULT_THRESHOLD_PX})",
    )
    args = parser.parse_args()

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

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    frame_num = 1
    paused = False

    print(
        f"Controls: SPACE=play/pause  RIGHT=step  q=quit  "
        f"(threshold={args.threshold} px/frame)"
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

            curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None, **FARNEBACK_PARAMS,
            )

            mask = compute_motion_mask(flow, args.threshold)
            overlay = render_blue_overlay(curr_frame, mask)
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

            draw_overlay(overlay, frame_num, total_frames, args.threshold)
            draw_overlay(mask_bgr, frame_num, total_frames, args.threshold)

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
