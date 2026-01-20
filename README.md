# RHS Desktop Application

**Right Heart Simulator - Control & Monitoring System**

A desktop application for real-time monitoring and control of the Right Heart Simulator (RHS) medical training device. Built as a senior design project at UC Riverside (January-March 2025).

## Features

### Monitoring
- Real-time sensor data visualization (pressure, flow rate, heart rate)
- High-speed camera feed (60 fps) with dot tracking
- CSV data logging with timestamps
- 3D reconstruction export for MapAnything

### Control 
- **Hardware Control:** Fan, solenoid valve, BPM setpoint
- **Three Control Modes:**
  - POT: Potentiometer control (fallback)
  - AUTO: App-controlled BPM with auto-pulsing
  - MANUAL: Direct solenoid control
- **Safety Features:** Emergency stop, command validation, mode constraints
- **Bidirectional Communication:** Reliable command/acknowledgment protocol

## Tech Stack

- **Frontend:** PyQt6 + pyqtgraph
- **Camera:** Basler pypylon SDK
- **Vision:** OpenCV
- **Hardware:** Arduino (31250 baud serial)
- **3D:** Meta MapAnything

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install Basler Pylon SDK (camera)
# Download from: https://www.baslerweb.com/

# Run application
python run.py
```

## Documentation

- **[Development Timeline](RHS_Development_Timeline.md)** - 10-week implementation plan
- **[Code Structure](RHS_Code_Structure.md)** - Architecture and component details
- **[Project Instructions](PROJECT_INSTRUCTIONS.md)** - For AI assistance context
- **[Arduino Protocol](docs/arduino_protocol.md)** - Command specification
- **[Timeline Change Notice](TIMELINE_CHANGE_NOTICE.md)** - Why we expanded scope

## Project Status

**Current Phase:** Week [X] of 10  
**Hardware Status:** Camera [pending/arrived] | Arduino [connected/pending]

See [RHS_Development_Timeline.md](RHS_Development_Timeline.md) for detailed progress.

## Safety

⚠️ **EMERGENCY STOP:** Large red button in toolbar kills all outputs immediately.

See [docs/safety_guide.md](docs/safety_guide.md) for complete safety procedures.

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

## Team

UC Riverside Bioengineering Senior Design Team  
January - March 2025

## License

[To be determined]
