# GUI Architecture & Optical-Flow Integration

> Handoff doc 02. Audience: an incoming maintainer (and the high-school students who will operate the tool). Read `docs/handoff/01-*` first if it exists; read `CLAUDE.md` for project rules. This doc covers (1) how the live GUI is wired, (2) what data the app already writes to disk, and (3) the decision of *how* to integrate the offline metric-displacement pipeline into a data-extraction tool.

---

## 1. GUI Architecture Overview

RHS Monitor is a **read-only** PySide6 desktop app. It does three things live: read the Arduino sensor stream, preview two Basler cameras, and record both to disk on demand. All computer-vision / metric-displacement work is **offline** in `tools/` — none of it runs in the live GUI today.

### 1.1 The QThread model

The architecture rule (`CLAUDE.md`) is: **every blocking I/O source gets its own QThread; components talk only through signals/slots; never block the UI thread.** Concretely there are three I/O objects, two of which are threads:

| Object | File | Thread? | Role |
|---|---|---|---|
| `SerialReader` | `src/core/serial_reader.py` | **QThread** | Reads 7-field 31250-baud Arduino stream; emits `data_received(dict)`. Read-only — never writes serial. |
| `BaslerCamera` (×2, left/right) | `src/core/basler_camera.py` | **QThread** | Grab loop + MJPG/AVI recording via piped ffmpeg; emits throttled `frame_ready(dict)`. |
| `DataRecorder` | `src/core/data_recorder.py` | **No** (plain object) | CSV recorder. `record_row()` runs synchronously on the **UI thread** inside the `data_received` slot — fine at ~30 Hz. |
| `MockArduino` | `tests/mock_arduino.py` | QThread | `--mock` replacement for `SerialReader`; same signals, replays `tests/mock_data.csv`. |

Two subtleties worth internalizing before you touch this code:

- **`BaslerCamera.connect()` opens the device on the calling (UI) thread**, *before* `.start()` is called. Only the `RetrieveResult` grab loop runs on the worker thread (`basler_camera.py`). So "camera startup" is partly synchronous.
- **The grab thread shares recording state with the UI thread** (`stop_recording` runs on the UI thread, `_write_frame` on the grab thread). A `threading.Lock` (`_writer_lock`) serializes the ffmpeg handle; `stop_recording` swaps the process out under the lock, then does the slow `stdin.close()/wait()` outside it.

### 1.2 Signal/slot wiring

`MainWindow.__init__` (`src/ui/main_window.py`) is the startup orchestrator and the wiring hub. Everything fans out from there:

- **`SerialReader.data_received(dict)`** → `MainWindow._on_data_received` → fans out to `GraphPanel.update_data` **and** `DataRecorder.record_row` (when recording).
- **`BaslerCamera.frame_ready(dict)`** (left/right) → `CameraPanel._update_left` / `_update_right`.
- **`ControlBar`** declares `record_clicked / stop_clicked / plot_clicked / log_clicked` (re-emitted from button `.clicked`); `MainWindow` connects each to `_on_record / _on_stop / _on_plot / _on_log`. `_on_plot` and `_on_log` open `PlotDialog` / `LogDialog` modally with lazy imports.
- **`BaslerCamera.recording_finished(str)` is declared but NOT connected to anything** in the GUI. It is a ready-made, unused hook — relevant later for an "analysis when recording done" trigger.

### 1.3 Data flow (the two real-time paths)

- **Sensor path:** Arduino bytes → `SerialReader.run()` `readline()` → `split()` → reject if token count ≠ 7 → build dict keyed by `SERIAL_FIELDS` with a host-clock `timestamp` → `data_received.emit()` → `GraphPanel` appends to 7 `deque(maxlen=150)` and sets a dirty flag. A separate **20 Hz** `QTimer` calls `_refresh_curves` which only redraws if dirty — this decouples paint rate (20 Hz) from data rate (~30 Hz).
- **Camera path:** grab thread copies `grab.Array`, captures `time.time()` and `grab.GetTimeStamp()`, calls `_write_frame()` (records all 30 fps), then emits `frame_ready` **throttled to every 6th frame while recording** (≈5 fps preview) to protect the GIL. *Preview frame rate ≠ recorded frame rate.*

