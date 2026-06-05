"""Record a short MJPG/AVI clip from one or both Basler cameras.

Mirrors the camera configuration and recording format from
src/core/basler_camera.py (exposure 25ms, gain 18, MJPG/AVI intra-only
at -q:v 2 visually lossless). Also writes a per-frame timestamp sidecar
(<video>.avi.timestamps.csv) with system time + Basler hardware timestamp,
matching the GUI so tools/triangulate.py can consume the output for
free-run sync correction via temporal interpolation.

The --dual mode runs both cameras in parallel headless threads (no Qt /
no preview) — useful for isolating whether the UI is dropping frames vs
the cameras themselves.

Encodes via ffmpeg using the binary bundled by imageio-ffmpeg — no
system ffmpeg install required, works on macOS and Windows identically.

Usage:
    python tools/record_valve.py                    # Camera 0, 10 seconds @ 30fps
    python tools/record_valve.py --camera 1         # Camera 1 (30-degree)
    python tools/record_valve.py --dual             # Both cameras in parallel
    python tools/record_valve.py --duration 5       # 5 seconds
    python tools/record_valve.py --output my_clip   # Custom filename (single-cam only)
    python tools/record_valve.py --fps 60           # Override FPS (default 30, matches GUI)
    python tools/record_valve.py --preview          # Play back after recording (single-cam only)
    python tools/record_valve.py --list             # List connected cameras
"""

import argparse
import math
import subprocess
import sys
import threading
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


MJPG_QUALITY = 2  # ffmpeg -q:v scale: 1=best, 31=worst; 2 is visually lossless

# Reference exposure/gain anchored at 30 fps in src/core/basler_camera.py.
# At higher fps the frame period shrinks below 25 ms so exposure must drop;
# gain is bumped 6 dB per stop of lost exposure to keep image brightness flat.
BASE_FPS = 30.0
BASE_EXPOSURE_US = 25000.0       # 25 ms at 30 fps
BASE_GAIN_DB = 18.0              # 18 dB at 30 fps
EXPOSURE_DUTY = 0.75             # exposure / frame_period; matches 25 ms @ 30 fps
MAX_GAIN_DB = 36.0               # a2A1920-160umBAS practical ceiling


def _auto_exposure_gain(fps: float) -> tuple[int, float]:
    """Scale exposure (us) and gain (dB) to the target frame rate.

    Anchored on BASE_FPS / BASE_EXPOSURE_US / BASE_GAIN_DB so behavior at
    30 fps matches the GUI exactly. Above 30 fps, exposure is clipped to
    EXPOSURE_DUTY * frame_period and gain is increased by 6 dB per stop
    of lost exposure (clamped at MAX_GAIN_DB). Below 30 fps both stay at
    the baseline — no point overexposing or losing SNR.
    """
    frame_period_us = 1e6 / fps
    exposure_us = min(BASE_EXPOSURE_US, EXPOSURE_DUTY * frame_period_us)
    stops_lost = (math.log2(BASE_EXPOSURE_US / exposure_us)
                  if exposure_us < BASE_EXPOSURE_US else 0.0)
    gain_db = min(MAX_GAIN_DB, BASE_GAIN_DB + 6.0 * stops_lost)
    return int(round(exposure_us)), gain_db


def list_cameras() -> list[str]:
    """Enumerate connected Basler cameras."""
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    return [d.GetFriendlyName() for d in devices]


def _spawn_ffmpeg(output_path: Path, width: int, height: int,
                  is_mono: bool, fps: float) -> Optional[subprocess.Popen]:
    """Spawn ffmpeg reading raw frames from stdin, writing MJPG/AVI."""
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo",
        "-pix_fmt", "gray" if is_mono else "bgr24",
        "-s", f"{width}x{height}",
        "-r", f"{fps:g}",
        "-i", "-",
        "-c:v", "mjpeg",
        "-q:v", str(MJPG_QUALITY),
        "-pix_fmt", "yuv420p",
        "-color_range", "jpeg",
        str(output_path),
    ]
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    except OSError as e:
        print(f"ERROR: Failed to spawn ffmpeg: {e}")
        return None


