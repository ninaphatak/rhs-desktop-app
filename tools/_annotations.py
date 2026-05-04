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


def read_annotations(path: Path) -> list[Annotation]:
    """Read annotations from CSV at `path`.

    Returns an empty list if the file does not exist. Rows are returned
    in ascending frame_idx order. Raises ValueError on malformed input.
    """
    if not Path(path).exists():
        return []

    rows: list[Annotation] = []
    seen_frames: set[int] = set()
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if tuple(header or ()) != CSV_HEADER:
            raise ValueError(f"Bad header in {path}: {header!r}")
        for line_no, raw in enumerate(reader, start=2):
            if len(raw) != 4:
                raise ValueError(f"{path}:{line_no}: expected 4 columns, got {len(raw)}")
            try:
                frame_idx = int(raw[0])
                px = int(raw[1])
                py = int(raw[2])
            except ValueError as e:
                raise ValueError(f"{path}:{line_no}: non-integer field: {e}") from e
            phase = raw[3]
            if phase not in VALID_PHASES:
                raise ValueError(f"{path}:{line_no}: invalid phase {phase!r}")
            if frame_idx in seen_frames:
                raise ValueError(f"{path}:{line_no}: duplicate frame_idx {frame_idx}")
            seen_frames.add(frame_idx)
            rows.append(Annotation(frame_idx=frame_idx, point_x=px, point_y=py, phase=phase))

    rows.sort(key=lambda r: r.frame_idx)
    return rows