### 1.4 ASCII architecture diagram

```
                       ┌──────────────────────────── UI THREAD (Qt event loop) ──────────────────────────────┐
                       │                                                                                     │
  ┌────────────┐       │   ┌──────────────┐   data_received(dict)     ┌──────────────────────────────────┐   │
  │  Arduino   │  USB  │   │ SerialReader │ ───────────┬────────────► │ MainWindow._on_data_received     │   │
  │ (7 fields) │──────►│   │  (QThread)   │            │              │   ├─► GraphPanel.update_data     │   │
  └────────────┘ 31250 │   └──────────────┘            │              │   │     (deque×7, 20Hz refresh)  │   │
                  baud │      [--mock → MockArduino, same signals]    │   └─► DataRecorder.record_row    │──┐│
                       │                                              └──────────────────────────────────┘  ││
                       │                                                                                    ││ writes
  ┌────────────┐       │   ┌──────────────┐  frame_ready(dict)        ┌─────────────────────────────────┐   ││ (UI thread)
  │ Basler cam0│──USB──┼──►│ BaslerCamera │ ──(throttled 5fps)──────► │ CameraPanel._update_left/right  │   ││
  └────────────┘       │   │  (QThread L) │                           │   (QLabel preview, scale-crop)  │   ││
  ┌────────────┐       │   ├──────────────┤                           └─────────────────────────────────┘   ││
  │ Basler cam1│──USB──┼──►│ BaslerCamera │                                                                 ││
  └────────────┘       │   │  (QThread R) │   recording_finished(str) ····► [DECLARED, NOT CONNECTED]       ││
                       │   └──────┬───────┘                                                                 ││
                       │          │ _write_frame() — ALL 30 fps, under _writer_lock                         ││
                       │          ▼ (grab thread, NOT UI thread)                                            ││
                       │   ┌──────────────┐         ┌─────────────┐  plot_clicked / log_clicked             ││
                       │   │ piped ffmpeg │         │  ControlBar │ ──────────┬─────────────────────────────┘│
                       │   │ MJPG/AVI -q2 │         │ Rec/Stop/   │           │  (lazy import + .exec())     │
                       │   └──────┬───────┘         │ Plot/Log    │           ▼                              │
                       └──────────┼─────────────────┴─────────────┴─ PlotDialog / LogDialog (modal QDialog) ─┘
                                  │                                          ▲  ◄── REUSE TEMPLATE for analysis
                                  ▼                                          │
                ╔═══════════════════════════════════════════════════════════╗│ reads
                ║                   ON-DISK DATA SURFACE                    ║┘
                ║  outputs/rhs_<ts>.csv                  (sensors)          ║
                ║  outputs/run_log.csv                   (run quality)      ║      ┌───────────────────────────┐
                ║  outputs/videos/cameraN_<ts>.avi       (MJPG video)       ║─────►│   OFFLINE tools/ pipeline │
                ║  outputs/videos/...avi.timestamps.csv  (free-run sync)    ║      │  (separate processes,     │
                ║  outputs/videos/...avi.metadata.json   (fps/serial/dims)  ║      │   no live GUI today)      │
                ║  outputs/calib/stereo_calib_<fluid>.json (calibration)    ║      └───────────────────────────┘
                ╚═══════════════════════════════════════════════════════════╝
```

The boxed bottom region — the on-disk data surface — is the bridge between the live app and the offline pipeline, and is the subject of the integration question.

---

## 2. The Data-Extraction Surface That Exists TODAY

Everything the offline pipeline needs is **already written to disk by the live app and the recording tools.** No new capture work is required to integrate analysis. Here is the complete extant surface (note: `outputs/` is gitignored — these files are produced at runtime, not committed):

