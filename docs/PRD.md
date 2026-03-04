# RHS Monitor — Product Requirements Document

## 1. Product Overview

**Product:** RHS Monitor — a PySide6 desktop application for the Right Heart Simulator
**Users:** BIEN 175B senior design group (1 software lead (user), rest non-technical for coding, using macOS and Windows)
**Purpose:** Real-time sensor monitoring, data recording, and run quality logging for a cardiovascular simulator

## 2. Problem Statement

The previous workflow required terminal interaction at every step: running `python serial_reader.py`, typing valve material, running separate plot scripts from the command line, and manually managing CSV files. Group members unfamiliar with Python/conda struggled to set up and use the tool. The codebase was cluttered with unused stubs, making it hard to maintain.

## 3. Goals

| Goal | Success Criteria |
|------|-----------------|
| Zero terminal interaction during use | App launches from a script; all features accessible via GUI buttons |
| Real-time sensor monitoring | 4 live graphs (pressure, flow, HR, temperature) update at 30Hz |
| Dual camera feeds | 2 Basler camera feeds display simultaneously in the GUI |
| On-demand CSV recording | Users start/stop recording via button; graphs continue regardless |
| In-app data visualization | Users plot any recorded CSV without leaving the app |
| Run quality logging | Users rate runs (good/bad/neutral) with notes, stored in run_log.csv |
| Easy setup for group members | Single setup script installs everything; single launch script runs the app |
| Cross-platform | Works on macOS (bash) and Windows (batch) |

## 4. Non-Goals (Out of Scope)

- Dot tracking / fiducial marker detection (deferred to future phase)
- Bidirectional Arduino control (firmware stays read-only in this phase)
- Solenoid start/stop from GUI (protocol designed but not implemented; firmware modification required)
- Standalone executable packaging (PyInstaller/cx_Freeze)
- MapAnything integration
- CI/CD pipeline (GitHub Actions)

## 5. User Workflows

### Workflow 1: Daily Use
1. User double-clicks `run.sh` (macOS) or `run.bat` (Windows)
2. App opens with live graphs streaming immediately (auto-detects Arduino)
3. Two camera feeds appear below the graphs
4. User adjusts air compressor / hardware as needed while watching live data
5. When ready, user clicks **Record** — CSV recording begins (`rhs_YYYY-MM-DD_HH-MM-SS.csv`)
6. Status bar shows "Recording: rhs_2026-03-03_14-30-22.csv"
7. User clicks **Stop** — recording ends, graphs continue live
8. User clicks **Plot** — file picker opens (defaults to `outputs/`), user selects the CSV, 4 subplots appear
9. User clicks **Log** — dialog opens, user selects the CSV, rates it good/bad/neutral, adds notes
10. User closes the app

### Workflow 2: First-Time Setup
1. User installs Basler Pylon SDK from basler.com (documented prerequisite)
2. User runs `setup.sh` (macOS) or `setup.bat` (Windows) — creates `rhs-app` conda env
3. User runs `run.sh` / `run.bat` — app launches
4. After a `git pull`, if `environment.yml` changed, `run.sh` prints "Dependencies changed. Re-run setup." and exits

### Workflow 3: Post-Run Analysis (Without Hardware)
1. User launches app (graphs show "No Arduino Connected" placeholder)
2. User clicks **Plot** -> selects a previously recorded CSV -> views plots
3. User clicks **Log** -> rates the run

## 6. Serial Data Protocol

| Field | Name | Unit | Arduino Variable | Index |
|-------|------|------|-----------------|-------|
| P1 | Atrium Pressure | mmHg | PT1 (analog A0) | 0 |
| P2 | Ventricle Pressure | mmHg | PT2 (analog A1) | 1 |
| FLOW | Flow Rate | mL/s | FRPin (analog A2) | 2 |
| HR | Heart Rate | BPM | Hardcoded (130) | 3 |
| VT1 | Ventricle Temp 1 | C | DS18B20 sensor 3 | 4 |
| VT2 | Ventricle Temp 2 | C | DS18B20 sensor 2 | 5 |
| AT1 | Atrium Temp | C | DS18B20 sensor 1 | 6 |

Format: `"P1 P2 FLOW HR VT1 VT2 AT1\n"` — 7 space-separated values, 31250 baud

