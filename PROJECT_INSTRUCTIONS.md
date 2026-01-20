# Project Instructions: RHS Desktop Application

## Project Context
You are helping build a **desktop application for the Right Heart Simulator (RHS)** - a medical device simulation platform. This is a senior design project at UC Riverside, scheduled for January 12 - March 22, 2026 (Week 2-12, 10 weeks total, ~100 hours).

## What is RHS?
The RHS simulates right heart cardiovascular procedures for medical training. The system consists of:
- **Arduino-based control system** measuring pressure (P1, P2), flow rate, and heart rate
- **Controllable hardware:** Fan (pin 12), solenoid valve (pin 13), BPM setpoint (potentiometer override)
- **Basler high-speed camera** (1920x1200 @ 60fps) tracking valve movement via black dots
- **Goal:** Real-time monitoring + active control + 3D reconstruction using Meta's MapAnything

**CRITICAL:** This is NOT just a monitoring tool - it's an **active control system** that can directly control RHS hardware components.

## Technical Stack
- **Language:** Python 3.11
- **GUI:** PyQt6 + pyqtgraph for real-time plotting
- **Camera:** pypylon (Basler SDK)
- **Computer Vision:** OpenCV for dot detection
- **Hardware Communication:** pyserial for bidirectional Arduino communication (31250 baud)
- **3D Reconstruction:** MapAnything (Facebook Research)

## Architecture Overview
```
rhs-desktop-app/
├── src/
│   ├── core/           # Business logic
│   │   ├── arduino_handler.py      # Bidirectional serial (read sensors + send commands)
│   │   ├── basler_camera.py        # Camera capture (QThread)
│   │   ├── dot_tracker.py          # CV-based dot detection
│   │   ├── state_manager.py        # Central event hub + hardware state tracking
│   │   ├── data_logger.py          # CSV + frame recording
│   │   └── mapanything_exporter.py # Export format conversion
│   ├── ui/             # PyQt6 interface
│   │   ├── main_window.py          # Three-column layout (sensors | control | camera)
│   │   ├── sensor_panel.py         # Real-time graphs (P1/P2, flow, HR)
│   │   ├── camera_panel.py         # Live video feed + dot overlay
│   │   ├── connection_panel.py     # Device connection controls + E-STOP
│   │   ├── hardware_control_panel.py # Hardware control UI (fan, BPM, solenoid, modes)
│   │   └── dialogs/
│   │       ├── threshold_dialog.py # Dot detection tuning
│   │       └── safety_dialog.py    # Confirmation dialogs
│   └── utils/
│       ├── config.py               # JSON-based settings
│       ├── constants.py            # App-wide constants (including control limits)
│       └── validators.py           # Input validation for control commands
├── tests/
│   ├── mock_arduino.py             # Simulated sensor data + command echo
│   └── mock_camera.py              # Simulated camera frames
├── arduino/
│   └── rhs_firmware/
│       └── rhs_firmware.ino        # Modified Arduino firmware (accepts commands)
├── docs/
│   ├── arduino_protocol.md         # Command protocol specification
│   └── safety_guide.md             # Emergency procedures
└── output/                         # Recorded sessions
```

## Key Design Patterns
1. **Threaded I/O:** Arduino and camera run in QThreads to prevent UI blocking
2. **Signal/Slot Architecture:** StateManager acts as central message bus
3. **Bidirectional Communication:** Command queue + acknowledgment system for reliable hardware control
4. **Mock Hardware:** Development continues without physical devices via mock generators
5. **Rolling Buffers:** 5-second deque buffers for real-time graph scrolling
6. **Three Control Modes:**
   - **POT:** Potentiometer controls BPM (app controls disabled, fallback mode)
   - **AUTO:** App sets BPM target, Arduino auto-pulses solenoid
   - **MANUAL:** Direct solenoid control from app, no auto-pulsing

## Development Timeline
**PRIMARY REFERENCE:** `RHS_Development_Timeline.md` (10-week plan with control system, Week 2-12)
**BACKUP REFERENCE:** `RHS_Development_Timeline_BACKUP.md` (original 8-week monitoring-only plan)

Current priorities depend on which week we're in - **always check the timeline document first** before suggesting implementation approaches.

### Timeline Overview:
- **Week 2 (Jan 12-15):** Setup
- **Week 3 (Jan 16-22):** Foundation
- **Week 4 (Jan 23-29):** Bidirectional Arduino communication
- **Week 4.5 (Jan 30 - Feb 2):** Arduino firmware modification (C++ work)
- **Week 5 (Feb 3-9):** UI layout + state management with control
- **Week 6 (Feb 10-16):** Hardware control panel implementation
- **Week 7 (Feb 17-23):** Sensor visualization
- **Week 8 (Feb 24 - Mar 2):** Basler camera integration
- **Week 9 (Mar 3-9):** Dot tracking & data logging
- **Week 10 (Mar 10-16):** MapAnything export
- **Week 11 (Mar 17-20):** Control system integration testing
- **Week 12 (Mar 21-22):** Polish and release

