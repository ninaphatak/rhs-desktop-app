# RHS Desktop Application - Updated Code Structure v2.0

## Architecture Overview: Monitoring + Control System

```
rhs-desktop-app/
├── src/
│   ├── core/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── arduino_handler.py   # ✏️ ENHANCED - Bidirectional communication
│   │   ├── basler_camera.py     # (unchanged)
│   │   ├── dot_tracker.py       # (unchanged)
│   │   ├── state_manager.py     # ✏️ ENHANCED - Control state tracking
│   │   ├── data_logger.py       # ✏️ ENHANCED - Log control commands
│   │   └── mapanything_exporter.py  # (unchanged)
│   │
│   ├── ui/                      # PyQt6 interface layer
│   │   ├── __init__.py
│   │   ├── main_window.py       # ✏️ ENHANCED - Three-column layout
│   │   ├── sensor_panel.py      # (unchanged)
│   │   ├── camera_panel.py      # (unchanged)
│   │   ├── connection_panel.py  # 🆕 RENAMED from control_panel.py
│   │   ├── hardware_control_panel.py  # 🆕 NEW - Control UI
│   │   └── dialogs/
│   │       ├── threshold_dialog.py
│   │       ├── settings_dialog.py
│   │       └── safety_dialog.py     # 🆕 NEW - Safety confirmations
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py            # ✏️ ENHANCED - Control settings
│   │   ├── constants.py         # ✏️ ENHANCED - Control constants
│   │   └── validators.py        # 🆕 NEW - Input validation
│   │
│   └── main.py                  # (unchanged)
│
├── tests/
│   ├── __init__.py
│   ├── mock_arduino.py          # ✏️ ENHANCED - Echo commands
│   ├── mock_camera.py           # (unchanged)
│   ├── test_arduino_handler.py  # 🆕 NEW - Command tests
│   ├── test_dot_tracker.py      # (unchanged)
│   └── test_validators.py       # 🆕 NEW - Validation tests
│
├── docs/
│   ├── installation.md
│   ├── user_guide.md            # ✏️ ENHANCED - Control instructions
│   ├── mapanything_guide.md
│   ├── arduino_protocol.md      # 🆕 NEW - Command protocol spec
│   └── safety_guide.md          # 🆕 NEW - Emergency procedures
│
├── arduino/                     # 🆕 NEW - Firmware code
│   ├── rhs_firmware/
│   │   └── rhs_firmware.ino     # ✏️ MODIFIED - Bidirectional
│   └── README.md                # Upload instructions
│
├── output/                      # Session recordings
└── [other files unchanged]

Legend:
✏️ = File enhanced with new features
🆕 = New file to create
(unchanged) = Existing design, no modifications
```

---

## Core Layer Changes

### src/core/arduino_handler.py (ENHANCED)

**Purpose:** Bidirectional serial communication with Arduino

**New Capabilities:**
- Send commands to Arduino
- Receive command acknowledgments
- Parse command responses
- Thread-safe command queue

```python
"""
ArduinoHandler - Bidirectional Serial Communication

**Purpose:** Manage serial I/O with Arduino for both sensor data and control commands

**Class Structure:**
```
ArduinoHandler(QThread)
│
├── Signals:
│   ├── data_received(dict)              # Sensor data
│   ├── connection_changed(bool)         # Connection status
│   ├── command_sent(str)                # 🆕 Command was sent
│   ├── command_acknowledged(str, bool)  # 🆕 Arduino responded
│   ├── hardware_state_updated(dict)     # 🆕 Hardware state changed
│   └── error_occurred(str)              # Error message
│
├── Attributes:
│   ├── _serial: Serial                  # Serial port object
│   ├── _running: bool                   # Thread control
│   ├── _command_queue: Queue            # 🆕 Thread-safe command queue
│   ├── _pending_command: str            # 🆕 Awaiting ACK
│   └── _command_timeout: float          # 🆕 1.0 seconds
│
├── Methods (existing):
│   ├── list_ports() → list[str]         # Static: enumerate ports
│   ├── connect(port: str)               # Open connection
│   ├── disconnect()                     # Close connection
│   ├── run()                            # Thread loop
│   └── stop()                           # Stop thread
│
├── Methods (NEW):
│   ├── send_command(cmd: str) → None   # Queue command for sending
│   ├── set_fan(state: bool) → None     # Helper: fan control
│   ├── set_bpm(value: int) → None      # Helper: BPM setpoint
│   ├── set_mode(mode: str) → None      # Helper: POT/AUTO/MANUAL
│   ├── set_solenoid(state: bool) → None # Helper: solenoid (MANUAL mode)
│   ├── emergency_stop() → None         # Helper: kill all outputs
│   └── get_status() → None             # Request hardware state
│
└── Internal (NEW):
    ├── _process_command_queue()         # Write queued commands
    ├── _parse_response(line: str) → dict  # Parse OK/ERROR/STATUS
    └── _handle_command_ack(success: bool)
