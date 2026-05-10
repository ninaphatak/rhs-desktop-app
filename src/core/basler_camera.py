"""QThread-based Basler camera interface using pypylon (PySide6).

Recording writes MJPG/AVI via a piped ffmpeg subprocess (bundled by
imageio-ffmpeg for cross-OS support). The grab loop writes raw frames
into ffmpeg's stdin; ffmpeg encodes per-frame JPEG (intra-only by
construction) into the .avi container. MJPG is technically lossy but
visually lossless at -q:v 2; trade-off vs FFV1 (which we used briefly)
is much faster encode — FFV1 was averaging ~38ms per frame which
exceeded the 33ms grab budget at 30fps and dropped actual capture to
~26 fps with high jitter. MJPG encodes in ~3-5ms per frame, hitting
true 30fps and reducing inter-camera sync residual from ~10ms median
to ~16ms bounded (still bounded by the cameras being free-running, not
hardware-triggered — that's the eventual fix).
"""

import json
import subprocess
import threading
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from PySide6.QtCore import QThread, Signal

try:
    from pypylon import pylon
    PYPYLON_AVAILABLE = True
except ImportError:
    PYPYLON_AVAILABLE = False
    pylon = None

try:
    import imageio_ffmpeg
    IMAGEIO_FFMPEG_AVAILABLE = True
except ImportError:
    IMAGEIO_FFMPEG_AVAILABLE = False

logger = logging.getLogger(__name__)

MJPG_QUALITY = 2    # ffmpeg -q:v scale: 1=best, 31=worst; 2 is visually lossless


def _spawn_ffmpeg(output_path: Path, width: int, height: int, is_mono: bool,
                  fps: float) -> Optional[subprocess.Popen]:
    """Spawn ffmpeg reading raw frames from stdin, writing MJPG/AVI."""
    if not IMAGEIO_FFMPEG_AVAILABLE:
        logger.error("imageio-ffmpeg not installed — cannot record")
        return None
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "rawvideo",
        "-pix_fmt", "gray" if is_mono else "bgr24",
        "-s", f"{width}x{height}",
        "-r", f"{fps:g}",
        "-i", "-",
        "-c:v", "mjpeg",
        "-q:v", str(MJPG_QUALITY),
        "-pix_fmt", "yuvj420p",  # mjpeg encoder requires YUV; ffmpeg auto-converts from gray
        str(output_path),
    ]
    # stderr goes to the terminal so ffmpeg's actual error message is visible
    # if it crashes (otherwise BrokenPipeError on stdin write hides the cause).
    try:
        return subprocess.Popen(cmd, stdin=subprocess.PIPE)
    except OSError as e:
        logger.error(f"Failed to spawn ffmpeg: {e}")
        return None


