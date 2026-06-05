# RHS Monitor — Handoff Readiness & Documentation-Drift Report
> Auto-generated from a multi-agent codebase audit on 2026-05-30. This is the **pre-handoff checklist**: it lists everywhere the committed docs (CLAUDE.md / PRD) have drifted from the actual code, plus a prioritized cleanup list. Fix P0+P1 before students arrive.

## Unified project map (as the code actually is today)
## RHS Monitor — Project Map (as it ACTUALLY is, 2026-05-30)

Branch: `feature/flow-export` (HEAD `fb87367`). This branch is the canonical CV branch; `main` is the **pre-CV app** and has **no `tools/` directory at all**.

### A. The Live App (`src/`) — committed, on `feature/flow-export`
A read-only PySide6 sensor monitor. Three QThread I/O objects; everything else communicates by signal/slot.

- `src/main.py` — entry point; argparse (`--mock`, `--record CAM`, `--record-duration`, `--record-fps`, `--record-output`); QApplication + `MainWindow`; Ctrl+C keepalive QTimer.
- `src/core/serial_reader.py` — QThread; reads the 7-field 31250-baud stream (`P1 P2 FLOW HR VT1 VT2 AT1`), DTR-resets the board, strict 7-field count guard, emits `data_received(dict)`. **Read-only — never writes serial.**
- `src/core/basler_camera.py` — QThread grab loop + recording via piped ffmpeg. **Records MJPG/AVI at `-q:v 2`** (NOT FFV1 — see discrepancies). Writes `.avi` + `.avi.timestamps.csv` + `.avi.metadata.json` sidecars. Two instances (left/right), free-run (not hardware-triggered).
- `src/core/data_recorder.py` — non-thread CSV recorder; `record_row()` runs on the UI thread at ~30 Hz; writes `outputs/rhs_<ts>.csv`.
- `src/core/run_logger.py` — append-only `outputs/run_log.csv`.
- `src/ui/` — `main_window.py` (startup orchestrator + signal hub), `graph_panel.py` (2×2 pyqtgraph, deque maxlen 150, 20 Hz dirty-flag refresh), `camera_panel.py` (dual QLabel preview; auto-connects cameras; shows "No Camera" with no SDK), `control_bar.py` (Record/Stop/Plot/Log + permanently-disabled "Start RHS" placeholder), `plot_dialog.py` + `log_dialog.py` (reuse templates: QDialog + QFileDialog + embedded matplotlib canvas / form+table).
- `src/utils/config.py` — constants Rosetta Stone (`BAUD_RATE=31250`, `SERIAL_FIELDS`, paths, buffer sizes, `MJPG_QUALITY=2`).
- `src/utils/port_detection.py` — cross-platform Arduino port detect.

### B. Offline CV — the HEADLINE metric pipeline (`tools/`) — committed
Standalone scripts, no pypylon at analysis time. Deliverable = per-frame metric (mm) leaflet displacement.

`record_calibration.py` (Stage 1, calibration object) → `stereo_calibrate.py` (Stage 2, single-view per-camera calibration) → `annotate_stereo_point.py` (Stage 3, dual-pane landmark labeler, run on the VALVE video) → `triangulate.py` (Stage 4, 3D mm + displacement) → `analyze_metric.py` (Stage 5, cycle CVs).
- Calibration model (`CALIB_FLAGS`): fixed focal length + fixed principal point; fits only k1, p1, p2. Seed `f_px = (16.0/0.00345)·n_fluid` (water 1.333, analog 1.385). **Lens constants in code: #33-304 UC Series, EPP 10.68 mm.**
- `markers.csv` — 41 markers across 5 z-depth rings + cam0/cam1/optical-axis rows.
- Calibration outputs present locally (`outputs/` is gitignored): `stereo_calib_water.json` (median 0.154 mm / max 0.431 mm) AND **`stereo_calib_analog.json`** (median 0.131 / max 0.500 mm, cam0 EPP discrepancy 14.42 mm — just inside the 15 mm gate) + correspondence files.

### C. Offline CV — single-camera pixel validation (`tools/`) — committed
`annotate_point.py` → `playback_annotations.py` (`--save` MP4, `--plot` PNG to `outputs/`) → `analyze_annotations.py` (Mode A cycle CVs; Mode B Farneback-vs-manual error). Shared spine: `_annotations.py`, `_flow_params.py` (Farneback dict). `flow_explore.py` = dual-cam dense-flow explorer (per-pixel object-frame Jacobian → mm; direction→hue Red=+x/Green=+y/Cyan=−x/Magenta=−y, magnitude→opacity; 2D only, ±z invisible by construction).