```

**Key Implementation Details:**

```python
from queue import Queue
from PyQt6.QtCore import QThread, Signal
import serial
import time

class ArduinoHandler(QThread):
    # Signals
    data_received = Signal(dict)
    connection_changed = Signal(bool)
    command_sent = Signal(str)
    command_acknowledged = Signal(str, bool)  # command, success
    hardware_state_updated = Signal(dict)
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._serial = None
        self._running = False
        self._command_queue = Queue()
        self._pending_command = None
        self._command_timeout = 1.0
        self._last_command_time = 0
        
    def send_command(self, cmd: str):
        """Thread-safe command queueing"""
        self._command_queue.put(cmd)
        
    def set_fan(self, state: bool):
        """High-level fan control"""
        self.send_command(f"SET_FAN {1 if state else 0}")
        
    def set_bpm(self, value: int):
        """High-level BPM control (AUTO mode)"""
        if 60 <= value <= 180:
            self.send_command(f"SET_BPM {value}")
        else:
            self.error_occurred.emit("BPM out of range (60-180)")
            
    def set_mode(self, mode: str):
        """High-level mode control"""
        if mode in ["POT", "AUTO", "MANUAL"]:
            self.send_command(f"SET_MODE {mode}")
        else:
            self.error_occurred.emit(f"Invalid mode: {mode}")
            
    def emergency_stop(self):
        """Emergency: kill all outputs immediately"""
        # Clear queue and send immediately
        while not self._command_queue.empty():
            self._command_queue.get()
        self.send_command("EMERGENCY_STOP")
        
    def run(self):
        """Main thread loop - read data AND process command queue"""
        self._running = True
        
        while self._running:
            try:
                # 1. Process outgoing commands
                self._process_command_queue()
                
                # 2. Read incoming data
                if self._serial and self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8').strip()
                    
                    # Check if it's a response or sensor data
                    if line.startswith(("OK", "ERROR", "STATUS")):
                        self._handle_response(line)
                    else:
                        # Parse sensor data
                        data = self._parse_data(line)
                        if data:
                            self.data_received.emit(data)
                            
            except Exception as e:
                self.error_occurred.emit(str(e))
                
        self.disconnect()
        
    def _process_command_queue(self):
        """Send queued commands to Arduino"""
        if self._pending_command:
            # Check timeout
            if time.time() - self._last_command_time > self._command_timeout:
                self.command_acknowledged.emit(self._pending_command, False)
                self._pending_command = None
                
        # Send next command if no pending ACK
        if not self._pending_command and not self._command_queue.empty():
            cmd = self._command_queue.get()
            self._serial.write(f"{cmd}\n".encode('utf-8'))
            self._pending_command = cmd
            self._last_command_time = time.time()
            self.command_sent.emit(cmd)
            
    def _handle_response(self, line: str):
        """Parse Arduino response"""
        if line.startswith("OK"):
            self.command_acknowledged.emit(self._pending_command, True)
            self._pending_command = None
            
        elif line.startswith("ERROR"):
            error_msg = line.split(" ", 1)[1] if " " in line else "Unknown error"
            self.command_acknowledged.emit(self._pending_command, False)
            self.error_occurred.emit(f"Arduino error: {error_msg}")
            self._pending_command = None
            
        elif line.startswith("STATUS"):
            # Parse: STATUS FAN:1 SOL:0 BPM:72 MODE:AUTO
            state = self._parse_status(line)
            self.hardware_state_updated.emit(state)
            
    def _parse_status(self, line: str) -> dict:
        """Parse STATUS response into dict"""
        parts = line.split()[1:]  # Skip "STATUS"
        state = {}
        for part in parts:
            key, value = part.split(":")
            state[key.lower()] = value
        return state
```

---

### src/core/state_manager.py (ENHANCED)

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
        """Update and emit hardware state changes"""
        self.current_hardware_state.update(state)
        self.hardware_state_changed.emit(state)
```

