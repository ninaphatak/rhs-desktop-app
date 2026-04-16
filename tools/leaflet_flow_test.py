"""Interactive Lucas-Kanade leaflet tracker prototype.

Loads reference points from calibrate_valve.py output, then tracks them
frame-to-frame using sparse LK optical flow with forward-backward validation.
Displays tracked points on video + a real-time displacement plot.

Usage:
    python tools/leaflet_flow_test.py path/to/valve_recording.avi
    python tools/leaflet_flow_test.py path/to/valve_recording.avi --calibration config/valve_calibration_cam1.json
"""

import argparse
import json
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np

# --- LK parameters (tune here) ---
LK_PARAMS = dict(
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    minEigThreshold=1e-4,
)
FB_ERROR_THRESHOLD = 1.0  # pixels — forward-backward consistency cutoff

# --- Display constants ---
PLOT_WIDTH = 800
PLOT_HEIGHT = 400
PLOT_HISTORY = 300  # frames shown on the plot x-axis
MAX_DISPLACEMENT_PX = 50.0  # plot y-axis upper bound (auto-rescales if exceeded)

# Colors for the 3 seam groups (BGR)
SEAM_COLORS = [
    (0, 255, 255),   # cyan
    (0, 255, 0),     # green
    (255, 128, 0),   # orange
]


def load_calibration(path: Path) -> tuple[np.ndarray, list[int], tuple[int, int], int]:
    """Load calibration JSON and cluster reference points into 3 seams by angle.

    Returns:
        points: (N, 1, 2) float32 array ready for cv2.calcOpticalFlowPyrLK
        seam_ids: list mapping each point to seam index 0, 1, or 2
        center: (cx, cy) valve center
        radius: valve radius
    """
    data = json.loads(path.read_text())
    ref = np.array(data["reference_points"], dtype=np.float32)  # (N, 2)
    center = tuple(data["valve_center"])
    radius = int(data["valve_radius"])

    if len(ref) == 0:
        raise ValueError("Calibration has no reference points")

    # Cluster points into 3 seams by angle from valve center.
    # Seams are roughly 120° apart; angle mod 120° gives us the seam ID.
    dx = ref[:, 0] - center[0]
    dy = ref[:, 1] - center[1]
    angles = np.arctan2(dy, dx)  # radians, -pi to pi

    # Use k-means on angle to find 3 clusters (robust to where the seams land)
    if len(ref) >= 3:
        angles_feat = np.column_stack([np.cos(angles), np.sin(angles)]).astype(np.float32)
        _, labels, _ = cv2.kmeans(
            angles_feat, 3, None,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, 0.1),
            5, cv2.KMEANS_PP_CENTERS
        )
        seam_ids = labels.flatten().tolist()
    else:
        seam_ids = list(range(len(ref)))

    # Reshape points for LK: (N, 1, 2)
    points = ref.reshape(-1, 1, 2).astype(np.float32)
    return points, seam_ids, center, radius


