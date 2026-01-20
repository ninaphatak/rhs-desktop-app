# RHS Desktop Application - Updated Development Timeline v2.0

## Executive Summary of Changes

**Original Plan:** 8 weeks, passive monitoring tool  
**Updated Plan:** 10 weeks, active control system + monitoring

**Key Additions:**
1. Bidirectional Arduino communication (Week 2 expansion + Week 2.5)
2. Hardware control panel UI (Week 4)
3. Command validation and safety systems (Week 4)
4. Extended testing for control features (Week 9)

**Timeline Extension:** +2 weeks (total 10 weeks, ending March 22, 2026)

---

## Revised Week Structure

### Week 2: Setup & Research (January 12-15, 2026)

### Goals
- Development environment ready
- All SDKs installed and tested
- MapAnything verified working

### Tasks

#### January 12-13: Environment Setup
- [x] Install Python 3.11
- [x] Install Basler Pylon SDK (download from baslerweb.com)
- [ ] Test pypylon installation: `pip install pypylon`
- [ ] Run pypylon sample script to verify camera SDK works
- [x] Install remaining packages: `pip install PyQt6 pyqtgraph opencv-python pyserial numpy pandas`
- [x] Create GitHub repository
- [x] Create directory structure per architecture document

#### January 14: MapAnything Setup
- [ ] Clone MapAnything repo: `git clone https://github.com/facebookresearch/map-anything.git`
- [ ] Install MapAnything dependencies (may require GPU)
- [ ] Run MapAnything on sample images to verify it works
- [ ] Document the input format requirements for your use case
- [ ] Note any issues or special requirements

#### January 15: Arduino Review
- [ ] Review existing Arduino code from RHS SOP
- [ ] Connect Arduino to computer
- [ ] Test serial communication with simple Python script
- [ ] Verify data format: "P1 P2 FLOW HR" space-separated
- [ ] Note baud rate (31250) and any parsing requirements

### Deliverables
- [x] Working development environment on your machine
- [ ] pypylon successfully captures test frames (or ready for when camera arrives)
- [ ] MapAnything runs successfully on sample images
- [ ] Serial communication with Arduino verified
- [x] GitHub repo created with initial structure

### Notes
```
If camera hasn't arrived yet, you can still:
- Install Pylon SDK
- Install pypylon
- Write camera code using mock_camera.py for testing
- Verify SDK installation with: python -c "from pypylon import pylon; print('pypylon works')"
```

---

### Week 3: Project Foundation (January 16-22, 2026)

### Goals
- Complete project structure
- Configuration system working
- Mock data generators for testing without hardware

### Tasks

#### January 16-17: Project Structure
- [x] Create all directories:
  ```
  src/
  src/core/
  src/ui/
  src/ui/dialogs/
  src/utils/
  tests/
  output/
  docs/
  arduino/
  ```
- [x] Create all `__init__.py` files
- [x] Write `requirements.txt`:
  ```
  PyQt6>=6.4.0
  pyqtgraph>=0.13.0
  pypylon>=2.0.0
  opencv-python>=4.8.0
  pyserial>=3.5
  numpy>=1.24.0
  pandas>=2.0.0
  ```
- [x] Write `src/utils/constants.py` with all application constants
- [ ] Write `src/utils/config.py` with Config class (load/save JSON)

#### January 18-19: Mock Data Generators
- [ ] Create `tests/mock_arduino.py`:
  - Class that generates realistic P1, P2, flow, HR values
  - Simulates serial timing
  - Can emit data via callback or queue
  - **Enhanced for v2:** Should echo commands back for testing control system
  - Useful for testing without Arduino connected
- [ ] Create `tests/mock_camera.py`:
  - Generates grayscale test frames (1920x1200)
  - Draws black dots on white background
  - Dots can move slightly between frames
  - Useful for testing without Basler camera

#### January 20-22: Basic Application Shell
- [ ] Create `src/main.py`:
  - Initialize QApplication
  - Create MainWindow
  - Start event loop
- [ ] Create `src/ui/main_window.py`:
  - Basic QMainWindow subclass
  - Empty layout with placeholders
  - Menu bar (File > Exit)
  - Status bar
- [ ] Create `run.py` launcher script
- [ ] Test app launches on your machine
- [ ] If possible, test on both macOS and Windows

### Deliverables
- [x] Complete directory structure in GitHub (including `arduino/` folder)
- [x] `constants.py` with all app constants defined
- [ ] `config.py` that saves/loads settings to JSON file
- [ ] `mock_arduino.py` generates fake sensor data (and echoes commands)
- [ ] `mock_camera.py` generates fake frames with dots
- [ ] Basic app window opens without errors