### D. Offline CV — the UNCOMMITTED "tracks" workstream (`tools/`, all `??` untracked)
A second, parallel pipeline NOT described in CLAUDE.md/PRD. Auto-tracks MULTIPLE inked valve "intersection" corners over time, triangulates each, analyzes/visualizes, and correlates with Arduino pressure. Builds directly on committed `triangulate.py` + `stereo_calib_<fluid>.json`.
- `_tracks.py` (shared spine, 19-col CSV, mature), `track_intersections.py` (hybrid LK-prior + frozen-frame-0 NCC anchor; primitives unit-tested), `pick_track_seeds.py`, `playback_tracks.py`, `analyze_tracks.py` (FFT cycle period), `splice_manual_into_tracks.py` (manual repair of lost tracks; most fragile, untested), `analyze_pressure_vs_tracks.py` (P2/Flow vs displacement — exploratory, NOT a sanctioned gate), `plot_calibration_error.py`, `plot_calibration_geometry_3d.py`.
- `tests/test_tracking.py` — **17 tests, all pass** (verified `17 passed`). Covers `_tracks.py` I/O + `track_intersections` primitives only; NOT `main()`, GUI tools, analyze/splice/plot scripts.
- `annotate_stereo_point.py` is the one MODIFIED tracked file: retrofitted with `--step` sparse labeling + `--output` + yellow/red carry-forward to feed `splice_manual_into_tracks.py`.
- 4 untracked math/onboarding docs: `docs/metric_displacement_mathematics.md` (primary primer), `docs/calibration_to_displacement_walkthrough.md`, `docs/backup_slides_math_and_algorithm.md`, `docs/TODO.md`.

### E. Deprecated / relic tools (committed, in repo, NOT in CLAUDE.md tools list)
- `calibrate_valve.py` — legacy 2D pixel valve-ROI picker → `config/valve_calibration.json`. Superseded by `stereo_calibrate.py`; relic of the pixel framing.
- `leaflet_flow_test.py` — failed sparse-LK prototype (CLAUDE.md does list this as "deprecated, retained").
- `record_valve.py`, `record_debug.py`, `playback_stereo_annotations.py` — committed and useful, but absent from CLAUDE.md's tools enumeration.

### F. Arduino (`arduino/`)
- `rhs_firmware.ino` — maintainer's hand-synced MIRROR (NOT the flashed source); 7-field output, BPM hardcoded 130, drives solenoid autonomously, no serial-read. Compatible with the app.
- `Right_Heart_Simulator_Arduino_new.ino` — older 4-field firmware (no temps, PTMax=10, BPM=170). **Incompatible** with the current 7-field parser.
- `arduino/README.md` — empty (0 bytes).
- `docs/solenoid_protocol.md` — ASPIRATIONAL, never implemented; references nonexistent `solenoidPin` (real pin `SPin=13`). Bidirectional control is "What NOT to Build."

### G. Docs (`docs/`)
- CURRENT plan of record: `docs/plans/2026-05-08-stereo-calibration-design.md`. `PRD.md` carries the May-8 pivot (§3.5/§8/§12).
- HISTORICAL (banner-marked): `2026-04-20-flow-export-*`, `2026-05-01-flow-export-amendment.md`, `2026-05-04-point-annotator-*`.
- Untracked CURRENT primers: the 4 math/TODO docs above.

### H. Setup / onboarding
- `setup.sh` / `setup.bat` (conda env `rhs-app` from `environment.yml`, SHA-256 hash to `.env_hash`), `run.sh` / `run.bat` (refuses to launch if env hash drifted). `bash run.sh --mock` = no-hardware path (mocks Arduino only; cameras show "No Camera").
- `environment.yml` (Python 3.11; PySide6, pyqtgraph, pyserial, pypylon, opencv-python, imageio-ffmpeg, pytest). No `requirements.txt`.
- Sample videos at repo root (`analog.mp4`, `water.mp4`, `water2.mp4`, `water3.mp4`, `out.mp4`) present locally but `*.mp4` is gitignored — a fresh clone will NOT include them.

