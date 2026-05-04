"""Tests for tools/_annotations.py — annotation CSV I/O."""

import sys
from pathlib import Path

# Allow `from tools._annotations import ...`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools._annotations import Annotation, VALID_PHASES


def test_valid_phases_are_the_four_documented_tokens():
    assert VALID_PHASES == ("open", "opening", "closing", "closed")


def test_annotation_construction():
    a = Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening")
    assert a.frame_idx == 12
    assert a.point_x == 412
    assert a.point_y == 305
    assert a.phase == "opening"
