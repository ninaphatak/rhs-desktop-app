"""Diagnostic probe for the Basler recording pipeline.

READ-ONLY. Does not modify app code. Runs a series of instrumented
experiments to locate where frame rate and file-size problems originate.

Layers probed:
    1. Camera capability  — what the sensor advertises vs. resolves to
    2. Grab loop          — real grab rate, camera-side frame drops (BlockID gaps)
    3. Write loop         — MJPG write latency, does it block the grab?
    4. File on disk       — metadata fps vs. real frame count, bytes/frame
    5. BaslerCamera class — reproduce the target_fps / record_fps mismatch
    6. H.264 pipeline     — pipe frames to bundled ffmpeg (imageio-ffmpeg),
                            compare file size + encode latency vs MJPG

Each test prints its own section, and a summary table appears at the end.
Output files go to outputs/debug/ so they are isolated from real recordings.

Usage:
    python tools/record_debug.py                      # run everything (~90s)
    python tools/record_debug.py --duration 3         # shorter runs
    python tools/record_debug.py --test info          # camera probe only
    python tools/record_debug.py --test grab          # grab-only scenarios
    python tools/record_debug.py --test write         # grab + MJPG write
    python tools/record_debug.py --test class         # BaslerCamera class path
    python tools/record_debug.py --test h264          # grab + H.264 via ffmpeg
    python tools/record_debug.py --camera 1           # use second camera
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

try:
    from pypylon import pylon
except ImportError:
    print("ERROR: pypylon not installed.")
    sys.exit(1)

try:
    import imageio_ffmpeg
    IMAGEIO_FFMPEG_AVAILABLE = True
except ImportError:
    IMAGEIO_FFMPEG_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parent.parent
DEBUG_DIR = REPO_ROOT / "outputs" / "debug"


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """One row in the final summary table."""
    label: str
    scenario: str
    target_fps: float
    exposure_ms: float
    grab_fps: float = 0.0          # wall-clock grab rate
    write_fps: float = 0.0         # wall-clock write rate (if applicable)
    camera_drops: int = 0          # BlockID gaps (camera-side drops)
    grab_ms_mean: float = 0.0
    grab_ms_p95: float = 0.0
    write_ms_mean: float = 0.0
    write_ms_p95: float = 0.0
    file_fps_meta: float = 0.0     # fps stored in file header
    file_frames: int = 0
    file_mb: float = 0.0
    bytes_per_frame_kb: float = 0.0
    notes: str = ""


RESULTS: list[TestResult] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hr(title: str) -> None:
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")


def _kv(key: str, value) -> None:
    print(f"  {key:<34} {value}")


def _pctl(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    idx = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return sorted(xs)[idx]


def _open_camera(index: int) -> "pylon.InstantCamera":
    tl = pylon.TlFactory.GetInstance()
    devices = tl.EnumerateDevices()
    if not devices:
        print("ERROR: No Basler cameras found.")
        sys.exit(1)
    if index >= len(devices):
        print(f"ERROR: Camera index {index} of {len(devices)} not available.")
        sys.exit(1)
    cam = pylon.InstantCamera(tl.CreateDevice(devices[index]))
    cam.Open()
    return cam


def _configure(cam, exposure_us: int, fps: float) -> None:
    """Apply the same settings the app uses. Silent on failure."""
    try:
        cam.ExposureTime.SetValue(exposure_us)
    except Exception as e:
        print(f"  [warn] ExposureTime failed: {e}")
    try:
        cam.AcquisitionFrameRateEnable.SetValue(True)
        cam.AcquisitionFrameRate.SetValue(fps)
    except Exception as e:
        print(f"  [warn] AcquisitionFrameRate failed: {e}")
    try:
        cam.Gain.SetValue(18)
    except Exception:
        pass


def _read_back(path: Path) -> tuple[int, float, float]:
    """Open the written AVI and report (frame_count, fps_metadata, size_MB)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return (0, 0.0, 0.0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_meta = float(cap.get(cv2.CAP_PROP_FPS))
    cap.release()
    mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0.0
    return frames, fps_meta, mb


# ---------------------------------------------------------------------------
# Test 1: camera capability probe (no recording)
# ---------------------------------------------------------------------------

def test_camera_info(camera_index: int) -> None:
    _hr("TEST 1 — Camera capability probe")
    cam = _open_camera(camera_index)
    try:
        dev = cam.GetDeviceInfo()
        _kv("Device", dev.GetFriendlyName())
        try:
            _kv("Serial", dev.GetSerialNumber())
        except Exception:
            pass
        # Dimensions
        try:
            _kv("Sensor WxH",
                f"{cam.SensorWidth.GetValue()} x {cam.SensorHeight.GetValue()}")
        except Exception:
            pass
        try:
            _kv("Width / Height (current)",
                f"{cam.Width.GetValue()} x {cam.Height.GetValue()}")
        except Exception:
            pass
        try:
            _kv("PixelFormat", cam.PixelFormat.GetValue())
        except Exception:
            pass

        # Exposure bounds
        try:
            emin = cam.ExposureTime.GetMin()
            emax = cam.ExposureTime.GetMax()
            ecur = cam.ExposureTime.GetValue()
            _kv("ExposureTime (min/cur/max µs)",
                f"{emin:.0f} / {ecur:.0f} / {emax:.0f}")
            # Theoretical fps ceiling due to exposure alone
            _kv("Exposure-limited FPS ceiling",
                f"{1_000_000 / ecur:.2f} fps (at current exposure {ecur/1000:.1f} ms)")
        except Exception as e:
            _kv("ExposureTime", f"unreadable: {e}")

        # Frame rate bounds
        try:
            cam.AcquisitionFrameRateEnable.SetValue(True)
            fmin = cam.AcquisitionFrameRate.GetMin()
            fmax = cam.AcquisitionFrameRate.GetMax()
            fcur = cam.AcquisitionFrameRate.GetValue()
            _kv("AcquisitionFrameRate (min/cur/max)",
                f"{fmin:.2f} / {fcur:.2f} / {fmax:.2f} fps")
        except Exception as e:
            _kv("AcquisitionFrameRate", f"unreadable: {e}")

        # ResultingFrameRate = the real fps the camera will produce
        try:
            _kv("ResultingFrameRate (real ceiling)",
                f"{cam.ResultingFrameRate.GetValue():.2f} fps")
        except Exception as e:
            _kv("ResultingFrameRate", f"unreadable: {e}")

        try:
            _kv("Gain", f"{cam.Gain.GetValue():.1f}")
        except Exception:
            pass
    finally:
        if cam.IsOpen():
            cam.Close()


# ---------------------------------------------------------------------------
# Test 2: grab-only (no writer, no BaslerCamera class)
# ---------------------------------------------------------------------------

def test_grab_only(camera_index: int, duration_s: float,
                   target_fps: float, exposure_us: int,
                   strategy: str = "latest") -> None:
    """Measure the raw grab rate without any writing.

    strategy: "latest" (LatestImageOnly — app default) or
              "queue"  (OneByOne — buffers frames, exposes true drop count)
    """
    scenario = f"grab/{strategy} fps={target_fps:g} exp={exposure_us/1000:g}ms"
    _hr(f"TEST 2 — {scenario}")

    cam = _open_camera(camera_index)
    _configure(cam, exposure_us, target_fps)

    try:
        _kv("ResultingFrameRate (post-config)",
            f"{cam.ResultingFrameRate.GetValue():.2f} fps")
    except Exception:
        pass

    grab_ms: list[float] = []
    block_ids: list[int] = []
    strat = (pylon.GrabStrategy_LatestImageOnly if strategy == "latest"
             else pylon.GrabStrategy_OneByOne)

    cam.StartGrabbing(strat)
    t0 = time.time()
    frames = 0
    interval = 1.0 / target_fps
    try:
        while time.time() - t0 < duration_s:
            t_g = time.time()
            timeout_ms = int(exposure_us / 1000) + 1000
            grab = cam.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                try:
                    block_ids.append(int(grab.GetBlockID()))
                except Exception:
                    pass
                _ = grab.Array  # force materialize
                grab.Release()
                frames += 1
                grab_ms.append((time.time() - t_g) * 1000)
                # Same pacing as the app — sleep any leftover of the frame interval
                remain = interval - (time.time() - t_g)
                if remain > 0:
                    time.sleep(remain)
            elif grab:
                grab.Release()
    finally:
        cam.StopGrabbing()
        cam.Close()

    elapsed = time.time() - t0
    grab_fps = frames / elapsed if elapsed > 0 else 0.0

    # camera-side drops = BlockID gaps
    drops = 0
    if len(block_ids) >= 2:
        for a, b in zip(block_ids, block_ids[1:]):
            if b > a + 1:
                drops += (b - a - 1)

    _kv("Wall-clock elapsed", f"{elapsed:.2f}s")
    _kv("Frames grabbed", frames)
    _kv("Grab rate (wall clock)", f"{grab_fps:.2f} fps")
    _kv("Camera-side drops (BlockID gaps)", drops)
    if grab_ms:
        _kv("Per-grab ms (mean / p95 / max)",
            f"{statistics.mean(grab_ms):.2f} / "
            f"{_pctl(grab_ms, 95):.2f} / {max(grab_ms):.2f}")

    RESULTS.append(TestResult(
        label="grab-only",
        scenario=scenario,
        target_fps=target_fps,
        exposure_ms=exposure_us / 1000,
        grab_fps=grab_fps,
        camera_drops=drops,
        grab_ms_mean=statistics.mean(grab_ms) if grab_ms else 0.0,
        grab_ms_p95=_pctl(grab_ms, 95),
        notes=f"strategy={strategy}",
    ))


# ---------------------------------------------------------------------------
# Test 3: full pipeline (grab + MJPG write, like record_valve.py does)
# ---------------------------------------------------------------------------

def test_full_pipeline(camera_index: int, duration_s: float,
                       target_fps: float, exposure_us: int,
                       writer_fps: Optional[float] = None) -> None:
    """Grab + MJPG write. Instruments each frame's grab AND write ms.

    writer_fps defaults to target_fps. Pass a different value to
    reproduce the container-metadata-mismatch bug.
    """
    if writer_fps is None:
        writer_fps = target_fps

    scenario = (f"write camFps={target_fps:g} writerFps={writer_fps:g} "
                f"exp={exposure_us/1000:g}ms")
    _hr(f"TEST 3 — {scenario}")

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    out = DEBUG_DIR / f"probe_{int(target_fps)}x{int(writer_fps)}_{stamp}.avi"

    cam = _open_camera(camera_index)
    _configure(cam, exposure_us, target_fps)

    # Grab first frame for dimensions
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    first = cam.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
    if not first.GrabSucceeded():
        print("ERROR: first frame grab failed")
        cam.Close()
        return
    frame0 = first.Array.copy()
    first.Release()
    h, w = frame0.shape[:2]
    is_mono = frame0.ndim == 2

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(out), fourcc, writer_fps, (w, h),
                             isColor=not is_mono)
    if not writer.isOpened():
        print("ERROR: VideoWriter did not open")
        cam.StopGrabbing()
        cam.Close()
        return

    # Write the primed first frame
    t_w = time.time()
    writer.write(frame0)
    write_ms: list[float] = [(time.time() - t_w) * 1000]
    grab_ms: list[float] = []
    block_ids: list[int] = []
    frames = 1
    interval = 1.0 / target_fps

    t0 = time.time()
    try:
        while time.time() - t0 < duration_s:
            t_g = time.time()
            timeout_ms = int(exposure_us / 1000) + 1000
            grab = cam.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                try:
                    block_ids.append(int(grab.GetBlockID()))
                except Exception:
                    pass
                frame = grab.Array.copy()
                grab.Release()
                grab_ms.append((time.time() - t_g) * 1000)

                t_w = time.time()
                writer.write(frame)
                write_ms.append((time.time() - t_w) * 1000)
                frames += 1

                remain = interval - (time.time() - t_g)
                if remain > 0:
                    time.sleep(remain)
            elif grab:
                grab.Release()
    finally:
        cam.StopGrabbing()
        cam.Close()
        writer.release()

    elapsed = time.time() - t0
    real_fps = frames / elapsed if elapsed > 0 else 0.0

    drops = 0
    if len(block_ids) >= 2:
        for a, b in zip(block_ids, block_ids[1:]):
            if b > a + 1:
                drops += (b - a - 1)

    file_frames, file_meta_fps, file_mb = _read_back(out)
    bpf_kb = (file_mb * 1024 / file_frames) if file_frames else 0.0

    _kv("Output", out.relative_to(REPO_ROOT))
    _kv("Wall-clock elapsed", f"{elapsed:.2f}s")
    _kv("Frames written", frames)
    _kv("Wall-clock fps", f"{real_fps:.2f}")
    _kv("Camera-side drops (BlockID gaps)", drops)
    if grab_ms:
        _kv("Per-grab ms (mean / p95 / max)",
            f"{statistics.mean(grab_ms):.2f} / "
            f"{_pctl(grab_ms, 95):.2f} / {max(grab_ms):.2f}")
    if write_ms:
        _kv("Per-write ms (mean / p95 / max)",
            f"{statistics.mean(write_ms):.2f} / "
            f"{_pctl(write_ms, 95):.2f} / {max(write_ms):.2f}")
    _kv("File fps metadata", f"{file_meta_fps:.2f}")
    _kv("File frame count (readback)", file_frames)
    _kv("File size", f"{file_mb:.1f} MB  ({bpf_kb:.1f} KB/frame)")
    if file_meta_fps > 0 and abs(file_meta_fps - real_fps) > 1.0:
        _kv("!! MISMATCH",
            f"metadata says {file_meta_fps:.1f} fps, "
            f"real rate was {real_fps:.1f} fps → playback will be wrong-speed")

    RESULTS.append(TestResult(
        label="full",
        scenario=scenario,
        target_fps=target_fps,
        exposure_ms=exposure_us / 1000,
        grab_fps=real_fps,
        write_fps=real_fps,
        camera_drops=drops,
        grab_ms_mean=statistics.mean(grab_ms) if grab_ms else 0.0,
        grab_ms_p95=_pctl(grab_ms, 95),
        write_ms_mean=statistics.mean(write_ms) if write_ms else 0.0,
        write_ms_p95=_pctl(write_ms, 95),
        file_fps_meta=file_meta_fps,
        file_frames=file_frames,
        file_mb=file_mb,
        bytes_per_frame_kb=bpf_kb,
        notes=f"writerFps={writer_fps:g}",
    ))


