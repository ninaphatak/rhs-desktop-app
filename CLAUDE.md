# RHS Monitor

A PySide6 desktop app for the Right Heart Simulator (RHS) — a cardiovascular medical training device simulating post-Fontan hemodynamics. RHS = Right Heart Simulator.

## What This App Does
Unified GUI for: Arduino sensor monitoring (P1, P2, Flow, HR, VT1, VT2, AT1), on-demand CSV recording, in-app data visualization, run quality logging, and dual Basler camera feeds. **This is a read-only sensor monitoring app.** The solenoid is controlled by a manual potentiometer on the hardware (serial command protocol designed but not yet implemented — see `docs/solenoid_protocol.md`).

## Tech Stack
Python 3.11+ | PySide6 + pyqtgraph | pypylon (Basler camera) | pyserial (31250 baud, read-only) | pandas/numpy | matplotlib (in-app dialogs) | pytest

## How to Run
```bash
bash setup.sh          # Create/update rhs-app conda env (first time + after env changes)
bash run.sh            # Launch the app
bash run.sh --mock     # Launch with mock data (no hardware needed)
pytest tests/ -v       # Run tests
```

## Project Structure
- `src/main.py` — App entry point (QApplication + MainWindow)
- `src/core/` — Business logic: serial_reader, basler_camera, data_recorder, run_logger
- `src/ui/` — PySide6 widgets: main_window, graph_panel, camera_panel, control_bar, plot_dialog, log_dialog
- `src/utils/` — Config constants, port detection
- `tests/` — pytest tests + mock hardware (mock_arduino.py, mock_camera.py)
- `docs/` — Protocol specs (solenoid_protocol.md)
- `outputs/` — Recorded CSVs + run_log.csv (gitignored)
- `arduino/` — Arduino firmware (rhs_firmware.ino)
- `legacy/` — Archived old code (serial_reader.py, plots, old src/)

## Architecture Rules
- **QThread for all I/O** — serial and camera each get their own QThread. Never block the UI thread.
- **Signal/Slot only** — Components communicate via PySide6 signals, not direct method calls between unrelated objects.
- **No async/await** — we use QThreads, not asyncio.
- **Rolling deque buffers** for real-time graphs (5-second window at 30Hz = maxlen 150).
- **PySide6, not PyQt6** — all imports use `from PySide6.QtCore import QThread, Signal` etc.

## Serial Data Protocol
7 space-separated values at 31250 baud: `P1 P2 FLOW HR VT1 VT2 AT1\n`

| Field | Name | Unit |
|-------|------|------|
| P1 | Atrium Pressure | mmHg |
| P2 | Ventricle Pressure | mmHg |
| FLOW | Flow Rate | mL/s |
| HR | Heart Rate | BPM |
| VT1 | Ventricle Temp 1 | C |
| VT2 | Ventricle Temp 2 | C |
| AT1 | Atrium Temp | C |

## Key Hardware Facts
- Arduino outputs 7 fields, 31250 baud, read-only
- Camera: Basler ace 2 a2A1920-160umBAS, 1920x1200 @ 60fps, monochrome, pypylon
- Second camera for dual feed (both display simultaneously in GUI)

## Current Status
- Serial reader + live graphs (4 panels: pressure, flow, HR, temp)
- On-demand CSV recording (Record/Stop buttons, auto-named files)
- In-app matplotlib plotting dialog
- Run quality logging (good/bad/neutral + notes)
- Dual Basler camera panel
- Mock mode (--mock flag for testing without hardware)
- 17 pytest tests passing
- Solenoid control: protocol designed, UI button present but disabled

## Testing Requirements
Every new module or feature must have corresponding pytest tests. Run `pytest tests/ -v` before committing.

## Code Style
- Type hints on all function signatures
- Docstrings on all classes and public methods
- f-strings for formatting
- `pathlib.Path` over `os.path`
- snake_case for functions/variables, PascalCase for classes

## Git Workflow
Always create a feature branch off the current branch before implementing new features.
Branch naming: feature/<feature-name>. Commit frequently with descriptive messages.
Do not push — I will review and push manually.

## Cross-Platform Notes
- Serial ports: macOS = `/dev/cu.*`, Windows = `COM*`, Linux = `/dev/ttyUSB*`
- File paths: always use `pathlib.Path`, never hardcode separators
- Setup: `setup.sh` (macOS/Linux) / `setup.bat` (Windows)

## What NOT to Build
- Dot tracking / fiducial marker detection (deferred to future phase)
- Bidirectional Arduino control (firmware modification required first)
- Standalone executable packaging (PyInstaller/cx_Freeze)
- MapAnything integration
- CI/CD pipeline (GitHub Actions)

## Available Skills
When using any of the following skills, check `.claude/skills/` for the full instructions.
- **arduino-serial-protocol** — 7-field serial format, parsing, CSV output
- **pyqt-threading** — PySide6 QThread patterns for real-time I/O
- **weekly-progress-summary** — Weekly progress slides for BIEN 175B
- **update-memory** — Update memory from conversation transcripts