| Artifact | Producer | Schema / contents |
|---|---|---|
| `outputs/rhs_<ts>.csv` | `DataRecorder` | `Time (s)` (relative, t=0 at first sample) + P1, P2, Flow, HR, VT1, VT2, AT1. One row per ~30 Hz sample. |
| `outputs/run_log.csv` | `run_logger.py` (append-only) | `timestamp, csv_filename, rating, notes`. `read_run_log()` → DataFrame; `list_csv_files()` globs `rhs_*.csv` newest-first. |
| `outputs/videos/cameraN_<ts>.avi` | `BaslerCamera` (GUI) / `record_valve.py` | **MJPG/AVI at `-q:v 2`** (intra-only, "visually lossless" — *not* FFV1 despite some doc text; intra-only is fine for optical flow). |
| `outputs/videos/<avi>.timestamps.csv` | same | `frame_index, system_time_s, hw_timestamp_ticks`. **Load-bearing for stereo:** cameras free-run, not hardware-triggered, so this sidecar is the *only* way to temporally align cam0↔cam1. |
| `outputs/videos/<avi>.metadata.json` | same | serial_number, model_name, width/height_px, pixel_format, configured fps/exposure, `hw_timestamp_tick_hz_assumed = 1e9`. |
| `outputs/calib/stereo_calib_<fluid>.json` | `tools/stereo_calibrate.py` | Per-camera `K, dist, rvec, tvec`, plus a `validation` block (reprojection RMS, per-marker 3D error, EPP discrepancy). Both `water` and `analog` exist today. |
| `<avi>.stereo_annotations.csv` | `tools/annotate_stereo_point.py` | `frame_idx, u0, v0, u1, v1, phase`. Sparse, one row per labeled frame. |
| `<csv>.triangulated.csv` | `tools/triangulate.py` | `frame_idx, x_mm, y_mm, z_mm, displacement_mm, dx_mm, dy_mm, dz_mm, phase`. **This is the metric (mm) deliverable.** |
| `<csv>.metric.json` | `tools/analyze_metric.py` | `n_cycles_complete/incomplete` + per-metric `{mean, std, cv, values}` for `cycle_period_ms`, `path_length_mm`, `peak_displacement_mm`. |

**Filename pairing is the linkage.** When the GUI records cameras alongside sensors, the CSV's timestamp segment is reused: `rhs_<ts>.csv` ↔ `outputs/videos/camera0_<ts>.avi` + `camera1_<ts>.avi` (`main_window.py`). That shared `<ts>` is how a post-processing tool correlates a sensor run with its two camera videos.

**Two importable seams already exist** (verified — both are pure file-loaders with no `cv2.imshow`/window code):

- `tools/triangulate.py` exposes `load_calibration(path)`, `load_stereo_annotations(path)`, `load_timestamps(path)`, `interpolate_pixel_at_time(...)`, `triangulate_point(...)`.
- `tools/analyze_metric.py` exposes `load_triangulated_csv`, `Sample`, `Cycle`, `detect_cycles`, `cycle_period_ms`, `path_length_mm`, `peak_displacement_mm`, `aggregate`.

These can be imported and run **in-process** with no hardware and no GPU.

---

## 3. THE INTEGRATION QUESTION

> The maintainer wants to integrate the offline optical-flow / metric-displacement post-processing into a tool with **strong data extraction** — i.e. a place a non-expert can load a recording + calibration, get mm displacement plots, and export a clean CSV.

There are two honest routes. Both consume the *same* on-disk surface from §2; they differ in where the UI lives.

### Route A — A new in-app PySide6 analysis dialog/tab

Add an `AnalysisDialog` (a `QDialog`, or a tab in `MainWindow`) modeled directly on the existing `PlotDialog` pattern. Flow: pick an `.stereo_annotations.csv` (or AVI pair) + a `stereo_calib_<fluid>.json` via `QFileDialog`, run `triangulate` + `analyze_metric` **in-process**, draw displacement-vs-time and 3D-path plots on an embedded `FigureCanvasQTAgg`, and offer an "Export CSV" button. This is the same modal-dialog mechanism Plot and Log already use.

