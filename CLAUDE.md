# RHS Desktop Application

A PyQt6 desktop app for the Right Heart Simulator (RHS) — a cardiovascular medical training device simulating post-Fontan hemodynamics. RHS = Right Heart Simulator.

## What This App Does
Unified GUI for: Arduino sensor monitoring (HR, FR, P1, P2), data recording to CSV, data visualization, and camera-based dot tracking on a silicone heart valve. Fiducial markers (black dots) on the silicone tricuspid valve are tracked to measure 3D leaflet displacement during simulated cardiac cycles, providing the data needed to characterize valve mechanical behavior and eventually calculate strain.


**This is a read-only sensor monitoring app.** No bidirectional Arduino control. The solenoid is controlled by a manual potentiometer on the hardware.

## Tech Stack
Python 3.11+ | PyQt6 + pyqtgraph | pypylon (Basler camera) | OpenCV | pyserial (31250 baud, read-only) | pandas/numpy | pytest + GitHub Actions

## How to Run
```bash
conda activate rhs-desktop          # or your env name
python run.py               # launch the app
python serial_reader.py     # standalone serial reader (legacy)
python tests/test_manual_dot_selection.py  # manual dot selection demo (MockCamera)
python tests/test_manual_dot_selection.py --real-camera  # with Basler camera
pytest                      # run tests
pytest tests/test_specific.py -v  # run specific test
```

## Project Structure
- `src/core/` — Business logic: serial reader, camera, dot tracker, data logger, state manager
- `src/ui/` — PyQt6 widgets: main window, sensor panel, camera panel, dialogs
- `src/utils/` — Config, constants
- `tests/` — pytest tests + mock hardware (mock_arduino.py, mock_camera.py)
- `plots/` — Data visualization scripts (view_csv.py, compare_trials.py, visualize_pressure_diff.py)
- `prototypes/` — Early experimental code (serial_reader.py versions)
- `arduino/` — Arduino firmware (rhs_firmware.ino)
- `docs/` — Documentation (protocol specs, guides, installation)
- `outputs/` — Generated plots and recorded data

## Architecture Rules
- **QThread for all I/O** — serial and camera each get their own QThread. Never block the UI thread.
- **Signal/Slot only** — StateManager is the central hub. Components communicate via Qt signals, not direct method calls between unrelated objects.
- **No async/await** — we use QThreads, not asyncio.
- **Rolling deque buffers** for real-time graphs (5-second window at 30Hz = maxlen 150).

## Key Hardware Facts
- Arduino outputs: `"P1 P2 FLOW HR\n"` space-separated, 31250 baud
- Camera: Basler ace 2 a2A1920-160umBAS, 1920x1200 @ 60fps, monochrome, pypylon
- Lens: 16mm Edmund Optics, ~140mm working distance
- Dots: Black waterproof marker on white silicone valve (imperfect circles, operates underwater)
- Second camera ordered for 30° offset (dual camera DIC — stretch goal, keep modular)

## Current Status
- ✅ serial_reader.py — works on macOS + Windows, live plots, CSV export
- ✅ BaslerCamera class — captures frames via pypylon
- ✅ DotTracker class — dual-mode: automatic (global threshold) + manual (user-selected seeds)
- ✅ Manual dot selection — fully functional, 34 tests passing, standalone demo app ready
- ✅ Visualization scripts — time-series, trial comparison, divergence charts
- ✅ SyntheticValveGenerator — test data generation
- 🔨 pytest + CI/CD — needs updating for new modules
- 🔨 Unified PyQt6 app — needs building (integrate all existing components)
- 🔨 Record button with t=0 reset
- 🔨 In-app visualization tools
- 📋 Dual camera DIC — stretch goal

## Manual Dot Selection Feature

The app now supports manual dot selection for underwater valve tracking (automatic thresholding fails due to water reflections and uneven lighting).

**How it works:**
1. User clicks on dots in camera feed (SELECT mode)
2. OpenCV refines click to precise dot boundary using local Otsu thresholding
3. Frame-to-frame tracking maintains dot IDs across frames
4. Displacement vectors show movement from reference position (t=0)
5. Lost dots (occluded/out-of-frame) are marked and removed after 10 frames

**Three modes:**
- **VIEW_ONLY:** Display camera feed only, no interaction
- **SELECT_DOTS:** Click to add dots, drag to adjust, remove/clear
- **TRACKING:** Dots locked, real-time tracking active, displacement shown

**Files:**
- `src/core/dot_tracker.py` — DotTracker class with manual mode support
- `src/utils/dot_refinement.py` — OpenCV refinement: `refine_dot_at_click()`
- `src/ui/camera_panel.py` — CameraPanel widget (QGraphicsView)
- `src/ui/graphics_items.py` — DotGraphicsItem, FrameGraphicsItem
- `tests/test_manual_dot_selection.py` — Standalone demo app

**Try it:**
```bash
python tests/test_manual_dot_selection.py
```
Then:
1. Select "Select Dots" mode
2. Click on moving dots (MockCamera generates synthetic valve with dots)
3. Switch to "Tracking" mode
4. Click "Set Reference (t=0)"
5. Watch displacement vectors update in real-time

**Integration:** Feature is fully functional as a standalone widget. When MainWindow is implemented, wire the same signals shown in `tests/test_manual_dot_selection.py`.

## Testing Requirements
IMPORTANT: Every new module or feature must have corresponding pytest tests. Run `pytest` before committing. CI runs on push via GitHub Actions.

## Code Style
- Type hints on all function signatures
- Docstrings on all classes and public methods
- f-strings for formatting
- `pathlib.Path` over `os.path`
- snake_case for functions/variables, PascalCase for classes

## Git Workflow
Always create a feature branch off the current branch before implementing new features.
Branch naming: feature/<feature-name>, e.g. feature/manual-dot-selection.
Commit frequently with descriptive messages. Do not push — I will review and push manually.

## Cross-Platform Notes
- Serial ports: macOS = `/dev/tty.*` or `/dev/cu.*`, Windows = `COM*`
- File paths: always use `pathlib.Path`, never hardcode separators
- Test on both macOS and Windows before merging

## What NOT to Build
- ❌ Bidirectional Arduino control / command protocol
- ❌ Hardware control panel (fan, solenoid, BPM modes)
- ❌ Emergency stop from app (physical button on hardware)
- ❌ Arduino firmware modifications
- ❌ MapAnything integration (deferred)