### I. Git lineage (one-line)
Two histories split at `0684791` and never reconverged: `feature/flow-export` is simultaneously **+66 / −44** vs `main`. `main` is the pre-CV app (no `tools/`). Mergeable only after reconciling 44 app/sensor commits; expect conflicts in `src/core/basler_camera.py`.

## Documentation-vs-code discrepancies

### [HIGH] Camera lens spec (internal contradiction in CLAUDE.md)
- **Doc claims:** CLAUDE.md CV-Pipeline subsection (lines 117-118): 'Lens: Edmund Optics #59-870, 16mm C-Series, C-mount. EPP=24.42 mm per spec sheet.' CLAUDE.md Hardware Facts (line 57) and PRD §4 say '#33-304 16mm UC Series, EPP=10.68 mm'.
- **Reality:** The CODE and the actual artifacts settle it: tools/stereo_calibrate.py:44-49 defines LENS_EPP_FROM_FRONT_FACE_MM=10.68, LENS_FOCAL_MM=16.0, PIXEL_SIZE_MM=0.00345, commented '(Edmund #33-304, 16mm UC Series)'. Both outputs/calib/stereo_calib_water.json and stereo_calib_analog.json carry lens_epp_offset_mm: 10.68. The root PDFs are 'lens _specsheet.pdf'/'lens_drawing.pdf' = the #33-304 datasheet. The May-8 design doc explicitly states #59-870 was an incorrect link superseded by #33-304. So #33-304 / 10.68 mm is correct and seeds the calibration; the #59-870 / 24.42 mm line is stale and WRONG.
- **Fix:** Delete the stale 'Lens: Edmund #59-870 ... EPP=24.42 mm' block from the CLAUDE.md CV-Pipeline section (lines 117-118). The only correct values are #33-304 / EPP 10.68 mm, which the code and JSONs already use. Leaving the wrong EPP in the doc risks a future recalibration cross-check (CAD EPP = front_face − 10.68·axis) being recomputed with 24.42 and silently failing the 15 mm gate.

### [HIGH] Recording format (FFV1 vs MJPG)
- **Doc claims:** CLAUDE.md Hardware Facts line 60 and PRD §4 + §12 ('Lossless FFV1/AVI recording ✅ Done'): recording format is 'lossless FFV1 in AVI container (was H.264/MP4 — reverted 2026-05-08...)'.
- **Reality:** The live app records MJPG/AVI, not FFV1. src/core/basler_camera.py module docstring (lines 3-10) and _spawn_ffmpeg use '-c:v mjpeg -q:v 2', explicitly noting FFV1 was tried but reverted to MJPG for speed (~38 ms/frame FFV1 → ~3-5 ms/frame MJPG). MJPG_QUALITY=2 = 'visually lossless' but technically lossy. tools/record_valve.py also records MJPG/AVI. Only tools/record_calibration.py still uses FFV1/AVI. So CLAUDE.md/PRD overstate: the valve recordings the CV pipeline consumes are MJPG (lossy), not lossless FFV1.
- **Fix:** Correct CLAUDE.md line 60 and PRD §4/§12 to: 'MJPG/AVI at -q:v 2 (intra-only, visually lossless) for valve recording; FFV1 retained only in record_calibration.py'. This matters because the whole reason for abandoning H.264 was inter-frame compression biasing optical flow — students must know valve clips are MJPG (intra-only, so OK for flow) and that the 'lossless' label is approximate.

### [HIGH] Entire uncommitted 'tracks' workstream is invisible to the docs
- **Doc claims:** CLAUDE.md frames the CV deliverable as a SINGLE manually-labeled landmark (annotate_stereo_point → triangulate → analyze_metric) and lists 'Dot tracking / fiducial markers on the valve' and Arduino flow correlation under 'What NOT to Build'.
- **Reality:** A second, working, parallel pipeline exists entirely UNTRACKED (git ??): tools/_tracks.py, track_intersections.py, pick_track_seeds.py, playback_tracks.py, analyze_tracks.py, splice_manual_into_tracks.py, analyze_pressure_vs_tracks.py, plot_calibration_error.py, plot_calibration_geometry_3d.py, plus tests/test_tracking.py (verified 17 passed) and 4 untracked docs. It auto-tracks MULTIPLE valve intersection corners (hybrid LK-prior + frozen frame-0 NCC anchor — a deliberate ID-drift mitigation distinct from naive fiducials) and one tool correlates with Arduino P2/Flow. None of this is in CLAUDE.md or PRD, and no docs/plans/ design doc exists for it.
- **Fix:** Before handoff: (a) write docs/plans/2026-05-xx-tracking-design.md, (b) commit the workstream on a correctly-named branch, (c) update CLAUDE.md/PRD to describe the tracks pipeline as the multi-point successor and explicitly reconcile it with the 'no valve dot tracking' rule (the frame-0 NCC anchor is the mitigation) and the 'flow correlation not a gate' rule (analyze_pressure_vs_tracks is exploratory, not validation). Otherwise a student reading git/CLAUDE.md will not know this code exists or will think it violates project rules.

