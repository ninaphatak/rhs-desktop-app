"""
Docstring for rhs-desktop-app.src.core.basler_camera

Purpose: Capture frames from Basler Camera using pypylon
Input: 
- camera index (default 0)
- target FPS (default 60 FPS)
- exposure time in microseconds (default 1000 = 1ms)

"""

import time
import logging
from collections import deque
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

# pypylon import - fails gracefully if not installed
try:
    from pypylon import pylon
    PYPYLON_AVAILABLE = True
except ImportError:
    PYPYLON_AVAILABLE = False
    pylon = None  # Type hint placeholder

logger = logging.getLogger(__name__)


class BaslerCamera(QThread):
    """
    Threaded Basler camera interface using pypylon.
    
    Uses GrabStrategy_LatestImageOnly for real-time monitoring - always
    gets the most recent frame rather than queuing up old ones.
    
    Usage:
        camera = BaslerCamera()
        camera.frame_ready.connect(my_handler)
        
        cameras = BaslerCamera.list_cameras()
        if cameras:
            camera.connect(0)
            camera.start()
            # ... later ...
            camera.stop()
            camera.disconnect()
    """
    
    # Qt Signals
    frame_ready = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    fps_updated = pyqtSignal(float)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._camera: Optional["pylon.InstantCamera"] = None
        self._running = False
        self._connected = False
        
        # Configuration (can be changed before connect())
        self.target_fps = 30
        self.exposure_us = 25000  # 1ms default
        
        # FPS tracking
        self._frame_times: deque = deque(maxlen=60)
        self._frame_count = 0
        self._last_fps_emit = 0.0
    
    @staticmethod
    def list_cameras() -> list[str]:
        """
        Get list of connected Basler cameras.
        
        Returns:
            List of camera friendly names, e.g.:
            ["Basler ace 2 a2A1920-160umBAS (40063823)"]
        """
        if not PYPYLON_AVAILABLE:
            logger.warning("pypylon not installed")
            return []
        
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            return [device.GetFriendlyName() for device in devices]
        except Exception as e:
            logger.error(f"Error enumerating cameras: {e}")
            return []
    
    @staticmethod
    def get_camera_info() -> list[dict]:
        """
        Get detailed info for all connected cameras.
        
        Returns:
            List of dicts with camera details (model, serial, etc.)
        """
        if not PYPYLON_AVAILABLE:
            return []
        
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            return [
                {
                    "friendly_name": d.GetFriendlyName(),
                    "model": d.GetModelName(),
                    "serial": d.GetSerialNumber(),
                    "full_name": d.GetFullName(),
                }
                for d in devices
            ]
        except Exception as e:
            logger.error(f"Error getting camera info: {e}")
            return []
    
    def connect(self, index: int = 0) -> bool:
        """
        Connect to camera by index.
        
        Args:
            index: Camera index from list_cameras()
        
        Returns:
            True if connected successfully
        """
        if not PYPYLON_AVAILABLE:
            self.error_occurred.emit("pypylon not installed")
            return False
        
        if self._connected:
            logger.warning("Already connected, disconnecting first")
            self.disconnect()
        
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            
            if index >= len(devices):
                self.error_occurred.emit(f"Camera index {index} not found")
                return False
            
            # Create camera instance
            self._camera = pylon.InstantCamera(
                tl_factory.CreateDevice(devices[index])
            )
            self._camera.Open()
            
            # Apply configuration
            self._configure_camera()
            
            self._connected = True
            self.connection_changed.emit(True)
            
            camera_name = devices[index].GetFriendlyName()
            logger.info(f"Connected to: {camera_name}")
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {e}")
            logger.error(f"Camera connection error: {e}")
            return False
    
    def _configure_camera(self):
        """Apply camera settings after connection."""
        if not self._camera or not self._camera.IsOpen():
            return
        
        try:
            # Exposure time (microseconds)
            self._camera.ExposureTime.SetValue(self.exposure_us)
            
            # Frame rate control
            try:
                self._camera.AcquisitionFrameRateEnable.SetValue(True)
                self._camera.AcquisitionFrameRate.SetValue(self.target_fps)
            except Exception:
                logger.warning("Frame rate control not available on this camera")
            
            try: 
                self._camera.Gain.SetValue(18)
            except Exception as e:
                logger.warning(f"Could not set gain: {e}")
            

            # Log actual settings
            actual_exposure = self._camera.ExposureTime.GetValue()
            logger.info(f"Camera configured: exposure={actual_exposure}µs, target_fps={self.target_fps}")
            
        except Exception as e:
            logger.warning(f"Could not configure camera: {e}")
    
    def disconnect(self):
        """Disconnect from camera."""
        self.stop()  # Stop grabbing first
        
        if self._camera is not None:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                if self._camera.IsOpen():
                    self._camera.Close()
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self._camera = None
        
        self._connected = False
        self.connection_changed.emit(False)
        logger.info("Camera disconnected")
    
    def set_exposure(self, exposure_us: int):
        """
        Set exposure time.
        
        Args:
            exposure_us: Exposure time in microseconds
        """
        self.exposure_us = exposure_us
        
        if self._camera and self._camera.IsOpen():
            try:
                self._camera.ExposureTime.SetValue(exposure_us)
                logger.info(f"Exposure set to {exposure_us}µs")
            except Exception as e:
                self.error_occurred.emit(f"Could not set exposure: {e}")
    
    def set_fps(self, fps: int):
        """
        Set target frame rate.
        
        Args:
            fps: Target frames per second
        """
        self.target_fps = fps
        
        if self._camera and self._camera.IsOpen():
            try:
                self._camera.AcquisitionFrameRate.SetValue(fps)
                logger.info(f"FPS set to {fps}")
            except Exception as e:
                self.error_occurred.emit(f"Could not set FPS: {e}")
    
    def run(self):
        """
        Thread main loop - grabs frames continuously.
        
        Uses GrabStrategy_LatestImageOnly to always get the most recent frame.
        """
        if not self._connected or not self._camera:
            self.error_occurred.emit("Camera not connected")
            return
        
        self._running = True
        self._frame_count = 0
        self._frame_times.clear()
        self._last_fps_emit = time.time()
        
        try:
            # Start grabbing - LatestImageOnly skips old frames if we're slow
            self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            logger.info("Started frame grabbing")
            
            while self._running and self._camera.IsGrabbing():
                try:
                    # Timeout = exposure + generous buffer (in ms)
                    timeout_ms = int(self.exposure_us / 1000) + 1000
                    
                    grab_result = self._camera.RetrieveResult(
                        timeout_ms, 
                        pylon.TimeoutHandling_Return
                    )
                    
                    if grab_result and grab_result.GrabSucceeded():
                        timestamp = time.time()
                        
                        # CRITICAL: Copy frame before releasing buffer
                        frame = grab_result.Array.copy()
                        grab_result.Release()
                        
                        self._frame_count += 1
                        self._frame_times.append(timestamp)
                        
                        # Emit frame data
                        frame_data = {
                            "timestamp": timestamp,
                            "frame": frame,
                            "frame_number": self._frame_count,
                        }
                        self.frame_ready.emit(frame_data)
                        
                        # Emit FPS update every ~1 second
                        if timestamp - self._last_fps_emit >= 1.0:
                            fps = self._calculate_fps()
                            self.fps_updated.emit(fps)
                            self._last_fps_emit = timestamp
                    
                    elif grab_result:
                        error_code = grab_result.GetErrorCode()
                        error_desc = grab_result.GetErrorDescription()
                        logger.warning(f"Grab failed: {error_code} - {error_desc}")
                        grab_result.Release()
                
                except Exception as e:
                    logger.error(f"Error in grab loop: {e}")
                    time.sleep(0.01)  # Brief pause before retry
            
        except Exception as e:
            self.error_occurred.emit(f"Grabbing error: {e}")
            logger.error(f"Fatal grab error: {e}")
        
        finally:
            if self._camera and self._camera.IsGrabbing():
                self._camera.StopGrabbing()
            logger.info("Stopped frame grabbing")
    
    def _calculate_fps(self) -> float:
        """Calculate FPS from recent frame timestamps."""
        if len(self._frame_times) < 2:
            return 0.0
        
        time_span = self._frame_times[-1] - self._frame_times[0]
        if time_span <= 0:
            return 0.0
        
        return (len(self._frame_times) - 1) / time_span
    
    def stop(self):
        """Stop the grabbing thread."""
        self._running = False
        
        if self.isRunning():
            self.wait(2000)  # 2 second timeout
    
    @property
    def is_connected(self) -> bool:
        """Check if camera is connected."""
        return self._connected
    
    @property
    def is_grabbing(self) -> bool:
        """Check if camera is actively grabbing."""
        return self._running and self._camera is not None and self._camera.IsGrabbing()