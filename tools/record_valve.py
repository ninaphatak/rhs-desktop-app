"""Record a short AVI clip from a Basler camera for CV exploration.

Mirrors the camera configuration from src/core/basler_camera.py
(exposure 25ms, gain 18, MJPG codec). No PySide6 — pure pypylon + OpenCV.

Usage:
    python tools/record_valve.py                    # Camera 0, 10 seconds
    python tools/record_valve.py --camera 1         # Camera 1 (30-degree)
    python tools/record_valve.py --duration 5       # 5 seconds
    python tools/record_valve.py --output my_clip   # Custom filename
    python tools/record_valve.py --fps 60           # Override FPS (default 60)
    python tools/record_valve.py --preview            # Play back after recording
    python tools/record_valve.py --list              # List connected cameras
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    from pypylon import pylon
except ImportError:
    print("ERROR: pypylon not installed. Run: pip install pypylon")
    sys.exit(1)


def list_cameras() -> list[str]:
    """Enumerate connected Basler cameras."""
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    return [d.GetFriendlyName() for d in devices]


def record(camera_index: int, duration_sec: float, fps: float,
           output_path: Path) -> None:
    """Connect to camera, record frames to AVI, and disconnect."""
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()

    if not devices:
        print("ERROR: No Basler cameras found.")
        sys.exit(1)
    if camera_index >= len(devices):
        print(f"ERROR: Camera index {camera_index} not found. "
              f"{len(devices)} camera(s) available.")
        sys.exit(1)

    camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[camera_index]))
    camera.Open()
    print(f"Connected: {devices[camera_index].GetFriendlyName()}")

    # Configure — matches src/core/basler_camera.py settings
    try:
        camera.ExposureTime.SetValue(25000)  # 25ms
    except Exception as e:
        print(f"Warning: Could not set exposure: {e}")
    try:
        camera.AcquisitionFrameRateEnable.SetValue(True)
        camera.AcquisitionFrameRate.SetValue(fps)
    except Exception as e:
        print(f"Warning: Could not set frame rate: {e}")
    try:
        camera.Gain.SetValue(18)
    except Exception as e:
        print(f"Warning: Could not set gain: {e}")

    # Grab one frame to get dimensions
    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    grab = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
    if not grab.GrabSucceeded():
        print("ERROR: Failed to grab initial frame.")
        camera.Close()
        sys.exit(1)

    frame = grab.Array.copy()
    grab.Release()
    h, w = frame.shape[:2]
    is_mono = len(frame.shape) == 2
    print(f"Frame size: {w}x{h}, {'mono' if is_mono else 'color'}")

    # Set up VideoWriter (MJPG for broad compatibility)
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h), isColor=not is_mono)
    if not writer.isOpened():
        print(f"ERROR: Cannot open VideoWriter for {output_path}")
        camera.StopGrabbing()
        camera.Close()
        sys.exit(1)

    # Write the first frame we already grabbed
    if is_mono:
        writer.write(frame)
    else:
        writer.write(frame)
    frame_count = 1

    # Record loop
    target_frames = int(duration_sec * fps)
    frame_interval = 1.0 / fps
    print(f"Recording {duration_sec}s @ {fps}fps ({target_frames} frames) → {output_path}")
    print("Press Ctrl+C to stop early.")

    t_start = time.time()
    try:
        while frame_count < target_frames and camera.IsGrabbing():
            t_frame = time.time()
            timeout_ms = int(25000 / 1000) + 1000  # exposure_ms + 1s
            grab = camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                frame = grab.Array.copy()
                grab.Release()
                writer.write(frame)
                frame_count += 1

                # Progress every 60 frames
                if frame_count % 60 == 0:
                    elapsed = time.time() - t_start
                    print(f"  {frame_count}/{target_frames} frames "
                          f"({elapsed:.1f}s elapsed)")

                # Pace to target FPS
                sleep_time = frame_interval - (time.time() - t_frame)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            elif grab:
                grab.Release()
    except KeyboardInterrupt:
        print("\nStopped early by user.")

    elapsed = time.time() - t_start
    camera.StopGrabbing()
    camera.Close()
    writer.release()

    actual_fps = frame_count / elapsed if elapsed > 0 else 0
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\nDone: {frame_count} frames in {elapsed:.1f}s "
          f"(actual {actual_fps:.1f} fps)")
    print(f"Saved: {output_path} ({file_size_mb:.1f} MB)")


def preview(video_path: Path, fps: float) -> None:
    """Play back a recorded AVI. SPACE=pause, RIGHT=step, q=quit."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"ERROR: Cannot open {video_path} for preview.")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_delay = int(1000 / fps)
    frame_num = 0
    paused = False

    print(f"\nPreview: {video_path.name} ({total_frames} frames)")
    print("Controls: SPACE=play/pause  RIGHT=step  q=quit")

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("End of video.")
                paused = True
                continue
            frame_num += 1
            # Frame counter overlay
            display = frame if len(frame.shape) == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            cv2.putText(display, f"Frame {frame_num}/{total_frames}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("Preview", display)
            key = cv2.waitKey(frame_delay) & 0xFF
        else:
            key = cv2.waitKey(0) & 0xFF

        if key == ord('q'):
            break
        elif key == ord(' '):
            paused = not paused
        elif paused and key in (83, ord('d')):  # RIGHT ARROW
            ret, frame = cap.read()
            if not ret:
                print("End of video.")
                continue
            frame_num += 1
            display = frame if len(frame.shape) == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            cv2.putText(display, f"Frame {frame_num}/{total_frames}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("Preview", display)

    cap.release()
    cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record a short AVI from a Basler camera.")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default: 0)")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Recording duration in seconds (default: 10)")
    parser.add_argument("--fps", type=float, default=60.0,
                        help="Target frame rate (default: 60)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (without extension)")
    parser.add_argument("--preview", action="store_true",
                        help="Play back recording after capture")
    parser.add_argument("--list", action="store_true",
                        help="List connected cameras and exit")
    args = parser.parse_args()

    if args.list:
        cameras = list_cameras()
        if not cameras:
            print("No Basler cameras found.")
        else:
            for i, name in enumerate(cameras):
                print(f"  [{i}] {name}")
        return

    # Default output name: valve_cam0_20260329_191500.avi
    if args.output:
        filename = args.output if args.output.endswith(".avi") else args.output + ".avi"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"valve_cam{args.camera}_{timestamp}.avi"

    output_path = Path(__file__).resolve().parent.parent / "outputs" / filename
    output_path.parent.mkdir(exist_ok=True)

    record(args.camera, args.duration, args.fps, output_path)

    if args.preview:
        preview(output_path, args.fps)


if __name__ == "__main__":
    main()
