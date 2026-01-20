# CLAUDE.MD - AI Assistant Context

## Project Overview

**Project Name:** RHS Desktop Application (Right Heart Simulator Control & Monitoring System)
**Type:** Medical device training application
**Timeline:** January 12 - March 22, 2025 (10 weeks, ~100 hours)
**Institution:** UC Riverside Bioengineering Senior Design

This is a **real-time control and monitoring system** for the Right Heart Simulator (RHS), a medical training device that simulates cardiovascular procedures. The application provides bidirectional communication with Arduino-based hardware, live camera feed processing, and 3D reconstruction capabilities.

## Tech Stack

- **Language:** Python 3.11
- **GUI Framework:** PyQt6 + pyqtgraph (real-time plotting)
- **Camera:** Basler pypylon SDK (1920x1200 @ 60fps)
- **Computer Vision:** OpenCV (dot tracking)
- **Hardware Communication:** pyserial (31250 baud, bidirectional)
- **3D Reconstruction:** Meta MapAnything
- **Testing:** Mock generators for hardware-independent development

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Port ▼] [Connect] [Camera ▼] [Connect Cam] [🔴 E-STOP] [Record]   │
├──────────────────┬──────────────────┬───────────────────────────────┤
│  SENSOR PANEL    │  CONTROL PANEL   │      CAMERA PANEL             │
│  (Left, 25%)     │  (Middle, 25%)   │      (Right, 50%)             │
│                  │                  │                               │
│  • P1/P2 graphs  │  • Mode selector │  • Live camera feed           │
│  • Flow graph    │  • Fan control   │  • Dot overlay                │
│  • HR display    │  • BPM slider    │  • Tracking data              │
│                  │  • Solenoid ctl  │                               │
└──────────────────┴──────────────────┴───────────────────────────────┘
```

### Directory Structure

```
rhs-desktop-app/
├── src/
│   ├── core/              # Business logic (QThread workers)
│   │   ├── arduino_handler.py        # Bidirectional serial communication
│   │   ├── basler_camera.py          # Camera capture thread
│   │   ├── dot_tracker.py            # OpenCV dot detection
│   │   ├── state_manager.py          # Central event hub + state
│   │   ├── data_logger.py            # CSV + frame recording
│   │   └── mapanything_exporter.py   # 3D export format
│   ├── ui/                # PyQt6 interface
│   │   ├── main_window.py            # Three-column layout
│   │   ├── sensor_panel.py           # Real-time graphs
│   │   ├── camera_panel.py           # Live video display
│   │   ├── connection_panel.py       # Device connections + E-STOP
│   │   ├── hardware_control_panel.py # Hardware control UI
│   │   └── dialogs/                  # Modal dialogs
│   └── utils/             # Configuration & validation
│       ├── config.py                 # JSON settings
│       ├── constants.py              # App-wide constants
│       └── validators.py             # Input validation
├── tests/
│   ├── mock_arduino.py               # Simulated sensor data
│   └── mock_camera.py                # Simulated camera frames
├── arduino/
│   └── rhs_firmware/
│       └── rhs_firmware.ino          # Arduino firmware (C++)
├── docs/
│   ├── arduino_protocol.md           # Command protocol spec
│   └── safety_guide.md               # Emergency procedures
└── outputs/                          # Recorded sessions
```

## Key Design Patterns

1. **Threaded I/O:** Arduino and camera run in separate QThreads to prevent UI blocking
2. **Signal/Slot Architecture:** StateManager acts as central message bus (Qt signals)
3. **Bidirectional Communication:** Command queue + acknowledgment protocol for reliable hardware control
4. **Mock Hardware:** Development continues without physical devices via mock generators
5. **Rolling Buffers:** 5-second deque buffers for real-time graph scrolling without memory leaks

## Control System

### Three Control Modes

1. **POT (Potentiometer):** Hardware potentiometer controls BPM, app controls disabled (fallback mode)
2. **AUTO:** App sets BPM setpoint, Arduino auto-pulses solenoid at specified rate
3. **MANUAL:** Direct solenoid on/off control from app, no auto-pulsing

### Arduino Command Protocol

Commands are newline-delimited ASCII text over serial (31250 baud):

```
Desktop → Arduino:
- SET_FAN <0|1>           # Turn fan on/off
- SET_SOLENOID <0|1>      # Manual solenoid control (MANUAL mode only)
- SET_BPM <60-180>        # Set BPM setpoint (AUTO mode)
- SET_MODE <POT|AUTO|MANUAL>  # Switch control mode
- EMERGENCY_STOP          # Kill all outputs immediately
- GET_STATUS              # Request hardware state

