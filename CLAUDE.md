# RHS Monitor

A PySide6 desktop app for the Right Heart Simulator (RHS) — a cardiovascular medical training device simulating post-Fontan hemodynamics. RHS = Right Heart Simulator.

## What This App Does
Unified GUI for: Arduino sensor monitoring (P1, P2, Flow, HR, VT1, VT2, AT1), on-demand CSV recording, in-app data visualization, run quality logging, and dual Basler camera feeds. Computer vision work is offline — standalone tools in `tools/` produce an **HDF5 optical-flow dataset** for handoff to researchers downstream. **This is a read-only sensor monitoring app.**

> See `docs/PRD.md` for product requirements, CV pipeline design, and current build state.

## Tech Stack
Python 3.11+ | PySide6 + pyqtgraph | pypylon (Basler camera) | OpenCV (optical flow) | pyserial (31250 baud, read-only) | pandas/numpy | matplotlib (in-app dialogs) | pytest

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
- `tools/` — Standalone CV exploration scripts (not part of the main app)
- `docs/` — PRD.md, plans/, solenoid_protocol.md
- `outputs/` — Recorded CSVs + run_log.csv (gitignored)
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
- Cameras: 2× Basler ace 2 a2A1920-160umBAS, 1920x1200 @ 60fps, monochrome
- Camera positions: 0° direct view + 30° offset. Both positions are fixed — valve appears at the same pixel location every session.
- Valve: white silicone tricuspid valve, 3 leaflets, operates underwater, leaflets bow outward toward camera when open
- Visual conditions: bubbles on leaflet surface, uneven underwater lighting, dark triangular orifice when open

## CV Pipeline — Current State

**Status: DATASET EXPORT PHASE** (pivot from in-app tracker)

**Approach:** Produce a structured per-frame **dense optical flow dataset** from recorded valve videos as a handoff artifact for Dr. Lee / a downstream researcher (annotation, CNN training, further analysis). No live in-app tracker. The CV work lives entirely in `tools/` — the app itself stays a read-only sensor monitor.

**Why the pivot:** Sparse LK on boundary points (`tools/leaflet_flow_test.py`) did not produce reliable tracks on actual footage — the textureless white silicone surface and bubble noise described in PRD §5.6 hurt LK too, not just dense-flow-on-surface. Farneback dense flow at the **orifice boundary** (donut ROI — NOT the leaflet surface interior) qualitatively tracks leaflet motion and can be packaged as a dataset.

**What's decided:**
- Dense Farneback inside a donut ROI around the orifice. Not on the textureless leaflet interior — PRD §5.6's rejection stands for the interior; regularization-propagated flow there is hallucinated.
- Fixed absolute-magnitude threshold on saved flow fields. No `NORM_MINMAX` in saved data.
- HDF5 handoff format. Core `session.h5` = grayscale frames + motion masks + contours + metadata. Optional `flow.h5` sidecar = raw dense flow (large).
- Both 0° and 30° cameras supported by the same exporter (`--camera` CLI arg).
- Hardcoded Farneback params (winsize=21, poly_n=7, poly_sigma=1.5, OPTFLOW_FARNEBACK_GAUSSIAN) + CLAHE preprocessing + morph cleanup, stamped into HDF5 attrs for reproducibility.

**What's in progress:**
- `tools/flow_export.py` — CLI exporter (to be built). See `docs/plans/2026-04-20-flow-export-plan.md`.
- Phase 0 validation: correlate donut-ROI mean flow magnitude vs Arduino FLOW channel. Gate the build on r² ≥ 0.5.
- New recordings from both cameras scheduled (valve cycling with motion).

**Planned (after exporter ships):**
- `tools/annotate_leaflets.py` — lightweight polygon annotator (~30-50 frames).
- `tools/param_sweep.py` + `tools/_metrics.py` — parameter grid (winsize × threshold × donut) run across the same video, metrics computed per run.
- `tools/validation_report.py` — produces IoU/Arduino-correlation heatmaps + `docs/validation_results.md`.
- This validation study turns the deliverable from "data pipeline" into "validated optical flow pipeline with parameter-sensitivity analysis" — the research framing for Dr. Lee. **"Reconstruction" here = motion reconstruction (flow vs Arduino sensor, flow-derived contours vs annotations), NOT 3D/SfM.**

**Deprecated but retained for reference:**
- `tools/leaflet_flow_test.py` — LK prototype. Keep in repo; do not extend.
- `src/core/leaflet_tracker.py` — never created; removed from the roadmap.

> See `docs/plans/2026-04-20-flow-export-design.md` for full design rationale and `docs/PRD.md` for algorithm background and rejected alternatives.

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
- Deep learning / CNN for segmentation in this project (no GPU, unnecessary) — a downstream researcher may train one on the exported dataset, which is a separate workstream.
- Dot tracking / fiducial markers (ID drift)
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