def track_lk(prev_gray: np.ndarray, curr_gray: np.ndarray,
             p_prev: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Run forward + backward LK and return (new_points, fb_errors).

    fb_errors[i] = Euclidean distance between round-trip and original position.
    """
    p_forward, _, _ = cv2.calcOpticalFlowPyrLK(
        prev_gray, curr_gray, p_prev, None, **LK_PARAMS)

    if p_forward is None:
        # LK utterly failed — return current points unchanged, huge errors
        return p_prev, np.full(len(p_prev), np.inf, dtype=np.float32)

    p_backward, _, _ = cv2.calcOpticalFlowPyrLK(
        curr_gray, prev_gray, p_forward, None, **LK_PARAMS)

    if p_backward is None:
        return p_forward, np.full(len(p_prev), np.inf, dtype=np.float32)

    fb_errors = np.linalg.norm(
        p_backward.reshape(-1, 2) - p_prev.reshape(-1, 2), axis=1
    ).astype(np.float32)
    return p_forward, fb_errors


def draw_tracking_overlay(frame_bgr: np.ndarray, p_curr: np.ndarray,
                          p_ref: np.ndarray, seam_ids: list[int],
                          frame_num: int, total_frames: int) -> np.ndarray:
    """Draw tracked points and displacement vectors on the frame."""
    display = frame_bgr.copy()

    curr_pts = p_curr.reshape(-1, 2)
    ref_pts = p_ref.reshape(-1, 2)

    for i, (cp, rp) in enumerate(zip(curr_pts, ref_pts)):
        color = SEAM_COLORS[seam_ids[i] % len(SEAM_COLORS)]
        cx, cy = int(cp[0]), int(cp[1])
        rx, ry = int(rp[0]), int(rp[1])
        # Faint line from reference to current (displacement vector)
        cv2.line(display, (rx, ry), (cx, cy), color, 1)
        # Current tracked position
        cv2.circle(display, (cx, cy), 3, color, -1)
        # Reference position as a small hollow ring
        cv2.circle(display, (rx, ry), 2, (100, 100, 100), 1)

    # Frame counter
    cv2.putText(display, f"Frame {frame_num}/{total_frames}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return display


def draw_displacement_plot(history: deque, seam_ids: list[int],
                           y_max: float) -> np.ndarray:
    """Render the displacement history as a plot canvas.

    history: deque of (N,) displacement arrays, one per recent frame.
    """
    canvas = np.zeros((PLOT_HEIGHT, PLOT_WIDTH, 3), dtype=np.uint8)

    # Axes
    cv2.line(canvas, (50, PLOT_HEIGHT - 30), (PLOT_WIDTH - 10, PLOT_HEIGHT - 30),
             (200, 200, 200), 1)
    cv2.line(canvas, (50, 10), (50, PLOT_HEIGHT - 30), (200, 200, 200), 1)

    # Y-axis labels
    cv2.putText(canvas, f"{y_max:.0f}px", (5, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    cv2.putText(canvas, "0", (35, PLOT_HEIGHT - 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    cv2.putText(canvas, "displacement (px)", (5, PLOT_HEIGHT - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    if len(history) < 2:
        return canvas

    n_points = len(history[0])
    history_arr = np.array(history)  # (T, N)
    T = len(history)

    plot_w = PLOT_WIDTH - 60
    plot_h = PLOT_HEIGHT - 40
    x_origin = 50
    y_origin = PLOT_HEIGHT - 30

    # One polyline per tracked point, colored by seam
    for pt_idx in range(n_points):
        color = SEAM_COLORS[seam_ids[pt_idx] % len(SEAM_COLORS)]
        pts = []
        for t in range(T):
            x = int(x_origin + (t / max(PLOT_HISTORY - 1, 1)) * plot_w)
            disp = history_arr[t, pt_idx]
            disp_clamped = min(disp, y_max)
            y = int(y_origin - (disp_clamped / y_max) * plot_h)
            pts.append((x, y))
        pts_np = np.array(pts, dtype=np.int32)
        cv2.polylines(canvas, [pts_np], False, color, 1)

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="LK leaflet tracker prototype")
    parser.add_argument("video", type=str, help="Path to AVI recording")
    parser.add_argument("--calibration", type=str,
                        default="config/valve_calibration.json",
                        help="Path to valve calibration JSON")
    args = parser.parse_args()

    video_path = Path(args.video)
    calib_path = Path(args.calibration)
    if not calib_path.is_absolute():
        calib_path = Path(__file__).resolve().parent.parent / calib_path

    if not video_path.exists():
        print(f"Video not found: {video_path}")
        sys.exit(1)
    if not calib_path.exists():
        print(f"Calibration not found: {calib_path}")
        sys.exit(1)

    # Load reference points
    p_ref, seam_ids, center, radius = load_calibration(calib_path)
    print(f"Loaded {len(p_ref)} reference points from {calib_path.name}")
    print(f"Seam groups: {[seam_ids.count(i) for i in range(3)]} points per seam")

    # Open video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Cannot open video: {video_path}")
        sys.exit(1)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ret, frame0 = cap.read()
    if not ret:
        print("Cannot read first frame")
        sys.exit(1)

    prev_gray = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY) if len(frame0.shape) == 3 else frame0
    p_curr = p_ref.copy()
    frame_num = 0

    # Displacement history for the plot
    history: deque = deque(maxlen=PLOT_HISTORY)
    y_max = MAX_DISPLACEMENT_PX

    paused = False
    print("\nControls: SPACE=play/pause  RIGHT=step  r=reset  q=quit\n")

    # Show frame 0 before starting
    display0 = draw_tracking_overlay(
        frame0 if len(frame0.shape) == 3 else cv2.cvtColor(frame0, cv2.COLOR_GRAY2BGR),
        p_curr, p_ref, seam_ids, frame_num, total_frames)
    cv2.imshow("Leaflet Tracking", display0)
    cv2.imshow("Displacement", draw_displacement_plot(history, seam_ids, y_max))

    while True:
        advance = not paused
        if paused:
            key = cv2.waitKey(0) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = False
                continue
            elif key == ord('r'):
                p_curr = p_ref.copy()
                history.clear()
                print(f"Reset at frame {frame_num}")
                # Redraw current frame with reset points
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, curr = cap.read()
                if ret:
                    curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY) if len(curr.shape) == 3 else curr
                    prev_gray = curr_gray
                    display = draw_tracking_overlay(
                        curr if len(curr.shape) == 3 else cv2.cvtColor(curr, cv2.COLOR_GRAY2BGR),
                        p_curr, p_ref, seam_ids, frame_num, total_frames)
                    cv2.imshow("Leaflet Tracking", display)
                    cv2.imshow("Displacement", draw_displacement_plot(history, seam_ids, y_max))
                continue
            elif key in (83, ord('d')):  # RIGHT
                advance = True

        if advance:
            ret, curr = cap.read()
            if not ret:
                print(f"End of video at frame {frame_num}")
                paused = True
                continue
            frame_num += 1

            curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY) if len(curr.shape) == 3 else curr

            # Run LK with forward-backward validation
            p_new, fb_errors = track_lk(prev_gray, curr_gray, p_curr)

            # Mark unreliable points (log only — not shown differently on screen)
            n_bad = int(np.sum(fb_errors > FB_ERROR_THRESHOLD))

            # Compute displacement from reference for all points
            curr_xy = p_new.reshape(-1, 2)
            ref_xy = p_ref.reshape(-1, 2)
            displacements = np.linalg.norm(curr_xy - ref_xy, axis=1)
            history.append(displacements.copy())

            # Auto-rescale plot y-axis if we exceed current max
            frame_max = float(displacements.max())
            if frame_max > y_max:
                y_max = frame_max * 1.2

            # Draw
            display = draw_tracking_overlay(
                curr if len(curr.shape) == 3 else cv2.cvtColor(curr, cv2.COLOR_GRAY2BGR),
                p_new, p_ref, seam_ids, frame_num, total_frames)
            cv2.imshow("Leaflet Tracking", display)
            cv2.imshow("Displacement", draw_displacement_plot(history, seam_ids, y_max))

            # Update state
            p_curr = p_new
            prev_gray = curr_gray

            # Log progress + any drift
            if n_bad > 0 and frame_num % 30 == 0:
                print(f"  Frame {frame_num}: {n_bad}/{len(p_curr)} points have FB error > {FB_ERROR_THRESHOLD}px")

        if not paused:
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = True
            elif key == ord('r'):
                p_curr = p_ref.copy()
                history.clear()
                print(f"Reset at frame {frame_num}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
