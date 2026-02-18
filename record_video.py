"""
Record video from a Basler camera.

Usage:
    python record_video.py                     # record 10s as .avi
    python record_video.py --duration 30       # record for 30 seconds
    python record_video.py --fps 60 --output my_video.avi
    python record_video.py --exposure 25000    # set exposure in microseconds
    python record_video.py --raw               # save lossless PNGs instead of video

Press Ctrl+C to stop recording early.
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from pypylon import pylon


def _connect_camera(fps: int, exposure_us: int, gain: float):
    """Find and configure the first available Basler camera."""
    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    if not devices:
        print("No Basler cameras found.")
        return None

    camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[0]))
    camera.Open()
    print(f"Connected to: {devices[0].GetFriendlyName()}")

    camera.ExposureTime.SetValue(exposure_us)
    try:
        camera.AcquisitionFrameRateEnable.SetValue(True)
        camera.AcquisitionFrameRate.SetValue(fps)
    except Exception:
        print("Warning: could not set frame rate, using camera default")
    try:
        camera.Gain.SetValue(gain)
    except Exception:
        print(f"Warning: could not set gain to {gain}")

    width = camera.Width.GetValue()
    height = camera.Height.GetValue()
    print(f"Resolution: {width}x{height}, target FPS: {fps}, exposure: {exposure_us}µs")
    return camera


def record_video(output: str, duration: float, fps: int, exposure_us: int, gain: float) -> None:
    """Record video as compressed .avi using MJPG codec."""
    camera = _connect_camera(fps, exposure_us, gain)
    if camera is None:
        return

    width = camera.Width.GetValue()
    height = camera.Height.GetValue()

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height), isColor=False)

    if not writer.isOpened():
        print("Error: could not open video writer")
        camera.Close()
        return

    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    frame_count = 0
    start_time = time.time()

    print(f"Recording video for {duration}s — press Ctrl+C to stop early...")
    try:
        while camera.IsGrabbing():
            elapsed = time.time() - start_time
            if elapsed >= duration:
                break

            grab = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                frame = grab.Array
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                writer.write(frame_bgr)
                frame_count += 1

                if frame_count % fps == 0:
                    print(f"  {elapsed:.1f}s — {frame_count} frames")
            grab.Release()

    except KeyboardInterrupt:
        print("\nStopped early by user.")

    elapsed = time.time() - start_time
    camera.StopGrabbing()
    camera.Close()
    writer.release()

    actual_fps = frame_count / elapsed if elapsed > 0 else 0
    print(f"\nDone — saved {frame_count} frames ({elapsed:.1f}s, {actual_fps:.1f} fps) to {output_path}")


def record_raw(output_dir: str, duration: float, fps: int, exposure_us: int, gain: float) -> None:
    """Record lossless PNG frames to a directory."""
    camera = _connect_camera(fps, exposure_us, gain)
    if camera is None:
        return

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    frame_count = 0
    start_time = time.time()

    print(f"Recording raw frames for {duration}s — press Ctrl+C to stop early...")
    try:
        while camera.IsGrabbing():
            elapsed = time.time() - start_time
            if elapsed >= duration:
                break

            grab = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                frame = grab.Array
                cv2.imwrite(str(out / f"frame_{frame_count:06d}.png"), frame)
                frame_count += 1

                if frame_count % fps == 0:
                    print(f"  {elapsed:.1f}s — {frame_count} frames")
            grab.Release()

    except KeyboardInterrupt:
        print("\nStopped early by user.")

    elapsed = time.time() - start_time
    camera.StopGrabbing()
    camera.Close()

    actual_fps = frame_count / elapsed if elapsed > 0 else 0
    print(f"\nDone — saved {frame_count} PNGs ({elapsed:.1f}s, {actual_fps:.1f} fps) to {out}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record video from a Basler camera")
    parser.add_argument("--output", "-o", default="output/recording.avi", help="Output file path")
    parser.add_argument("--duration", "-d", type=float, default=10.0, help="Recording duration in seconds")
    parser.add_argument("--fps", type=int, default=30, help="Target frame rate")
    parser.add_argument("--exposure", type=int, default=25000, help="Exposure time in microseconds")
    parser.add_argument("--gain", type=float, default=18.0, help="Camera gain")
    parser.add_argument("--raw", action="store_true", help="Save lossless PNGs instead of compressed video")
    args = parser.parse_args()

    if args.raw:
        # Default raw output to a directory (strip file extension if given)
        raw_dir = Path(args.output).with_suffix("") if args.output != "output/recording.avi" else Path("output/raw_frames")
        record_raw(str(raw_dir), args.duration, args.fps, args.exposure, args.gain)
    else:
        record_video(args.output, args.duration, args.fps, args.exposure, args.gain)