# ---------------------------------------------------------------------------
# Test 3b: H.264 pipeline via imageio-ffmpeg (bundled ffmpeg, cross-OS)
# ---------------------------------------------------------------------------

def test_h264_pipeline(camera_index: int, duration_s: float,
                       target_fps: float, exposure_us: int,
                       crf: int = 18, preset: str = "fast") -> None:
    """Grab + pipe raw frames to ffmpeg (libx264) via stdin.

    Compares H.264 encode latency and file size to the MJPG pipeline.
    Uses imageio_ffmpeg.get_ffmpeg_exe() so the test works on macOS/Windows
    without a system ffmpeg install.
    """
    if not IMAGEIO_FFMPEG_AVAILABLE:
        print("SKIP: imageio-ffmpeg not installed. "
              "Run: pip install imageio-ffmpeg")
        return

    scenario = (f"h264 crf={crf} preset={preset} camFps={target_fps:g} "
                f"exp={exposure_us/1000:g}ms")
    _hr(f"TEST 3b — {scenario}")

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    out = DEBUG_DIR / f"probe_h264_crf{crf}_{int(target_fps)}fps_{stamp}.mp4"

    cam = _open_camera(camera_index)
    _configure(cam, exposure_us, target_fps)

    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    first = cam.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
    if not first.GrabSucceeded():
        print("ERROR: first frame grab failed")
        cam.Close()
        return
    frame0 = first.Array.copy()
    first.Release()
    h, w = frame0.shape[:2]
    is_mono = frame0.ndim == 2

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",                                  # overwrite
        "-hide_banner", "-loglevel", "error",  # quiet but keep errors
        "-f", "rawvideo",                      # input is raw pixels
        "-pix_fmt", "gray" if is_mono else "bgr24",
        "-s", f"{w}x{h}",
        "-r", f"{target_fps:g}",               # input fps
        "-i", "-",                             # read from stdin
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",                 # playback-compatible output
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    # Pipe first frame
    t_w = time.time()
    proc.stdin.write(frame0.tobytes())
    write_ms: list[float] = [(time.time() - t_w) * 1000]
    grab_ms: list[float] = []
    block_ids: list[int] = []
    frames = 1
    interval = 1.0 / target_fps

    t0 = time.time()
    try:
        while time.time() - t0 < duration_s:
            t_g = time.time()
            timeout_ms = int(exposure_us / 1000) + 1000
            grab = cam.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                try:
                    block_ids.append(int(grab.GetBlockID()))
                except Exception:
                    pass
                frame = grab.Array  # tobytes() copies, no need to .copy()
                grab.Release()
                grab_ms.append((time.time() - t_g) * 1000)

                t_w = time.time()
                try:
                    proc.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    err = proc.stderr.read().decode(errors="replace")
                    print(f"ERROR: ffmpeg stdin closed. stderr:\n{err}")
                    break
                write_ms.append((time.time() - t_w) * 1000)
                frames += 1

                remain = interval - (time.time() - t_g)
                if remain > 0:
                    time.sleep(remain)
            elif grab:
                grab.Release()
    finally:
        cam.StopGrabbing()
        cam.Close()
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
        print(f"WARN: ffmpeg exit {proc.returncode}. stderr tail:\n"
              f"{err[-600:]}")

    elapsed = time.time() - t0
    real_fps = frames / elapsed if elapsed > 0 else 0.0

    drops = 0
    if len(block_ids) >= 2:
        for a, b in zip(block_ids, block_ids[1:]):
            if b > a + 1:
                drops += (b - a - 1)

    file_frames, file_meta_fps, file_mb = _read_back(out)
    bpf_kb = (file_mb * 1024 / file_frames) if file_frames else 0.0

    _kv("Output", out.relative_to(REPO_ROOT))
    _kv("ffmpeg binary", ffmpeg_exe)
    _kv("Wall-clock elapsed", f"{elapsed:.2f}s")
    _kv("Frames piped", frames)
    _kv("Wall-clock fps", f"{real_fps:.2f}")
    _kv("Camera-side drops (BlockID gaps)", drops)
    if grab_ms:
        _kv("Per-grab ms (mean / p95 / max)",
            f"{statistics.mean(grab_ms):.2f} / "
            f"{_pctl(grab_ms, 95):.2f} / {max(grab_ms):.2f}")
    if write_ms:
        _kv("Per-pipe-write ms (mean / p95 / max)",
            f"{statistics.mean(write_ms):.2f} / "
            f"{_pctl(write_ms, 95):.2f} / {max(write_ms):.2f}")
    _kv("File fps metadata", f"{file_meta_fps:.2f}")
    _kv("File frame count (readback)", file_frames)
    _kv("File size", f"{file_mb:.2f} MB  ({bpf_kb:.1f} KB/frame)")

    RESULTS.append(TestResult(
        label="h264",
        scenario=scenario,
        target_fps=target_fps,
        exposure_ms=exposure_us / 1000,
        grab_fps=real_fps,
        write_fps=real_fps,
        camera_drops=drops,
        grab_ms_mean=statistics.mean(grab_ms) if grab_ms else 0.0,
        grab_ms_p95=_pctl(grab_ms, 95),
        write_ms_mean=statistics.mean(write_ms) if write_ms else 0.0,
        write_ms_p95=_pctl(write_ms, 95),
        file_fps_meta=file_meta_fps,
        file_frames=file_frames,
        file_mb=file_mb,
        bytes_per_frame_kb=bpf_kb,
        notes=f"crf={crf} preset={preset}",
    ))


