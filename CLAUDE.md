# RHS Monitor

A PySide6 desktop app for the Right Heart Simulator (RHS) — a cardiovascular medical training device simulating post-Fontan hemodynamics. RHS = Right Heart Simulator.

## What This App Does
Unified GUI for: Arduino sensor monitoring (P1, P2, Flow, HR, VT1, VT2, AT1), on-demand CSV recording, in-app data visualization, run quality logging, and dual Basler camera feeds. Computer vision work is offline — standalone tools in `tools/` compute **metric (mm) leaflet displacement** via stereo calibration + triangulation. **This is a read-only sensor monitoring app.**

> See `docs/PRD.md` for product requirements and `docs/plans/2026-05-08-stereo-calibration-design.md` for the active CV workstream.

## Tech Stack
Python 3.11+ | PySide6 + pyqtgraph | pypylon (Basler camera) | OpenCV (optical flow + stereo calibration + triangulation) | imageio-ffmpeg (FFV1/AVI recording) | pyserial (31250 baud, read-only) | pandas/numpy | matplotlib (in-app dialogs + offline plots) | pytest

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
- `tests/` — pytest tests + mock hardware + `cv_frames/` (static valve frames for CV dev)
- `tools/` — Standalone CV scripts (not part of the main app): record_calibration, flow_explore, annotate_point, playback_annotations, analyze_annotations + planned stereo tools
- `docs/` — PRD.md, plans/, solenoid_protocol.md, lens_spec_sheet.pdf
- `outputs/` — Recorded CSVs + run_log.csv (gitignored). Subdirs: `videos/` (FFV1/AVI camera recordings + calibration captures), `calib/` (per-fluid stereo calibration JSONs)
- `arduino/` — Arduino firmware (rhs_firmware.ino)
- `legacy/` — Archived old code

## Architecture Rules
- **QThread for all I/O** — serial and camera each get their own QThread. Never block the UI thread.
- **Signal/Slot only** — Components communicate via PySide6 signals, not direct method calls between unrelated objects.
- **No async/await** — we use QThreads, not asyncio.
- **Rolling deque buffers** for real-time graphs (5-second window at 30Hz = maxlen 150).
- **PySide6, not PyQt6** — all imports use `from PySide6.QtCore import QThread, Signal` etc.

## Serial Data Protocol
7 space-separated values at 31250 baud: `P1 P2 FLOW HR VT1 VT2 AT1\n`

| Field | Unit |
|-------|------|
| P1 (Atrium Pressure) | mmHg |
| P2 (Ventricle Pressure) | mmHg |
| FLOW (Flow Rate) | mL/s |
| HR (Heart Rate) | BPM |
| VT1, VT2 (Ventricle Temp) | °C |
| AT1 (Atrium Temp) | °C |

## Hardware Facts
- Arduino: 7 fields, 31250 baud, read-only
- Cameras: 2× Basler ace 2 a2A1920-160umBAS, 1920×1200 monochrome. Sensor capable of 60 fps; **recording at 30 fps** (set in `src/core/basler_camera.py:target_fps`)
- Camera lens: **Edmund Optics #33-304, 16mm UC Series, C-mount**. Same lens on both cameras. EPP = 10.68 mm from front vertex of first lens element, positive into lens (per `lens _specsheet.pdf` + `lens_drawing.pdf`). (Earlier reference to #59-870 C-Series was an incorrect lens link)
- Camera sync: **NOT hardware-triggered** — both cameras free-run independently. For stereo analysis use **software timestamp matching** via `grabResult.GetTimeStamp()`. Hardware sync via Basler GPIO is the eventual fix but deferred
- Camera positions: 0° direct view + "30° offset" (label only — the as-built optical axis tilt is **19.33° from vertical**, verified in CAD 2026-05-08; the 30° was design intent that got compromised during mounting). Both positions are fixed — valve appears at the same pixel location every session
- Recording format: **lossless FFV1 in AVI container** (was H.264/MP4 — reverted 2026-05-08 to remove inter-frame compression artifacts that bias optical flow). ~30-50 MB/sec mono at 30 fps. Threading model + lock pattern preserved from MP4 implementation
- Valve: white silicone tricuspid valve, 3 leaflets, operates underwater, leaflets bow outward toward camera when open
- Working fluids (both in scope): water (n≈1.333) and 35% glycerin blood analog with 0.02% xanthan gum (n≈1.385). Separate stereo calibration per fluid
- Visual conditions: bubbles on leaflet surface, uneven underwater lighting, dark triangular orifice when open

## CV Pipeline — Current State

