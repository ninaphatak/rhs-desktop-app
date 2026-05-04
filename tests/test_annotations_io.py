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


def test_write_annotations_produces_expected_csv(tmp_path):
    from tools._annotations import write_annotations

    rows = [
        Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening"),
        Annotation(frame_idx=14, point_x=418, point_y=312, phase="open"),
    ]
    out = tmp_path / "ann.csv"
    write_annotations(rows, out)

    text = out.read_text()
    assert text.splitlines()[0] == "frame_idx,point_x,point_y,phase"
    assert "12,412,305,opening" in text
    assert "14,418,312,open" in text


def test_write_annotations_sorts_by_frame_idx(tmp_path):
    from tools._annotations import write_annotations

    rows = [
        Annotation(frame_idx=14, point_x=418, point_y=312, phase="open"),
        Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening"),
    ]
    out = tmp_path / "ann.csv"
    write_annotations(rows, out)

    lines = out.read_text().splitlines()
    assert lines[1].startswith("12,")
    assert lines[2].startswith("14,")


def test_read_annotations_round_trip(tmp_path):
    from tools._annotations import write_annotations, read_annotations

    rows = [
        Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening"),
        Annotation(frame_idx=14, point_x=418, point_y=312, phase="open"),
        Annotation(frame_idx=20, point_x=425, point_y=320, phase="closing"),
    ]
    out = tmp_path / "ann.csv"
    write_annotations(rows, out)

    loaded = read_annotations(out)
    assert loaded == rows


def test_read_annotations_missing_file_returns_empty_list(tmp_path):
    from tools._annotations import read_annotations
    assert read_annotations(tmp_path / "nope.csv") == []