class BaslerCamera(QThread):
    """Threaded Basler camera — grabs latest frame and emits it.

    Uses GrabStrategy_LatestImageOnly for real-time monitoring.
    """

    frame_ready = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    recording_finished = Signal(str)  # emits output path when done

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._camera: Optional["pylon.InstantCamera"] = None
        self._running = False
        self._connected = False
        self.target_fps = 30
        self.exposure_us = 25000
        self._frame_count = 0
        # Recording state. Accessed from both the grab thread (_write_frame)
        # and whatever thread calls stop_recording — serialize via lock.
        self._writer_lock = threading.Lock()
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._record_path: Optional[Path] = None
        self._record_fps: float = 30.0
        self._record_max_frames: int = 0
        self._record_frame_count: int = 0
        # Per-frame timestamp sidecar — paired with the AVI for sync analysis
        # and the temporal-interpolation feature in tools/triangulate.py
        self._ts_file: Optional[TextIO] = None

    @staticmethod
    def list_cameras() -> list[str]:
        """Get list of connected Basler camera names."""
        if not PYPYLON_AVAILABLE:
            return []
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            return [d.GetFriendlyName() for d in devices]
        except Exception as e:
            logger.error(f"Error enumerating cameras: {e}")
            return []

    def connect(self, index: int = 0) -> bool:
        """Connect to camera by index."""
        if not PYPYLON_AVAILABLE:
            self.error_occurred.emit("pypylon not installed")
            return False
        if self._connected:
            self.disconnect()
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if index >= len(devices):
                self.error_occurred.emit(f"Camera index {index} not found")
                return False
            self._camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[index]))
            self._camera.Open()
            self._configure()
            self._connected = True
            self.connection_changed.emit(True)
            logger.info(f"Connected to: {devices[index].GetFriendlyName()}")
            return True
        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {e}")
            return False

    def _configure(self) -> None:
        if not self._camera or not self._camera.IsOpen():
            return
        try:
            self._camera.ExposureTime.SetValue(self.exposure_us)
            try:
                self._camera.AcquisitionFrameRateEnable.SetValue(True)
                self._camera.AcquisitionFrameRate.SetValue(self.target_fps)
            except Exception:
                pass
            try:
                self._camera.Gain.SetValue(18)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Could not configure camera: {e}")

    def start_recording(self, output_path: Path, duration_sec: float = 10.0,
                        fps: Optional[float] = None) -> None:
        """Begin writing grabbed frames to an MJPG/AVI file.

        Recording happens inside the existing grab loop — no second
        camera connection needed. The ffmpeg subprocess is spawned on
        the first frame so we know the image dimensions.

        fps is the frame rate written into the output container.
        Defaults to self.target_fps so the file plays at the rate the
        camera actually produces.
        """
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".avi":
            output_path = output_path.with_suffix(".avi")
        record_fps = fps if fps is not None else self.target_fps

        with self._writer_lock:
            if self._ffmpeg_proc is not None or self._record_path is not None:
                logger.warning("Already recording — stop first")
                return
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._record_path = output_path
            self._record_fps = record_fps
            self._record_max_frames = int(duration_sec * record_fps)
            self._record_frame_count = 0
            # Open per-frame timestamp sidecar (consumed by tools/triangulate.py
            # for free-run sync correction via temporal interpolation).
            ts_path = output_path.with_suffix(output_path.suffix + ".timestamps.csv")
            try:
                self._ts_file = open(ts_path, "w", newline="")
                self._ts_file.write("frame_index,system_time_s,hw_timestamp_ticks\n")
            except OSError as e:
                logger.warning(f"Could not open timestamp sidecar {ts_path}: {e}")
                self._ts_file = None
            # ffmpeg proc created lazily on first frame
        # Write metadata sidecar (camera serial, configured params, etc.)
        self._write_metadata_sidecar(output_path)
        logger.info(f"Recording armed: {output_path} "
                    f"({duration_sec}s @ {record_fps}fps, MJPG/AVI q={MJPG_QUALITY})")

    def _write_metadata_sidecar(self, output_path: Path) -> None:
        """Companion to start_recording: dumps device + capture config to JSON."""
        if not self._camera or not self._camera.IsOpen():
            return
        try:
            info = self._camera.GetDeviceInfo()
            meta: dict = {
                "serial_number": info.GetSerialNumber(),
                "model_name": info.GetModelName(),
                "configured": {
                    "target_fps": self.target_fps,
                    "exposure_us": self.exposure_us,
                    "record_fps": self._record_fps,
                },
                "recording_started_iso": datetime.now().isoformat(timespec="seconds"),
                "hw_timestamp_tick_hz_assumed": 1_000_000_000,  # ace 2 USB3
            }
            for key, attr in (("width_px", "Width"), ("height_px", "Height"),
                              ("pixel_format", "PixelFormat")):
                try:
                    meta[key] = getattr(self._camera, attr).GetValue()
                except Exception:
                    pass
            meta_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
            meta_path.write_text(json.dumps(meta, indent=2))
        except Exception as e:
            logger.warning(f"Could not write metadata sidecar: {e}")

    def stop_recording(self) -> None:
        """Stop an in-progress recording. Safe to call from any thread."""
        # Swap out the proc under the lock so no further writes land on it,
        # then do the slow finalize (stdin.close + wait) outside the lock.
        with self._writer_lock:
            proc = self._ffmpeg_proc
            path = self._record_path
            count = self._record_frame_count
            ts_file = self._ts_file
            self._ffmpeg_proc = None
            self._record_path = None
            self._record_frame_count = 0
            self._record_max_frames = 0
            self._ts_file = None

        if ts_file is not None:
            try:
                ts_file.close()
            except Exception:
                pass

        if proc is None:
            return
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            logger.warning("ffmpeg wouldn't finalize in 30s — killed")
        if proc.returncode not in (0, None):
            err = (proc.stderr.read().decode(errors="replace")
                   if proc.stderr else "")
            logger.warning(f"ffmpeg exit {proc.returncode}. stderr:\n"
                           f"{err[-600:]}")
        if path:
            logger.info(f"Recording saved: {path} ({count} frames)")
            self.recording_finished.emit(str(path))

    def _write_frame(self, frame, sys_time: float = 0.0,
                     hw_timestamp: int = -1) -> None:
        """Write a single frame if recording is active. Runs on grab thread.

        sys_time is the Python-side time.time() at frame retrieval.
        hw_timestamp is grab.GetTimeStamp() (Basler ace 2 USB3 = ns since
        camera startup; 1 ns per tick). Both go to the timestamp sidecar.
        """
        need_stop = False
        with self._writer_lock:
            if self._record_path is None:
                return
            # Lazy-spawn ffmpeg on first frame so dimensions are known
            if self._ffmpeg_proc is None:
                h, w = frame.shape[:2]
                is_mono = frame.ndim == 2
                proc = _spawn_ffmpeg(self._record_path, w, h, is_mono,
                                     self._record_fps)
                if proc is None:
                    logger.error(f"Cannot spawn ffmpeg for {self._record_path}")
                    self._record_path = None
                    return
                self._ffmpeg_proc = proc
                logger.info(f"Recording started: {w}x{h} → {self._record_path}")

            try:
                self._ffmpeg_proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError) as e:
                logger.error(f"ffmpeg stdin write failed: {e}")
                return
            # Log per-frame timestamp (sidecar opened in start_recording)
            if self._ts_file is not None:
                try:
                    self._ts_file.write(
                        f"{self._record_frame_count},{sys_time:.6f},{hw_timestamp}\n")
                except Exception:
                    pass
            self._record_frame_count += 1
            if self._record_frame_count % 60 == 0:
                logger.info(f"  Recorded {self._record_frame_count}/"
                            f"{self._record_max_frames} frames")
            if 0 < self._record_max_frames <= self._record_frame_count:
                need_stop = True

        if need_stop:
            self.stop_recording()

    def disconnect(self) -> None:
        self.stop_recording()
        self.stop()
        if self._camera:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                if self._camera.IsOpen():
                    self._camera.Close()
            except Exception as e:
                logger.error(f"Disconnect error: {e}")
            finally:
                self._camera = None
        self._connected = False
        self.connection_changed.emit(False)

    def run(self) -> None:
        if not self._connected or not self._camera:
            self.error_occurred.emit("Camera not connected")
            return

        self._running = True
        self._frame_count = 0
        frame_interval = 1.0 / self.target_fps

        try:
            self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            while self._running and self._camera.IsGrabbing():
                try:
                    frame_start = time.time()
                    timeout_ms = int(self.exposure_us / 1000) + 1000
                    grab = self._camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
                    if grab and grab.GrabSucceeded():
                        ts = time.time()
                        frame = grab.Array.copy()
                        # Pull hardware timestamp before releasing the grab
                        try:
                            hw_ts = int(grab.GetTimeStamp())
                        except Exception:
                            hw_ts = -1
                        grab.Release()
                        self._frame_count += 1
                        self._write_frame(frame, sys_time=ts, hw_timestamp=hw_ts)
                        # Throttle live preview during recording. 30 fps display
                        # x 2 cameras saturates the GIL on small Macs (user
                        # report: ~84% CPU on M2 8GB before throttle); the
                        # recording path needs that headroom or grabs back up.
                        # 5 fps preview (every 6th frame) is plenty for "is it
                        # framed right" during a session. Recording itself
                        # captures all 30 fps regardless — only the cross-thread
                        # frame_ready emit is throttled.
                        display_every = 6 if self._record_path is not None else 1
                        if self._frame_count % display_every == 0:
                            self.frame_ready.emit({
                                "timestamp": ts,
                                "frame": frame,
                                "frame_number": self._frame_count,
                                "hw_timestamp_ticks": hw_ts,
                            })
                        elapsed = time.time() - frame_start
                        sleep_time = frame_interval - elapsed
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                    elif grab:
                        grab.Release()
                except Exception:
                    time.sleep(0.01)
        except Exception as e:
            self.error_occurred.emit(f"Grab error: {e}")
        finally:
            if self._camera and self._camera.IsGrabbing():
                self._camera.StopGrabbing()

    def stop(self) -> None:
        self._running = False
        if self.isRunning():
            self.wait(2000)

    @property
    def is_connected(self) -> bool:
        return self._connected
