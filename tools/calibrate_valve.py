"""Valve geometry calibration tool.

Establish fixed valve geometry (center, radius, leaflet seam reference points)
from a single frame where the valve is at rest (closed). Saves calibration JSON
that all future CV tools can load.

Usage:
    python tools/calibrate_valve.py path/to/valve_recording.avi
    python tools/calibrate_valve.py path/to/closed_frame.png
"""

import json
import sys
from datetime import date
from pathlib import Path

import cv2
import numpy as np

# --- State machine ---
STATE_CENTER = 0       # Waiting for center click
STATE_RADIUS = 1       # Waiting for drag to edge
STATE_POINTS = 2       # Clicking leaflet seam points

# --- Global state (needed for OpenCV mouse callback) ---
state = STATE_CENTER
valve_center: list[int] | None = None
valve_radius: int | None = None
reference_points: list[list[int]] = []
drag_preview_pos: tuple[int, int] | None = None
display_dirty = True


def mouse_callback(event: int, x: int, y: int, flags: int, param: object) -> None:
    """Handle mouse events for the calibration state machine."""
    global state, valve_center, valve_radius, drag_preview_pos, display_dirty

    if state == STATE_CENTER:
        if event == cv2.EVENT_LBUTTONDOWN:
            valve_center = [x, y]
            state = STATE_RADIUS
            display_dirty = True
            print(f"  Center set: ({x}, {y}). Now drag to housing edge and click.")

    elif state == STATE_RADIUS:
        if event == cv2.EVENT_MOUSEMOVE:
            drag_preview_pos = (x, y)
            display_dirty = True
        elif event == cv2.EVENT_LBUTTONDOWN:
            dx = x - valve_center[0]
            dy = y - valve_center[1]
            valve_radius = int(np.sqrt(dx * dx + dy * dy))
            drag_preview_pos = None
            state = STATE_POINTS
            display_dirty = True
            print(f"  Radius set: {valve_radius}px. Click leaflet seam points. S=save, R=reset.")

    elif state == STATE_POINTS:
        if event == cv2.EVENT_LBUTTONDOWN:
            reference_points.append([x, y])
            display_dirty = True
            print(f"  Point {len(reference_points)}: ({x}, {y})")
        elif event == cv2.EVENT_RBUTTONDOWN:
            if reference_points:
                # Remove nearest point
                dists = [np.sqrt((p[0] - x) ** 2 + (p[1] - y) ** 2) for p in reference_points]
                nearest_idx = int(np.argmin(dists))
                removed = reference_points.pop(nearest_idx)
                display_dirty = True
                print(f"  Removed point ({removed[0]}, {removed[1]}). {len(reference_points)} remaining.")


def draw_overlay(base_frame: np.ndarray) -> np.ndarray:
    """Draw current calibration state on frame."""
    display = base_frame.copy()

    # Ensure color for drawing
    if len(display.shape) == 2:
        display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)

    # Draw center
    if valve_center is not None:
        cv2.drawMarker(display, tuple(valve_center), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)

    # Draw radius preview while dragging
    if state == STATE_RADIUS and valve_center is not None and drag_preview_pos is not None:
        dx = drag_preview_pos[0] - valve_center[0]
        dy = drag_preview_pos[1] - valve_center[1]
        r = int(np.sqrt(dx * dx + dy * dy))
        cv2.circle(display, tuple(valve_center), r, (0, 255, 255), 1)

    # Draw confirmed radius
    if valve_radius is not None and valve_center is not None:
        cv2.circle(display, tuple(valve_center), valve_radius, (0, 255, 255), 2)

    # Draw reference points
    for i, pt in enumerate(reference_points):
        cv2.circle(display, tuple(pt), 4, (255, 255, 0), -1)
        cv2.putText(display, str(i + 1), (pt[0] + 6, pt[1] - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

    # Draw instruction text
    instructions = {
        STATE_CENTER: "Click center of valve housing",
        STATE_RADIUS: "Drag to housing edge and click",
        STATE_POINTS: f"Click leaflet seams ({len(reference_points)} pts). S=save R=reset",
    }
    text = instructions[state]
    cv2.putText(display, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return display


def save_calibration(source_label: str) -> None:
    """Save calibration data to config/valve_calibration.json."""
    output_dir = Path(__file__).resolve().parent.parent / "config"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "valve_calibration.json"

    data = {
        "valve_center": valve_center,
        "valve_radius": valve_radius,
        "reference_points": reference_points,
        "source_frame": source_label,
        "notes": f"Closed valve, 0-degree camera, {date.today().isoformat()}",
    }

    output_path.write_text(json.dumps(data, indent=4) + "\n")
    print(f"  Saved calibration to {output_path}")
    print(f"  {len(reference_points)} reference points, radius={valve_radius}px")


def reset_all() -> None:
    """Reset all calibration state."""
    global state, valve_center, valve_radius, reference_points, drag_preview_pos, display_dirty
    state = STATE_CENTER
    valve_center = None
    valve_radius = None
    reference_points = []
    drag_preview_pos = None
    display_dirty = True
    print("  Reset. Click center of valve housing.")


def main() -> None:
    global display_dirty

    if len(sys.argv) < 2:
        print("Usage: python tools/calibrate_valve.py <video_or_image_path>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    # Determine if video or image
    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    is_image = input_path.suffix.lower() in image_exts

    if is_image:
        frame = cv2.imread(str(input_path))
        if frame is None:
            print(f"Cannot read image: {input_path}")
            sys.exit(1)
        frames = [frame]
        frame_idx = 0
        total_frames = 1
    else:
        cap = cv2.VideoCapture(str(input_path))
        if not cap.isOpened():
            print(f"Cannot open video: {input_path}")
            sys.exit(1)
        # Read all frames into memory for random access (valve videos are short)
        frames = []
        while True:
            ret, f = cap.read()
            if not ret:
                break
            frames.append(f)
        cap.release()
        if not frames:
            print("No frames in video")
            sys.exit(1)
        frame_idx = 0
        total_frames = len(frames)
        print(f"Loaded {total_frames} frames. Use LEFT/RIGHT arrows to navigate.")

    window_name = "Valve Calibration"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window_name, mouse_callback)

    print("Click center of valve housing.")

    while True:
        if display_dirty:
            base = frames[frame_idx]
            display = draw_overlay(base)
            # Show frame number for video
            if not is_image:
                label = f"Frame {frame_idx}/{total_frames - 1}"
                cv2.putText(display, label, (10, display.shape[0] - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow(window_name, display)
            display_dirty = False

        key = cv2.waitKey(30) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            if valve_center is None or valve_radius is None:
                print("  Cannot save: set center and radius first.")
            elif len(reference_points) == 0:
                print("  Cannot save: add at least one reference point.")
            else:
                source_label = f"frame_{frame_idx:04d}" if not is_image else input_path.name
                save_calibration(source_label)
        elif key == ord('r'):
            reset_all()
        elif key == 83 or key == ord('d'):  # RIGHT ARROW
            if not is_image and frame_idx < total_frames - 1:
                frame_idx += 1
                display_dirty = True
        elif key == 81 or key == ord('a'):  # LEFT ARROW
            if not is_image and frame_idx > 0:
                frame_idx -= 1
                display_dirty = True

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
