"""Annotation row dataclass and CSV I/O for the point-annotator tools.

Shared by tools/annotate_point.py, tools/playback_annotations.py, and
tools/analyze_annotations.py. Keep this module free of cv2/GUI deps so
analysis can run headless.
"""

from __future__ import annotations

from dataclasses import dataclass


VALID_PHASES: tuple[str, ...] = ("open", "opening", "closing", "closed")


@dataclass(frozen=True)
class Annotation:
    """One labeled frame: a tracked landmark position and a cardiac phase.

    Attributes:
        frame_idx: 0-based index of the frame in the source video.
        point_x: x pixel coordinate of the labeled landmark.
        point_y: y pixel coordinate of the labeled landmark.
        phase: one of VALID_PHASES.
    """

    frame_idx: int
    point_x: int
    point_y: int
    phase: str


import csv
from pathlib import Path
from typing import Iterable


CSV_HEADER = ("frame_idx", "point_x", "point_y", "phase")


def write_annotations(rows: Iterable[Annotation], path: Path) -> None:
    """Write annotations to CSV at `path`, sorted ascending by frame_idx.

    Overwrites any existing file at the path.
    """
    rows_sorted = sorted(rows, key=lambda r: r.frame_idx)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for r in rows_sorted:
            writer.writerow([r.frame_idx, r.point_x, r.point_y, r.phase])
