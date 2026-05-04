"""Cycle detection + per-cycle metrics + CV aggregation for valve annotations.

Mode A (default): runs only on the annotations CSV.
Mode B (--video): additionally compares Farneback dense flow at each
annotated point to the manual frame-to-frame displacement.

Usage:
    python tools/analyze_annotations.py path/to/recording.mp4.annotations.csv
    python tools/analyze_annotations.py path/to/recording.mp4.annotations.csv \
        --video path/to/recording.mp4 --fps 30
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._annotations import Annotation, read_annotations
from tools._flow_params import FARNEBACK_PARAMS


@dataclass
class Cycle:
    """One complete cardiac cycle: closed -> opening -> open -> closing -> closed."""

    start_frame: int
    end_frame: int
    rows: list[Annotation] = field(default_factory=list)


# Required phase sequence inside a cycle, including both endpoint `closed` frames.
_PHASE_SEQUENCE: tuple[str, ...] = ("closed", "opening", "open", "closing", "closed")


def detect_cycles(rows: Sequence[Annotation]) -> list[Cycle]:
    """Detect complete cardiac cycles from a phase-labeled annotation list.

    A cycle starts at a `closed` annotation and ends at the next `closed`
    annotation, having passed through `opening`, `open`, and `closing` in
    that order. Multiple consecutive frames sharing the same phase are
    allowed (treated as repeats). Out-of-order or missing tokens cause the
    in-progress cycle attempt to be abandoned; cycle search then resumes
    from the next row after the failed start.
    """
    rows = sorted(rows, key=lambda r: r.frame_idx)
    cycles: list[Cycle] = []
    i = 0
    n = len(rows)

    while i < n:
        # Find the next `closed` annotation — the candidate cycle start.
        while i < n and rows[i].phase != "closed":
            i += 1
        if i >= n:
            break
        start_idx = i

        # Walk through _PHASE_SEQUENCE, consuming repeats of the current and
        # previous phase tokens. Token at index 0 is the leading `closed`
        # we already matched at start_idx, so begin searching for token 1.
        token_idx = 1
        j = start_idx + 1
        ok = True
        while token_idx < len(_PHASE_SEQUENCE):
            if j >= n:
                ok = False
                break
            phase = rows[j].phase
            if phase == _PHASE_SEQUENCE[token_idx]:
                token_idx += 1
                j += 1
            elif phase == _PHASE_SEQUENCE[token_idx - 1]:
                # Repeat of the phase we just consumed — allow it.
                j += 1
            else:
                ok = False
                break

        if ok:
            cycle_rows = rows[start_idx:j]
            cycles.append(
                Cycle(
                    start_frame=rows[start_idx].frame_idx,
                    end_frame=rows[j - 1].frame_idx,
                    rows=list(cycle_rows),
                )
            )
            # Terminating `closed` of cycle N is the leading `closed` of
            # cycle N+1, so resume search from j-1.
            i = j - 1
        else:
            # This `closed` did not start a valid cycle — try the next row.
            i = start_idx + 1

    return cycles


def cycle_period_ms(cycle: Cycle, fps: float) -> float:
    """Cycle duration in milliseconds (peak-to-peak interval).

    Computed as `(end_frame - start_frame) / fps * 1000`. This is the
    inter-event period (the gap between the two `closed` boundary frames),
    NOT the number of frames spanned by the cycle's annotations.
    """
    frames = cycle.end_frame - cycle.start_frame
    return (frames / fps) * 1000.0


def path_length_px(cycle: Cycle) -> float:
    """Sum of pixel distances between consecutive annotated points in the cycle."""
    total = 0.0
    for a, b in zip(cycle.rows, cycle.rows[1:]):
        total += math.hypot(b.point_x - a.point_x, b.point_y - a.point_y)
    return total


def peak_displacement_px(cycle: Cycle) -> float:
    """Max distance from the cycle-start point to any point in the cycle."""
    if not cycle.rows:
        return 0.0
    sx, sy = cycle.rows[0].point_x, cycle.rows[0].point_y
    return max(math.hypot(r.point_x - sx, r.point_y - sy) for r in cycle.rows)


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var)


def _cv(mean: float, std: float) -> float:
    return 0.0 if mean == 0 else std / mean


def aggregate_cycles(cycles: Sequence[Cycle], fps: float) -> dict:
    """Aggregate per-cycle metrics across complete cycles."""
    periods = [cycle_period_ms(c, fps) for c in cycles]
    peaks = [peak_displacement_px(c) for c in cycles]
    paths = [path_length_px(c) for c in cycles]

    p_mean, p_std = _mean_std(periods)
    pk_mean, pk_std = _mean_std(peaks)
    pl_mean, pl_std = _mean_std(paths)

    return {
        "n_cycles_complete": len(cycles),
        "mean_cycle_period_ms": p_mean,
        "std_cycle_period_ms": p_std,
        "cv_cycle_period_ms": _cv(p_mean, p_std),
        "mean_peak_displacement_px": pk_mean,
        "std_peak_displacement_px": pk_std,
        "cv_peak_displacement_px": _cv(pk_mean, pk_std),
        "mean_path_length_px": pl_mean,
        "std_path_length_px": pl_std,
        "cv_path_length_px": _cv(pl_mean, pl_std),
    }


def sample_flow_at_point(flow: "np.ndarray", x: float, y: float) -> tuple[float, float]:
    """Bilinearly sample a 2-channel flow field at sub-pixel `(x, y)`.

    `flow` is shape (H, W, 2) with channel 0 = dx, channel 1 = dy. Out-of-bounds
    coordinates are clamped to the nearest in-bounds pixel.
    """
    import numpy as np
    h, w = flow.shape[:2]
    # Clamp to [0, w-1] x [0, h-1].
    x = max(0.0, min(float(x), w - 1))
    y = max(0.0, min(float(y), h - 1))
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    x1 = min(x0 + 1, w - 1)
    y1 = min(y0 + 1, h - 1)
    tx = x - x0
    ty = y - y0
    f00 = flow[y0, x0]
    f10 = flow[y0, x1]
    f01 = flow[y1, x0]
    f11 = flow[y1, x1]
    fx = (1 - ty) * ((1 - tx) * f00[0] + tx * f10[0]) + ty * ((1 - tx) * f01[0] + tx * f11[0])
    fy = (1 - ty) * ((1 - tx) * f00[1] + tx * f10[1]) + ty * ((1 - tx) * f01[1] + tx * f11[1])
    return float(fx), float(fy)


def compare_flow_to_manual(
    rows: Sequence[Annotation],
    flow_provider: "dict[tuple[int, int], np.ndarray]",
) -> dict:
    """Compare Farneback flow at each labeled point to the manual displacement.

    `flow_provider` maps `(prev_frame_idx, curr_frame_idx)` -> flow field of
    shape (H, W, 2). The caller is responsible for computing/loading these
    flow fields lazily (they are large). Only consecutive frame pairs
    (curr - prev == 1) are evaluated.

    Returns a dict with `n_pairs`, `n_pairs_skipped_nonconsecutive`,
    `n_pairs_skipped_no_flow`, `median_error_px`, `p95_error_px`.
    """
    import numpy as np
    rows = sorted(rows, key=lambda r: r.frame_idx)
    errors: list[float] = []
    skipped_nonconsec = 0
    skipped_no_flow = 0

    for a, b in zip(rows, rows[1:]):
        if b.frame_idx - a.frame_idx != 1:
            skipped_nonconsec += 1
            continue
        manual_dx = b.point_x - a.point_x
        manual_dy = b.point_y - a.point_y
        flow = flow_provider.get((a.frame_idx, b.frame_idx))
        if flow is None:
            skipped_no_flow += 1
            continue
        fx, fy = sample_flow_at_point(flow, a.point_x, a.point_y)
        err = math.hypot(fx - manual_dx, fy - manual_dy)
        errors.append(err)

    if not errors:
        return {
            "n_pairs": 0,
            "n_pairs_skipped_nonconsecutive": skipped_nonconsec,
            "n_pairs_skipped_no_flow": skipped_no_flow,
            "median_error_px": 0.0,
            "p95_error_px": 0.0,
        }
    arr = np.array(errors)
    return {
        "n_pairs": len(errors),
        "n_pairs_skipped_nonconsecutive": skipped_nonconsec,
        "n_pairs_skipped_no_flow": skipped_no_flow,
        "median_error_px": float(np.median(arr)),
        "p95_error_px": float(np.percentile(arr, 95)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path,
                        help="Path to the annotations CSV.")
    parser.add_argument("--video", type=Path, default=None,
                        help="Source MP4. When provided, runs Mode B: Farneback dense-flow vs manual displacement at each labeled point.")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="Frame rate for period calculation (default 30).")
    args = parser.parse_args()

    if not args.annotations.exists():
        print(f"Annotations CSV not found: {args.annotations}", file=sys.stderr)
        sys.exit(1)
    rows = read_annotations(args.annotations)
    cycles = detect_cycles(rows)
    agg = aggregate_cycles(cycles, fps=args.fps)

    print("=== Mode A: cycle metrics ===")
    print(f"n_cycles_complete = {agg['n_cycles_complete']}")
    print(f"cycle_period_ms      mean={agg['mean_cycle_period_ms']:.1f}  "
          f"std={agg['std_cycle_period_ms']:.1f}  CV={agg['cv_cycle_period_ms']:.4f}")
    print(f"peak_displacement_px mean={agg['mean_peak_displacement_px']:.2f}  "
          f"std={agg['std_peak_displacement_px']:.2f}  CV={agg['cv_peak_displacement_px']:.4f}")
    print(f"path_length_px       mean={agg['mean_path_length_px']:.2f}  "
          f"std={agg['std_path_length_px']:.2f}  CV={agg['cv_path_length_px']:.4f}")

    sidecar: dict = {"mode_a": agg}

    if args.video is not None:
        if not args.video.exists():
            print(f"Video not found: {args.video}", file=sys.stderr)
            sys.exit(1)
        import cv2
        cap = cv2.VideoCapture(str(args.video))
        if not cap.isOpened():
            print(f"Cannot open video: {args.video}", file=sys.stderr)
            sys.exit(1)

        consecutive_pairs = [
            (a.frame_idx, b.frame_idx)
            for a, b in zip(rows, rows[1:])
            if b.frame_idx - a.frame_idx == 1
        ]
        flow_provider: dict = {}
        for prev_idx, curr_idx in consecutive_pairs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, prev_idx)
            ret_p, prev_frame = cap.read()
            cap.set(cv2.CAP_PROP_POS_FRAMES, curr_idx)
            ret_c, curr_frame = cap.read()
            if not (ret_p and ret_c):
                continue
            prev_g = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            curr_g = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
            flow_provider[(prev_idx, curr_idx)] = cv2.calcOpticalFlowFarneback(
                prev_g, curr_g, None, **FARNEBACK_PARAMS,
            )
        cap.release()

        flow_result = compare_flow_to_manual(rows, flow_provider)
        sidecar["mode_b"] = flow_result

        print("\n=== Mode B: dense-flow point-tracking accuracy ===")
        print(f"n_pairs                      = {flow_result['n_pairs']}")
        print(f"n_pairs_skipped_nonconsec    = {flow_result['n_pairs_skipped_nonconsecutive']}")
        print(f"n_pairs_skipped_no_flow      = {flow_result['n_pairs_skipped_no_flow']}")
        print(f"median_error_px              = {flow_result['median_error_px']:.3f}")
        print(f"p95_error_px                 = {flow_result['p95_error_px']:.3f}")

    out_json = args.annotations.with_suffix(".analysis.json")
    out_json.write_text(json.dumps(sidecar, indent=2))
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
