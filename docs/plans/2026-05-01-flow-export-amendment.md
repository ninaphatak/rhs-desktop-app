# Flow Export Plan — Amendment: Drop Arduino FLOW as Ground Truth
_2026-05-01_

> Amends: `2026-04-20-flow-export-design.md`, `2026-04-20-flow-export-plan.md`.
> Effect: keeps the dataset exporter and most of the validation phase intact;
> removes Arduino FLOW comparisons and replaces them with HR-derived
> consistency checks.

## Reason

The Arduino FLOW sensor measures volumetric flow upstream of the valve, in a
section of pipe with a different cross-sectional area than the valve plane.
Once flow crosses the valve, the effective area changes and the relationship
between recorded FLOW and instantaneous leaflet motion is non-trivial — they
are not the same physical quantity expressed in different units. Treating
Arduino FLOW as ground truth for leaflet motion conflates two reference
frames and would either falsely validate (when both signals correlate due to
shared cyclic forcing from the pump) or falsely invalidate the pipeline.

This amendment removes that comparison everywhere it appears and replaces
the temporal-reconstruction metric with a check that does not depend on the
upstream FLOW reading.

## Frame rate correction (added 2026-05-01)

The original design doc cites a `flow_threshold_px = 1.5` default with a
working zone of 1.0–2.0 px/frame, derived from "expected 60 fps leaflet
kinematics." Recordings are actually at **30 fps**, so each frame covers
twice the elapsed time and the same physical leaflet motion produces
roughly twice the per-frame pixel displacement.

**Rescaled defaults for 30 fps:**

| Param | Original (60 fps assumption) | Rescaled (30 fps) |
|---|---|---|
| `flow_threshold_px` default | 1.5 | **3.0** |
| Working zone | 1.0–2.0 | **2.0–4.0** |

`tools/flow_explore.py` and `tools/flow_export.py` should both default to
3.0 px/frame. The exporter still stamps the value into HDF5 attrs, so older
60-fps datasets remain self-identifying.

If recordings later move back to 60 fps (or to any other rate), the
threshold should rescale linearly: `threshold_px ≈ 1.5 * (60 / fps)`.

## What stays the same

- HDF5 dataset schema (frames, masks, contours, flow sidecar)
- Donut ROI strategy
- Farneback params, CLAHE, morphology pipeline
- Annotation tooling (Task 9)
- Spatial IoU validation (Reconstruction §2)
- File layout, CLI design, tests for synthetic flow + mask geometry
- Handoff README structure

The amendment is scoped to validation methodology and framing language, not
to the export pipeline itself.

## Changes to design doc (`2026-04-20-flow-export-design.md`)

### Reconstruction validation §1 — REPLACE

The current §1 reads: *"Temporal reconstruction: flow-derived 'valve
open-ness' (mean flow magnitude in donut ROI, or total motion-mask area per
frame) vs the Arduino FLOW sensor signal. No annotation needed — Arduino CSV
is the ground truth. Metric: Pearson r, peak-timing offset in ms."*

**Replace with:** §1 — Phase-timing reconstruction. The valve cycle is
forced by the user-set HR (BPM). Expected leaflet cycle period =
60 / HR seconds. For each recording, extract the flow-derived motion signal
(mean magnitude in the donut ROI per frame, or total motion-mask area per
frame), compute its dominant period via FFT, and check that the period
matches the commanded HR within tolerance (target: ±5 %).

This is a *consistency* check, not a ground-truth check — it confirms the
pipeline recovers the cyclic motion the simulator was driving, without
treating the upstream FLOW reading as truth.

Optional secondary metric: hand-label a small set of frames (~10–20) as
{open, transitioning, closed} and check that the binary motion mask area
peaks during *transitioning* frames, where leaflets are physically moving,
rather than during steady open/closed phases.

### Reconstruction validation §2 — UNCHANGED

Spatial reconstruction (flow-derived contours vs hand-drawn leaflet
boundaries via IoU and centroid distance) does not depend on Arduino FLOW
and survives unchanged.

### Risks table — UPDATE first row

The first risk row currently mitigates "out-of-plane bowing → near-zero 2D
flow" with: *"Phase 0 sanity check: correlate donut-ROI mean flow magnitude
against Arduino FLOW channel on one recording. Gate the rest of the build
on r² ≥ 0.5."*

