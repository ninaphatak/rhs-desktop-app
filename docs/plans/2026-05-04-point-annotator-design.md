# Point Annotator + Cycle CV Analysis — Design

_2026-05-04_

> Amends: `2026-04-20-flow-export-design.md`, `2026-04-20-flow-export-plan.md`,
> `2026-05-01-flow-export-amendment.md`.
>
> Effect: replaces the polygon-annotator + IoU + cycle-period-FFT validation
> with a single-point + per-frame-phase annotator. Output enables three
> downstream metrics: dense-flow point-tracking accuracy, CV of cycle period,
> CV of per-cycle landmark displacement.

## Why

The earlier validation plan tried to characterize the *whole valve* from
the dense flow field — IoU between flow-derived contours and hand-drawn
leaflet polygons, and FFT period-match against commanded HR. Both metrics
are coarse and neither tells us how well dense optical flow tracks an
*identifiable physical landmark* over time.

The new validation framing: pick one anatomical landmark on a leaflet,
manually label its pixel position frame-by-frame, and label the cardiac
phase {open, opening, closing, closed} of every annotated frame. From that
sparse-but-honest ground truth we get:

1. **Dense-flow point-tracking accuracy** (per-frame error between manual
   displacement and Farneback flow vector at the manual point).
2. **CV of cycle period** across cycles in one recording (rhythm regularity).
3. **CV of per-cycle landmark displacement** across cycles (kinematic
   regularity of one identifiable point on the valve).

This is the deliverable now: a *validated point-tracker accuracy number*
plus a *cardiac-cycle reproducibility characterization*. No orifice-area
proxies, no flow-rate analogues — just leaflet kinematics.

## What stays / what drops

**Stays from the existing design (`2026-04-20-flow-export-design.md`):**
- HDF5 dataset schema and the dense-flow exporter (Tasks 1–8 of the plan)
- Donut ROI strategy at the orifice boundary
- Farneback params, CLAHE, morphology pipeline
- Per-frame motion mask in HDF5 (still useful as a sanity-check overlay)

**Drops:**
- Polygon annotator `tools/annotate_leaflets.py` (Task 9 — never built;
  remove from plan)
- Spatial IoU validation (Reconstruction §2 in the design doc)
- Cycle-period FFT consistency check (amendment §1, §Task 11)
  including `_metrics.cycle_period_seconds` and
  `_metrics.cycle_period_match_pct`
- Motion-mask-area "valve open-ness" signal as a validation metric
  (this conflates with the orifice-area framing the user has rejected)
- Param sweep + validation-report (Tasks 10, 12) **deferred**, not killed.
  Revisit after the first annotated session — the new metrics may suggest
  a different sweep target than mean IoU.

The exporter itself is unchanged. This pivot is entirely on the validation
side of the workstream.

## Components

### 1. Annotator — `tools/annotate_point.py`

CLI:
```
python tools/annotate_point.py path/to/recording.mp4
```

Auto-resumes from `recording.annotations.csv` next to the video if it exists.

**Per-frame state:** one tracked landmark `(x, y)` and one phase label
∈ {open, opening, closing, closed}. Frames the user skips have no row in
the output — the CSV is sparse.

**Window:** single OpenCV window, matches the style of
`tools/flow_explore.py`. No Qt dependency.

**Controls:**

| Key / event | Action |
|---|---|
| Left-click | Set landmark at click position on current frame |
| `1` / `2` / `3` / `4` | Set phase to open / opening / closing / closed |
| `→` or `d` | Step forward one frame |
| `←` or `a` | Step backward one frame |
| `u` | Undo current frame's annotation (clear point + phase) |
| `s` | Save annotations CSV |
| `q` | Quit (prompts to save if there are unsaved changes) |

**Display overlay (top-left of frame):**
- Frame counter `Frame f / F`
- Phase label of current frame, e.g. `phase=opening`, blank if unlabeled
- `unsaved *` indicator if dirty

**Annotation visualization:**
- Red filled circle (radius 4 px) at the labeled landmark on each frame
- Optional: light gray polyline connecting recent annotated points (last
  ~30 frames) so the trajectory is visible while the user labels —
  helps spot drift.

**Output schema** (CSV, one row per annotated frame):
```
frame_idx,point_x,point_y,phase
12,412,305,opening
13,414,308,opening
14,418,312,open
...
```

- Header is required.
- `phase` ∈ {open, opening, closing, closed}.
- Frame indices are strictly increasing (sparse OK; no duplicates).
- Saved alongside the input video (same basename, `.annotations.csv`
  suffix).

**Constraint: same anatomical landmark across the entire video.**
The annotator does not enforce this — it's the user's responsibility — but
the analysis script assumes it. Switching leaflets mid-video would corrupt
per-cycle CV calculations.

**Implementation notes:**
- Read frames lazily via `cv2.VideoCapture`; cache the current and adjacent
  frames in memory only. The full video is not preloaded.
- Mouse-click coordinates need to be inversely transformed if the displayed
  frame is letterboxed/scaled to fit the screen — keep the display 1:1
  with frame pixels for the first version (skip the scaling code path).
- Keep the file under ~250 lines.

### 2. Analysis — `tools/analyze_annotations.py`

CLI:
```
python tools/analyze_annotations.py path/to/recording.annotations.csv \
    [--video path/to/recording.mp4] \
    [--fps 30]
```

Two modes, gated by the presence of `--video`:

**Mode A — annotations-only (default).** Compute cycle metrics from the
phase labels and point coordinates. Does not touch the video.

**Mode B — annotations + video.** Additionally compute Farneback dense
flow at each annotated point and report point-tracking accuracy. Requires
the source MP4.