def _record_one(camera_index: int, duration_sec: float, fps: float,
                output_path: Path, stop_event: Optional[threading.Event] = None,
                label: str = "") -> dict:
    """Run one camera's record loop. Safe to call from a thread.

    Returns a summary dict {frame_count, elapsed_s, actual_fps, output_path}.
    """
    tag = f"[{label}] " if label else ""

    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    if not devices:
        print(f"{tag}ERROR: No Basler cameras found.")
        return {"frame_count": 0, "elapsed_s": 0.0, "actual_fps": 0.0,
                "output_path": output_path}
    if camera_index >= len(devices):
        print(f"{tag}ERROR: Camera index {camera_index} not found. "
              f"{len(devices)} camera(s) available.")
        return {"frame_count": 0, "elapsed_s": 0.0, "actual_fps": 0.0,
                "output_path": output_path}

    camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[camera_index]))
    camera.Open()
    print(f"{tag}Connected: {devices[camera_index].GetFriendlyName()}")

    exposure_us, gain_db = _auto_exposure_gain(fps)
    print(f"{tag}Auto exposure/gain for {fps:g} fps: "
          f"{exposure_us/1000:.2f} ms, {gain_db:.1f} dB")
    try:
        camera.ExposureTime.SetValue(exposure_us)
    except Exception as e:
        print(f"{tag}Warning: Could not set exposure: {e}")
    try:
        camera.AcquisitionFrameRateEnable.SetValue(True)
        camera.AcquisitionFrameRate.SetValue(fps)
    except Exception as e:
        print(f"{tag}Warning: Could not set frame rate: {e}")
    try:
        camera.Gain.SetValue(gain_db)
    except Exception as e:
        print(f"{tag}Warning: Could not set gain: {e}")

    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    grab = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
    if not grab.GrabSucceeded():
        print(f"{tag}ERROR: Failed to grab initial frame.")
        camera.Close()
        return {"frame_count": 0, "elapsed_s": 0.0, "actual_fps": 0.0,
                "output_path": output_path}

    frame = grab.Array.copy()
    try:
        hw_ts_first = int(grab.GetTimeStamp())
    except Exception:
        hw_ts_first = -1
    sys_time_first = time.time()
    grab.Release()
    h, w = frame.shape[:2]
    is_mono = frame.ndim == 2
    print(f"{tag}Frame size: {w}x{h}, {'mono' if is_mono else 'color'}")
    print(f"{tag}Codec: MJPG/AVI (-q:v {MJPG_QUALITY}, intra-only)")

    proc = _spawn_ffmpeg(output_path, w, h, is_mono, fps)
    if proc is None:
        camera.StopGrabbing()
        camera.Close()
        return {"frame_count": 0, "elapsed_s": 0.0, "actual_fps": 0.0,
                "output_path": output_path}

    ts_path = output_path.with_suffix(output_path.suffix + ".timestamps.csv")
    try:
        ts_file = open(ts_path, "w", newline="")
        ts_file.write("frame_index,system_time_s,hw_timestamp_ticks\n")
    except OSError as e:
        print(f"{tag}Warning: Could not open timestamp sidecar {ts_path}: {e}")
        ts_file = None

    proc.stdin.write(frame.tobytes())
    if ts_file is not None:
        ts_file.write(f"0,{sys_time_first:.6f},{hw_ts_first}\n")
    frame_count = 1

    target_frames = int(duration_sec * fps)
    print(f"{tag}Recording {duration_sec}s @ {fps}fps "
          f"({target_frames} frames) → {output_path}")

    t_start = time.time()
    try:
        while frame_count < target_frames and camera.IsGrabbing():
            if stop_event is not None and stop_event.is_set():
                break
            timeout_ms = 25 + 1000
            grab = camera.RetrieveResult(timeout_ms,
                                         pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                frame = grab.Array
                try:
                    hw_ts = int(grab.GetTimeStamp())
                except Exception:
                    hw_ts = -1
                sys_time = time.time()
                grab.Release()
                try:
                    proc.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    err = proc.stderr.read().decode(errors="replace")
                    print(f"\n{tag}ERROR: ffmpeg stdin closed. stderr:\n{err}")
                    break
                if ts_file is not None:
                    try:
                        ts_file.write(
                            f"{frame_count},{sys_time:.6f},{hw_ts}\n")
                    except Exception:
                        pass
                frame_count += 1

                if frame_count % 60 == 0:
                    elapsed = time.time() - t_start
                    print(f"{tag}  {frame_count}/{target_frames} frames "
                          f"({elapsed:.1f}s elapsed)")
            elif grab:
                grab.Release()
    except KeyboardInterrupt:
        print(f"\n{tag}Stopped early by user.")
        if stop_event is not None:
            stop_event.set()

    elapsed = time.time() - t_start
    camera.StopGrabbing()
    camera.Close()

    if ts_file is not None:
        try:
            ts_file.close()
        except Exception:
            pass

    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"{tag}WARN: ffmpeg wouldn't finalize in 30s — killed")
    if proc.returncode not in (0, None):
        err = proc.stderr.read().decode(errors="replace")
        print(f"{tag}WARN: ffmpeg exit {proc.returncode}. stderr:\n"
              f"{err[-600:]}")

    actual_fps = frame_count / elapsed if elapsed > 0 else 0
    file_size_mb = (output_path.stat().st_size / (1024 * 1024)
                    if output_path.exists() else 0)
    print(f"{tag}Done: {frame_count} frames in {elapsed:.1f}s "
          f"(actual {actual_fps:.1f} fps)")
    print(f"{tag}Saved: {output_path} ({file_size_mb:.1f} MB)")
    return {"frame_count": frame_count, "elapsed_s": elapsed,
            "actual_fps": actual_fps, "output_path": output_path}