**Replace the mitigation with:** *"Sanity-check on first recording: visualize
the binary motion mask through one full cycle. If the leaflet region never
lights up during transitions, the pipeline is recovering only out-of-plane
motion and we pivot to threshold-based orifice segmentation (PRD §5.4)."*

Visual inspection replaces the regression gate. Subjective, but appropriate
given that Arduino FLOW is not a valid reference for what we are measuring.

### Framing language

Where the deliverable is described as a "valve flow rate proxy" or anything
implying the dataset measures volumetric flow, restate as "leaflet motion
dataset." Wording only — no schema impact.

## Changes to implementation plan (`2026-04-20-flow-export-plan.md`)

### Task 0 — REPLACE

Drop the r² ≥ 0.5 gate against Arduino FLOW. Replace with a 30-minute
visual spike:

1. Load one MP4 from `outputs/`.
2. Compute Farneback flow on a donut ROI with the new params
   (winsize=21, poly_n=7, poly_sigma=1.5, OPTFLOW_FARNEBACK_GAUSSIAN).
3. Render a binary motion mask with `flow_threshold_px = 1.5` over the
   whole clip.
4. Confirm by eye: does the mask region track the leaflets through
   open/close transitions? If yes, proceed to Task 1. If no, pivot to
   PRD §5.4 (threshold-based orifice segmentation).

This script remains a throwaway, do not commit. The new
`tools/flow_explore.py` (this branch) already produces an equivalent
visualization with the older Farneback params; updating it to the new
params is the only delta.

### Task 11 — REPLACE `arduino_flow_correlation`

Remove the function from `tools/_metrics.py`. Replace with:

```python
def cycle_period_seconds(
    flow_time_series: np.ndarray,
    fps: float,
) -> float:
    """Estimate dominant cycle period (seconds) of a flow-derived time series
    via FFT. Used to compare against commanded HR.
    """

def cycle_period_match_pct(
    measured_period_s: float,
    commanded_hr_bpm: float,
) -> float:
    """1 - |measured - 60/hr| / (60/hr). Closer to 1.0 = better match."""
```

Tests: synthetic sinusoid at known frequency → recovered period within 1 %.
Drop the in-phase / anti-phase correlation tests.

### Task 12 — UPDATE VALIDATION REPORT FIGURES

| Figure | Old | New |
|---|---|---|
| 1 | Heatmap: mean IoU across param grid | UNCHANGED |
| 2 | Heatmap: Arduino Pearson r across param grid | **Heatmap: cycle_period_match_pct across param grid** |
| 3 | Time-series overlay: flow-derived signal vs Arduino FLOW | **Time-series: flow-derived motion signal with HR-derived expected cycle period as vertical phase lines** |

`docs/validation_results.md` text adjusts: drop "Arduino correlation" as a
headline metric; lead with mean IoU + cycle-period match.

### Task 10 — PARAM SWEEP METRICS

`sweeps/summary.csv` columns change. Old:

```
param_hash, winsize, threshold, donut_outer, mean_iou,
arduino_pearson_r, median_centroid_err_px
```

New:

```
param_hash, winsize, threshold, donut_outer, mean_iou,
median_centroid_err_px, cycle_period_match_pct
```

### Build sequence summary — UPDATE PHASE 0

| Phase | Tasks | Gate (new) |
|---|---|---|
| 0 | Visual spike (revised Task 0) | Mask tracks leaflets through one cycle, by eye |

Phases 1–8 are otherwise unchanged. The validation deliverable in Phase 7
swaps the Arduino metric for the HR-derived metric; everything else holds.

## Effect on the research framing

Old framing: *"validated optical flow pipeline for tricuspid valve motion
tracking, with parameter-sensitivity analysis and hand-annotated ground
truth, plus correlation against the simulator's flow sensor."*

New framing: *"validated optical flow pipeline for tricuspid valve leaflet
motion, with parameter-sensitivity analysis, hand-annotated spatial ground
truth, and cycle-period consistency against the commanded heart rate."*

The deliverable is still a research contribution. The honesty improves: we
no longer claim the dataset corresponds to volumetric flow at the valve,
which it does not.