**Why it fits:** `PlotDialog`/`LogDialog` are pure file-loaders that touch no hardware; the offline tools import cv2/numpy but no pypylon; the whole app already launches with zero hardware (`--mock` for serial, "No Camera" placeholders for cameras). So an analysis dialog inherits the hardware-free property completely.

| Pros | Cons |
|---|---|
| **One tool, one launch.** Students already run `bash run.sh`. Analysis lives behind a button next to Plot/Log — nothing new to install or start. | **Couples analysis to the Qt app.** Heavy imports (cv2, matplotlib, the tools) must be lazy-loaded to keep startup fast (the existing pattern already does this). |
| **Maximal reuse.** Reuses `PlotDialog`'s `FigureCanvasQTAgg` embed, the `QFileDialog`-rooted-at-`OUTPUTS_DIR` idiom, and the importable `triangulate`/`analyze_metric` functions verbatim. ~1 new file + ~1 button. | **The interactive *annotate* step is a native cv2 window, not Qt.** `annotate_stereo_point.py` opens an OpenCV window for clicking. A fully in-app annotate flow would need reimplementation in a Qt widget — so the clean first cut consumes an **already-saved** `.stereo_annotations.csv` and only runs triangulate+analyze+plot+export in-app. |
| **No new dependency, no network, no server.** Everything is already in `environment.yml` (PySide6, matplotlib, opencv, pandas). | **Plots are static matplotlib** (zoom/pan via the canvas, but not web-grade interactivity). Adequate for displacement-vs-time; not a dashboard. |
| **Same maintenance surface.** A remote maintainer debugs one Python app, one env, one launcher. | Tied to the desktop — can't hand someone a URL to view results without screen-sharing. |

### Route B — A separate lightweight web tool (FastAPI/Flask + browser, or Streamlit)

Stand up a small local server (Streamlit is the lightest: one `app.py`, `st.file_uploader`, `st.pyplot`/`st.plotly_chart`, `st.download_button`). It ingests recorded AVIs/CSVs + a calibration JSON, calls the same `triangulate`/`analyze_metric` functions, and renders interactive plots with a download link.

| Pros | Cons |
|---|---|
| **Best-in-class data extraction UX.** Drag-drop upload, interactive (Plotly) zoom/hover, one-click download — genuinely strong for "extract data and hand it to someone." | **A second app to install, run, and maintain.** New dependency (`streamlit` or `fastapi`+`uvicorn`+a JS-free template) not in `environment.yml`; a second process to launch (`streamlit run`), a port to manage, a second thing that can break. |
| **Shareable via URL** on a LAN; results viewable without the desktop app. | **Splits the codebase in two.** The team now maintains the Qt app *and* a web app. For a remotely-maintained project staffed by basic-Python high-schoolers, that doubles the "what is this and how do I run it" surface. |
| Decoupled from PySide6 — analysis evolves independently of the monitor. | **Streamlit's rerun-on-interaction model is its own learning curve** (caching, session state). FastAPI means writing HTML/JS templates or a frontend — strictly more web knowledge than this team has. |
| Could later become a hosted dashboard if the project grows. | **Re-running the cv2 pipeline per upload over HTTP** invites timeout/large-file issues (AVIs are tens of MB); needs care the Qt in-process call doesn't. No offline benefit — the work is identical, just behind a socket. |

### Recommendation: **Route A — the in-app PySide6 analysis dialog.**

Reasoning specific to *this* team and project:

