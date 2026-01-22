# RHS Desktop Application

**Right Heart Simulator - Control & Monitoring System**

A desktop application for real-time monitoring and control of the Right Heart Simulator (RHS) medical training device. Built as a senior design project at UC Riverside (January-March 2025).

## Features

### Monitoring
- Real-time sensor data visualization (pressure, flow rate, heart rate)
- High-speed camera feed (60 fps) with fiducial marker tracking
- CSV data logging with timestamps
- 3D displacement/strain analysis via MapAnything

### Control 
- **Hardware Control:** Fan, solenoid valve, BPM setpoint
- **Three Control Modes:**
  - POT: Potentiometer control (fallback)
  - AUTO: App-controlled BPM with auto-pulsing
  - MANUAL: Direct solenoid control
- **Safety Features:** Emergency stop, command validation, pressure monitoring

## Tech Stack

- **GUI:** PyQt6 + pyqtgraph
- **Camera:** Basler pypylon SDK
- **Vision:** OpenCV
- **Hardware:** Arduino (31250 baud serial)
- **3D Reconstruction:** Meta MapAnything

## Quick Start
```bash
# Clone repository
git clone https://github.com/yourusername/rhs-desktop-app.git
cd rhs-desktop-app

# Install dependencies
pip install -r requirements.txt

# Run application
python run.py
```

> **Note:** Basler camera features require the [Pylon SDK](https://www.baslerweb.com/en/downloads/software-downloads/). We used Pylon 25.11

## Development Setup

1. Create conda environment:
```bash
   conda create -n rhs-desktop python=3.11
   conda activate rhs-desktop
```

2. Install development dependencies:
```bash
   pip install -r requirements-dev.txt
```

3. Run tests:
```bash
   pytest
```

## Architecture
```
┌─────────────────────────────────────────────────────────────────────┐
│ [Port ▼] [Connect] [Camera ▼] [Connect Cam] [🔴 E-STOP] [Record]   │
├──────────────────┬──────────────────┬───────────────────────────────┤
│  SENSOR PANEL    │  CONTROL PANEL   │      CAMERA PANEL             │
│  (25%)           │  (25%)           │      (50%)                    │
│                  │                  │                               │
│  • P1/P2 graphs  │  • Mode selector │  • Live camera feed           │
│  • Flow graph    │  • Fan control   │  • Dot overlay                │
│  • HR display    │  • BPM slider    │  • Tracking data              │
└──────────────────┴──────────────────┴───────────────────────────────┘
```

## Safety

⚠️ **EMERGENCY STOP:** Red button in toolbar immediately stops all hardware outputs.

The system includes:
- Automatic pressure monitoring with low-pressure warnings
- Command validation to prevent invalid inputs
- Fallback to potentiometer control if app disconnects

## Project Status

🚧 **Under Development** - Senior Design Project (Winter/Spring 2025)

## Team

UC Riverside Bioengineering Senior Design Team

## License

[TBD]
```