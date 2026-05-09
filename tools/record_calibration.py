"""Standalone calibration-clip recorder for both Basler cameras.

Records a short FFV1/AVI clip from each connected Basler camera
simultaneously and writes them to outputs/videos/. Bypasses the GUI —
intended for one-off lab capture sessions where you just need a few
clean frames of the calibration object in the chamber.

Usage:
    python tools/record_calibration.py water
    python tools/record_calibration.py analog --duration 5
    python tools/record_calibration.py water --duration 10 --camera 0
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.basler_camera import _spawn_ffmpeg

try:
    from pypylon import pylon
except ImportError:
    print("ERROR: pypylon not installed. Activate the rhs-app conda env.")
    sys.exit(1)


TARGET_FPS = 30
EXPOSURE_US = 25000
GAIN = 18


def _configure(camera: "pylon.InstantCamera") -> None:
    """Match the configuration used by src/core/basler_camera.py."""
    camera.ExposureTime.SetValue(EXPOSURE_US)
    try:
        camera.AcquisitionFrameRateEnable.SetValue(True)
        camera.AcquisitionFrameRate.SetValue(TARGET_FPS)
    except Exception:
        pass
    try:
        camera.Gain.SetValue(GAIN)
    except Exception:
        pass


def _record_one(device, out_path: Path, duration_sec: float, cam_idx: int) -> None:
    """Open one camera, grab for duration_sec, write FFV1/AVI to out_path.

    Also writes a sidecar `<out_path>.timestamps.csv` with one row per frame:
        frame_index, system_time_s, hw_timestamp_ticks
    Used to characterize inter-camera timing offset post-hoc.
    """
    camera = pylon.InstantCamera(device)
    camera.Open()
    _configure(camera)

    proc = None
    frame_interval = 1.0 / TARGET_FPS
    written = 0
    deadline = time.time() + duration_sec

    ts_path = out_path.with_suffix(out_path.suffix + ".timestamps.csv")
    ts_file = open(ts_path, "w", newline="")
    ts_file.write("frame_index,system_time_s,hw_timestamp_ticks\n")

    try:
        camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        while time.time() < deadline and camera.IsGrabbing():
            frame_start = time.time()
            timeout_ms = int(EXPOSURE_US / 1000) + 1000
            grab = camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                frame = grab.Array
                sys_time = time.time()
                try:
                    hw_ts = int(grab.GetTimeStamp())
                except Exception:
                    hw_ts = -1  # camera doesn't expose timestamp
                if proc is None:
                    h, w = frame.shape[:2]
                    proc = _spawn_ffmpeg(out_path, w, h, is_mono=True, fps=TARGET_FPS)
                    if proc is None:
                        print(f"[cam{cam_idx}] failed to spawn ffmpeg")
                        grab.Release()
                        return
                    print(f"[cam{cam_idx}] recording started: {w}x{h} -> {out_path}")
                try:
                    proc.stdin.write(frame.tobytes())
                    ts_file.write(f"{written},{sys_time:.6f},{hw_ts}\n")
                    written += 1
                except (BrokenPipeError, OSError) as e:
                    print(f"[cam{cam_idx}] ffmpeg stdin write failed: {e}")
                    grab.Release()
                    break
                grab.Release()
                elapsed = time.time() - frame_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
            elif grab:
                grab.Release()
    finally:
        if camera.IsGrabbing():
            camera.StopGrabbing()
        if proc is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.wait(timeout=30)
        ts_file.close()
        camera.Close()
        print(f"[cam{cam_idx}] wrote {written} frames -> {out_path}")
        print(f"[cam{cam_idx}] timestamps -> {ts_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", help="Fluid label, e.g. 'water' or 'analog'.")
    parser.add_argument("--duration", type=float, default=5.0,
                        help="Seconds to record from each camera (default 5).")
    parser.add_argument("--camera", type=int, default=None,
                        help="Restrict to a single camera index (default: all).")
    parser.add_argument("--out-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "outputs" / "videos",
                        help="Output directory (default: outputs/videos/).")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    devices = pylon.TlFactory.GetInstance().EnumerateDevices()
    if not devices:
        print("No Basler cameras detected.")
        sys.exit(1)

    if args.camera is not None:
        if args.camera >= len(devices):
            print(f"Camera index {args.camera} not found ({len(devices)} connected).")
            sys.exit(1)
        targets = [(args.camera, devices[args.camera])]
    else:
        targets = list(enumerate(devices))

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"Recording {args.duration:g}s from {len(targets)} camera(s) "
          f"(label='{args.label}', timestamp={ts})...")

    threads = []
    for idx, dev in targets:
        out_path = args.out_dir / f"calib_{args.label}_{ts}_cam{idx}.avi"
        t = threading.Thread(target=_record_one,
                             args=(dev, out_path, args.duration, idx))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    print("Done.")


if __name__ == "__main__":
    main()
