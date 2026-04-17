"""Record a short H.264/MP4 clip from a Basler camera for CV exploration.

Mirrors the camera configuration from src/core/basler_camera.py
(exposure 25ms, gain 18). Encodes via ffmpeg using the binary bundled
by imageio-ffmpeg — no system ffmpeg install required, works on
macOS and Windows identically.

Usage:
    python tools/record_valve.py                    # Camera 0, 10 seconds
    python tools/record_valve.py --camera 1         # Camera 1 (30-degree)
    python tools/record_valve.py --duration 5       # 5 seconds
    python tools/record_valve.py --output my_clip   # Custom filename
    python tools/record_valve.py --fps 60           # Override FPS (default 60)
    python tools/record_valve.py --preview          # Play back after recording
    python tools/record_valve.py --list             # List connected cameras
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

try:
    from pypylon import pylon
except ImportError:
    print("ERROR: pypylon not installed. Run: pip install pypylon")
    sys.exit(1)

try:
    import imageio_ffmpeg
except ImportError:
    print("ERROR: imageio-ffmpeg not installed. "
          "Run: pip install imageio-ffmpeg")
    sys.exit(1)


H264_PRESET = "fast"
H264_CRF = 18


def list_cameras() -> list[str]:
    """Enumerate connected Basler cameras."""
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    return [d.GetFriendlyName() for d in devices]


def _spawn_ffmpeg(output_path: Path, width: int, height: int,
                  is_mono: bool, fps: float) -> Optional[subprocess.Popen]:
    """Spawn ffmpeg reading raw frames from stdin, writing H.264/MP4."""
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo",
        "-pix_fmt", "gray" if is_mono else "bgr24",
        "-s", f"{width}x{height}",
        "-r", f"{fps:g}",
        "-i", "-",
        "-c:v", "libx264",
        "-preset", H264_PRESET,
        "-crf", str(H264_CRF),
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    except OSError as e:
        print(f"ERROR: Failed to spawn ffmpeg: {e}")
        return None


def record(camera_index: int, duration_sec: float, fps: float,
           output_path: Path) -> None:
    """Connect to camera, record frames to H.264/MP4, and disconnect."""
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
    is_mono = frame.ndim == 2
    print(f"Frame size: {w}x{h}, {'mono' if is_mono else 'color'}")
    print(f"Codec: H.264 (libx264 CRF {H264_CRF} preset {H264_PRESET})")

    proc = _spawn_ffmpeg(output_path, w, h, is_mono, fps)
    if proc is None:
        camera.StopGrabbing()
        camera.Close()
        sys.exit(1)

    # Write the primed first frame
    proc.stdin.write(frame.tobytes())
    frame_count = 1

    target_frames = int(duration_sec * fps)
    frame_interval = 1.0 / fps
    print(f"Recording {duration_sec}s @ {fps}fps "
          f"({target_frames} frames) → {output_path}")
    print("Press Ctrl+C to stop early.")

    t_start = time.time()
    try:
        while frame_count < target_frames and camera.IsGrabbing():
            t_frame = time.time()
            timeout_ms = 25 + 1000  # exposure_ms + 1s
            grab = camera.RetrieveResult(timeout_ms,
                                         pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                frame = grab.Array
                grab.Release()
                try:
                    proc.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    err = proc.stderr.read().decode(errors="replace")
                    print(f"\nERROR: ffmpeg stdin closed. stderr:\n{err}")
                    break
                frame_count += 1

                if frame_count % 60 == 0:
                    elapsed = time.time() - t_start
                    print(f"  {frame_count}/{target_frames} frames "
                          f"({elapsed:.1f}s elapsed)")

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

    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("WARN: ffmpeg wouldn't finalize in 30s — killed")
    if proc.returncode not in (0, None):
        err = proc.stderr.read().decode(errors="replace")
        print(f"WARN: ffmpeg exit {proc.returncode}. stderr:\n"
              f"{err[-600:]}")

    actual_fps = frame_count / elapsed if elapsed > 0 else 0
    file_size_mb = (output_path.stat().st_size / (1024 * 1024)
                    if output_path.exists() else 0)
    print(f"\nDone: {frame_count} frames in {elapsed:.1f}s "
          f"(actual {actual_fps:.1f} fps)")
    print(f"Saved: {output_path} ({file_size_mb:.1f} MB)")


def preview(video_path: Path, fps: float) -> None:
    """Play back a recorded MP4. SPACE=pause, RIGHT=step, q=quit."""
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
            display = (frame if len(frame.shape) == 3
                       else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
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
            display = (frame if len(frame.shape) == 3
                       else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
            cv2.putText(display, f"Frame {frame_num}/{total_frames}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("Preview", display)

    cap.release()
    cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record a short H.264/MP4 clip from a Basler camera.")
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

    # Default output name: valve_cam0_20260417_191500.mp4
    if args.output:
        filename = (args.output if args.output.endswith(".mp4")
                    else args.output + ".mp4")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"valve_cam{args.camera}_{timestamp}.mp4"

    output_path = Path(__file__).resolve().parent.parent / "outputs" / filename
    output_path.parent.mkdir(exist_ok=True)

    record(args.camera, args.duration, args.fps, output_path)

    if args.preview:
        preview(output_path, args.fps)


if __name__ == "__main__":
    main()
