"""Tests for tools/analyze_annotations.py — cycle detection + metrics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math

import pytest

from tools._annotations import Annotation
from tools.analyze_annotations import detect_cycles, Cycle


def _ann(i: int, x: int, y: int, p: str) -> Annotation:
    return Annotation(frame_idx=i, point_x=x, point_y=y, phase=p)


def test_detect_cycles_finds_two_complete_cycles():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "open"),
        _ann(6, 0, 0, "closing"),
        _ann(8, 0, 0, "closed"),    # cycle 1 ends + cycle 2 starts
        _ann(10, 0, 0, "opening"),
        _ann(12, 0, 0, "open"),
        _ann(14, 0, 0, "closing"),
        _ann(16, 0, 0, "closed"),   # cycle 2 ends
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 2
    assert cycles[0].start_frame == 0
    assert cycles[0].end_frame == 8
    assert cycles[1].start_frame == 8
    assert cycles[1].end_frame == 16


def test_detect_cycles_drops_leading_partial_cycle():
    rows = [
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "open"),
        _ann(6, 0, 0, "closing"),
        _ann(8, 0, 0, "closed"),    # could only act as start of next cycle
        _ann(10, 0, 0, "opening"),
        _ann(12, 0, 0, "open"),
        _ann(14, 0, 0, "closing"),
        _ann(16, 0, 0, "closed"),   # one complete cycle: 8 -> 16
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 1
    assert cycles[0].start_frame == 8
    assert cycles[0].end_frame == 16


def test_detect_cycles_drops_trailing_incomplete_cycle():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "open"),
        _ann(6, 0, 0, "closing"),
        _ann(8, 0, 0, "closed"),    # one complete cycle
        _ann(10, 0, 0, "opening"),  # trailing partial — no terminating closed
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 1


def test_detect_cycles_skips_out_of_order_phase_sequence():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "closing"),   # missing `open`
        _ann(6, 0, 0, "closed"),
        _ann(8, 0, 0, "opening"),
        _ann(10, 0, 0, "open"),
        _ann(12, 0, 0, "closing"),
        _ann(14, 0, 0, "closed"),   # one valid cycle: 6 -> 14
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 1
    assert cycles[0].start_frame == 6
    assert cycles[0].end_frame == 14


from tools.analyze_annotations import (
    cycle_period_ms,
    path_length_px,
    peak_displacement_px,
)


def test_cycle_period_ms_at_30fps():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(15, 0, 0, "opening"),
        _ann(30, 0, 0, "open"),
        _ann(45, 0, 0, "closing"),
        _ann(60, 0, 0, "closed"),
    ]
    c = detect_cycles(rows)[0]
    assert math.isclose(cycle_period_ms(c, fps=30.0), 2000.0)


def test_path_length_px_sums_consecutive_distances():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(1, 3, 4, "opening"),    # +5 px
        _ann(2, 6, 8, "open"),       # +5 px
        _ann(3, 6, 8, "closing"),    # +0 px
        _ann(4, 0, 0, "closed"),     # +10 px
    ]
    c = detect_cycles(rows)[0]
    assert math.isclose(path_length_px(c), 5.0 + 5.0 + 0.0 + 10.0)


def test_peak_displacement_px_is_max_distance_from_start():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(1, 3, 4, "opening"),    # 5 from start
        _ann(2, 6, 8, "open"),       # 10 from start (peak)
        _ann(3, 3, 4, "closing"),    # 5 from start
        _ann(4, 0, 0, "closed"),     # 0 from start
    ]
    c = detect_cycles(rows)[0]
    assert math.isclose(peak_displacement_px(c), 10.0)
