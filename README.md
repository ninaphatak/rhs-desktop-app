# RHS Desktop Application

**Right Heart Simulator - Sensor Monitoring System**

A desktop application for real-time sensor monitoring and visualization of the Right Heart Simulator (RHS) medical training device. Built as a senior design project at UC Riverside (January-March 2025).

**This is a read-only sensor monitoring app.** Hardware control (solenoid, BPM) is via manual potentiometer on the device.

## Features

- Real-time sensor data visualization (pressure, flow rate, heart rate)
- High-speed camera feed (60 fps) with dot tracking
- CSV data logging with timestamps
- Live plotting with 5-second rolling window

## Tech Stack

- **Frontend:** PyQt6 + pyqtgraph
- **Camera:** Basler pypylon SDK (ace 2 a2A1920-160umBAS)
- **Vision:** OpenCV
- **Hardware:** Arduino (31250 baud serial, read-only)

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

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ [Port ▼] [Connect] [Camera ▼] [Connect Cam] [Record]         │
├──────────────────────────┬────────────────────────────────────┤
│    SENSOR PANEL          │      CAMERA PANEL                  │
│    (Left, 40%)           │      (Right, 60%)                  │
│                          │                                    │
│  • P1 pressure graph     │  • Live camera feed (60fps)        │
│  • P2 pressure graph     │  • Dot tracking overlay            │
│  • Flow rate graph       │  • Distance measurements           │
│  • Heart rate display    │                                    │
└──────────────────────────┴────────────────────────────────────┘
```

## Team

UC Riverside Bioengineering Senior Design Team  
January - March 2025

## License

[To be determined]
