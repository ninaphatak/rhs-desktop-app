"""Dense optical flow explorer for valve camera footage.

Visualizes Farneback dense optical flow as HSV overlay and magnitude heatmap.
Pure exploration tool — no tracking, no measurements.

Usage:
    python tools/flow_explore.py path/to/valve_recording.avi
"""

import sys
from pathlib import Path

import cv2
import numpy as np


def compute_flow_hsv(flow: np.ndarray) -> np.ndarray:
    """Convert optical flow field to HSV color image.

    Hue = direction, Value = magnitude, Saturation = 255.
    """
    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    hsv = np.zeros((*flow.shape[:2], 3), dtype=np.uint8)
    hsv[..., 0] = ang * 180 / np.pi / 2  # hue: 0-179
    hsv[..., 1] = 255  # saturation: constant
    hsv[..., 2] = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def compute_magnitude_heatmap(flow: np.ndarray) -> np.ndarray:
    """Convert optical flow to grayscale magnitude heatmap (white = high motion)."""
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    norm = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)


def draw_frame_counter(img: np.ndarray, frame_num: int, total_frames: int) -> None:
    """Draw frame counter in top-left corner."""
    text = f"Frame {frame_num}/{total_frames}"
    cv2.putText(img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/flow_explore.py <video_path>")
        sys.exit(1)

    video_path = Path(sys.argv[1])
    if not video_path.exists():
        print(f"File not found: {video_path}")
        sys.exit(1)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Cannot open video: {video_path}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_num = 0

    ret, prev_frame = cap.read()
    if not ret:
        print("Cannot read first frame")
        sys.exit(1)

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    frame_num = 1
    paused = False

    print("Controls: SPACE=play/pause  RIGHT=step  q=quit")

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
                prev_gray, curr_gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )

            # HSV flow overlay (semi-transparent on original)
            flow_hsv = compute_flow_hsv(flow)
            overlay = cv2.addWeighted(curr_frame, 0.5, flow_hsv, 0.5, 0)

            # Magnitude heatmap
            heatmap = compute_magnitude_heatmap(flow)

            # Draw frame counters
            draw_frame_counter(overlay, frame_num, total_frames)
            draw_frame_counter(heatmap, frame_num, total_frames)

            # Side by side display
            combined = np.hstack([overlay, heatmap])
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
