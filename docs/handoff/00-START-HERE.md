# RHS Monitor — Handoff & Onboarding Package

> Single entry point for handing this project to a new maintainer / researcher
> taking over the codebase. Generated from a full read of `src/`, `tools/`, all
> git branches, and the docs.

## What is this project?

**RHS Monitor** is a PySide6 desktop app for the **Right Heart Simulator** — a
cardiovascular training device that simulates post-Fontan hemodynamics. The app
does **read-only** monitoring: it reads a 7-field Arduino sensor stream
(pressures, flow, heart rate, temperatures), previews two Basler cameras, and
records both to disk on demand. The headline research deliverable is **offline**:
a computer-vision pipeline that measures, in **millimeters**, how far the
silicone valve leaflets move during each cardiac cycle, by triangulating points
across the two calibrated cameras.

## Read these in order

| # | Document | What it answers |
|---|----------|-----------------|
| **00** | this file | What's here and where to start |
| **01** | [`01-git-branch-report.md`](01-git-branch-report.md) | Which branch is canonical (`feature/flow-export`), how branches relate, what to merge/delete |
| **02** | [`02-gui-architecture-and-integration.md`](02-gui-architecture-and-integration.md) | How the GUI is wired (threads, signals, data flow) and how to integrate the CV pipeline into a data-extraction tool |
| **03** | [`03-cv-and-optical-flow-primer.md`](03-cv-and-optical-flow-primer.md) | Optical flow from scratch, the stereo-calibration → triangulation math, the multi-point "tracks" work, and a glossary |
| **05** | [`05-handoff-readiness-and-drift.md`](05-handoff-readiness-and-drift.md) | Pre-handoff checklist: every place `CLAUDE.md`/PRD have drifted from the code, prioritized P0→P2 |

## The 60-second status

- **Canonical branch:** `feature/flow-export`. It carries the entire CV pipeline
  and the dual-camera GUI recording. `main` is the **pre-CV app** and is
  `+66/−44` divergent (it has no `tools/` directory at all). Reconciling the two
  is the main outstanding integration task — see doc 01.
- **The metric (mm) deliverable works.** Stereo calibration is validated for
  **both** working fluids — water (median 3D error 0.154 mm) and 35% glycerin
  analog (0.131 mm). Sub-millimeter accuracy; the hard requirement (metric, not
  pixel, displacement) is met.
- **Two CV pipelines exist.** (1) The single-landmark stereo
  triangulation pipeline (`stereo_calibrate` → `annotate_stereo_point` →
  `triangulate` → `analyze_metric`). (2) A multi-point **"tracks"** workstream
  that auto-tracks valve intersection corners over time with a frame-0 NCC
  anchor to resist drift (`track_intersections`, `pick_track_seeds`,
  `playback_tracks`, `analyze_tracks`, `splice_manual_into_tracks`; 17 passing
  tests in `tests/test_tracking.py`). The richest math docs in the repo
  (`docs/metric_displacement_mathematics.md`,
  `docs/calibration_to_displacement_walkthrough.md`) document this work.
- **Hardware-free development works.** `bash run.sh --mock` runs the GUI on
  recorded data; the offline tools run on sample videos. The whole CV learning
  surface is hardware-free.

## Before handing it off (short version of doc 05)

1. **Reconcile `feature/flow-export` with `main`** so a single branch carries the
   complete project (the CV pipeline + the pressure/UI work merged into `main`).
2. **Fix the factual drifts in `CLAUDE.md`/PRD** flagged in doc 05 (lens spec and
   recording-format details). These are map-vs-territory fixes; they don't block
   running the app or the tests.
