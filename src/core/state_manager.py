"""
Docstring for state_manager
**Purpose:** Central hub for application state and signal distribution


(ENHANCED)

**New State Tracking:**
```python
class StateManager(QObject):
    # Existing signals
    sensor_updated = Signal(dict)
    frame_updated = Signal(dict)
    tracking_updated = Signal(dict)
    connection_changed = Signal(str, bool)
    recording_changed = Signal(bool)
    error_occurred = Signal(str, str)
    
    # NEW signals for control
    control_command_sent = Signal(str)
    hardware_state_changed = Signal(dict)
    
    def __init__(self):
        super().__init__()
        # Existing state
        self.arduino_connected = False
        self.camera_connected = False
        self.recording = False
        self.current_sensor_data = {}
        self.current_tracking_data = {}
        
        # NEW: Hardware control state
        self.current_hardware_state = {
            "fan": False,
            "solenoid": False,
            "bpm": 0,
            "mode": "POT"
        }
        
    def update_hardware_state(self, state: dict):
        # Update and emit hardware state changes
        self.current_hardware_state.update(state)
        self.hardware_state_changed.emit(state)
```

"""