---

### src/core/data_logger.py (ENHANCED)

**New Feature:** Log control commands to CSV

```python
class DataLogger(QThread):
    # ... existing code ...
    
    def log_data(self, sensor: dict, tracking: dict, frame, control_cmd: str = None):
        """
        Enhanced to log control commands
        
        CSV columns:
        timestamp, elapsed, p1, p2, flow, hr, dot0_x, dot0_y, ..., control_command
        """
        row = [
            sensor['timestamp'],
            sensor['elapsed'],
            sensor['p1'],
            sensor['p2'],
            sensor['flow_rate'],
            sensor['heart_rate'],
            # ... dot positions ...
            control_cmd if control_cmd else ""  # NEW: log command if present
        ]
        self._queue.put(row)
```

---

## UI Layer Changes

### src/ui/hardware_control_panel.py (NEW)

**Purpose:** User interface for hardware control

```python
"""
HardwareControlPanel - Hardware Control Interface

**Purpose:** Provide user controls for RHS hardware (fan, BPM, solenoid, mode)

**Class Structure:**
```
HardwareControlPanel(QWidget)
│
├── Signals:
│   ├── mode_changed(str)          # POT/AUTO/MANUAL
│   ├── fan_toggled(bool)          # Fan on/off
│   ├── bpm_changed(int)           # BPM setpoint (AUTO mode)
│   └── solenoid_toggled(bool)     # Solenoid (MANUAL mode)
│
├── Widgets:
│   ├── mode_combo: QComboBox      # Mode selector
│   ├── fan_checkbox: QCheckBox    # Fan control
│   ├── bpm_slider: QSlider        # BPM slider (60-180)
│   ├── bpm_spinbox: QSpinBox      # BPM number input
│   ├── solenoid_checkbox: QCheckBox  # Solenoid control
│   └── status_group: QGroupBox    # Read-only state display
│
├── Methods:
│   ├── update_state(hw_state: dict)  # Update from Arduino state
│   ├── _on_mode_changed(mode: str)   # Handle mode selection
│   ├── _on_fan_toggled(state: bool)  # Handle fan toggle
│   ├── _on_bpm_changed(value: int)   # Handle BPM change
│   ├── _validate_bpm(value: int) → bool  # Validate input
│   └── _enable_widgets_for_mode(mode: str)  # Mode-specific UI
│
└── Layout:
    [Mode: POT ▼]
    ├─ POT mode:  Controls disabled (potentiometer active)
    ├─ AUTO mode: BPM slider enabled, solenoid auto-pulses
    └─ MANUAL mode: All controls enabled
```

**Implementation:**

```python
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QComboBox, QCheckBox, QSlider, QSpinBox,
                              QGroupBox, QMessageBox)
from PyQt6.QtCore import Signal, Qt