**Status: METRIC DISPLACEMENT VIA STEREO CALIBRATION** (pivot 2026-05-08, supersedes pixel-displacement framing)

**Approach:** The CV deliverable is per-frame **metric (mm) leaflet
displacement** computed by triangulating a single manually-labeled
anatomical landmark across both cameras using a stereo calibration
fitted from a fixed 3D-printed calibration object. Dr. Lee made
metric displacement a hard requirement.

**Refraction handling:** Approach A — effective pinhole. Calibrate
underwater, in final mounting, looking through acrylic at the
calibration object submerged in the working fluid. Fitted intrinsics
absorb refraction. Approach B (explicit Snell's law ray tracing)
deferred unless A's residuals are unacceptable.

**Per-fluid calibration:** separate calibration JSON files for water
and the 35% glycerin blood analog. Switching fluids requires
recalibration.

**Single-view DLT-style:** the calibration object is fixed (cannot be
moved or rotated — designed to occupy the valve displacement volume).
Standard multi-view (Zhang's method) doesn't apply. Single-view
calibration works because the cylinder stack provides markers at
multiple z-depths (non-coplanar).

**Calibration object spec (committed):**
- Coordinate frame: **origin at center of top face**, +z pointing up
  out of the top face (= direction of water flow), +x designated by
  teammate on a sketch (a physically distinguishable direction in the
  top-face plane). Right-handed (+y = +z × +x). Cylinder markers below
  the top face have negative z.
- Stack of cylinders. Each cylinder has a flat **forward face** with
  dots arranged in a circle on that face. Top cylinder additionally
  has individually-positioned dots on its top face.
- Dots: 1.5 mm diameter, painted with waterproof black eyeliner ink,
  CAD-extruded outlines (0.08 mm) as guides.
- ~31 markers visible to the 30° camera; more visible to 0°.
- **Marker spec format from teammate: direct `(dx, dy, dz)` per
  marker** in CSV (`marker_id, dx_mm, dy_mm, dz_mm`). One row per
  painted dot on the entire object. No parametric ring description
  needed.
- Camera spec format: `(cmount_dx, cmount_dy, cmount_dz, axis_dx,
  axis_dy, axis_dz)` per camera in CSV — C-mount center position +
  optical-axis unit vector in the same frame.
- Plus a sketch showing the +x direction and a labeled reference dot
  per ring (for the manual ID-assignment step).

**Camera sync:** software timestamp matching via
`grabResult.GetTimeStamp()`. Hardware GPIO sync is the eventual fix
but deferred.

**Lens:** Edmund Optics #59-870, 16mm C-Series, C-mount. Same lens
both cameras. EPP=24.42 mm per spec sheet.

**Pipeline (offline, in `tools/`):**
1. `record_calibration.py` (built) — captures dual-camera AVI of
   submerged calibration object
2. `stereo_calibrate.py` (planned) — single-view calibration per
   camera, manual dot ID assignment, validation report
3. `annotate_stereo_point.py` (planned) — dual-camera side-by-side
   landmark labeler
4. `triangulate.py` (planned) — stereo CSV + calibration → per-frame
   XYZ in mm + metric displacement
5. `analyze_metric.py` (planned) — cycle CVs in mm

**Pixel pipeline (kept as supporting validation):**
The point-annotator + cycle-CV tools from
`docs/plans/2026-05-04-point-annotator-design.md` still exist and
work, but as a single-camera sanity check on optical-flow accuracy,
not the headline deliverable:
- `tools/annotate_point.py`, `tools/playback_annotations.py`,
  `tools/analyze_annotations.py`, `tools/_annotations.py`,
  `tools/_flow_params.py`

**Tools enhanced this session:**
- `tools/playback_annotations.py` — `--save` (renders MP4),
  `--plot` (writes displacement-vs-time PNG to `outputs/`),
  per-frame vector length in HUD, auto-loops between first/last
  annotated frame
- `tools/flow_explore.py` — direction-encoded color (red=N,
  yellow=ENE, cyan=E), magnitude-encoded opacity, `--max-mag` and
  `--contrast` knobs, direction legend in bottom-left

**Killed (do not build):**
- `tools/flow_export.py` (HDF5 dataset exporter) — killed 2026-05-08.
  Downstream-researcher / CNN-on-flow-data path no longer prioritized
  in favor of direct metric displacement.
- `tools/param_sweep.py` and `tools/validation_report.py` — subsumed
  by stereo calibration's built-in validation.
- `tools/annotate_leaflets.py` (polygon annotator) — superseded.
- `tools/_metrics.py` cycle-period FFT helpers — cycle metrics derived
  from phase labels in `analyze_annotations.py`.
- Arduino FLOW correlation as validation gate.
- Refractive ray tracing (Approach B) — deferred.

**Deprecated but retained for reference:**
- `tools/leaflet_flow_test.py` — LK prototype. Keep in repo; do not
  extend.
- `src/core/leaflet_tracker.py` — never created; removed from roadmap.

> Active design: `docs/plans/2026-05-08-stereo-calibration-design.md`.
> Earlier plans (`2026-04-20-flow-export-*`, `2026-05-01-flow-export-amendment.md`,
> `2026-05-04-point-annotator-*`) are historical; the
> stereo-calibration design supersedes them as the headline framing.

## Testing Requirements
Every new module or feature must have corresponding pytest tests. Run `pytest tests/ -v` before committing.

## Mock Data Rules
Do not introduce new mocks or expand mock coverage unless explicitly requested.
`tests/mock_data.csv` and `tests/mock_arduino.py` exist for UI development and demos only.

When mock data is explicitly requested:
1. **Values** — `tests/mock_data.csv` must be sourced from an actual recorded CSV in `outputs/`.
2. **Timing** — `tests/mock_arduino.py` must use `delay_sec = 0.1 * abs(30.0 / BPM)`. `_MOCK_BPM` is managed manually by the user.

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
- Dense optical flow on the **leaflet surface interior** (no texture — Farneback propagates boundary flow inward via regularization; interior values are hallucinated). Dense flow at the orifice **boundary** via a donut ROI is fine.
- Live in-app CV tracking (`src/core/leaflet_tracker.py`) — CV work is offline, in `tools/`.
- Deep learning / CNN for segmentation in this project (no GPU, unnecessary).
- **HDF5 dataset exporter** (`tools/flow_export.py`) — killed 2026-05-08. The downstream-researcher / CNN handoff is no longer the deliverable framing. Direct metric displacement is.
- **Refractive ray tracing** (Snell's law modeling) — deferred. Effective-pinhole calibration absorbs refraction; only revisit if validation fails.
- **Hardware camera trigger sync** — deferred this iteration. Software timestamp matching via `grabResult.GetTimeStamp()` is the chosen workaround.
- Dot tracking / fiducial markers on the **valve** (ID drift). Note: dots on the calibration object are different — they're identified manually once and triangulated, not tracked over time.
- Spiderweb / HoughLinesP (bubble noise, 3D deformation)
- Bidirectional Arduino control (firmware modification required first)
- Standalone executable packaging (PyInstaller/cx_Freeze)
- MapAnything integration
- CI/CD pipeline (GitHub Actions)

## Context Management

| Situation | Action |
|-----------|--------|
| Starting a session | Run `/update-memory` to sync `memory/MEMORY.md` from recent transcripts |
| Picking up mid-feature | Read the relevant `docs/plans/` file — source of truth for where we left off |
| Starting new feature | Brainstorm → design doc → writing-plans → plan saved to `docs/plans/` |
| Finishing a feature | Update PRD.md §12 build state table, run `finishing-a-development-branch`, run `/update-memory` |

**What each file owns:**

| File | Owns | Update frequency |
|------|------|-----------------|
| `CLAUDE.md` | Dev conventions, architecture rules, current project state | When state changes |
| `docs/PRD.md` | Requirements, CV pipeline design, build state | Every feature |
| `docs/plans/` | Feature designs + implementation plans | Every feature |
| `memory/MEMORY.md` | Recent session context | Every session |

## Available Skills
When using any of the following skills, check `.claude/skills/` for the full instructions.
Superpowers skills are installed globally — invoke via the Skill tool.

**Project-specific:**
- **arduino-serial-protocol** — 7-field serial format, parsing, CSV output
- **pyqt-threading** — PySide6 QThread patterns for real-time I/O
- **weekly-progress-summary** — Weekly progress slides for BIEN 175B
- **update-memory** — Update memory from conversation transcripts

**Superpowers (global):**
- **superpowers:brainstorming** — Design before code. Always runs before new features.
- **superpowers:writing-plans** — Implementation plan after approved design.
- **superpowers:executing-plans** — Execute a written plan task-by-task.
- **superpowers:systematic-debugging** — Root cause analysis before any fix.
- **superpowers:test-driven-development** — RED-GREEN-REFACTOR with review gate.
- **superpowers:verification-before-completion** — Run and paste actual output before claiming done.
- **superpowers:using-git-worktrees** — Isolated worktree for feature branches.
- **superpowers:finishing-a-development-branch** — Structured branch completion and merge.
- **superpowers:subagent-driven-development** — Parallel subagents for independent tasks.
- **superpowers:requesting-code-review** — Code review before merging.