def record(camera_index: int, duration_sec: float, fps: float,
           output_path: Path) -> None:
    """Single-camera record (compat wrapper)."""
    _record_one(camera_index, duration_sec, fps, output_path,
                stop_event=None, label="")


def record_dual(duration_sec: float, fps: float, out_dir: Path,
                timestamp: str) -> None:
    """Record cam0 and cam1 in parallel threads, no Qt/no UI.

    Both threads start within microseconds of each other so the cameras
    free-run side-by-side under as little Python overhead as possible.
    This is the headless A/B test for whether the GUI grab thread is
    losing frames.
    """
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    if len(devices) < 2:
        print(f"ERROR: --dual needs 2 cameras, found {len(devices)}.")
        sys.exit(1)

    p0 = out_dir / f"valve_dual_cam0_{timestamp}.avi"
    p1 = out_dir / f"valve_dual_cam1_{timestamp}.avi"

    stop_event = threading.Event()
    results: dict[int, dict] = {}

    def worker(idx: int, path: Path) -> None:
        results[idx] = _record_one(idx, duration_sec, fps, path,
                                    stop_event=stop_event,
                                    label=f"cam{idx}")

    t0 = threading.Thread(target=worker, args=(0, p0), daemon=False)
    t1 = threading.Thread(target=worker, args=(1, p1), daemon=False)

    print(f"Starting dual-camera headless recording: {duration_sec}s @ {fps}fps")
    t0.start()
    t1.start()

    try:
        while t0.is_alive() or t1.is_alive():
            t0.join(timeout=0.5)
            t1.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nStopping both cameras...")
        stop_event.set()
        t0.join()
        t1.join()

    print("\n=== Dual recording summary ===")
    for idx in (0, 1):
        r = results.get(idx)
        if r is None:
            print(f"cam{idx}: no result")
            continue
        print(f"cam{idx}: {r['frame_count']} frames in {r['elapsed_s']:.1f}s "
              f"(actual {r['actual_fps']:.1f} fps)")
    if 0 in results and 1 in results:
        df = results[0]["frame_count"] - results[1]["frame_count"]
        print(f"frame count delta (cam0 - cam1): {df:+d}")
        print(f"\nCompare against GUI recording: pair timestamps by "
              f"hw_timestamp_ticks, not frame_index.")


def preview(video_path: Path, fps: float) -> None:
    """Play back a recorded clip. SPACE=pause, RIGHT=step, q=quit."""
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
        description="Record a short MJPG/AVI clip from one or both Basler "
                    "cameras (headless — no Qt).")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default: 0). Ignored with --dual.")
    parser.add_argument("--dual", action="store_true",
                        help="Record both cameras in parallel threads (headless A/B test vs GUI)")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Recording duration in seconds (default: 10)")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="Target frame rate (default: 30, matches GUI)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename (single-cam only; --dual auto-names)")
    parser.add_argument("--preview", action="store_true",
                        help="Play back recording after capture (single-cam only)")
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

    if args.dual:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_dir = Path(__file__).resolve().parent.parent / "outputs" / "videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        record_dual(args.duration, args.fps, out_dir, timestamp)
        return

    # Default output name: valve_cam0_20260417_191500.avi
    if args.output:
        filename = (args.output if args.output.endswith(".avi")
                    else args.output + ".avi")
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
