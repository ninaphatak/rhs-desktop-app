"""
Docstring for state_manager
**Purpose:** Central hub for application state and signal distribution

**Class Structure:**
```
StateManager(QObject)
│
├── Signals:
│   ├── sensor_updated(dict)         # New sensor data
│   ├── frame_updated(dict)          # New camera frame
│   ├── tracking_updated(dict)       # New dot positions
│   ├── connection_changed(str, bool)  # Device connection status
│   ├── recording_changed(bool)      # Recording started/stopped
│   └── error_occurred(str, str)     # Source, message
│
├── Attributes:
│   ├── arduino_connected: bool
│   ├── camera_connected: bool
│   ├── recording: bool
│   ├── current_sensor_data: dict
│   ├── current_tracking_data: dict
│   └── config: Config
│
├── Methods:
│   ├── update_sensor_data(data: dict)
│   ├── update_frame(frame_data: dict)
│   ├── update_tracking(tracking_data: dict)
│   ├── set_connection(device: str, connected: bool)
│   ├── set_recording(recording: bool)
│   ├── get_sensor_data() → dict
│   └── get_tracking_data() → dict
```

"""