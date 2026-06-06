# RHS Monitor

**Right Heart Simulator — Desktop Monitoring App + Offline Leaflet-Tracking CV Pipeline**

The **Right Heart Simulator (RHS)** is a benchtop cardiovascular training device that
simulates post-Fontan hemodynamics: a white silicone tricuspid valve opens and closes
underwater while a solenoid pumps fluid through it. This repository contains two things:

1. **A real-time desktop monitoring app** (`src/`) — a read-only PySide6 GUI that plots
   the Arduino sensor stream, previews two Basler cameras, and records sensor CSVs +
   camera video on demand.
2. **An offline computer-vision pipeline** (`tools/`) — standalone scripts that measure,
   in **millimeters**, how far the valve leaflets move during each cardiac cycle, by
   auto-tracking points across two calibrated cameras and triangulating them in 3D.

> The desktop app only **reads** hardware (sensors + cameras). It never sends commands to
> the Arduino. All CV work is **offline** and run from the command line, not the GUI.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Running the Desktop App](#running-the-desktop-app)
- [The CV Pipeline (offline)](#the-cv-pipeline-offline)
  - [Primary workflow: multi-point auto-tracking](#primary-workflow-multi-point-auto-tracking)
  - [Backup workflow: single manual landmark](#backup-workflow-single-manual-landmark)
  - [Plotting & inspection](#plotting--inspection)
- [Codebase Structure](#codebase-structure)
- [Which files you actually interact with](#which-files-you-actually-interact-with)
- [Serial Data Format](#serial-data-format)
- [Arduino Firmware](#arduino-firmware)
- [Testing](#testing)
- [Team](#team)

---

## Quick Start

```bash
bash setup.sh         # one-time: create the rhs-app conda environment
bash run.sh           # launch the GUI (needs Arduino + cameras)
bash run.sh --mock    # launch the GUI on recorded mock data (NO hardware needed)
pytest tests/ -v      # run the test suite
```

On Windows use `setup.bat` / `run.bat`.

> **Need conda first?** Install [Miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install) (lightweight, recommended) or full [Anaconda](https://www.anaconda.com/download) — `setup.sh` / `run.sh` use it to build and activate the `rhs-app` environment.

---

## Prerequisites

1. **Conda** — [Miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install) or [Anaconda](https://www.anaconda.com/download).
2. **Basler Pylon SDK** — from [baslerweb.com](https://www.baslerweb.com/). Required only
   for live camera feeds; the GUI runs without it in `--mock` mode, and the offline CV
   tools run on already-recorded video.
3. **ffmpeg** — pulled in automatically via the `imageio-ffmpeg` dependency; used for
   lossless camera recording.

`setup.sh` builds a conda env named **`rhs-app`** from `environment.yml`. `run.sh`
activates it for you, so you do not need to `conda activate` manually. If `environment.yml`
changes, re-run `setup.sh` (it re-validates a hash and will tell you when this is needed).

---

## Running the Desktop App

```bash
bash run.sh                 # normal: reads the serial port + both cameras
bash run.sh --mock          # replays tests/mock_data.csv; no Arduino/cameras required
```

In the GUI:

- **Live graphs** — P1, P2, Flow, HR, and three temperatures stream at ~30 Hz.
- **Camera panel** — both Basler feeds side by side (left = 0°, right = ~19.3° view).
- **Record** — starts a sensor CSV in `outputs/`; if both cameras are connected it offers
  to also record synchronized **MJPG/AVI** video (visually lossless at `-q:v 2`) to
  `outputs/videos/` (named
  `camera0_<timestamp>.avi` / `camera1_<timestamp>.avi`, paired with the CSV timestamp).
- **Lap** — drops a lap marker into the CSV.
- **Plot** — opens any recorded CSV in an in-app matplotlib dialog.
- **Review** — opens recorded camera videos for playback.
- **Log** — rate a run good/bad/neutral with notes (appended to `outputs/run_log.csv`).

Headless single-camera capture (no GUI) is also available straight from `main.py` flags;
see `src/main.py` for `--record-camera`, `--record-duration`, `--record-fps`.

---

## The CV Pipeline (offline)

Goal: **per-frame metric (mm) leaflet displacement.** Two cameras view the valve from
different angles; labeling the same point in both views lets us **triangulate** its true
3D position. Because the cameras look through acrylic into water/glycerin (refraction), we
calibrate **underwater, in the final rig**, against a 3D-printed object with dots at known
positions — the fitted calibration absorbs the refraction. **Calibration is per fluid**
(water vs. 35% glycerin analog).

> **The headline deliverable is the automatic multi-point tracker.** Manual point-clicking
> is only a **backup** used to patch frames where auto-tracking fails. Lead with the
> tracking workflow below.

All commands assume the `rhs-app` env is active (run them via `conda run -n rhs-app python ...`
or after `conda activate rhs-app`).

### Primary workflow: multi-point auto-tracking

Auto-tracks inked valve intersection corners across the whole clip using a **hybrid
Lucas-Kanade + frame-0 NCC anchor** tracker. (Plain LK alone drifts on the textureless,
deforming leaflets, so LK is only a search *prior* — the actual position each frame is the
NCC peak matched against a never-updating frame-0 patch.)

```bash
# 0. Record the valve (both cameras) and the calibration object (once per fluid)
python tools/record_valve.py --dual
python tools/record_calibration.py water          # or: analog

# 1. Calibrate the stereo rig for this fluid  ->  outputs/calib/stereo_calib_water.json
python tools/stereo_calibrate.py \
    outputs/videos/calib_water_<ts>_cam0.avi \
    outputs/videos/calib_water_<ts>_cam1.avi \
    --markers markers.csv

# 2. Pick the points to track (click each corner once, in both views, on a reference frame)
python tools/pick_track_seeds.py CAM0.avi CAM1.avi        # -> CAM0.track_seeds.json

# 3. Auto-track every point across the clip and triangulate to 3D mm
python tools/track_intersections.py \
    --seeds CAM0.track_seeds.json \
    --calib outputs/calib/stereo_calib_water.json         # -> CAM0.tracks.csv

# 4. Inspect the result (side-by-side video with the tracks overlaid)
python tools/playback_tracks.py CAM0.avi CAM1.avi --tracks CAM0.tracks.csv

# 5. Compute per-point + aggregate metrics (peak displacement, 3D path length, period)
python tools/analyze_tracks.py CAM0.tracks.csv --fps 30
```

### Backup workflow: single manual landmark

Use this only for a single hand-labeled point, or to **repair** frames the tracker lost.
Manual labels can be spliced back into the auto-tracked master:

```bash
# Label the same landmark in both views, frame by frame (carry-forward speeds this up)
python tools/annotate_stereo_point.py CAM0.avi CAM1.avi --output point6.stereo_annotations.csv

# Splice the manual point into the master tracks CSV (interpolates between labeled frames)
python tools/splice_manual_into_tracks.py CAM0.tracks.csv \
    --calib outputs/calib/stereo_calib_water.json \
    --point 6 point6.stereo_annotations.csv

# Standalone single-point path (no tracking): annotate -> triangulate -> metrics
python tools/triangulate.py point6.stereo_annotations.csv outputs/calib/stereo_calib_water.json
python tools/analyze_metric.py point6.triangulated.csv --fps 30
```

### Plotting & inspection

```bash
python tools/analyze_pressure_vs_tracks.py PRESSURE.csv CAM0.tracks.csv   # pressure/flow vs displacement
python tools/plot_calibration_error.py                                    # per-marker triangulation error
python tools/plot_calibration_geometry_3d.py                              # 3D view of markers + cameras
python tools/flow_explore.py CAM0.avi CAM1.avi                            # dense optical-flow visualizer
```

---

## Codebase Structure

```
src/                         # The desktop monitoring app (PySide6)
  main.py                    #   entry point: QApplication + MainWindow, CLI flags
  core/                      #   I/O + business logic (each I/O type on its own QThread)
    serial_reader.py         #     reads + parses the 7-field Arduino stream (read-only)
    basler_camera.py         #     Basler grab thread + MJPG/AVI recording (ffmpeg subprocess)
    data_recorder.py         #     sensor CSV recording (start/stop/lap)
    run_logger.py            #     run-quality log (outputs/run_log.csv)
  ui/                        #   widgets, all communicating via Qt signals/slots
    main_window.py           #     top-level window; wires panels + recording
    graph_panel.py           #     real-time pyqtgraph plots (rolling deques)
    camera_panel.py          #     dual camera preview + recording controls
    control_bar.py           #     Record/Stop/Lap/Plot/Review/Log buttons + status
    plot_dialog.py           #     in-app matplotlib CSV viewer
    review_dialog.py         #     recorded-video review
    log_dialog.py            #     run-quality logging dialog
  utils/                     #   config.py (constants, paths), port detection

tools/                       # Offline CV pipeline (standalone CLI scripts — NOT in the app)
  record_valve.py            #   capture valve video (single or --dual)
  record_calibration.py      #   capture the submerged calibration object
  stereo_calibrate.py        #   fit per-camera stereo calibration -> outputs/calib/*.json
  pick_track_seeds.py        #   click the points to track (writes *.track_seeds.json)
  track_intersections.py     #   hybrid LK + frame-0 NCC anchor tracker -> *.tracks.csv
  playback_tracks.py         #   dual-camera playback with tracks overlaid
  analyze_tracks.py          #   per-point + aggregate metrics from *.tracks.csv
  splice_manual_into_tracks.py #  patch failed frames with manual labels
  annotate_stereo_point.py   #   manual single-landmark labeler (backup)
  triangulate.py             #   stereo annotations + calib -> 3D mm (single point)
  analyze_metric.py          #   cycle metrics for a single triangulated point
  analyze_pressure_vs_tracks.py # pressure/flow vs displacement plots
  plot_calibration_error.py  #   calibration accuracy bar charts
  plot_calibration_geometry_3d.py # 3D calibration geometry render
  flow_explore.py            #   dense optical-flow visualizer
  _tracks.py / _annotations.py / _flow_params.py  # shared headless helpers

tests/                       # pytest suite + mock hardware (mock_arduino.py, mock_camera.py)
arduino/                     # Arduino firmware — reference copy only (see below)
markers.csv                  # CAD-derived calibration-object geometry (consumed by stereo_calibrate.py)
outputs/                     # Recordings, videos, calibration JSONs, run log (gitignored)
```

## Which files you actually interact with

- **Run the app:** `run.sh` / `run.bat` (don't call `src/main.py` directly).
- **Run the CV pipeline:** the scripts in `tools/` (see commands above).
- **Tune behavior:** `src/utils/config.py` (paths, buffer sizes, camera FPS).
- **Calibration geometry:** `markers.csv` if the calibration object changes.
- **Firmware:** `arduino/rhs_firmware.ino` (reference only — see next section).
- **Everything in `outputs/`** is generated and gitignored — your recordings live here.

---

## Serial Data Format

7 space-separated values at **31250 baud**: `P1 P2 FLOW HR VT1 VT2 AT1\n`

| Field | Sensor | Unit |
|-------|--------|------|
| P1 | Atrium Pressure | mmHg |
| P2 | Ventricle Pressure | mmHg |
| FLOW | Flow Rate | mL/s |
| HR | Heart Rate | BPM |
| VT1 | Ventricle Temp 1 | °C |
| VT2 | Ventricle Temp 2 | °C |
| AT1 | Atrium Temp | °C |

The app is **read-only** — it parses this stream and never writes back to the Arduino.

---

## Arduino Firmware

The firmware lives at **`arduino/rhs_firmware.ino`** and is kept here as a **reference /
file-history copy only**:

- **The desktop app does NOT run, flash, or upload this file.** The app only reads the
  serial stream the board emits.
- If the firmware changes, **upload it manually via the Arduino IDE.** Otherwise the board
  already has the current version flashed — no action needed.
- The firmware drives the solenoid and sensors **autonomously**; there is intentionally no
  app→Arduino control path (bidirectional control is out of scope).

---

## Testing

```bash
pytest tests/ -v
```

Tests use mock hardware (`tests/mock_arduino.py`, `tests/mock_camera.py`) and a recorded
`tests/mock_data.csv`, so the full suite — including the CV tracking tests — runs with no
Arduino or cameras attached.

---

## Team

UC Riverside Bioengineering Senior Design; sponsored by Dr. Lee @ [Biomechanics & Biomaterials Design Laboratory (BBDL)](https://bbdl.engr.ucr.edu/) — BIEN 175 (2025 - 2026)
