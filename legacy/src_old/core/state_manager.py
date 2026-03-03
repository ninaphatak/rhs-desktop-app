"""StateManager - Central Application State Hub

Purpose: Central hub for application state and signal distribution.
Manages sensor data, camera frames, tracking data, and connection states.

This is a READ-ONLY monitoring system - no hardware control state.

Signals:
    sensor_updated(dict): New sensor data from Arduino
    frame_updated(dict): New camera frame captured
    tracking_updated(dict): New dot tracking data
    connection_changed(str, bool): Device connection state changed (device_name, is_connected)
    recording_changed(bool): Data recording state changed
    error_occurred(str, str): Error occurred (source, message)

State Attributes:
    arduino_connected: bool - Arduino connection status
    camera_connected: bool - Camera connection status
    recording: bool - Currently recording data
    current_sensor_data: dict - Latest sensor readings (P1, P2, FLOW, HR)
    current_tracking_data: dict - Latest dot tracking measurements

Example usage:
```python
from PyQt6.QtCore import QObject, pyqtSignal as Signal

class StateManager(QObject):
    # Signals for monitoring only
    sensor_updated = Signal(dict)
    frame_updated = Signal(dict)
    tracking_updated = Signal(dict)
    connection_changed = Signal(str, bool)
    recording_changed = Signal(bool)
    error_occurred = Signal(str, str)

    def __init__(self):
        super().__init__()
        # Connection states
        self.arduino_connected = False
        self.camera_connected = False
        self.recording = False

        # Data caches
        self.current_sensor_data = {}
        self.current_tracking_data = {}

    def update_sensor_data(self, data: dict):
        # Update and emit sensor data
        self.current_sensor_data = data
        self.sensor_updated.emit(data)

    def set_recording(self, state: bool):
        # Update recording state
        self.recording = state
        self.recording_changed.emit(state)
```
"""
