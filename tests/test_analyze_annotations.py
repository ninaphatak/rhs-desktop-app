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
