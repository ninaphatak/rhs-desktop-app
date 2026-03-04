# RHS Monitor

A PySide6 desktop app for the Right Heart Simulator (RHS) — a cardiovascular medical training device simulating post-Fontan hemodynamics. RHS = Right Heart Simulator.

## What This App Does
Unified GUI for: Arduino sensor monitoring (P1, P2, Flow, HR, VT1, VT2, AT1), on-demand CSV recording, in-app data visualization, run quality logging, and dual Basler camera feeds. **This is a read-only sensor monitoring app.** The solenoid is controlled by a manual potentiometer on the hardware (serial command protocol designed but not yet implemented — see `docs/solenoid_protocol.md`).

> See `docs/PRD.md` for product requirements and current build state.

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
- `docs/` — PRD.md (requirements + build state), plans/ (design + implementation plans), solenoid_protocol.md
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

## Testing Requirements
Every new module or feature must have corresponding pytest tests. Run `pytest tests/ -v` before committing.

## Mock Data Rules
Do not introduce new mocks or expand mock coverage unless explicitly requested.
`tests/mock_data.csv` and `tests/mock_arduino.py` exist for UI development and demos
only — not for validating data-path logic. Serial data mocks do not accurately represent
hardware behavior.

When mock data is explicitly requested:
1. **Values** — `tests/mock_data.csv` must be sourced from an actual recorded CSV in
   `outputs/`. Do not generate synthetic data.
2. **Timing** — `tests/mock_arduino.py` must use `delay_sec = 0.1 * abs(30.0 / BPM)`.
   `_MOCK_BPM` is managed manually by the user — do not change it.

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
| `CLAUDE.md` | Dev conventions, architecture rules | Rarely |
| `docs/PRD.md §12` | Current build state | Every feature |
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
- **superpowers:test-driven-development** — RED-GREEN-REFACTOR with review gate (see global CLAUDE.md).
- **superpowers:verification-before-completion** — Run and paste actual output before claiming done.
- **superpowers:using-git-worktrees** — Isolated worktree for feature branches.
- **superpowers:finishing-a-development-branch** — Structured branch completion and merge.
- **superpowers:subagent-driven-development** — Parallel subagents for independent tasks.
- **superpowers:requesting-code-review** — Code review before merging.
