"""Tests for DataRecorder CSV recording."""

import csv
import time
from pathlib import Path

import pytest

from src.core.data_recorder import DataRecorder
from src.utils.config import CSV_HEADERS, OUTPUTS_DIR


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    """DataRecorder writing to a temporary directory."""
    monkeypatch.setattr("src.core.data_recorder.OUTPUTS_DIR", tmp_path)
    return DataRecorder()


def _sample_data(ts: float = None) -> dict:
    return {
        "timestamp": ts or time.time(),
        "p1": 10.5,
        "p2": 22.3,
        "flow": 3.1,
        "hr": 72.0,
        "vt1": 30.0,
        "vt2": 29.5,
        "at1": 28.0,
    }


class TestDataRecorder:
    def test_start_creates_csv(self, recorder, tmp_path):
        filename = recorder.start_recording()
        assert filename.startswith("rhs_")
        assert filename.endswith(".csv")
        assert (tmp_path / filename).exists()
        recorder.stop_recording()

    def test_stop_without_start(self, recorder):
        recorder.stop_recording()  # Should not raise

    def test_record_row_writes_data(self, recorder, tmp_path):
        filename = recorder.start_recording()
        t0 = time.time()
        recorder.record_row(_sample_data(t0))
        recorder.record_row(_sample_data(t0 + 0.5))
        recorder.stop_recording()

        path = tmp_path / filename
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert rows[0] == CSV_HEADERS  # Header row
        assert len(rows) == 3  # Header + 2 data rows
        assert float(rows[1][0]) == 0.0  # t=0 for first sample

    def test_record_row_ignored_when_not_recording(self, recorder):
        recorder.record_row(_sample_data())  # Should not raise

    def test_is_recording_flag(self, recorder):
        assert not recorder.is_recording
        recorder.start_recording()
        assert recorder.is_recording
        recorder.stop_recording()
        assert not recorder.is_recording