class HardwareControlPanel(QWidget):
    # Signals
    mode_changed = Signal(str)
    fan_toggled = Signal(bool)
    bpm_changed = Signal(int)
    solenoid_toggled = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Mode selector
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Control Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["POT", "AUTO", "MANUAL"])
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        
        # Fan control
        self.fan_checkbox = QCheckBox("Fan On")
        layout.addWidget(self.fan_checkbox)
        
        # BPM control (for AUTO mode)
        bpm_group = QGroupBox("BPM Setpoint (AUTO mode only)")
        bpm_layout = QVBoxLayout()
        
        self.bpm_slider = QSlider(Qt.Orientation.Horizontal)
        self.bpm_slider.setRange(60, 180)
        self.bpm_slider.setValue(120)
        
        self.bpm_spinbox = QSpinBox()
        self.bpm_spinbox.setRange(60, 180)
        self.bpm_spinbox.setValue(120)
        
        # Link slider and spinbox
        self.bpm_slider.valueChanged.connect(self.bpm_spinbox.setValue)
        self.bpm_spinbox.valueChanged.connect(self.bpm_slider.setValue)
        
        bpm_layout.addWidget(self.bpm_slider)
        bpm_layout.addWidget(self.bpm_spinbox)
        bpm_group.setLayout(bpm_layout)
        layout.addWidget(bpm_group)
        self.bpm_group = bpm_group
        
        # Solenoid control (for MANUAL mode)
        self.solenoid_checkbox = QCheckBox("Solenoid Open (MANUAL mode only)")
        layout.addWidget(self.solenoid_checkbox)
        
        # Status display (read-only)
        status_group = QGroupBox("Current Hardware State")
        status_layout = QVBoxLayout()
        self.status_labels = {
            "fan": QLabel("Fan: Unknown"),
            "solenoid": QLabel("Solenoid: Unknown"),
            "bpm": QLabel("BPM: Unknown"),
            "mode": QLabel("Mode: Unknown")
        }
        for label in self.status_labels.values():
            status_layout.addWidget(label)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        layout.addStretch()
        
        # Initial state: POT mode (everything disabled)
        self._enable_widgets_for_mode("POT")
        
    def _connect_signals(self):
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.fan_checkbox.toggled.connect(self._on_fan_toggled)
        self.bpm_spinbox.valueChanged.connect(self._on_bpm_changed)
        self.solenoid_checkbox.toggled.connect(self.solenoid_toggled)
        
    def _on_mode_changed(self, mode: str):
        """Handle mode selection"""
        # Confirm mode change if user might lose control
        if mode == "POT":
            reply = QMessageBox.question(
                self, "Switch to POT Mode?",
                "Switching to POT mode will disable app control. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                # Revert combo box
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentText(self._current_mode)
                self.mode_combo.blockSignals(False)
                return
                
        self._current_mode = mode
        self._enable_widgets_for_mode(mode)
        self.mode_changed.emit(mode)
        
    def _enable_widgets_for_mode(self, mode: str):
        """Enable/disable widgets based on mode"""
        if mode == "POT":
            # POT mode: everything disabled
            self.fan_checkbox.setEnabled(False)
            self.bpm_group.setEnabled(False)
            self.solenoid_checkbox.setEnabled(False)
            
        elif mode == "AUTO":
            # AUTO mode: fan + BPM enabled
            self.fan_checkbox.setEnabled(True)
            self.bpm_group.setEnabled(True)
            self.solenoid_checkbox.setEnabled(False)
            
        elif mode == "MANUAL":
            # MANUAL mode: everything enabled
            self.fan_checkbox.setEnabled(True)
            self.bpm_group.setEnabled(False)
            self.solenoid_checkbox.setEnabled(True)
            
    def update_state(self, hw_state: dict):
        """Update status display from Arduino state"""
        self.status_labels["fan"].setText(f"Fan: {'ON' if hw_state.get('fan') == '1' else 'OFF'}")
        self.status_labels["solenoid"].setText(f"Solenoid: {'OPEN' if hw_state.get('sol') == '1' else 'CLOSED'}")
        self.status_labels["bpm"].setText(f"BPM: {hw_state.get('bpm', 'Unknown')}")
        self.status_labels["mode"].setText(f"Mode: {hw_state.get('mode', 'Unknown')}")
        
    def _on_fan_toggled(self, state: bool):
        """Validate and emit fan toggle"""
        self.fan_toggled.emit(state)
        
    def _on_bpm_changed(self, value: int):
        """Validate and emit BPM change"""
        if self._validate_bpm(value):
            self.bpm_changed.emit(value)
            
    def _validate_bpm(self, value: int) -> bool:
        """Validate BPM is in valid range"""
        return 60 <= value <= 180
```

---

### src/ui/connection_panel.py (RENAMED)

**Note:** This is the old `control_panel.py` renamed to avoid confusion

**Purpose:** Device connection controls only

- Arduino port selection + connect button
- Camera selection + connect button
- **Emergency Stop button (large, red)**
- Record button
- Export button

---

### src/ui/main_window.py (ENHANCED)

**New Layout:** Three columns instead of two

```python
def _setup_ui(self):
    central_widget = QWidget()
    self.setCentralWidget(central_widget)
    
    # Three-column layout
    main_splitter = QSplitter(Qt.Orientation.Horizontal)
    
    # Left: Sensor visualization (25%)
    self.sensor_panel = SensorPanel()
    
    # Middle: Hardware control (25%)
    self.hardware_control_panel = HardwareControlPanel()
    
    # Right: Camera feed (50%)
    self.camera_panel = CameraPanel()
    
    main_splitter.addWidget(self.sensor_panel)
    main_splitter.addWidget(self.hardware_control_panel)
    main_splitter.addWidget(self.camera_panel)
    main_splitter.setSizes([250, 250, 500])  # Proportional widths
    
    # Top: Connection controls
    self.connection_panel = ConnectionPanel()
    
    # Layout
    layout = QVBoxLayout(central_widget)
    layout.addWidget(self.connection_panel)
    layout.addWidget(main_splitter)
```

---

## Utils Layer Changes

### src/utils/validators.py (NEW)

**Purpose:** Input validation for control commands

```python
"""
Validators - Input Validation for Control Commands

**Functions:**
- validate_bpm(value: int) → tuple[bool, str]
- validate_mode(mode: str) → tuple[bool, str]
- validate_fan_state(state: bool) → tuple[bool, str]
- validate_command_rate(last_time: float, min_interval: float) → tuple[bool, str]
"""

def validate_bpm(value: int) -> tuple[bool, str]:
    """Validate BPM is in acceptable range"""
    if not isinstance(value, int):
        return False, "BPM must be an integer"
    if value < 60:
        return False, "BPM too low (minimum 60)"
    if value > 180:
        return False, "BPM too high (maximum 180)"
    return True, ""

def validate_mode(mode: str) -> tuple[bool, str]:
    """Validate control mode"""
    valid_modes = ["POT", "AUTO", "MANUAL"]
    if mode not in valid_modes:
        return False, f"Invalid mode. Must be one of: {valid_modes}"
    return True, ""

def validate_command_rate(last_time: float, min_interval: float = 0.1) -> tuple[bool, str]:
    """Prevent command flooding"""
    import time
    if time.time() - last_time < min_interval:
        return False, "Commands sent too rapidly. Please wait."
    return True, ""
```

---

### src/utils/constants.py (ENHANCED)

**New Control Constants:**

```python
# Existing constants
APP_NAME = "RHS Desktop"
APP_VERSION = "2.0.0"  # Updated for control system
PRESSURE_RANGE = (0, 258)
FLOW_RATE_TARGET = 1.5
HEART_RATE_RANGE = (60, 100)
ARDUINO_BAUD_RATE = 31250
ARDUINO_DATA_FIELDS = ["p1", "p2", "flow_rate", "heart_rate"]
CAMERA_RESOLUTION = (1920, 1200)
CAMERA_DEFAULT_FPS = 60
CAMERA_DEFAULT_EXPOSURE = 1000
GRAPH_TIME_WINDOW = 5

# NEW: Control constants
CONTROL_MODES = ["POT", "AUTO", "MANUAL"]
BPM_RANGE = (60, 180)
BPM_DEFAULT = 120
COMMAND_TIMEOUT = 1.0  # seconds
MIN_COMMAND_INTERVAL = 0.1  # seconds (prevent flooding)

# NEW: Arduino pins (for documentation)
PIN_FAN = 12
PIN_SOLENOID = 13
PIN_POT = "A3"
PIN_PT1 = "A0"
PIN_PT2 = "A1"
PIN_FLOW = "A2"
```

---

## Testing Layer Changes

### tests/mock_arduino.py (ENHANCED)

**New Feature:** Echo commands back

```python
class MockArduino(QThread):
    # ... existing sensor generation ...
    
    def __init__(self):
        super().__init__()
        self._command_queue = Queue()
        self.current_state = {
            "fan": True,
            "solenoid": False,
            "bpm": 120,
            "mode": "POT"
        }
        
    def send_command(self, cmd: str):
        """Process command and send ACK"""
        self._command_queue.put(cmd)
        
    def run(self):
        while self._running:
            # Generate sensor data
            # ...
            
            # Process commands
            if not self._command_queue.empty():
                cmd = self._command_queue.get()
                self._process_command(cmd)
                
    def _process_command(self, cmd: str):
        """Simulate Arduino command processing"""
        if cmd.startswith("SET_FAN"):
            value = int(cmd.split()[1])
            self.current_state["fan"] = bool(value)
            print(f"OK")  # Simulate response
            
        elif cmd.startswith("SET_BPM"):
            value = int(cmd.split()[1])
            self.current_state["bpm"] = value
            print(f"OK")
            
        elif cmd == "EMERGENCY_STOP":
            self.current_state["fan"] = False
            self.current_state["solenoid"] = False
            print(f"OK")
            
        # ... other commands ...
```

---

## Documentation Changes

### docs/arduino_protocol.md (NEW)

See timeline update document for full protocol spec

### docs/safety_guide.md (NEW)

```markdown
# RHS Desktop Application - Safety Guide

## Emergency Stop Procedure

**When to use Emergency Stop:**
- Hardware malfunction
- Unexpected pressure readings
- Loss of control
- Any unsafe condition

**How to Emergency Stop:**
1. Click large red "E-STOP" button in toolbar
2. All outputs (fan, solenoid) will shut down immediately
3. UI will lock all control widgets
4. Arduino will kill outputs independently (hardware-level safety)

**After Emergency Stop:**
1. Identify and fix the issue
2. Click "Reset" button to unlock UI
3. Manually reconnect devices if needed

## Safe Operating Procedures

### Before Starting
- Verify all connections secure
- Check pressure sensor calibration
- Test emergency stop button

### During Operation
- Monitor pressure readings continuously
- Do not exceed 258 mmHg
- Keep BPM between 60-180

### Mode Switching
- **POT → AUTO:** App takes over BPM control from potentiometer
- **AUTO → MANUAL:** Solenoid stops auto-pulsing, requires manual control
- **Any → POT:** App releases control back to potentiometer

## Failure Modes

| Failure | Behavior | Recovery |
|---------|----------|----------|
| Arduino disconnect | UI shows error, stops sending commands | Reconnect Arduino, app auto-recovers |
| Invalid command | Arduino responds ERROR, app shows notification | Correct input, retry |
| Command timeout | App assumes command failed | Check Arduino connection |
| Emergency stop | All outputs killed, UI locked | Click Reset after fixing issue |
```

---

## Arduino Firmware Structure

### arduino/rhs_firmware/rhs_firmware.ino (MODIFIED)

**Key Changes:**

```cpp
// Global control variables
bool fanState = HIGH;
bool solenoidOverride = false;
int bpmOverride = -1;  // -1 = use potentiometer
String controlMode = "POT";  // POT|AUTO|MANUAL

void loop() {
  // 1. Check for incoming commands FIRST
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    parseCommand(cmd);
  }
  
  // 2. Read sensors (existing code)
  // ...
  
  // 3. Control outputs using override values
  digitalWrite(FPin, fanState);
  
  int effectiveBPM = (bpmOverride > 0) ? bpmOverride : analogRead(POTPin);
  
  if (controlMode == "MANUAL") {
    digitalWrite(SPin, solenoidOverride);
  } else {
    // Existing auto-pulse logic using effectiveBPM
  }
  
  // 4. Serial output (existing code)
  // ...
}