1. **Offline, no-GPU, no-server is the whole ethos.** The CV work is deliberately offline file-crunching; nothing here benefits from a web server. Route B adds a network layer that buys zero analytical capability — the triangulation math is identical either way — while adding a process, a port, and a dependency.
2. **The maintainer must support it remotely, and operators are high-schoolers who know only basic Python.** "Open the app you already use, click Analyze, pick two files, click Export" is a far smaller cognitive and support surface than "also install streamlit, run a second command, open localhost in a browser." One app, one `bash run.sh`, one `environment.yml` is the lowest-friction thing to hand off and to debug over a video call.
3. **The hard requirement is metric (mm) data extraction, and Route A delivers exactly that with maximal reuse.** The `triangulate`/`analyze_metric` functions are already importable and window-free; `PlotDialog` is a proven embed-matplotlib-in-a-QDialog template. The displacement-vs-time + 3D-path plots plus an "Export triangulated CSV" button satisfy the requirement with roughly one new file and one new button — no new framework.
4. **It reuses the team's existing mental model.** Students already understand Record/Stop/Plot/Log. "Analyze" is the same shape (lazy-imported modal dialog launched from `ControlBar`). Route B would require them to learn a second paradigm.

**When Route B *would* win:** if the deliverable were a shared, always-on dashboard that non-team stakeholders (e.g. an advisor) browse to without running anything — or if analysis needed to scale to many concurrent users. Neither is true here. If that need ever materializes, the importable `triangulate`/`analyze_metric` seam means a Streamlit front-end can be bolted on later **without rewriting any analysis logic** — so choosing Route A now does not foreclose Route B later.

---

## 4. Concrete Component / File Plan for Route A

The first integration deliberately stops short of in-app annotation (which is a native cv2 window). It consumes an **already-saved** `.stereo_annotations.csv` (produced by the offline `annotate_stereo_point.py`) plus a calibration JSON, and does the metric extraction + plot + export in-app. This is the smallest correct, hardware-free, GPU-free slice.

### Files to ADD

- **`src/ui/analysis_dialog.py`** — new `AnalysisDialog(QDialog)`, modeled on `src/ui/plot_dialog.py`:
  - Three `QFileDialog.getOpenFileName` pickers (or comboboxes): the `.stereo_annotations.csv` rooted at `VIDEOS_DIR`; the calibration JSON rooted at `OUTPUTS_DIR / "calib"`; optionally the two `.timestamps.csv` sidecars for free-run sync correction.
  - In-process call chain: `triangulate.load_calibration` + `load_stereo_annotations` + (optional) `load_timestamps`/`interpolate_pixel_at_time` → `triangulate_point` per frame → in-memory triangulated rows → `analyze_metric` (`load`-equivalent on the in-memory rows, `detect_cycles`, `aggregate`). Surface the calibration JSON's `validation` numbers (reprojection RMS, 3D error, EPP discrepancy) in a small header label so the operator sees calibration quality.
  - Embed a `FigureCanvasQTAgg` (copy the `_plot` idiom from `plot_dialog.py`): displacement-vs-time, and a 3D path or dx/dy/dz panel.
  - An **"Export CSV"** `QPushButton` → `QFileDialog.getSaveFileName` defaulted at `OUTPUTS_DIR`, writing the triangulated CSV in the documented schema (`frame_idx, x_mm, y_mm, z_mm, displacement_mm, dx_mm, dy_mm, dz_mm, phase`). **Guard against clobbering** existing `<avi>.stereo_annotations.csv` / sidecars; never auto-write (a prior auto-overwrite destroyed a real annotations CSV — see project memory).
  - **Lazy-import cv2/numpy/the tools at the top of the dialog's method, not at module import**, mirroring how `PlotDialog`/`LogDialog` are imported lazily in their handlers — keeps app startup fast and hardware-free.
- **`src/utils/config.py`** — add `CALIB_DIR = OUTPUTS_DIR / "calib"` (currently no such constant; `OUTPUTS_DIR`, `VIDEOS_DIR`, `RUN_LOG_PATH` exist but calib is referenced ad hoc).
- **`tests/test_analysis_dialog.py`** — per the project's "every new module has tests" rule. Test the *non-GUI* core: a small helper that, given a tiny synthetic annotations CSV + a real `stereo_calib_water.json`, returns triangulated rows + aggregate metrics. Write all synthetic inputs/outputs to **`tmp_path` / `/tmp`, never `outputs/`** (project memory rule; follow the `monkeypatch`-OUTPUTS_DIR pattern in `test_data_recorder.py`).

### Files to REUSE (no change, just import/follow)