# ---------------------------------------------------------------------------
# Test 4: BaslerCamera class path (reproduces the target_fps/record_fps bug)
# ---------------------------------------------------------------------------

def test_basler_class(camera_index: int, duration_s: float,
                      target_fps: float, record_fps: float,
                      exposure_us: int) -> None:
    """Drive src/core/basler_camera.BaslerCamera headlessly.

    Passes target_fps (camera config) and record_fps (VideoWriter) separately
    to reproduce the mismatch suspected in the class.
    """
    scenario = (f"class target_fps={target_fps:g} record_fps={record_fps:g} "
                f"exp={exposure_us/1000:g}ms")
    _hr(f"TEST 4 — {scenario}")

    # Lazy import (PySide6 may not be strictly required for other tests)
    sys.path.insert(0, str(REPO_ROOT))
    from PySide6.QtCore import QCoreApplication, QTimer  # type: ignore
    from src.core.basler_camera import BaslerCamera  # type: ignore

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    out = DEBUG_DIR / f"probe_class_t{int(target_fps)}_r{int(record_fps)}_{stamp}.avi"

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    cam = BaslerCamera()
    cam.target_fps = target_fps
    cam.exposure_us = exposure_us

    counter = {"n": 0, "t_first": None, "t_last": None}

    def on_frame(data: dict) -> None:
        if counter["t_first"] is None:
            counter["t_first"] = time.time()
        counter["n"] += 1
        counter["t_last"] = time.time()

    cam.frame_ready.connect(on_frame)

    ok = cam.connect(camera_index)
    if not ok:
        print("ERROR: BaslerCamera.connect failed")
        return

    # duration_sec argument to start_recording interacts with record_fps
    # (max_frames = duration_sec * record_fps). Use a large value so that we
    # stop on wall-clock, not on frame count — this is what we want for diag.
    cam.start_recording(out, duration_sec=duration_s * 10, fps=record_fps)
    cam.start()

    QTimer.singleShot(int(duration_s * 1000), cam.stop_recording)
    QTimer.singleShot(int((duration_s + 0.5) * 1000),
                      lambda: (cam.stop(), cam.disconnect(), app.quit()))
    app.exec()

    elapsed = ((counter["t_last"] - counter["t_first"])
               if counter["t_first"] else 0.0)
    wall_fps = counter["n"] / elapsed if elapsed > 0 else 0.0

    file_frames, file_meta_fps, file_mb = _read_back(out)
    bpf_kb = (file_mb * 1024 / file_frames) if file_frames else 0.0

    _kv("Output", out.relative_to(REPO_ROOT))
    _kv("Frames emitted by class", counter["n"])
    _kv("Wall-clock elapsed", f"{elapsed:.2f}s")
    _kv("Wall-clock fps", f"{wall_fps:.2f}")
    _kv("File fps metadata (what it claims)", f"{file_meta_fps:.2f}")
    _kv("File frame count (readback)", file_frames)
    _kv("File size", f"{file_mb:.1f} MB  ({bpf_kb:.1f} KB/frame)")
    if file_meta_fps > 0 and abs(file_meta_fps - wall_fps) > 1.0:
        _kv("!! CLASS BUG REPRODUCED",
            f"writer says {file_meta_fps:.1f} fps, "
            f"real rate {wall_fps:.1f} fps → playback wrong speed")

    RESULTS.append(TestResult(
        label="class",
        scenario=scenario,
        target_fps=target_fps,
        exposure_ms=exposure_us / 1000,
        grab_fps=wall_fps,
        write_fps=wall_fps,
        file_fps_meta=file_meta_fps,
        file_frames=file_frames,
        file_mb=file_mb,
        bytes_per_frame_kb=bpf_kb,
        notes=f"recordFps={record_fps:g}",
    ))


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def print_summary() -> None:
    if not RESULTS:
        return
    _hr("SUMMARY")
    fmt = ("{label:<10} {scenario:<54} "
           "{grab:>6} {writef:>7} {drops:>6} "
           "{gms:>7} {wms:>7} {fmeta:>6} {fcount:>7} {mb:>6} {kbpf:>7}")
    print(fmt.format(
        label="test", scenario="scenario",
        grab="grabFs", writef="fileFps", drops="drops",
        gms="grabMs", wms="writeMs", fmeta="meta",
        fcount="frames", mb="MB", kbpf="KB/fr"))
    print("-" * 135)
    for r in RESULTS:
        print(fmt.format(
            label=r.label,
            scenario=r.scenario[:54],
            grab=f"{r.grab_fps:.1f}",
            writef=(f"{r.file_fps_meta:.1f}" if r.file_fps_meta else "-"),
            drops=str(r.camera_drops),
            gms=f"{r.grab_ms_mean:.1f}",
            wms=(f"{r.write_ms_mean:.1f}" if r.write_ms_mean else "-"),
            fmeta=(f"{r.file_fps_meta:.0f}" if r.file_fps_meta else "-"),
            fcount=(str(r.file_frames) if r.file_frames else "-"),
            mb=(f"{r.file_mb:.1f}" if r.file_mb else "-"),
            kbpf=(f"{r.bytes_per_frame_kb:.0f}" if r.bytes_per_frame_kb else "-"),
        ))
    print()
    print("Legend:")
    print("  grabFs   = real wall-clock grab/emit rate")
    print("  fileFps  = fps stored in the AVI file header")
    print("  drops    = camera-side drops (BlockID gaps — frames the camera")
    print("             made but the code never saw)")
    print("  grabMs   = mean per-frame grab time (incl. copy)")
    print("  writeMs  = mean per-frame MJPG writer.write() time")
    print("  meta vs grabFs mismatch = playback speed will be wrong")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--duration", type=float, default=5.0,
                    help="seconds per recording test (default: 5)")
    ap.add_argument("--test",
                    choices=["all", "info", "grab", "write", "class", "h264"],
                    default="all")
    args = ap.parse_args()

    print(f"RHS recording-pipeline probe — camera {args.camera}, "
          f"{args.duration:g}s per test")

    if args.test in ("all", "info"):
        test_camera_info(args.camera)

    if args.test in ("all", "grab"):
        # Scenario A: app's current defaults (30 fps, 25ms exposure, LatestImageOnly)
        test_grab_only(args.camera, args.duration,
                       target_fps=30, exposure_us=25000, strategy="latest")
        # Scenario B: OneByOne — exposes true drops instead of hiding them
        test_grab_only(args.camera, args.duration,
                       target_fps=30, exposure_us=25000, strategy="queue")
        # Scenario C: ask for 60 fps at current exposure — should hit ceiling
        test_grab_only(args.camera, args.duration,
                       target_fps=60, exposure_us=25000, strategy="latest")
        # Scenario D: drop exposure to unlock higher fps
        test_grab_only(args.camera, args.duration,
                       target_fps=60, exposure_us=10000, strategy="latest")

    if args.test in ("all", "write"):
        # Scenario E: matched fps, app defaults
        test_full_pipeline(args.camera, args.duration,
                           target_fps=30, exposure_us=25000)
        # Scenario F: mismatched fps — cam=30, writer=60 (reproduces file-metadata lie)
        test_full_pipeline(args.camera, args.duration,
                           target_fps=30, exposure_us=25000, writer_fps=60)
        # Scenario G: lower exposure + matched 60 — can the whole pipeline keep up?
        test_full_pipeline(args.camera, args.duration,
                           target_fps=60, exposure_us=10000)

    # H.264 tests run before the class test because the class test has a
    # known race that can segfault — don't want to lose H.264 numbers to it.
    if args.test in ("all", "h264"):
        # Scenario J: H.264 CRF 18 (visually lossless archival default) at best config
        test_h264_pipeline(args.camera, args.duration,
                           target_fps=60, exposure_us=10000, crf=18)
        # Scenario K: H.264 CRF 15 (near-mathematically-lossless) — quality upper bound
        test_h264_pipeline(args.camera, args.duration,
                           target_fps=60, exposure_us=10000, crf=15)
        # Scenario L: H.264 CRF 18 at the app's current default (30fps / 25ms)
        test_h264_pipeline(args.camera, args.duration,
                           target_fps=30, exposure_us=25000, crf=18)

    if args.test in ("all", "class"):
        # Scenario H: exactly the class bug hypothesis
        #   target_fps=30 (class default) + record_fps=60 (common caller value)
        test_basler_class(args.camera, args.duration,
                          target_fps=30, record_fps=60, exposure_us=25000)
        # Scenario I: class with matched values (control)
        test_basler_class(args.camera, args.duration,
                          target_fps=30, record_fps=30, exposure_us=25000)

    print_summary()


if __name__ == "__main__":
    main()
