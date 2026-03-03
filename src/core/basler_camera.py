"""QThread-based Basler camera interface using pypylon (PySide6)."""

import time
import logging
from collections import deque
from typing import Optional

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
    fps_updated = Signal(float)
    error_occurred = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._camera: Optional["pylon.InstantCamera"] = None
        self._running = False
        self._connected = False
        self.target_fps = 30
        self.exposure_us = 25000
        self._frame_times: deque = deque(maxlen=60)
        self._frame_count = 0
        self._last_fps_emit = 0.0

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
        self._frame_times.clear()
        self._last_fps_emit = time.time()

        try:
            self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            while self._running and self._camera.IsGrabbing():
                try:
                    timeout_ms = int(self.exposure_us / 1000) + 1000
                    grab = self._camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
                    if grab and grab.GrabSucceeded():
                        ts = time.time()
                        frame = grab.Array.copy()
                        grab.Release()
                        self._frame_count += 1
                        self._frame_times.append(ts)
                        self.frame_ready.emit({
                            "timestamp": ts,
                            "frame": frame,
                            "frame_number": self._frame_count,
                        })
                        if ts - self._last_fps_emit >= 1.0:
                            self.fps_updated.emit(self._calc_fps())
                            self._last_fps_emit = ts
                    elif grab:
                        grab.Release()
                except Exception:
                    time.sleep(0.01)
        except Exception as e:
            self.error_occurred.emit(f"Grab error: {e}")
        finally:
            if self._camera and self._camera.IsGrabbing():
                self._camera.StopGrabbing()

    def _calc_fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        return (len(self._frame_times) - 1) / span if span > 0 else 0.0

    def stop(self) -> None:
        self._running = False
        if self.isRunning():
            self.wait(2000)

    @property
    def is_connected(self) -> bool:
        return self._connected
