"""
Docstring for control_panel

**Purpose:** Connection controls and action buttons

**Class Structure:**
```
ControlPanel(QWidget)
│
├── Attributes:
│   ├── port_combo: QComboBox        # Arduino port selector
│   ├── camera_combo: QComboBox      # Camera selector
│   ├── connect_arduino_btn: QPushButton
│   ├── connect_camera_btn: QPushButton
│   ├── record_btn: QPushButton
│   ├── export_btn: QPushButton
│   └── refresh_btn: QPushButton
│
├── Signals:
│   ├── arduino_connect_requested(str)
│   ├── arduino_disconnect_requested()
│   ├── camera_connect_requested(int)
│   ├── camera_disconnect_requested()
│   ├── recording_toggled(bool)
│   └── export_requested()
│
├── Methods:
│   ├── refresh_ports()              # Update port list
│   ├── refresh_cameras()            # Update camera list
│   ├── set_arduino_connected(bool)  # Update button state
│   ├── set_camera_connected(bool)   # Update button state
│   └── set_recording(bool)          # Update record button
"""