### [MEDIUM] Branch name vs reality (feature/flow-export)
- **Doc claims:** Active branch is named 'feature/flow-export', implying the flow-export deliverable.
- **Reality:** tools/flow_export.py does NOT exist on disk (confirmed absent) — it was killed 2026-05-08, and CLAUDE.md/PRD both list it as Killed. The dense-flow framing the branch is named for is dead; the dense-stereo 'true 3D' retry (commit 73194b0) was reverted the same day (ec3876a) and is NOT in the tip. The actual current work on this branch is the metric stereo pipeline + the uncommitted point-tracking pivot. The branch name is a vestigial misnomer.
- **Fix:** Rename/replace the branch before handoff (e.g. feature/metric-displacement or feature/stereo-tracking). Note in CLAUDE.md that 'flow-export' as a branch name is historical and flow_export.py is intentionally absent (killed), so no one searches for a missing file.

### [MEDIUM] Analog (glycerin) calibration status is stale
- **Doc claims:** CLAUDE.md only documents 'First successful water calibration' and lists per-fluid calibration as the plan; PRD §12 marks 'Analog calibration ⬜ Pending — Awaiting lab session'.
- **Reality:** The analog calibration is DONE. outputs/calib/stereo_calib_analog.json exists (dated May 10, frame 69, n=1.385: median 0.131 mm, max 0.500 mm, cam0 EPP discrepancy 14.42 mm — only just inside the 15 mm gate, cam1 11.53 mm) plus correspondences_analog_2026-05-10_17-55-55.json. The uncommitted tools/plot_calibration_error.py REQUIRES both water and analog JSONs.
- **Fix:** Update CLAUDE.md to add the analog calibration numbers and flip PRD §12 'Analog calibration' from ⬜ Pending to ✅ Done. Flag the thin 14.42 mm cam0 EPP margin (vs 15 mm tolerance) as a known caveat for any blood-analog recalibration.

### [MEDIUM] CLAUDE.md tools/ enumeration is incomplete
- **Doc claims:** CLAUDE.md line 27 lists the tools as: record_calibration, flow_explore, annotate_point, playback_annotations, analyze_annotations, stereo_calibrate, annotate_stereo_point, triangulate, analyze_metric.
- **Reality:** Committed tools NOT listed: record_valve.py, record_debug.py, playback_stereo_annotations.py, calibrate_valve.py, leaflet_flow_test.py, _annotations.py, _flow_params.py. Plus the 9 uncommitted tracks tools. The repo has 24 tool files (excluding __pycache__); CLAUDE.md names 9.
- **Fix:** Either fully enumerate tools/ in CLAUDE.md (grouped: metric pipeline / pixel validation / tracks / recording / deprecated) or stop trying to list them and point to a generated index. At minimum add record_valve.py (the primary headless valve recorder, and the on-ramp for the tracks pipeline) and playback_stereo_annotations.py.

### [MEDIUM] calibrate_valve.py mislabeled by name / not flagged as relic
- **Doc claims:** CLAUDE.md does not mention calibrate_valve.py at all; its 'Killed/Deprecated' lists name leaflet_flow_test.py but not calibrate_valve.py.
- **Reality:** tools/calibrate_valve.py is committed and present. It is a legacy 2D pixel-space valve-ROI picker (center/radius/seam → config/valve_calibration.json) — NO 3D, NO mm, NO stereo. Its concepts (valve center/radius/orifice geometry) conflict with the 'no orifice-area metrics' rule, and its name is confusingly close to stereo_calibrate.py. It is only consumed by the deprecated leaflet_flow_test.py.
- **Fix:** Add calibrate_valve.py to CLAUDE.md's 'Deprecated but retained' list with a one-line note: 'legacy pixel valve-ROI picker, NOT a stereo calibration tool, superseded by stereo_calibrate.py'. Consider moving it (and leaflet_flow_test.py) to legacy/ so a student browsing tools/ alphabetically doesn't confuse calibrate_valve with stereo_calibrate.

