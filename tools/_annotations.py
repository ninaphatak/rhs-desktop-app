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