Arduino → Desktop:
- OK                      # Command successful
- ERROR <message>         # Command failed
- STATUS FAN:<0|1> SOL:<0|1> BPM:<value> MODE:<mode>
```

### Hardware State Tracking

StateManager maintains current hardware state:
```python
{
    "fan": bool,          # Fan on/off
    "solenoid": bool,     # Solenoid open/closed
    "bpm": int,           # Current BPM (60-180)
    "mode": str           # POT/AUTO/MANUAL
}
```

## Critical Requirements

### Real-Time Performance
- UI must handle 30+ sensor updates/second without lag
- 60fps camera feed with live dot tracking overlay
- Non-blocking I/O (all hardware operations in QThreads)

### Safety-First Design
- **Emergency stop must work instantly** - large red button in toolbar
- Hardware-level safety in Arduino firmware (independent of app state)
- Command validation prevents invalid inputs (BPM range 60-180, mode constraints)
- Emergency stop clears command queue and kills all outputs

### Reliability
- Graceful degradation when hardware disconnects mid-operation
- Command acknowledgment system (timeout after 1 second)
- Thread-safe command queue for reliable communication
- Data integrity: CSV logging is thread-safe, includes control commands

### Cross-Platform Support
- Must work on macOS and Windows
- Serial port naming differs across platforms (e.g., `/dev/tty.usbmodem*` vs `COM*`)
- Path handling uses `pathlib` for compatibility

## Development Timeline

**PRIMARY REFERENCE:** `RHS_Development_Timeline.md` (10-week plan)

Current phase (refer to timeline document for details):
- **Week 2 (Jan 12-15):** Setup & environment configuration
- **Week 3 (Jan 16-22):** Foundation (serial, camera, mock generators)
- **Week 4 (Jan 23-29):** Bidirectional Arduino communication
- **Week 4.5 (Jan 30 - Feb 2):** Arduino firmware modification (C++)
- **Week 5 (Feb 3-9):** UI layout + state management
- **Week 6 (Feb 10-16):** Hardware control panel implementation
- **Week 7 (Feb 17-23):** Sensor visualization
- **Week 8 (Feb 24 - Mar 2):** Basler camera integration
- **Week 9 (Mar 3-9):** Dot tracking & data logging
- **Week 10 (Mar 10-16):** MapAnything export
- **Week 11 (Mar 17-20):** Integration testing
- **Week 12 (Mar 21-22):** Polish & release

**Always check the timeline document first** before suggesting implementation approaches.

## When Helping

### DO:
1. **Reference the timeline** - Check which week we're in and what deliverables are expected
2. **Follow established architecture** - Don't introduce conflicting patterns (e.g., avoid async/await, we use QThreads)
3. **Consider hardware constraints** - Camera/Arduino may not be physically present, maintain identical mock interfaces
4. **Prioritize safety** - Control commands need validation, E-STOP must be fail-safe
5. **Challenge bad decisions** - If you see a design flaw or better approach, speak up
6. **Distinguish monitoring vs. control** - This is an active control system, not just a data viewer
7. **Think cross-platform** - Account for macOS/Windows differences
8. **Maintain thread safety** - All Qt signals from background threads must use queued connections

### DON'T:
1. Don't suggest architectural changes without understanding existing design decisions
2. Don't assume hardware is connected (ask first, use mocks when needed)
3. Don't add complexity without justification (YAGNI principle)
4. Don't bypass safety validations for "convenience"
5. Don't use blocking operations in the main thread (no time.sleep() in UI code)

## Common Gotchas

1. **Serial communication is asynchronous** - Use thread-safe queues for commands, not direct writes
2. **PyQt signals need thread context** - Can't emit from arbitrary threads, use QMetaObject.invokeMethod
3. **Arduino baud rate is unusual** - 31250, not standard 9600 or 115200
4. **Control modes affect widget states** - POT disables controls, AUTO enables BPM only, MANUAL enables all
5. **Emergency stop must clear command queue** - Don't send pending commands after E-STOP
6. **Mock generators must echo commands** - For testing control system without hardware
7. **Rolling buffers prevent memory leaks** - Use collections.deque with maxlen for graph data

## Safety-Critical Reminders

- **Emergency stop is non-negotiable** - Must work even if app crashes
- **Command validation** - Never send invalid commands to Arduino
- **Mode constraints** - Solenoid manual control only works in MANUAL mode
- **Fallback behavior** - Arduino should revert to potentiometer if app disconnects
- **No uncontrolled state** - Always know what mode the system is in
- **Pressure limits** - Never exceed 258 mmHg
- **BPM bounds** - Must stay within 60-180 range

## Student Context

The student has:
- CS fundamentals (Git, testing, design patterns from CS 100)
- Limited production Python experience
- Learning Arduino development (C++)
- Learning PyQt6 and real-time systems
- No prior experience with medical device development

Be prepared to:
- Explain threading concepts (QThread, signals/slots)
- Debug serial communication issues
- Help with Arduino firmware modification
- Explain real-time data handling strategies
- Discuss safety system design

## Important Documents

- **`PROJECT_INSTRUCTIONS.md`** - Detailed project context for AI assistance
- **`RHS_Development_Timeline.md`** - Week-by-week implementation plan (PRIMARY REFERENCE)
- **`RHS_Code_Structure_v2.md`** - Comprehensive architecture and implementation details
- **`TIMELINE_CHANGE_NOTICE.md`** - Why scope expanded from monitoring to control
- **`docs/arduino_protocol.md`** - Command protocol specification
- **`docs/safety_guide.md`** - Emergency procedures and safe operating practices

## Questions to Ask

Before implementing, consider asking:
- Has the hardware (camera, Arduino) arrived yet?
- Which week of development are we currently in?
- Are there specific hardware components beyond fan/solenoid that need control?
- What are the user's preferences for code style/verbosity?
- Have there been any deviations from the timeline?

## Quick Reference

### Serial Communication
```python
# Command format: "COMMAND_NAME param1 param2\n"
arduino_handler.send_command("SET_FAN 1")  # Queue command
arduino_handler.set_bpm(120)  # Helper method with validation
arduino_handler.emergency_stop()  # Clear queue and stop
```

### State Management
```python
# StateManager acts as central hub
state_manager.hardware_state_changed.connect(on_hardware_state_changed)
state_manager.update_hardware_state({"fan": True, "bpm": 120})
```

### UI Updates (from background threads)
```python
# Use Qt signals, not direct UI updates
self.data_received.emit(sensor_data)  # Safe from QThread
# Never: self.label.setText("foo")  # UNSAFE from QThread
```

### Validation
```python
from src.utils.validators import validate_bpm, validate_mode
valid, error_msg = validate_bpm(150)
if not valid:
    # Handle error
```

## External Resources

- **PyQt6 Documentation:** https://doc.qt.io/qtforpython-6/
- **pyqtgraph Documentation:** https://pyqtgraph.readthedocs.io/
- **pypylon Samples:** https://github.com/basler/pypylon-samples
- **OpenCV Documentation:** https://docs.opencv.org/
- **MapAnything Repository:** https://github.com/facebookresearch/map-anything

## Current Project Status

Check git log and timeline document for current progress. The project structure exists with docstrings and some stub implementations. Components are being implemented according to the 10-week timeline.

---

**Note to AI Assistants:** This is a safety-critical control system for medical training. Always prioritize safety validations, error handling, and fail-safe behavior. When in doubt about safety implications, ask the user for clarification.
