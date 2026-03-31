"""QThread-based Basler camera interface using pypylon (PySide6)."""

import time
import logging
from pathlib import Path
from typing import Optional

import cv2
from PySide6.QtCore import QThread, Signal

try:
    from pypylon import pylon
    PYPYLON_AVAILABLE = True
except ImportError:
    PYPYLON_AVAILABLE = False
    pylon = None

logger = logging.getLogger(__name__)


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
        # Recording state
        self._writer: Optional[cv2.VideoWriter] = None
        self._record_path: Optional[Path] = None
        self._record_fps: float = 60.0
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
                        fps: float = 60.0) -> None:
        """Begin writing grabbed frames to an AVI file.

        Recording happens inside the existing grab loop — no second
        camera connection needed.
        """
        if self._writer is not None:
            logger.warning("Already recording — stop first")
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._record_path = output_path
        self._record_fps = fps
        self._record_max_frames = int(duration_sec * fps)
        self._record_frame_count = 0
        # Writer is created on the first frame (need dimensions)
        self._writer = None  # sentinel — _write_frame handles creation
        logger.info(f"Recording armed: {output_path} "
                    f"({duration_sec}s @ {fps}fps)")

    def stop_recording(self) -> None:
        """Stop an in-progress recording."""
        if self._writer is not None:
            self._writer.release()
            logger.info(f"Recording saved: {self._record_path} "
                        f"({self._record_frame_count} frames)")
            self.recording_finished.emit(str(self._record_path))
        self._writer = None
        self._record_path = None
        self._record_frame_count = 0
        self._record_max_frames = 0

    def _write_frame(self, frame) -> None:
        """Write a single frame to the AVI if recording is active."""
        if self._record_path is None:
            return
        # Lazy-create writer on first frame so we know dimensions
        if self._writer is None:
            h, w = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            is_color = frame.ndim == 3
            self._writer = cv2.VideoWriter(
                str(self._record_path), fourcc, self._record_fps,
                (w, h), isColor=is_color)
            if not self._writer.isOpened():
                logger.error(f"Cannot open VideoWriter for {self._record_path}")
                self._record_path = None
                self._writer = None
                return
            logger.info(f"Recording started: {w}x{h} → {self._record_path}")

        self._writer.write(frame)
        self._record_frame_count += 1
        if self._record_frame_count % 60 == 0:
            logger.info(f"  Recorded {self._record_frame_count}/"
                        f"{self._record_max_frames} frames")
        if 0 < self._record_max_frames <= self._record_frame_count:
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
