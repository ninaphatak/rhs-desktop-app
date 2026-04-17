"""QThread-based Basler camera interface using pypylon (PySide6).

Recording writes H.264/MP4 via a piped ffmpeg subprocess (bundled by
imageio-ffmpeg for cross-OS support). The grab loop writes raw frames
into ffmpeg's stdin; ffmpeg encodes and finalizes the .mp4 container.
"""

import subprocess
import threading
import time
import logging
from pathlib import Path
from typing import Optional

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

H264_PRESET = "fast"
H264_CRF = 18


def _spawn_ffmpeg(output_path: Path, width: int, height: int, is_mono: bool,
                  fps: float) -> Optional[subprocess.Popen]:
    """Spawn ffmpeg reading raw frames from stdin, writing H.264/MP4."""
    if not IMAGEIO_FFMPEG_AVAILABLE:
        logger.error("imageio-ffmpeg not installed — cannot record")
        return None
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
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
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
        """Begin writing grabbed frames to an H.264/MP4 file.

        Recording happens inside the existing grab loop — no second
        camera connection needed. The ffmpeg subprocess is spawned on
        the first frame so we know the image dimensions.

        fps is the frame rate written into the output container.
        Defaults to self.target_fps so the file plays at the rate the
        camera actually produces.
        """
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
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
            # ffmpeg proc created lazily on first frame
        logger.info(f"Recording armed: {output_path} "
                    f"({duration_sec}s @ {record_fps}fps, H.264 CRF {H264_CRF})")

    def stop_recording(self) -> None:
        """Stop an in-progress recording. Safe to call from any thread."""
        # Swap out the proc under the lock so no further writes land on it,
        # then do the slow finalize (stdin.close + wait) outside the lock.
        with self._writer_lock:
            proc = self._ffmpeg_proc
            path = self._record_path
            count = self._record_frame_count
            self._ffmpeg_proc = None
            self._record_path = None
            self._record_frame_count = 0
            self._record_max_frames = 0

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

    def _write_frame(self, frame) -> None:
        """Write a single frame if recording is active. Runs on grab thread."""
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
                        grab.Release()
                        self._frame_count += 1
                        self._write_frame(frame)
                        self.frame_ready.emit({
                            "timestamp": ts,
                            "frame": frame,
                            "frame_number": self._frame_count,
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