void parseCommand(String cmd) {
  if (cmd.startsWith("SET_FAN")) {
    fanState = (cmd.substring(8).toInt() == 1) ? HIGH : LOW;
    Serial.println("OK");
  }
  else if (cmd.startsWith("SET_BPM")) {
    bpmOverride = cmd.substring(8).toInt();
    Serial.println("OK");
  }
  else if (cmd.startsWith("SET_MODE")) {
    controlMode = cmd.substring(9);
    Serial.println("OK");
  }
  else if (cmd == "EMERGENCY_STOP") {
    fanState = LOW;
    solenoidOverride = LOW;
    digitalWrite(FPin, fanState);
    digitalWrite(SPin, solenoidOverride);
    Serial.println("OK");
  }
  else if (cmd == "GET_STATUS") {
    Serial.print("STATUS FAN:");
    Serial.print(fanState == HIGH ? "1" : "0");
    Serial.print(" SOL:");
    Serial.print(solenoidOverride ? "1" : "0");
    Serial.print(" BPM:");
    Serial.print(effectiveBPM);
    Serial.print(" MODE:");
    Serial.println(controlMode);
  }
  else {
    Serial.println("ERROR Unknown command");
  }
}
```

---

## Summary of Changes by File

| File | Change Type | Description |
|------|-------------|-------------|
| `arduino_handler.py` | Enhanced | Bidirectional communication, command queue |
| `state_manager.py` | Enhanced | Hardware state tracking |
| `data_logger.py` | Enhanced | Log control commands in CSV |
| `hardware_control_panel.py` | **NEW** | Control UI widget |
| `connection_panel.py` | Renamed | Was `control_panel.py` |
| `safety_dialog.py` | **NEW** | Confirmation dialogs |
| `main_window.py` | Enhanced | Three-column layout |
| `validators.py` | **NEW** | Input validation |
| `constants.py` | Enhanced | Control constants added |
| `mock_arduino.py` | Enhanced | Command echo capability |
| `arduino_protocol.md` | **NEW** | Command specification |
| `safety_guide.md` | **NEW** | Emergency procedures |
| `rhs_firmware.ino` | Modified | Accept serial commands |

---

This structure supports the full control system while maintaining clean separation between monitoring and control concerns.