## 7. CSV Output Format

**Filename:** `rhs_YYYY-MM-DD_HH-MM-SS.csv` (auto-generated, no user prompt)
**Location:** `outputs/` directory
**Columns:**
```
Time (s),Pressure 1 (mmHg),Pressure 2 (mmHg),Flow Rate (mL/s),Heart Rate (BPM),Ventricle Temperature 1 (C),Ventricle Temperature 2 (C),Atrium Temperature (C)
```
**Time column:** Relative to record start (t=0 when user clicks Record)

## 8. Run Log Format

**File:** `outputs/run_log.csv`
**Columns:** `timestamp,csv_filename,rating,notes`
**Rating values:** `good`, `bad`, `neutral`
**Append-only:** new rows added, never overwritten

## 9. GUI Layout

```
+-------------------------------+
|        RHS Monitor            |
+---------------+---------------+
|   Pressure    |   Flow Rate   |
|  (P1 red,     |   (yellow)    |
|   P2 blue)    |               |
+---------------+---------------+
|  Heart Rate   |  Temperature  |
|   (white)     | (VT1/VT2/AT1)|
+---------------+---------------+
|   Camera 1    |   Camera 2    |
|               |               |
+---------------+---------------+
| [Record] [Stop] [Plot] [Log] |
|  Status: Not recording        |
+-------------------------------+
```

- Graphs: pyqtgraph PlotWidgets, 5-second rolling window, auto-scaling Y-axis
- Cameras: QLabel with QPixmap, FPS overlay, "No Camera" placeholder if disconnected
- Control bar: QPushButtons with status label
- Window opens maximized

## 10. Signal/Slot Architecture

```
SerialReader (QThread)
  ├─ data_received(dict) ──> GraphPanel.update_plots()
  ├─ data_received(dict) ──> DataRecorder.record_row()  [if recording]
  ├─ connection_changed(bool) ──> MainWindow.update_serial_status()
  └─ error_occurred(str) ──> MainWindow.show_error()

BaslerCamera #1 (QThread)
  └─ frame_ready(ndarray) ──> CameraPanel.update_left()

BaslerCamera #2 (QThread)
  └─ frame_ready(ndarray) ──> CameraPanel.update_right()

ControlBar (QPushButtons)
  ├─ record_clicked ──> DataRecorder.start_recording()
  ├─ stop_clicked ──> DataRecorder.stop_recording()
  ├─ plot_clicked ──> PlotDialog.exec()
  └─ log_clicked ──> LogDialog.exec()
```

## 11. Future: Solenoid Control Protocol (Design Only)

**Proposed serial commands** (requires firmware modification):
- App sends `S\n` -> Arduino starts solenoid cycling
- App sends `X\n` -> Arduino stops solenoid cycling
- Arduino default: solenoid OFF on power-up (safe state)

**GUI:** "Start RHS" / "Stop RHS" toggle button in control bar (grayed out until firmware supports it)

**Firmware changes needed:** Add `Serial.available()` check in `loop()`, parse single-char commands, gate solenoid cycling behind a `running` boolean. ~15 lines of code.

See `docs/solenoid_protocol.md` for full specification.

## 12. Current Build State

Update this table when features ship. This is the single source of truth for what is
and isn't built — do not track build state in CLAUDE.md.

| Goal (from §3)              | Status      | Notes                                       |
|-----------------------------|-------------|---------------------------------------------|
| Zero terminal interaction   | Done        | `bash run.sh` / `run.bat`                   |
| Real-time sensor monitoring | Done        | 4 pyqtgraph panels, 30Hz rolling window     |
| Dual camera feeds           | Done        | BaslerCamera QThread, auto-detect           |
| On-demand CSV recording     | Done        | Record/Stop, auto-named, t=0 reset          |
| In-app data visualization   | Done        | PlotDialog, matplotlib, 4 subplots          |
| Run quality logging         | Done        | good/bad/neutral + notes, run_log.csv       |
| Easy setup                  | Done        | setup.sh / setup.bat, environment.yml       |
| Cross-platform              | Partial     | macOS tested; Windows untested              |
| Solenoid control            | Not started | Protocol designed; firmware change needed   |