### Code to Verify
```python
# Test config
from src.utils.config import Config
config = Config()
config.set("test_key", "test_value")
config.save()
config.load()
assert config.get("test_key") == "test_value"
print("Config works!")

# Test mock arduino
from tests.mock_arduino import MockArduino
mock = MockArduino()
data = mock.generate_reading()
print(f"Mock sensor data: {data}")

# Test mock camera
from tests.mock_camera import MockCamera
mock_cam = MockCamera()
frame = mock_cam.generate_frame()
print(f"Mock frame shape: {frame.shape}")
```

---

### Week 4: Arduino Communication - BIDIRECTIONAL (January 23-29, 2026)
**CHANGES:**
- **January 27-28:** Add command sending capability to `ArduinoHandler`
  - New signals: `command_sent`, `command_acknowledged`
  - New methods: `send_command()`, `set_fan()`, `set_bpm()`, `set_mode()`, `emergency_stop()`
  - Implement command queue for thread-safe writing
- **January 29:** Test command sending/receiving with Arduino

**New Deliverables:**
- Bidirectional serial communication working
- Commands sent and acknowledged
- Mock generator echoes commands

### Week 4.5: Arduino Firmware Modification (January 30 - February 2, 2026)
**NEW WEEK - ARDUINO WORK**

**January 30-31: Command Protocol Design**
- Define text-based command format:
  ```
  SET_FAN <0|1>
  SET_SOLENOID <0|1>
  SET_BPM <value>
  SET_MODE <MANUAL|AUTO|POT>
  EMERGENCY_STOP
  GET_STATUS
  ```
- Define responses: `OK`, `ERROR <msg>`, `STATUS ...`
- Document in `docs/arduino_protocol.md`

**February 1: Firmware Implementation**
- Add serial input reading in `loop()`
- Implement command parser
- Add control override variables:
  ```cpp
  bool fanState = HIGH;
  bool solenoidOverride = false;
  int bpmOverride = -1;  // -1 = use potentiometer
  String controlMode = "POT";
  ```
- Modify existing control logic to use overrides

**February 2: Testing**
- Test via Serial Monitor
- Test mode switching
- Test emergency stop
- Test potentiometer fallback

**Deliverables:**
- Arduino accepts commands via serial
- Potentiometer still works as fallback
- Emergency stop tested
- Protocol documented

### Week 5: Core UI & State Manager (February 3-9, 2026)
**CHANGES:**
- State manager gets new signals:
  - `control_command_sent = Signal(str)`
  - `hardware_state_changed = Signal(dict)`
- State manager tracks hardware state:
  - `current_hardware_state: dict  # {fan, solenoid, bpm, mode}`
  
**Main Window Layout - THREE COLUMNS:**
```
┌─────────────────────────────────────────────────────────────────────┐
│ [Port ▼] [Connect] [Camera ▼] [Connect Cam] [🔴 E-STOP] [Record]   │
├──────────────────┬──────────────────┬───────────────────────────────┤
│  SENSOR PANEL    │  CONTROL PANEL   │      CAMERA PANEL             │
│  (Left, 25%)     │  (Middle, 25%)   │      (Right, 50%)             │
└──────────────────┴──────────────────┴───────────────────────────────┘
```

**New Components:**
- `HardwareControlPanel` widget (placeholder for Week 4)
- `ConnectionPanel` widget (renamed from ControlPanel)
- Emergency Stop button in toolbar (large, red, prominent)

**Deliverables:**
- Three-column layout working
- Hardware control panel connected to ArduinoHandler
- Emergency stop button functional
- Status bar shows control mode

### Week 6: Hardware Control Panel Implementation (February 10-16, 2026)
**NEW WEEK**

**February 10-11: HardwareControlPanel Widget**
Create `src/ui/hardware_control_panel.py` with:
- Mode selector: POT / AUTO / MANUAL
- Fan toggle (ON/OFF)
- BPM slider (60-180) + spinbox
- Solenoid toggle (for MANUAL mode)
- Status display (read-only, shows actual hardware state)

**February 12-13: Signal/Slot Connections**
- Connect widget signals to ArduinoHandler methods
- Implement `update_state(hw_state)` to show hardware feedback
- Handle mode-specific widget enabling/disabling

