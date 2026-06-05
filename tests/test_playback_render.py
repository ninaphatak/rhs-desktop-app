"""Pixel-level tests for tools/playback_annotations.py overlay rendering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from tools._annotations import Annotation
from tools.playback_annotations import draw_overlay, OverlayState


def _blank(shape=(200, 300, 3)) -> np.ndarray:
    return np.zeros(shape, dtype=np.uint8)


def test_origin_marker_drawn_on_every_frame_after_first_label():
    state = OverlayState()
    state.update(Annotation(frame_idx=0, point_x=50, point_y=80, phase="closed"))
    out = draw_overlay(_blank(), state)
    # Origin crosshair pixel should be non-black at P0.
    assert tuple(out[80, 50]) != (0, 0, 0)


def test_current_marker_drawn_at_current_point():
    state = OverlayState()
    state.update(Annotation(frame_idx=0, point_x=50, point_y=80, phase="closed"))
    state.update(Annotation(frame_idx=5, point_x=120, point_y=140, phase="opening"))
    out = draw_overlay(_blank(), state)
    # Red dot center pixel.
    assert tuple(out[140, 120]) != (0, 0, 0)


def test_no_origin_drawn_before_first_annotation():
    state = OverlayState()
    out = draw_overlay(_blank(), state)
    assert (out == 0).all()


def test_trail_grows_with_updates():
    state = OverlayState()
    state.update(Annotation(frame_idx=0, point_x=10, point_y=10, phase="closed"))
    assert len(state.trail) == 1
    state.update(Annotation(frame_idx=1, point_x=20, point_y=20, phase="opening"))
    assert len(state.trail) == 2
    # Same frame_idx update replaces, does not append.
    state.update(Annotation(frame_idx=1, point_x=21, point_y=21, phase="opening"))
    assert len(state.trail) == 2
    assert state.trail[-1] == (21, 21)
