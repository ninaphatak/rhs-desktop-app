"""Tests for BaslerCamera video recording methods."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.core.basler_camera import BaslerCamera


class TestBaslerCameraRecording:
    """Test the start/stop recording API on BaslerCamera."""

    def test_start_recording_sets_state(self, tmp_path: Path) -> None:
        """start_recording should set is_recording=True and create a VideoWriter."""
        cam = BaslerCamera()
        output_path = tmp_path / "test.avi"
        cam._last_frame_size = (640, 480)
        cam.start_recording(str(output_path))
        assert cam.is_recording is True
        cam.stop_recording()

    def test_stop_recording_clears_state(self, tmp_path: Path) -> None:
        """stop_recording should set is_recording=False."""
        cam = BaslerCamera()
        cam._last_frame_size = (640, 480)
        cam.start_recording(str(tmp_path / "test.avi"))
        cam.stop_recording()
        assert cam.is_recording is False

    def test_stop_recording_when_not_recording(self) -> None:
        """stop_recording when not recording should be a no-op."""
        cam = BaslerCamera()
        cam.stop_recording()
        assert cam.is_recording is False

    def test_start_recording_without_frame_size_raises(self, tmp_path: Path) -> None:
        """start_recording without a known frame size should raise ValueError."""
        cam = BaslerCamera()
        with pytest.raises(ValueError, match="frame size"):
            cam.start_recording(str(tmp_path / "test.avi"))

    def test_write_frame_writes_to_video(self, tmp_path: Path) -> None:
        """_write_frame should write a frame to the VideoWriter when recording."""
        cam = BaslerCamera()
        cam._last_frame_size = (640, 480)
        output_path = tmp_path / "test.avi"
        cam.start_recording(str(output_path))
        frame = np.zeros((480, 640), dtype=np.uint8)
        cam._write_frame(frame)
        cam.stop_recording()
        assert output_path.exists()
        assert output_path.stat().st_size > 0
