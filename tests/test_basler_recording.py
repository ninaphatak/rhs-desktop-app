"""Tests for BaslerCamera video recording methods (H.264/MP4 path)."""

import numpy as np
from pathlib import Path

from src.core.basler_camera import BaslerCamera


class TestBaslerCameraRecording:
    """Test the start/stop recording API on BaslerCamera."""

    def test_start_recording_sets_state(self, tmp_path: Path) -> None:
        """start_recording arms the recorder; is_recording becomes True."""
        cam = BaslerCamera()
        output_path = tmp_path / "test.mp4"
        cam.start_recording(str(output_path))
        assert cam.is_recording is True
        cam.stop_recording()

    def test_start_recording_forces_mp4_extension(self, tmp_path: Path) -> None:
        """A non-.mp4 path is coerced to .mp4."""
        cam = BaslerCamera()
        cam.start_recording(str(tmp_path / "test.avi"))
        assert cam._record_path is not None
        assert cam._record_path.suffix == ".mp4"
        cam.stop_recording()

    def test_stop_recording_clears_state(self, tmp_path: Path) -> None:
        """stop_recording resets is_recording to False."""
        cam = BaslerCamera()
        cam.start_recording(str(tmp_path / "test.mp4"))
        cam.stop_recording()
        assert cam.is_recording is False

    def test_stop_recording_when_not_recording(self) -> None:
        """stop_recording when not recording is a no-op."""
        cam = BaslerCamera()
        cam.stop_recording()
        assert cam.is_recording is False

    def test_double_start_is_ignored(self, tmp_path: Path) -> None:
        """Calling start_recording twice while already recording is a no-op."""
        cam = BaslerCamera()
        cam.start_recording(str(tmp_path / "first.mp4"))
        first_path = cam._record_path
        cam.start_recording(str(tmp_path / "second.mp4"))
        # Second call is rejected; first path is preserved
        assert cam._record_path == first_path
        cam.stop_recording()

    def test_write_frame_when_not_recording_is_noop(self) -> None:
        """_write_frame without an active recording should not crash."""
        cam = BaslerCamera()
        frame = np.zeros((480, 640), dtype=np.uint8)
        cam._write_frame(frame)  # should not raise
        assert cam._ffmpeg_proc is None

    def test_write_frame_produces_mp4(self, tmp_path: Path) -> None:
        """_write_frame after start_recording lazy-spawns ffmpeg and writes a real .mp4."""
        cam = BaslerCamera()
        output_path = tmp_path / "test.mp4"
        cam.start_recording(str(output_path))
        frame = np.zeros((120, 160), dtype=np.uint8)
        for _ in range(5):
            cam._write_frame(frame)
        cam.stop_recording()
        assert output_path.exists()
        assert output_path.stat().st_size > 0