**February 14-15: Command Validation & Safety**
- Input validation (BPM range, rapid clicking prevention)
- Confirmation dialogs for dangerous actions
- Safety lockouts (e.g., can't change mode while recording)
- Visual feedback (pending commands, success/failure notifications)

**February 16: Integration & Testing**
- Wire into MainWindow
- Test all three control modes
- Test emergency stop thoroughly
- Test validation edge cases

**Deliverables:**
- Full hardware control UI working
- All three modes (POT/AUTO/MANUAL) functional
- Command validation prevents invalid inputs
- Emergency stop locks UI and kills hardware
- Visual feedback for all actions

### Week 7: Sensor Visualization (February 17-23, 2026)
**SAME AS ORIGINAL WEEK 4**

### Week 8: Basler Camera Integration (February 24 - March 2, 2026)
**SAME AS ORIGINAL WEEK 5**

### Week 9: Dot Tracking & Data Logging (March 3-9, 2026)
**SAME AS ORIGINAL WEEK 6**

### Week 10: MapAnything Export (March 10-16, 2026)
**SAME AS ORIGINAL WEEK 7**

### Week 11: Control System Testing & Safety (March 17-20, 2026)
**NEW WEEK**

**March 17-18: Integration Testing**
- Test recording while controlling hardware
- Test mode switching during recording
- Test emergency stop during various operations
- Test camera + control simultaneously
- Verify CSV logging includes control commands

**March 19: Failure Mode Testing**
- Arduino disconnect during control
- Invalid command handling
- Rapid command flooding
- Concurrent control from multiple sources (if applicable)
- Power loss simulation

**March 20: Safety Documentation**
- Document all safety features
- Create user safety guide
- Document emergency procedures
- List all validation rules
- Create troubleshooting guide for control issues

**Deliverables:**
- All integration scenarios tested
- Failure modes handled gracefully
- Safety documentation complete

### Week 12: Polish & Release (March 21-22, 2026)
**COMPRESSED FROM ORIGINAL WEEK 8**

**March 21: Final Polish**
- Code cleanup
- Cross-platform testing (macOS + Windows)
- Final documentation review
- Screenshots for README

**March 22: Release**
- Tag v1.0.0
- Push to GitHub
- Demo to team

**Deliverables:**
- Production-ready application
- Complete documentation
- Tested on both platforms

---

## Updated Architecture Components

### New Files to Create

**src/core/arduino_handler.py (ENHANCED)**
```python
class ArduinoHandler(QThread):
    # Existing signals
    data_received = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    
    # NEW signals
    command_sent = Signal(str)
    command_acknowledged = Signal(str, bool)  # command, success
    
    # NEW methods
    def send_command(self, cmd: str) -> None
    def set_fan(self, state: bool) -> None
    def set_bpm(self, value: int) -> None
    def set_mode(self, mode: str) -> None  # POT/AUTO/MANUAL
    def set_solenoid(self, state: bool) -> None  # MANUAL mode only
    def emergency_stop(self) -> None
    
    # Enhanced run() method
    def run(self):
        # Read from serial
        # Parse data OR command responses
        # Handle command queue (write commands)
        # Emit appropriate signals
```

**src/ui/hardware_control_panel.py (NEW)**
```python
class HardwareControlPanel(QWidget):
    # Signals
    mode_changed = Signal(str)
    fan_toggled = Signal(bool)
    bpm_changed = Signal(int)
    solenoid_toggled = Signal(bool)
    
    # Widgets
    mode_combo: QComboBox  # POT/AUTO/MANUAL
    fan_toggle: QCheckBox
    bpm_slider: QSlider  # 60-180
    bpm_spinbox: QSpinBox
    solenoid_toggle: QCheckBox
    status_labels: dict  # read-only state display
    
    # Methods
    def update_state(self, hw_state: dict) -> None
    def _validate_bpm(self, value: int) -> bool
    def _enable_widgets_for_mode(self, mode: str) -> None
```

**src/ui/connection_panel.py (RENAMED from control_panel.py)**
```python
class ConnectionPanel(QWidget):
    # Connection controls only
    # Emergency stop button
    # Record/Export buttons
```

**src/core/state_manager.py (ENHANCED)**
```python
class StateManager(QObject):
    # Existing signals
    sensor_updated = Signal(dict)
    frame_updated = Signal(dict)
    tracking_updated = Signal(dict)
    connection_changed = Signal(str, bool)
    recording_changed = Signal(bool)
    error_occurred = Signal(str, str)
    
    # NEW signals
    control_command_sent = Signal(str)
    hardware_state_changed = Signal(dict)
    
    # NEW state
    current_hardware_state: dict  # {fan, solenoid, bpm, mode}
    
    # NEW methods
    def update_hardware_state(self, state: dict) -> None
```

**docs/arduino_protocol.md (NEW)**
```markdown
# Arduino Communication Protocol

## Command Format
Commands are newline-delimited ASCII text.

### Commands from Desktop → Arduino
- `SET_FAN 0|1` - Turn fan off/on
- `SET_SOLENOID 0|1` - Force solenoid closed/open (MANUAL mode only)
- `SET_BPM <60-180>` - Set target BPM (AUTO mode)
- `SET_MODE POT|AUTO|MANUAL` - Change control mode
- `EMERGENCY_STOP` - Kill all outputs immediately
- `GET_STATUS` - Request current hardware state

### Responses from Arduino → Desktop
- `OK` - Command executed successfully
- `ERROR <message>` - Command failed
- `STATUS FAN:<0|1> SOL:<0|1> BPM:<value> MODE:<mode>` - State response

## Data Stream Format (unchanged)
Space-delimited: `P1 P2 FLOW HR\n`

## Control Modes
- **POT:** BPM from potentiometer, app controls disabled
- **AUTO:** BPM from app, solenoid auto-pulses based on app BPM
- **MANUAL:** Direct solenoid control from app, no auto-pulsing
```

---

## Risk Assessment Updates

### New Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Arduino firmware bugs | **High** | **High** | Extensive testing Week 2.5, potentiometer fallback |
| Command protocol ambiguity | Medium | Medium | Clear documentation, test all edge cases |
| Safety failures (emergency stop) | Low | **Critical** | Hardware-level stop, extensive testing Week 9 |
| Mode confusion by users | Medium | Low | Clear UI, mode indicator in status bar |
| Control latency issues | Medium | Medium | Thread-safe queues, async command sending |

### Original Risks (Still Apply)
- Camera delayed → Use mock_camera.py
- Pylon SDK issues → Test in Week 0
- Dot detection unreliable → Tune thresholds, good lighting
- MapAnything fails → 2D tracking fallback
- Cross-platform issues → Test throughout

---

## Timeline Comparison

### Original 8-Week Plan
- Week 0: Setup
- Week 1: Foundation
- Week 2: Arduino (read-only)
- Week 3: UI + State
- Week 4: Sensor viz
- Week 5: Camera
- Week 6: Dot tracking
- Week 7: MapAnything
- Week 8: Polish

### New 10-Week Plan (Renumbered Starting at Week 2)
- Week 2: Setup **(same)** - Jan 12-15
- Week 3: Foundation **(same)** - Jan 16-22
- Week 4: Arduino - bidirectional **(enhanced)** - Jan 23-29
- **Week 4.5: Arduino firmware (NEW)** - Jan 30 - Feb 2
- Week 5: UI + State **(enhanced, +4 days)** - Feb 3-9
- **Week 6: Control panel (NEW)** - Feb 10-16
- Week 7: Sensor viz **(same)** - Feb 17-23
- Week 8: Camera **(same)** - Feb 24 - Mar 2
- Week 9: Dot tracking **(same)** - Mar 3-9
- Week 10: MapAnything **(same)** - Mar 10-16
- **Week 11: Control testing (NEW)** - Mar 17-20
- Week 12: Polish **(compressed)** - Mar 21-22

### Work Breakdown
- **Python desktop app:** ~75 hours
- **Arduino firmware:** ~15 hours
- **Testing/Documentation:** ~10 hours
- **Total:** ~100 hours over 10 weeks

---

## Critical Path Items

These MUST be completed in order:

1. **Week 2:** Environment setup
2. **Week 4:** Bidirectional ArduinoHandler
3. **Week 4.5:** Arduino firmware accepting commands
4. **Week 5:** State manager with control state
5. **Week 6:** Hardware control panel
6. **Week 11:** Safety testing

Everything else (camera, dot tracking, MapAnything) can proceed in parallel after Week 5.

---

## Questions for Team Meeting

Before proceeding with this timeline, discuss with your team:

1. **Hardware inventory:** What other components need control beyond fan/solenoid?
2. **Safety requirements:** What should emergency stop do? Any other safety features needed?
3. **Control authority:** Should app be able to override all manual controls?
4. **Recording behavior:** Can users change control settings during recording?
5. **Priority:** If timeline slips, what gets cut first? (MapAnything export? Advanced control modes?)

---

## Next Steps

1. **Immediate:** Get team consensus on hardware control requirements
2. **Week 4:** Start enhancing ArduinoHandler for bidirectional communication
3. **Week 4.5:** Modify Arduino firmware (highest risk item)
4. **Week 5:** Implement state management for control
5. **Week 6:** Build control panel UI

---

## Success Criteria (Updated)

By end of Week 12, the app should:

- [x] Connect to Arduino and read sensor data
- [x] Display real-time graphs for P1, P2, Flow, HR
- [x] Connect to Basler camera and show live feed
- [x] Detect and track dots on valve
- [x] Record data to CSV with timestamps
- [x] **Control fan on/off from UI**
- [x] **Control BPM setpoint from UI (AUTO mode)**
- [x] **Manual solenoid control (MANUAL mode)**
- [x] **Emergency stop kills all outputs**
- [x] **Three control modes working (POT/AUTO/MANUAL)**
- [x] Export session for MapAnything processing
- [x] Handle errors gracefully
- [x] Work on macOS and Windows
- [x] **Safe command validation and user feedback**
