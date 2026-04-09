"""QThread-based Basler camera interface using pypylon (PySide6)."""

import time
import logging
from typing import Optional

import cv2
import numpy as np

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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._camera: Optional["pylon.InstantCamera"] = None
        self._running = False
        self._connected = False
        self.target_fps = 30
        self.exposure_us = 25000
        self._frame_count = 0
        self._video_writer: Optional[cv2.VideoWriter] = None
        self._is_recording = False
        self._last_frame_size: Optional[tuple[int, int]] = None

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
                        self._last_frame_size = (frame.shape[1], frame.shape[0])
                        self._write_frame(frame)
                        self._frame_count += 1
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
        return self._is_recording

    def start_recording(self, output_path: str) -> None:
        """Start recording frames to an AVI file (MJPG codec).

        Args:
            output_path: Full path for the output .avi file.

        Raises:
            ValueError: If no frame size is known yet (no frames grabbed).
        """
        if self._is_recording:
            self.stop_recording()
        if self._last_frame_size is None:
            raise ValueError("Cannot start recording: frame size unknown (no frames grabbed yet)")
        w, h = self._last_frame_size
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self._video_writer = cv2.VideoWriter(output_path, fourcc, self.target_fps, (w, h), isColor=False)
        self._is_recording = True
        logger.info(f"Camera recording started: {output_path}")

    def stop_recording(self) -> None:
        """Stop recording and release the VideoWriter."""
        if not self._is_recording:
            return
        self._is_recording = False
        if self._video_writer:
            self._video_writer.release()
            self._video_writer = None
        logger.info("Camera recording stopped")

    def _write_frame(self, frame: "np.ndarray") -> None:
        """Write a single frame to the video file if recording."""
        if not self._is_recording or self._video_writer is None:
            return
        self._video_writer.write(frame)