### [MEDIUM] Untracked CURRENT docs (math primers + TODO) not committed
- **Doc claims:** CLAUDE.md context table says docs/plans/ owns designs and PRD owns the build state; no mention of the math/onboarding primers.
- **Reality:** docs/metric_displacement_mathematics.md, docs/calibration_to_displacement_walkthrough.md, docs/backup_slides_math_and_algorithm.md, and docs/TODO.md are all untracked (git ??). These are the best onboarding material in the repo (full derivation of the camera model, single-view legitimacy, DLT triangulation, tracker drift argument) and TODO.md documents a real ~7% GUI frame-drop bug. They are invisible to anyone reading committed history.
- **Fix:** Commit all four docs. They are the primary handoff primers and the TODO documents a live deferred bug (record valve runs via tools/record_valve.py --dual with split USB docks, not the GUI, to keep frame loss ~0.17%).

### [LOW] tests/cv_frames/ directory claimed but does not exist
- **Doc claims:** CLAUDE.md Project Structure line 26: 'tests/ — pytest tests + mock hardware + cv_frames/ (static valve frames for CV dev)'.
- **Reality:** There is no tests/cv_frames/ directory (confirmed: ls returns 'No such file or directory'). tests/ contains __init__.py, mock_arduino.py, mock_camera.py, mock_data.csv, and 6 test_*.py files only. CV dev now uses the root sample .mp4s and outputs/videos/ AVIs instead.
- **Fix:** Remove the 'cv_frames/' reference from CLAUDE.md line 26, or recreate the directory if those static frames are still wanted. As written it points a student to a path that doesn't exist.

### [LOW] config.py camera constants are dead (latent config/code drift)
- **Doc claims:** CLAUDE.md implies camera fps is set in src/core/basler_camera.py:target_fps; config.py defines CAMERA_FPS=30, CAMERA_EXPOSURE_US=25000.
- **Reality:** BaslerCamera hardcodes target_fps=30 / exposure_us=25000 in __init__ (basler_camera.py:90-91) and does NOT read config.py's CAMERA_FPS / CAMERA_EXPOSURE_US. Editing config.py will not change camera behavior.
- **Fix:** Either wire BaslerCamera to read config.py or delete the unused CAMERA_FPS/CAMERA_EXPOSURE_US constants. Document the single source of truth so a student doesn't change config.py expecting fps to change.

### [LOW] flow_explore direction-color legend description is stale
- **Doc claims:** CLAUDE.md line 162-164: flow_explore.py uses 'direction-encoded color (red=N, yellow=ENE, cyan=E)'.
- **Reality:** The code (flow_explore.py:8-15, 61-92) anchors colors to object-frame axes: Red=+x, Green=+y, Cyan=−x, Magenta=−y. The 'red=N, yellow=ENE, cyan=E' description is from an earlier version and is wrong.
- **Fix:** Update CLAUDE.md (and PRD §12 'Dense flow exploration' note) to Red=+x / Green=+y / Cyan=−x / Magenta=−y. The code is source of truth.

### [LOW] docs/solenoid_protocol.md is aspirational/unbuildable but still presented as a doc
- **Doc claims:** CLAUDE.md lists docs/solenoid_protocol.md under docs/; the disabled 'Start RHS' button tooltip points to it as if actionable.
- **Reality:** The doc was never implemented and is not buildable as written: it references a nonexistent symbol 'solenoidPin' (real pin is SPin=13), claims potentiometer control (now commented out, BPM hardcoded), and instructs editing rhs_firmware.ino which is only a mirror, not the flashed source. Bidirectional control is explicitly 'What NOT to Build'.
- **Fix:** Add a prominent 'NOT IMPLEMENTED / aspirational sketch' banner to solenoid_protocol.md (or move it to docs/plans/ as historical), and fix the 'Start RHS' tooltip so a student isn't sent to follow a non-compilable spec.

## Handoff readiness assessment
## Handoff Readiness: NOT YET ready for high-schoolers

