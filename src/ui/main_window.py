"""MainWindow - Main Application Window

Purpose: Main application window, orchestrates all components for read-only sensor monitoring.

Layout:
```
┌─────────────────────────────────────────────────────────────┐
│ Menu Bar: File | Settings | Help                            │
├─────────────────────────────────────────────────────────────┤
│ Toolbar: [Arduino ▼] [Connect] [Camera ▼] [Connect] [Record]│
├───────────────────────────┬─────────────────────────────────┤
│                           │                                 │
│     SENSOR PANEL          │       CAMERA PANEL              │
│     (Left, 40%)           │       (Right, 60%)              │
│                           │                                 │
│  ┌─────────────────────┐  │  ┌───────────────────────────┐  │
│  │ P1/P2 Pressure      │  │  │                           │  │
│  │ [Graph]             │  │  │     CAMERA FEED           │  │
│  └─────────────────────┘  │  │     (with dot overlay)    │  │
│  ┌─────────────────────┐  │  │                           │  │
│  │ Flow Rate           │  │  └───────────────────────────┘  │
│  │ [Graph]             │  │  ┌───────────────────────────┐  │
│  └─────────────────────┘  │  │ Dot Positions:            │  │
│  ┌─────────────────────┐  │  │ Dot 0: (523, 412)         │  │
│  │ Heart Rate: 72 BPM  │  │  │ Dot 1: (891, 398)         │  │
│  └─────────────────────┘  │  └───────────────────────────┘  │
│                           │                                 │
├───────────────────────────┴─────────────────────────────────┤
│ Status: Arduino: Connected | Camera: Connected | FPS: 60    │
└─────────────────────────────────────────────────────────────┘
```

Class Structure:
```
MainWindow(QMainWindow)
│
├── Attributes:
│   ├── state_manager: StateManager
│   ├── arduino_handler: ArduinoHandler
│   ├── basler_camera: BaslerCamera
│   ├── dot_tracker: DotTracker
│   ├── data_logger: DataLogger
│   ├── sensor_panel: SensorPanel
│   └── camera_panel: CameraPanel
│
├── Methods:
│   ├── _setup_ui()              # Create layout
│   ├── _setup_menu_bar()        # File, Settings, Help
│   ├── _connect_signals()       # Wire all signals/slots
│   ├── _on_arduino_connect()    # Handle Arduino connection
│   ├── _on_camera_connect()     # Handle camera connection
│   ├── _on_frame_received(dict) # Process new frame
│   ├── _on_record_clicked()     # Start/stop recording
│   └── closeEvent(event)        # Clean shutdown
```

Note: This is a read-only monitoring application. No hardware control panel or emergency stop.
The hardware is controlled manually via potentiometer on the device.
"""