**Mode A outputs:**
- Cycle detection: a "cycle" is one complete pass through phase states
  in the order `closed → opening → open → closing → closed`, both
  endpoints `closed` frames. The cycle starts at the *last* `closed`
  frame before the first `opening`, and ends at the *first* `closed`
  frame after the trailing `closing`. The end frame of cycle N is the
  start frame of cycle N+1.
  - Frames before the first cycle-start `closed` are ignored.
  - Frames after the last cycle-end `closed` are ignored (incomplete
    trailing cycle dropped).
  - A cycle missing any of the four phase tokens, or where tokens occur
    out of order (e.g., `opening → closing` without `open` in between),
    is reported as `n_cycles_incomplete` and excluded from CV
    aggregates.
- Per cycle:
  - `cycle_period_frames` (last frame index − first frame index)
  - `cycle_period_ms` (period_frames / fps × 1000)
  - `path_length_px` (sum of per-step Euclidean distances between
    consecutive annotated points in the cycle)
  - `peak_displacement_px` (max distance between any annotated point in
    the cycle and the cycle-start point)
- Aggregate across `N` complete cycles:
  - mean, std, **CV = std / mean** for `cycle_period_ms`
  - mean, std, **CV = std / mean** for `peak_displacement_px`
  - `n_cycles_complete`, `n_cycles_incomplete`

**Mode B additional outputs:**
- For each consecutive pair of annotated frames `(f_i, f_{i+1})` where
  both rows exist:
  - Compute Farneback flow on `(frame_{f_i}, frame_{f_{i+1}})`
    (full-frame, not just donut ROI — we need flow at the landmark, not
    just at the orifice boundary; one-off CV cost is fine).
  - Sample the flow vector at `(point_x_i, point_y_i)` via bilinear
    interpolation.
  - Manual displacement: `Δp = point_{i+1} − point_i`.
  - Per-pair error: `||flow_at_point − Δp||₂` in pixels.
- Aggregate: `median_error_px`, `p95_error_px`, `n_pairs`.
- Caveat: if `f_{i+1} − f_i > 1` (sparse annotation), the manual
  displacement spans multiple frames and Farneback (single-step) is not
  directly comparable. Skip such pairs and report
  `n_pairs_skipped_nonconsecutive`.

**Output:** print a human-readable summary to stdout, and write a sidecar
`recording.analysis.json` with the same data structured for downstream
plotting.

**Visualization (Mode B, optional `--plot` flag, scope-deferred):**
plot manual `(x, y)` trajectory and Farneback-integrated trajectory on
the same axes, plus the per-frame error time series. Not in v1.

## Plan amendments (succinct)

This section will be transcribed into `2026-04-20-flow-export-plan.md` as
amendments when the implementation plan is written.

| Plan task | Status under this design |
|---|---|
| Tasks 1–8 (exporter + tests + docs) | Unchanged |
| Task 9 (polygon annotator) | **Removed from plan**; superseded by `tools/annotate_point.py` |
| Task 10 (param sweep) | **Deferred**, retain in design as future work |
| Task 11 (`_metrics.py`) | **Removed**; cycle-period FFT helpers no longer needed. Cycle metrics live in `tools/analyze_annotations.py` |
| Task 12 (validation report) | **Deferred** until first annotated session yields data |
| _new_ Task 9' | Build `tools/annotate_point.py` |
| _new_ Task 10' | Build `tools/analyze_annotations.py` (Mode A) |
| _new_ Task 11' | Extend `tools/analyze_annotations.py` with Mode B (Farneback comparison at annotated points) |

Detailed task breakdown deferred to the implementation plan.

## Tests

Per the project rule (CLAUDE.md §Testing Requirements):

- `tests/test_annotate_point.py` — synthetic annotation dict round-trips
  through CSV save/load. Verify header, sparse rows, sorted frame_idx,
  rejection of malformed phases on load. **No GUI test.**
- `tests/test_analyze_annotations.py` —
  - Construct synthetic annotation rows with a known phase sequence and
    known cycle period (e.g., 30 frames per cycle × 4 cycles). Assert
    recovered period CV is `0` to within float tolerance.
  - Construct synthetic point trajectory of a unit-circle motion with
    radius 5 px. Assert recovered `peak_displacement_px ≈ 10`.
  - Mode B: pre-computed flow field that matches the manual displacement
    exactly → median error == 0. Then perturb flow by a known offset →
    error == ‖offset‖.

## Out of scope (explicit)

- Auto-tracking the landmark across frames (KLT, etc.). Manual is the
  point — manual labels are the ground truth, not a labor problem to
  solve.
- Multi-landmark annotation (3 leaflets). Reconsider only if the
  single-landmark study yields a tight enough CV that we want
  inter-leaflet comparisons.
- Statistical hypothesis tests on CV (e.g., is CV significantly
  different from baseline X?). Reporting raw CVs is sufficient for the
  Dr. Lee handoff.
- Live overlay of the dense-flow field inside the annotator window.
  `tools/flow_explore.py` already does that; running them side-by-side
  on the same MP4 covers the use case.

## File layout

```
tools/
  annotate_point.py        (new)
  analyze_annotations.py   (new)
tests/
  test_annotate_point.py        (new)
  test_analyze_annotations.py   (new)
```

No changes to `src/`. The CV pipeline stays offline, in `tools/`.

## Dependencies

Already in `rhs-app` env: `cv2`, `numpy`, `pandas` (used elsewhere in the
project). No new deps. The annotator and analyzer use only `cv2`,
`numpy`, `csv` (or `pandas`), and `argparse`.