## Critical Requirements
- **Real-time performance:** UI must handle 30+ sensor updates/second + 60fps camera without lag
- **Bidirectional communication:** Commands must be sent reliably with acknowledgment
- **Safety-first:** Emergency stop must work instantly, hardware-level safety in Arduino
- **Cross-platform:** Must work on macOS and Windows (serial port naming differs)
- **Data integrity:** CSV logging must be thread-safe, include control commands
- **Robust error handling:** Graceful degradation when hardware disconnects mid-operation
- **Command validation:** Prevent invalid inputs (BPM range 60-180, mode constraints)

## Control System Details

### Arduino Command Protocol
Commands are newline-delimited ASCII text:
```
Desktop → Arduino:
- SET_FAN <0|1>
- SET_SOLENOID <0|1>
- SET_BPM <60-180>
- SET_MODE <POT|AUTO|MANUAL>
- EMERGENCY_STOP
- GET_STATUS

Arduino → Desktop:
- OK
- ERROR <message>
- STATUS FAN:<0|1> SOL:<0|1> BPM:<value> MODE:<mode>
```

### Hardware State
StateManager tracks current hardware state:
```python
{
    "fan": bool,
    "solenoid": bool,
    "bpm": int,
    "mode": str  # POT/AUTO/MANUAL
}
```

## When Helping, You Should:
1. **Reference the timeline:** Check which week we're in and what deliverables are expected
2. **Follow the architecture:** Don't suggest patterns that conflict with established design (e.g., avoid async/await since we're using QThreads)
3. **Consider hardware constraints:** Camera/Arduino may not be physically present yet - mock generators must maintain identical interfaces
4. **Think about safety:** Control commands need validation, emergency stop must be fail-safe
5. **Challenge bad decisions:** If you see a design flaw or better approach, speak up - don't just implement what's asked
6. **Distinguish monitoring vs. control:** This is a control system, not just a data viewer

## Current State
The project structure exists with docstrings and some stub implementations. You'll be helping implement each component according to the timeline. The student has CS fundamentals (Git, testing, design patterns from CS 100) but limited production Python experience and is learning Arduino development.

## Questions You Might Get Asked
- Implementation details for bidirectional Arduino communication
- Hardware control panel UI design and validation logic
- Debugging PyQt signals, serial communication, command acknowledgments
- Arduino firmware modification (command parsing, control mode logic)
- Safety system design (emergency stop, command validation)
- Architecture decisions (e.g., "Should commands use a queue or direct serial write?")
- MapAnything integration (export format, running inference)
- Cross-platform compatibility (macOS vs Windows serial port naming, path handling)

## What You Won't Know Without Asking
- Whether hardware (camera, Arduino) has arrived yet (affects whether to use mocks)
- Which week of development we're currently in
- What specific hardware components need control beyond fan/solenoid (team decision pending)
- Specific error messages or behavior when debugging
- User's preferences for code style/verbosity

## Safety-Critical Reminders
- **Emergency stop is non-negotiable:** Must work even if app crashes
- **Command validation:** Never send invalid commands to Arduino (e.g., BPM outside 60-180)
- **Mode constraints:** Solenoid manual control only works in MANUAL mode
- **Fallback behavior:** Arduino should revert to potentiometer if app disconnects
- **No uncontrolled state:** Always know what mode the system is in

## Common Gotchas
1. **Serial communication is asynchronous:** Use thread-safe queues for commands
2. **PyQt signals need thread context:** Can't emit from arbitrary threads
3. **Arduino baud rate is unusual:** 31250, not standard 9600 or 115200
4. **Control modes have different widget states:** POT disables controls, AUTO enables BPM only, MANUAL enables all
5. **Emergency stop must clear command queue:** Don't send pending commands after E-STOP
6. **Mock generators must echo commands:** For testing without hardware

## References
- **Timeline:** `RHS_Development_Timeline.md`
- **Architecture:** `RHS_Code_Structure.md`
- **Protocol Spec:** `docs/arduino_protocol.md`
- **PyQt6 Docs:** https://doc.qt.io/qtforpython-6/
- **pyqtgraph Docs:** https://pyqtgraph.readthedocs.io/
- **pypylon Samples:** https://github.com/basler/pypylon-samples
- **OpenCV Docs:** https://docs.opencv.org/
- **MapAnything Repo:** https://github.com/facebookresearch/map-anything
