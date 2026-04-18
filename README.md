# RHS Monitor

**Right Heart Simulator — Desktop Monitoring Application**

A PySide6 desktop app for real-time sensor monitoring, data recording, and run quality logging for the Right Heart Simulator (RHS) cardiovascular training device.

## Prerequisites

1. **Conda** — Install [Miniconda](https://docs.anaconda.com/miniconda/) or Anaconda
2. **Basler Pylon SDK** — Download from [baslerweb.com](https://www.baslerweb.com/) (required for camera feeds)

## Setup

```bash
# macOS / Linux
bash setup.sh

# Windows
setup.bat
```

This creates a `rhs-app` conda environment with all dependencies.

## Run

```bash
# macOS / Linux
bash run.sh

# Windows
run.bat

# With mock data (no hardware needed)
bash run.sh --mock
```

## Features

- **Live sensor graphs** — Pressure (P1, P2), Flow Rate, Heart Rate, Temperature (VT1, VT2, AT1) at 30Hz
- **Dual camera feeds** — Two Basler camera streams displayed simultaneously
- **On-demand CSV recording** — Start/stop recording via GUI button; auto-named files in `outputs/`
- **In-app plotting** — Select any recorded CSV and view 4 matplotlib subplots without leaving the app
- **Run quality logging** — Rate runs as good/bad/neutral with notes, stored in `outputs/run_log.csv`

## Serial Data Format

7 space-separated values at 31250 baud:
```
P1 P2 FLOW HR VT1 VT2 AT1
```

| Field | Sensor | Unit |
|-------|--------|------|
| P1 | Atrium Pressure | mmHg |
| P2 | Ventricle Pressure | mmHg |
| FLOW | Flow Rate | mL/s |
| HR | Heart Rate | BPM |
| VT1 | Ventricle Temp 1 | C |
| VT2 | Ventricle Temp 2 | C |
| AT1 | Atrium Temp | C |

## Project Structure

```
src/
  main.py              # App entry point
  core/                # Business logic (serial reader, camera, data recorder, run logger)
  ui/                  # GUI widgets (main window, graphs, cameras, dialogs)
  utils/               # Config constants, port detection
tests/                 # pytest tests + mock hardware
outputs/               # Recorded CSVs + run log (gitignored)
arduino/               # Arduino firmware
docs/                  # Protocol specs
legacy/                # Archived old code (serial_reader.py, plots, old src/)
```

## Team

UC Riverside Bioengineering Senior Design; sponsored by Dr. Lee @ [Biomechanics & Biomaterials Design Laboratory (BBDL)](https://bbdl.engr.ucr.edu/) — BIEN 175 (2025 - 2026)