- **`src/ui/plot_dialog.py`** — the structural template (QDialog + QFileDialog rooted at `OUTPUTS_DIR` + `FigureCanvasQTAgg` embed + dark-theme styling). Copy its shape.
- **`src/ui/log_dialog.py`** — template if you want a results *table* (e.g. per-cycle metrics in a read-only `QTableWidget`) alongside the plot.
- **`tools/triangulate.py`** — `load_calibration`, `load_stereo_annotations`, `load_timestamps`, `interpolate_pixel_at_time`, `triangulate_point` (window-free, importable).
- **`tools/analyze_metric.py`** — `load_triangulated_csv`, `Sample`, `Cycle`, `detect_cycles`, `cycle_period_ms`, `path_length_mm`, `peak_displacement_mm`, `aggregate` (window-free, importable).
- **`outputs/calib/stereo_calib_<fluid>.json`** — example calibration inputs (water + analog both present).

### Files to EDIT (minimal diff — exactly the Plot/Log pattern)

- **`src/ui/control_bar.py`** — add `analyze_clicked = Signal()`, create a `QPushButton("Analyze")` (reuse the existing `btn_style`, add it to the button loop), and `self._analyze_btn.clicked.connect(self.analyze_clicked)` alongside the other four connections.
- **`src/ui/main_window.py`** — in `__init__`, connect `control_bar.analyze_clicked` to a new `_on_analyze` slot that **lazily imports** `AnalysisDialog`, then `dlg = AnalysisDialog(self); dlg.exec()` — identical in shape to `_on_plot` / `_on_log`.

### Explicitly NOT in the first cut (deferred, documented)

- **In-app stereo annotation.** `annotate_stereo_point.py` is a native cv2 click-window. Reimplementing landmark-clicking inside a Qt widget is a separate, larger task. First cut consumes an already-saved annotations CSV. (A future second cut could add a Qt annotate widget.)
- **The uncommitted multi-point "tracks" workstream** (`track_intersections.py` et al.). It is parameter-sensitive, partly untested, and sits in tension with committed `CLAUDE.md` rules; do not wire it into the GUI until it is committed, documented (`docs/plans/`), and reconciled.
- **Recording valve runs *from the GUI* for serious CV.** `docs/TODO.md` records a ~7% frame-drop bug when recording from the PySide6 GUI vs ~0.17% headless. For analysis-quality captures, record with `tools/record_valve.py --dual` (split USB docks); the GUI is for monitoring/preview. The analysis dialog only *reads* recordings, so this does not block it.

### Optional later polish

- Wire the currently-unconnected `BaslerCamera.recording_finished(str)` signal to offer "Analyze this recording now?" — the hook already exists, it is just not connected to any GUI slot today.

---

## Appendix: Gotchas that affect integration

- **MJPG, not FFV1.** Valve recordings the pipeline consumes are MJPG/AVI `-q:v 2` (intra-only — fine for flow). Some `CLAUDE.md`/PRD text still says "lossless FFV1"; the *code* records MJPG. FFV1 survives only in `tools/record_calibration.py`.
- **Free-run sync is mandatory for accuracy.** Cameras are not hardware-triggered. Any stereo analysis must use the `.timestamps.csv` sidecars for temporal alignment (`triangulate.py` does this via `interpolate_pixel_at_time`). Omitting them does naive frame-N pairing and only warns.
- **Lens spec to trust:** Edmund **#33-304**, 16 mm UC Series, **EPP 10.68 mm** (matches the code and both calibration JSONs). A stale `#59-870 / 24.42 mm` line in `CLAUDE.md` is wrong — do not use 24.42 in any cross-check.
- **`config.py` camera constants are dead.** `CAMERA_FPS`/`CAMERA_EXPOSURE_US` are not read by `BaslerCamera` (it hardcodes `target_fps=30`/`exposure_us=25000`). Editing config won't change camera behavior.
- **Never auto-write to `outputs/`.** A user-driven Export is fine; any default/auto write risks clobbering real sidecars. Synthetic test data goes to `/tmp` only.
