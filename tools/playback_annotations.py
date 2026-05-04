"""Animated playback of a manually-labeled landmark on a valve video.

Draws a green crosshair at the first annotated frame's point (origin),
a red dot at the current frame's annotated point, a yellow displacement
arrow from origin to current, and a faded-gray trail through every
labeled point seen so far.

Usage:
    python tools/playback_annotations.py path/to/recording.mp4
    python tools/playback_annotations.py path/to/recording.mp4 \
        --annotations path/to/recording.mp4.annotations.csv \
        --speed 0.5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._annotations import Annotation, read_annotations


WINDOW = "Annotation Playback"

ORIGIN_COLOR = (0, 255, 0)       # green
CURRENT_COLOR = (0, 0, 255)      # red
ARROW_COLOR = (0, 255, 255)      # yellow
TRAIL_COLOR = (180, 180, 180)    # faded gray


class OverlayState:
    """Cumulative state for the playback overlay."""

    def __init__(self) -> None:
        self.origin: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self.last_phase: str = ""
        self.trail: list[tuple[int, int]] = []
        # Map frame_idx -> position-in-trail to support same-frame replacement.
        self._trail_idx: dict[int, int] = {}

    def update(self, ann: Annotation) -> None:
        if self.origin is None:
            self.origin = (ann.point_x, ann.point_y)
        self.current = (ann.point_x, ann.point_y)
        self.last_phase = ann.phase
        if ann.frame_idx in self._trail_idx:
            self.trail[self._trail_idx[ann.frame_idx]] = (ann.point_x, ann.point_y)
        else:
            self._trail_idx[ann.frame_idx] = len(self.trail)
            self.trail.append((ann.point_x, ann.point_y))


def draw_overlay(frame: np.ndarray, state: OverlayState) -> np.ndarray:
    """Return a copy of `frame` with the playback overlay drawn on top."""
    out = frame.copy()
    if state.origin is None:
        return out
    # Trail polyline.
    if len(state.trail) >= 2:
        pts = np.array(state.trail, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], isClosed=False, color=TRAIL_COLOR, thickness=1)
    # Displacement arrow (origin -> current).
    if state.current is not None and state.current != state.origin:
        cv2.arrowedLine(
            out, state.origin, state.current,
            ARROW_COLOR, thickness=2, tipLength=0.05,
        )
    # Origin crosshair.
    ox, oy = state.origin
    cv2.line(out, (ox - 6, oy), (ox + 6, oy), ORIGIN_COLOR, 1)
    cv2.line(out, (ox, oy - 6), (ox, oy + 6), ORIGIN_COLOR, 1)
    # Current dot.
    if state.current is not None:
        cv2.circle(out, state.current, 4, CURRENT_COLOR, -1)
    return out
