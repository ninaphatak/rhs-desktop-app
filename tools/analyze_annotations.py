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
    """Cycle duration in milliseconds, given the source-video frame rate."""
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
