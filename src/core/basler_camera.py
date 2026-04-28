"""QThread-based Basler camera interface using pypylon (PySide6).

Recording writes H.264/MP4 via a piped ffmpeg subprocess (bundled by
imageio-ffmpeg for cross-OS support). Each camera owns a dedicated
writer thread that consumes a bounded frame queue and pipes raw bytes
into ffmpeg's stdin — this decouples the encode rate from the grab
rate so transient encoder lag does not cause pylon to drop frames.
"""

import queue
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

H264_PRESET = "ultrafast"
H264_CRF = 23
# Bounded queue absorbs transient encoder lag without blocking the
# grab thread. ~5 seconds at 30 fps. Full → drop frame, log warning.
FRAME_QUEUE_MAX = 150


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
        # stderr=DEVNULL so a slow consumer can't fill the pipe and
        # block ffmpeg's logging path. -loglevel error already silences
        # routine output; on actual failure the nonzero exit code surfaces.
        return subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._camera: Optional["pylon.InstantCamera"] = None
        self._running = False
        self._connected = False
        self.target_fps = 30
        self.exposure_us = 25000
        self._frame_count = 0
        # Recording state. The grab thread enqueues; the writer thread
        # consumes the queue and pipes to ffmpeg. State transitions
        # (start/stop) flip _record_path under _state_lock.
        self._state_lock = threading.Lock()
        self._record_path: Optional[Path] = None
        self._record_frame_count: int = 0
        self._record_dropped: int = 0
        self._frame_queue: Optional[queue.Queue] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_stop_event = threading.Event()
        self._ffmpeg_proc: Optional[subprocess.Popen] = None

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
                        self._enqueue_frame(frame)
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
        """Stop grabbing frames and finalize any active recording."""
        self.stop_recording()
        self._running = False
        if self.isRunning():
            self.wait(2000)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_recording(self) -> bool:
        """Return True if a video recording is currently active."""
        return self._record_path is not None

    def start_recording(self, output_path: str) -> None:
        """Start recording frames to an H.264/MP4 file.

        Spawns a dedicated writer thread that pipes queued frames into
        ffmpeg. Container fps = self.target_fps so playback speed
        matches the camera's actual grab rate.

        Args:
            output_path: Full path for the output .mp4 file.
        """
        path = Path(output_path)
        if path.suffix.lower() != ".mp4":
            path = path.with_suffix(".mp4")

        with self._state_lock:
            if self._record_path is not None:
                logger.warning("Already recording — stop first")
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            self._record_path = path
            self._record_frame_count = 0
            self._record_dropped = 0
            self._frame_queue = queue.Queue(maxsize=FRAME_QUEUE_MAX)
            self._writer_stop_event.clear()
            self._writer_thread = threading.Thread(
                target=self._writer_loop, daemon=True,
                name=f"BaslerCamera-writer-{path.stem}",
            )
            self._writer_thread.start()
        logger.info(f"Recording armed: {path} "
                    f"(@ {self.target_fps}fps, H.264 {H264_PRESET} CRF {H264_CRF})")

    def stop_recording(self) -> None:
        """Stop an in-progress recording. Safe to call from any thread.

        Signals the writer thread to drain the queue and exit, then
        joins it. The writer thread closes ffmpeg's stdin and waits
        for it to finalize the file.
        """
        with self._state_lock:
            path = self._record_path
            self._record_path = None
            writer = self._writer_thread
            self._writer_thread = None
        if path is None:
            return

        self._writer_stop_event.set()
        if writer is not None:
            writer.join(timeout=15)
            if writer.is_alive():
                logger.warning(
                    f"Writer thread for {path} did not exit in 15s")

    def _enqueue_frame(self, frame) -> None:
        """Hand a freshly-grabbed frame to the writer thread.

        Non-blocking. If the queue is full (encoder is too slow), the
        frame is dropped and a warning is logged at most every 30
        drops to avoid log spam.
        """
        q = self._frame_queue
        if q is None or self._record_path is None:
            return
        try:
            q.put_nowait(frame)
        except queue.Full:
            self._record_dropped += 1
            if self._record_dropped % 30 == 1:
                logger.warning(
                    f"Recording queue full — dropped "
                    f"{self._record_dropped} frame(s) so far")

    def _writer_loop(self) -> None:
        """Consume frames from the queue and write them to ffmpeg.

        Runs in its own thread. Lazy-spawns ffmpeg on the first frame
        so dimensions are known. Drains remaining frames after
        stop_recording is called.
        """
        proc: Optional[subprocess.Popen] = None
        path = self._record_path  # captured at start; for logging only
        q = self._frame_queue
        if q is None or path is None:
            return

        while True:
            stop_requested = self._writer_stop_event.is_set()
            try:
                frame = q.get(timeout=0.1)
            except queue.Empty:
                if stop_requested:
                    break
                continue

            if proc is None:
                h, w = frame.shape[:2]
                is_mono = frame.ndim == 2
                proc = _spawn_ffmpeg(path, w, h, is_mono,
                                     float(self.target_fps))
                if proc is None:
                    logger.error(f"Cannot spawn ffmpeg for {path}")
                    return
                self._ffmpeg_proc = proc
                logger.info(f"Recording started: {w}x{h} → {path}")

            try:
                proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError) as e:
                logger.error(f"ffmpeg stdin write failed: {e}")
                break
            self._record_frame_count += 1
            if self._record_frame_count % 60 == 0:
                logger.info(
                    f"  Recorded {self._record_frame_count} frames "
                    f"({self._record_dropped} dropped)")

        # Finalize ffmpeg
        if proc is not None:
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
                logger.warning(f"ffmpeg exit {proc.returncode} for {path}")
            self._ffmpeg_proc = None
            logger.info(
                f"Recording saved: {path} "
                f"({self._record_frame_count} frames, "
                f"{self._record_dropped} dropped)")