The repo is technically healthy (tests pass: app tests + 17 tracks tests; the GUI launches hardware-free via `bash run.sh --mock`; the metric pipeline is validated for both fluids). But the **documentation has drifted materially from the code**, and a substantial, working subsystem is uncommitted and undocumented. A high-schooler following CLAUDE.md today would: hit a wrong lens spec, look for a `tests/cv_frames/` that doesn't exist, search for a killed `flow_export.py` because of the branch name, believe analog calibration is still pending, and never discover the tracks pipeline that is half the actual CV work. None of these block running the app, but all sabotage a self-directed handoff.

### Readiness by area
- **Run the app with mock data:** READY. `bash setup.sh && bash run.sh --mock` works; cameras show "No Camera" (expected).
- **Run the test suite:** READY. `pytest tests/ -v` is hardware-free and side-effect-free (all writes redirected to tmp_path).
- **Run the committed CV metric pipeline:** READY but advanced (needs dual-cam AVIs + calibration object).
- **Understand current project state from docs:** NOT READY — multiple high/medium drifts (lens, recording format, tracks workstream, analog calibration).
- **Continue the CV work from git history:** NOT READY — the tracks workstream and its docs are untracked; branch name is misleading.

### Prioritized cleanup checklist (do before handoff)

**P0 — correctness/safety (do first):**
1. Fix the lens contradiction: delete the stale `#59-870 / EPP 24.42 mm` block in CLAUDE.md (CV-Pipeline section). Authoritative value is `#33-304 / EPP 10.68 mm` (matches code + both calib JSONs).
2. Fix the recording-format claim: CLAUDE.md line 60 + PRD §4/§12 say FFV1; the app + record_valve.py actually record MJPG/AVI `-q:v 2`. Correct to MJPG (intra-only); note FFV1 survives only in record_calibration.py.
3. Commit the tracks workstream (9 tools + tests/test_tracking.py + 4 docs) on a correctly-named branch, and write `docs/plans/<date>-tracking-design.md`. Currently invisible and at risk of loss.

**P1 — orientation accuracy:**
4. Update analog calibration status: CLAUDE.md add the numbers; flip PRD §12 'Analog calibration' ⬜→✅ (JSON exists; flag the 14.42 mm cam0 EPP margin).
5. Reconcile the tracks pipeline with the 'no valve dot tracking' and 'no flow correlation gate' rules in CLAUDE.md (explain the frame-0 NCC anchor mitigation; mark analyze_pressure_vs_tracks as exploratory).
6. Rename the `feature/flow-export` branch (flow_export.py is intentionally absent/killed).
7. Remove the nonexistent `tests/cv_frames/` reference from CLAUDE.md, or recreate it.
8. Complete CLAUDE.md's tools/ enumeration (add record_valve, record_debug, playback_stereo_annotations; flag calibrate_valve as a deprecated relic).

**P2 — polish / footguns:**
9. Commit the 4 untracked docs (they are the best onboarding primers; TODO.md documents the live ~7% GUI frame-drop bug — record valve runs via `tools/record_valve.py --dual` with split USB docks, not the GUI).
10. Fix flow_explore color legend in CLAUDE.md/PRD (Red=+x, Green=+y, Cyan=−x, Magenta=−y).
11. Resolve config/code drift: wire BaslerCamera to config.py CAMERA_FPS/EXPOSURE or delete the dead constants.
12. Banner docs/solenoid_protocol.md as NOT IMPLEMENTED (wrong pin name `solenoidPin`; bidirectional control is out of scope); fix the misleading 'Start RHS' tooltip.
13. Move `calibrate_valve.py` and `leaflet_flow_test.py` to `legacy/` (or clearly mark) so newcomers don't confuse calibrate_valve with stereo_calibrate or extend the failed LK prototype.
14. Note the git divergence prominently: `feature/flow-export` is +66/−44 vs `main` (which has no `tools/`); merging requires reconciling 44 commits, with conflicts expected in `src/core/basler_camera.py`.
15. Add a one-line note that root sample `.mp4`s are gitignored and won't survive a fresh clone, and that `arduino/rhs_firmware.ino` is a mirror (not the flashed source).

### Bottom line
Roughly a half-day of doc reconciliation + one commit of the tracks workstream stands between the current state and a clean handoff. The code is in good shape; the **map of the code is not**. Fix P0+P1 and this becomes a genuinely high-schooler-friendly handoff (clear no-hardware run path, passing tests, and strong math primers once committed).
