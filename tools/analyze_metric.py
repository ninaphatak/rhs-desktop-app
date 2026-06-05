"""Cycle-based metric analysis of a triangulated landmark trajectory.

Consumes the output of `tools/triangulate.py` (per-frame XYZ + phase) and
computes cardiac-cycle metrics in millimeters:

  - cycle period (ms), CV across cycles
  - 3D path length per cycle (mm), CV
  - peak 3D displacement per cycle (mm), CV
  - cycle counts (complete vs incomplete)

A "cycle" is one complete pass through phase tokens
{closed -> opening -> open -> closing -> closed}, both endpoint `closed`
frames. Same cycle-detection logic as tools/analyze_annotations.py
(pixel-mode), just operating on 3D positions instead of pixels.

Usage:
    python tools/analyze_metric.py TRIANGULATED_CSV [--fps 30]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


PHASE_SEQUENCE = ("closed", "opening", "open", "closing", "closed")


@dataclass
class Sample:
    frame_idx: int
    xyz: np.ndarray
    phase: str


@dataclass
class Cycle:
    samples: list[Sample]   # all samples within the cycle, in time order


def load_triangulated_csv(path: Path) -> list[Sample]:
    rows: list[Sample] = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            xyz = np.array([float(r["x_mm"]), float(r["y_mm"]), float(r["z_mm"])],
                           dtype=np.float64)
            rows.append(Sample(frame_idx=int(r["frame_idx"]),
                               xyz=xyz,
                               phase=r.get("phase", "").strip()))
    rows.sort(key=lambda s: s.frame_idx)
    return rows


def detect_cycles(rows: list[Sample]) -> tuple[list[Cycle], int]:
    """Detect complete cycles. Returns (complete_cycles, n_incomplete_attempts)."""
    if not rows:
        return [], 0

    # Find the index in PHASE_SEQUENCE for each sample's phase, or -1 if unknown
    cycles: list[Cycle] = []
    n_incomplete = 0
    i = 0
    n = len(rows)
    while i < n:
        # Find next "closed" frame to start a cycle attempt
        while i < n and rows[i].phase != "closed":
            i += 1
        if i >= n:
            break

        # Try to walk through closed -> opening -> open -> closing -> closed
        attempt_start = i
        seq_idx = 0  # index into PHASE_SEQUENCE
        cycle_samples: list[Sample] = [rows[i]]
        i += 1
        seq_idx = 1  # next expected: "opening"
        success = False
        while i < n and seq_idx < len(PHASE_SEQUENCE):
            expected = PHASE_SEQUENCE[seq_idx]
            current_phase = rows[i].phase
            if current_phase == expected:
                cycle_samples.append(rows[i])
                # Move to next expected phase only when we leave the current one
                # Look ahead: keep collecting until phase changes
                while i < n and rows[i].phase == expected:
                    if rows[i] is not cycle_samples[-1]:
                        cycle_samples.append(rows[i])
                    i += 1
                seq_idx += 1
                # The next iteration will start at the new (different) phase
                if seq_idx < len(PHASE_SEQUENCE):
                    next_expected = PHASE_SEQUENCE[seq_idx]
                    # If we landed on something other than next_expected, abort
                    if i < n and rows[i].phase != next_expected:
                        break
            else:
                # Phase didn't match what we expected next
                break

        if seq_idx == len(PHASE_SEQUENCE):
            # Walked the full sequence; we have a complete cycle
            cycles.append(Cycle(samples=cycle_samples))
            success = True
        else:
            n_incomplete += 1
        if not success:
            i = max(attempt_start + 1, i)
    return cycles, n_incomplete


def cycle_period_ms(cycle: Cycle, fps: float) -> float:
    period_frames = cycle.samples[-1].frame_idx - cycle.samples[0].frame_idx
    return (period_frames / fps) * 1000.0


def path_length_mm(cycle: Cycle) -> float:
    s = 0.0
    for a, b in zip(cycle.samples[:-1], cycle.samples[1:]):
        s += float(np.linalg.norm(b.xyz - a.xyz))
    return s


def peak_displacement_mm(cycle: Cycle) -> float:
    origin = cycle.samples[0].xyz
    return max(float(np.linalg.norm(s.xyz - origin)) for s in cycle.samples)


def _mean_std_cv(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    m = float(np.mean(values))
    sd = float(np.std(values))
    cv = sd / m if m else 0.0
    return m, sd, cv


def aggregate(cycles: list[Cycle], fps: float, n_incomplete: int) -> dict:
    if not cycles:
        return {"n_cycles_complete": 0, "n_cycles_incomplete": n_incomplete,
                "cycle_period_ms": None, "path_length_mm": None,
                "peak_displacement_mm": None}
    periods = [cycle_period_ms(c, fps) for c in cycles]
    paths = [path_length_mm(c) for c in cycles]
    peaks = [peak_displacement_mm(c) for c in cycles]
    pm, ps, pcv = _mean_std_cv(periods)
    am, asd, acv = _mean_std_cv(paths)
    km, ks, kcv = _mean_std_cv(peaks)
    return {
        "n_cycles_complete": len(cycles),
        "n_cycles_incomplete": n_incomplete,
        "cycle_period_ms":      {"mean": pm, "std": ps, "cv": pcv, "values": periods},
        "path_length_mm":       {"mean": am, "std": asd, "cv": acv, "values": paths},
        "peak_displacement_mm": {"mean": km, "std": ks, "cv": kcv, "values": peaks},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("triangulated_csv", type=Path,
                    help="Output of tools/triangulate.py")
    ap.add_argument("--fps", type=float, default=30.0,
                    help="Recording frame rate (default 30; matches recorder)")
    ap.add_argument("--output", type=Path, default=None,
                    help="JSON sidecar path (default: <input>.metric.json)")
    args = ap.parse_args()

    rows = load_triangulated_csv(args.triangulated_csv)
    print(f"Loaded {len(rows)} triangulated frames from {args.triangulated_csv}")

    cycles, n_incomplete = detect_cycles(rows)
    print(f"Detected {len(cycles)} complete cycles ({n_incomplete} incomplete attempts dropped)")

    if not cycles:
        print("\nNo complete cycles. Check phase labels — each cycle needs the full "
              "closed->opening->open->closing->closed sequence.", file=sys.stderr)
        sys.exit(1)

    agg = aggregate(cycles, args.fps, n_incomplete)
    print(f"\nMetric cycle analysis (fps={args.fps}):")
    for key in ("cycle_period_ms", "path_length_mm", "peak_displacement_mm"):
        d = agg[key]
        print(f"  {key:<22}: mean={d['mean']:8.3f}  std={d['std']:7.3f}  CV={d['cv']*100:6.2f}%  "
              f"(over {len(d['values'])} cycles)")

    out_path = args.output or args.triangulated_csv.with_suffix(".metric.json")
    out_path.write_text(json.dumps(agg, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
