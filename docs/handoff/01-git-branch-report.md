# Git Branch Report — RHS Monitor (Handoff)

> **Audience:** the maintainer, Dr. Lee (sponsor), and incoming students.
> **Generated:** 2026-05-30, read-only via `git log` / `git rev-list` / `git merge-base`.
> **All ahead/behind counts are relative to `main`** (`git rev-list --count main..<branch>` for ahead, `<branch>..main` for behind). Dates are last-commit author dates.

---

## TL;DR — read this first

- **`feature/flow-export` is the CANONICAL, live branch.** It is the current `HEAD`, the most recently worked branch (last commit **2026-05-14**, tip `fb87367`), and the **only** branch carrying the headline computer-vision (CV) deliverable — per-frame metric (mm) leaflet displacement via stereo calibration + triangulation, plus all the dual-camera recording wired into the GUI.
- **`main` is essentially the pre-CV application.** It has **no `tools/` directory at all** — none of the stereo calibration, triangulation, annotators, `markers.csv`, or CV design docs exist on it. It is the read-only sensor-monitoring app as it stood before any CV work began.
- **The gap is large and goes both ways:** `feature/flow-export` is **+66 / −44** versus `main`. It is 66 commits ahead (the entire CV pipeline) and 44 commits behind (the entire app/sensor evolution that landed on `main` separately). The two histories split at a single common ancestor and never reconverged.
- **A second, working CV pipeline is uncommitted.** The multi-point "tracks" workstream (auto-tracking valve intersection corners → 3D) lives entirely as untracked files and is invisible to anyone reading git history.
- **The branch name is a misnomer.** `flow_export.py` was killed; the dense-flow framing the branch is named for is dead. The real work on this branch is metric displacement.

---

## 1. Recency-ordered branch table

Newest last-commit first. "Theme" is a one-line summary of what the branch carries.

| Branch | Last commit | Ahead / Behind `main` | Status | Theme |
|---|---|---|---|---|
| **`feature/flow-export`** *(current HEAD, `fb87367`)* | **2026-05-14** | **+66 / −44** | **CANONICAL — live CV branch; NOT merged** | The complete metric (mm) leaflet-displacement CV pipeline + dual-camera recording in the GUI |
| `feature/dual-camera-h264` *(`8246cb2`)* | 2026-04-28 | +47 / −0 | Stale — dead-end, superseded | Abandoned H.264/MP4 dual-camera recording experiment |
| **`main`** *(`0af60f6`)* | 2026-04-27 | *(baseline)* | Active app/sensor trunk — **pre-CV app** | Read-only sensor monitor: serial, graphs, CSV, run log, review dialog |
| `feature/pressure-peak-labels` *(`888664e`)* | 2026-04-26 | +0 / −3 | Merged (PR #17, #18) — safe to delete | Pressure peak/trough analysis in `view_csv.py` |
| `feature/optical-flow` *(`ab2fbdb`)* | 2026-04-17 | +11 / −44 | Stale — fully contained in flow-export | Genesis of the CV work (dense flow + LK prototype + recording) |
| `origin/feature/peak-trend-fit` *(`787a1e7`)* | 2026-04-15 | +1 / −10 | Stale — 1 orphan unmerged commit | Plots for flow-rate (FR) CV calculations |
| `feature/timer` *(`0ad37e9`)* | 2026-04-11 | +0 / −20 | Merged (PR #10, #12) — safe to delete | Recording stopwatch + lap tracking + param-to-graph selection |
| `origin/feature/record_videos_inUI` *(`05eae5e`)* | 2026-04-09 | +0 / −27 | Merged (PR #8, #9) — safe to delete | In-UI synced camera recording + ReviewDialog + flow-sensor integration |
| `origin/fix/temp-remove-FR` *(`4fb48a0`)* | 2026-03-08 | +8 / −51 | Stale demo branch — archive/delete | One-off demo removing the flow-rate channel |

**Critical structural fact.** The repo split into two parallel lineages off the same pre-CV commit `0684791` ("Fix graph axis label color to white", 2026-03-08) and **never merged back together**:

1. **CV lineage** — `feature/optical-flow` → `feature/flow-export` (with a dead sibling `feature/dual-camera-h264`). Carries the entire computer-vision pipeline.
2. **App/sensor lineage** — `main`, fed by merged PRs from `feature/timer`, `feature/record_videos_inUI`, `feature/pressure-peak-labels`, `feature/peak-trend-fit`. The GUI / sensor-monitoring / CSV-analysis track.

Because they share only the ancestor `0684791`, `feature/flow-export` is simultaneously **66 ahead and 44 behind** `main`.

---

## 2. Narrative — how the CV pipeline evolved on `feature/flow-export`

This is the chronological story of the CV work, told through the real commit subjects on the branch. It begins on the predecessor branch `feature/optical-flow` (every one of whose commits is already contained in `feature/flow-export`) and continues on `feature/flow-export` itself.

### Phase 0 — Genesis: pixel-space optical flow (`feature/optical-flow`, Apr 2026)
The CV work started as a pixel-displacement effort. The earliest commits added a dense optical-flow explorer plus the valve-calibration tools (`aa2445d`), a Basler recording script (`8376142`), a Lucas-Kanade (LK) leaflet-tracking prototype (`cc8bc05`), and a first switch from MJPG to H.264 recording (`ab2fbdb`). The LK prototype (`tools/leaflet_flow_test.py`) **failed** on the textureless white silicone leaflet (the aperture problem + no inked features), which became the project's recurring lesson and the reason a human-in-the-loop annotator and, later, an anchor-based tracker were needed. `git rev-list --count feature/flow-export..feature/optical-flow` = **0**, so this entire phase already lives inside `feature/flow-export`.

### Phase 1 — The pivot to metric (mm) displacement (2026-05-08)
After a meeting with Dr. Lee, metric millimeter displacement became a **hard requirement**, and the deliverable pivoted from pixel displacement to true 3D. This is the densest day of work on the branch:

- `f6eb753` — *Fix calibrateCamera, add load/edit/autosave to stereo_calibrate* (resumable, crash-safe calibration).
- `dad0009` — *Constrain stereo calibration to physical lens parameters* (fix focal length + principal point; let only k1/p1/p2 fit).
- `b8e3882` — *Log first water calibration result + tilt validation* (the validated water calibration: 0.154 mm median / 0.431 mm max 3D error; recovered camera tilt 18.30° vs CAD 19.33°).
- `143ecf1` — *Replace stale '30°' with '19.3°' in active CV docs.*
- `8994b4a` — *Update historical flow-export docs + add k1+tangential to calibration.*
- `ebcaf87` — *Add metric pipeline: stereo annotator, triangulator, analyzer* (`annotate_stereo_point.py`, `triangulate.py`, `analyze_metric.py` — Stages 3–5 of the pipeline).
- `eec9195` — *Add markers.csv with CAD-derived calibration object geometry* (the 41-marker calibration object).
- `85edcb1` — *Update CLAUDE.md + PRD build state for completed metric pipeline.*

By the end of 2026-05-08 the headline 5-stage pipeline existed and the water calibration was validated.

### Phase 2 — Recording-format experiments + GUI wiring + sync correction (2026-05-09)
With the math in place, the focus moved to getting clean, time-alignable dual-camera footage into and out of the GUI:

- `2299c9c` — *Switch recording from lossless FFV1 to MJPG for sync-friendly capture* (FFV1 was too slow per frame; MJPG is intra-only/"visually lossless" — note this means valve clips are technically MJPG, not the "lossless FFV1" the docs still claim).
- `b02c585` — *Add temporal interpolation to triangulate for free-run sync correction* (the cameras free-run, not hardware-triggered; this aligns cam1 to cam0 by timestamp).
- `4d02301` — *Add timestamp + metadata sidecars to GUI recording path.*
- `11d0d5e` — *Wire UI Record button to dual-camera AVI recording + GIL throttle.*
- `b8ad942` — *Switch ffmpeg output pixel format from deprecated yuvj420p.*
- `2b22ab7` — *Add tools/playback_stereo_annotations.py for dual-camera playback + metric.*

### Phase 3 — Dual-camera metric visualization + a true-3D detour (2026-05-09 → 05-10)
- `986e63e` — *Convert flow_explore to dual-camera metric (mm) visualization.*
- `2c8652d` — *Color flow_explore overlays by object-frame xy axes.*
- `9f5636a` — *Bring record_valve.py to GUI parity + add headless --dual mode* (the `--dual` headless recorder that became the on-ramp for the tracks workstream).
- `73194b0` — *Replace in-plane projection with dense stereo + flow for true 3D* — an attempt at per-pane dense-stereo disparity (StereoSGBM) + flow for genuine 3D motion.
- `ec3876a` — *Revert "Replace in-plane projection with dense stereo + flow for true 3D"* — **reverted the same day.** It was only smoke-tested on synthetic frames and rejected in favor of the sparse approach. (Dense flow on the leaflet interior is also on the project's "do not build" list.)

### Phase 4 — Tip (2026-05-14)
- `fb87367` — *Auto-scale exposure and gain with --fps in record_valve.py* — the current `HEAD`. **Because of the revert in Phase 3, the dense-stereo experiment is NOT present at the tip** — do not assume dense-stereo flow is on the branch.

---

## 3. CANONICAL branch statement — and how far behind `main` is

> ### `feature/flow-export` is the canonical, live branch. It carries the algorithm and the GUI work. `main` is the pre-CV app and is far behind.

**Why `feature/flow-export` is canonical:**
- It is the current `HEAD` and the most recently committed branch in the repo (**2026-05-14**, tip `fb87367`).
- It is the **only** branch that carries the headline metric-displacement CV pipeline that `CLAUDE.md` and the PRD describe as the deliverable.
- It carries the GUI ↔ CV bridge: the Record button wired to dual-camera AVI capture with per-frame timestamp + metadata sidecars (`11d0d5e`, `4d02301`).

**How far behind `main` is — quantified:**
- `feature/flow-export` is **+66 / −44** versus `main`. The **66 ahead** commits are the entire CV deliverable. The **44 behind** commits are the entire app/sensor evolution on `main` that was never pulled into the CV branch.
- `main` is **essentially the pre-CV app**: it has **no `tools/` directory at all** and is missing every CV artifact, concretely:
  - **Stereo calibration:** `tools/stereo_calibrate.py`, `markers.csv`, the calibration-model work (`c7c8b44`, `6344f6f`, `dad0009`, `f6eb753`, `8994b4a`, `b8e3882`).
  - **Metric pipeline:** `tools/annotate_stereo_point.py`, `tools/triangulate.py`, `tools/analyze_metric.py`, `tools/playback_stereo_annotations.py` (`ebcaf87`, `b02c585`, `2b22ab7`).
  - **Flow / recording tooling:** `tools/flow_explore.py`, `record_calibration.py`, `record_valve.py`, `record_debug.py`, and the single-camera pixel-validation tools.
  - **GUI dual-AVI wiring** with timestamp/metadata sidecars (`986e63e`, `2c8652d`, `11d0d5e`, `4d02301`).
  - **All CV design docs** under `docs/plans/2026-04-20+`.
- Conversely, `feature/flow-export` is missing the **44** app/sensor commits on `main`: the recording stopwatch / lap tracking, the in-UI video ReviewDialog, the Arduino flow-sensor firmware integration, the "New Pressure Sensor" work (`9be21ab`), pressure peak/trough analysis, and the multi-CSV flow-CV comparison tool.

**Bottom line:** treat `feature/flow-export` as the source of truth for CV. Treat `main` as the pre-CV application trunk. Do not assume `main` contains anything CV-related — it does not.

---

## 4. Uncommitted work and the reverted experiment

### 4a. The "tracks" workstream — WORKING, but entirely UNCOMMITTED

There is a **second, parallel CV pipeline** that the committed docs do not describe. Where the committed pipeline triangulates a **single manually-labeled** landmark, the tracks workstream **automatically tracks MULTIPLE inked valve "intersection" corners over time** across both cameras, triangulates each into 3D mm per frame, and analyzes/visualizes them — including correlating against Arduino pressure/flow. It builds directly on the committed `tools/triangulate.py` and the committed `stereo_calib_<fluid>.json` calibrations.

**Tracker design (the technical heart, `tools/track_intersections.py`):** explicitly **not** plain LK. It is a hybrid — **LK as a search prior, NCC against a never-updated frame-0 anchor patch as the actual measurement**. If a camera's NCC peak drops below threshold the track is marked lost from that frame on ("lose loudly, never recover silently"). This frame-0 anchor is the deliberate anti-drift mitigation and is what distinguishes it from the naive fiducial-tracking that the project rules warn against.

**Status — every file (git `??` untracked) except one modified tracked file:**

| File | Status |
|---|---|
| `tools/_tracks.py` | WORKING / mature — shared CSV spine, unit-tested |
| `tools/track_intersections.py` | WORKING — primitives unit-tested (incl. anti-drift + loss-detection); `main()` orchestration untested; parameter-sensitive |
| `tools/pick_track_seeds.py` | WORKING (interactive, untested) |
| `tools/playback_tracks.py` | WORKING (interactive, untested) |
| `tools/analyze_tracks.py` | WORKING (untested) — FFT cycle-period + per-point metrics |
| `tools/splice_manual_into_tracks.py` | WORKING but most fragile — manual repair of lost tracks; untested interpolation/origin logic |
| `tools/analyze_pressure_vs_tracks.py` | WORKING / **exploratory** — P2/Flow vs displacement (NOTE: flow correlation is explicitly NOT a sanctioned validation gate) |
| `tools/plot_calibration_error.py` | WORKING presentation script — requires BOTH water and analog calibration JSONs |
| `tools/plot_calibration_geometry_3d.py` | WORKING presentation script |
| `tests/test_tracking.py` | WORKING — **17 tests, all pass** (`17 passed`) |
| `tools/annotate_stereo_point.py` | **MODIFIED** (the one tracked file changed) — retrofitted with `--step` sparse labeling + `--output` + yellow/red carry-forward to feed `splice_manual_into_tracks.py` |

It also carries four **untracked** documentation files that are the best onboarding material in the repo: `docs/metric_displacement_mathematics.md` (primary primer), `docs/calibration_to_displacement_walkthrough.md`, `docs/backup_slides_math_and_algorithm.md`, and `docs/TODO.md` (which documents a real ~7% GUI frame-drop bug).

**Why it is uncommitted (most likely):**
1. **Process lag, not abandonment.** The code works (passing tests, real end-to-end artifacts across multiple recordings, an 8-point spliced output), but the project's "feature isn't done until docs are updated + `finishing-a-development-branch` runs" ritual has not happened. There is no `docs/plans/*tracking*` design doc.
2. **It sits in tension with committed guidance.** `CLAUDE.md` lists "Dot tracking / fiducial markers on the valve" and Arduino flow correlation under "What NOT to Build." Committing it requires reconciling the framing (the frame-0 NCC anchor is the mitigation; the pressure correlation is exploratory eyeballing, not a gate).
3. **The branch is misnamed.** The work outgrew `feature/flow-export` and likely wants a freshly named branch.

**Also new and undocumented:** an **analog (35% glycerin) calibration now exists** (`outputs/calib/stereo_calib_analog.json`, added 2026-05-10: median 0.131 mm / max 0.500 mm; cam0 EPP discrepancy **14.42 mm**, only just inside the 15 mm gate). `CLAUDE.md` still documents only the first water calibration and the PRD still marks analog calibration as pending.

### 4b. The reverted "dense stereo + flow" experiment

On 2026-05-10 the author tried a true-3D approach — per-pane dense stereo (rectify both cameras → `cv2.StereoSGBM` disparity → `reprojectImageTo3D`) plus Farneback flow, sampling the 3D field at flowed coordinates for per-pixel 3D displacement. It was added in `73194b0` and **reverted the same day in `ec3876a`**, having only been smoke-tested on synthetic frames. The author rejected it in favor of the sparse hybrid LK+NCC tracker.

**Consequence for the tip:** because of the revert, `fb87367` does **not** contain the dense-stereo experiment. Do not resurrect it expecting it to work, and do not assume dense-stereo flow is present on the branch.

---

## 5. Cleanup / merge / archive recommendation

### Canonical branch
Treat **`feature/flow-export`** as the source of truth for CV. Everything else is either merged-and-stale, a dead-end, or the pre-CV trunk.

### Before anything else (commit the at-risk work)
The tracks workstream and the four math/onboarding docs are **untracked** and would be lost on a bad `git clean` or a fresh clone. Before any merge:
1. Create a correctly named branch off `feature/flow-export` — e.g. **`feature/stereo-tracking`** or **`feature/metric-displacement`** (the `flow-export` name is vestigial; `flow_export.py` was intentionally killed and is absent).
2. Commit the 9 tracks tools + `tests/test_tracking.py` + the modified `annotate_stereo_point.py` + the 4 untracked docs.
3. Write `docs/plans/2026-05-xx-tracking-design.md` and update `CLAUDE.md`/PRD to (a) describe the multi-point tracker as the successor pipeline, (b) reconcile it with the "no valve dot tracking" rule (frame-0 NCC anchor is the mitigation), and (c) mark `analyze_pressure_vs_tracks.py` as exploratory, not a validation gate.
4. Flip PRD §12 "Analog calibration" from pending to done and add the analog numbers (flagging the thin 14.42 mm cam0 EPP margin).

### Reunify the two lineages (the integration debt)
`feature/flow-export` is **44 commits behind** `main`. To reunify:
1. **Merge `main` INTO `feature/flow-export` first** to pick up the 44 app/sensor commits and surface conflicts in a safe place.
2. **Expect conflicts in `src/core/basler_camera.py` and recording code** — all three lines independently evolved camera recording (`main` → MJPG/AVI + ReviewDialog; the h264 fork → H.264/MP4; `feature/flow-export` → FFV1 then MJPG).
3. Then open a PR of the reconciled branch back to `main`.

### Delete (fully merged — no unique commits)
- `feature/timer` (PR #10, #12)
- `origin/feature/record_videos_inUI` (PR #8, #9)
- `feature/pressure-peak-labels` (PR #17, #18)

### Delete or archive (stale / dead-end)
- `feature/dual-camera-h264` — abandoned H.264 experiment; the canonical line reverted H.264 in favor of intra-only recording. Its `+47/−0` count is misleading (its merge-base is `main`'s tip, but it skipped the optical-flow CV work entirely).
- `feature/optical-flow` — **0 unique commits** vs `feature/flow-export` (`git rev-list --count feature/flow-export..feature/optical-flow` = 0). Deleting it loses nothing; retain only as a tag if historical reference is wanted.
- `origin/fix/temp-remove-FR` — obsolete demo branch (51 behind, never merged).

### Decide (one orphan commit)
- `origin/feature/peak-trend-fit` — has exactly one unmerged commit, `787a1e7` "plots for FR CV calculations". **Cherry-pick it onto `main`** if the FR-CV plots are wanted; otherwise delete.

### Footnotes for whoever does the merge
- `main` has **no `tools/`** — there is nothing CV to conflict with there; conflicts will be in `src/`.
- The root sample `.mp4` files are gitignored and **will not survive a fresh clone**.
- `arduino/rhs_firmware.ino` is a hand-synced **mirror**, not the flashed source — editing it does not change device behavior.

---

## Appendix — verification commands (run 2026-05-30)

```
$ git log -1 --format='%H %ci %s' fb87367
fb8736723025bc7755237ffe001f21ae9726c9da 2026-05-14 10:29:55 -0700 Auto-scale exposure and gain with --fps in record_valve.py

$ git rev-list --count main..feature/flow-export      # ahead
66
$ git rev-list --count feature/flow-export..main      # behind
44
$ git merge-base main feature/flow-export
06847911eeb2a78c3055e04da307e05a80fea738
```
