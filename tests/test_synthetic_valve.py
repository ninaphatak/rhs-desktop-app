"""
Unit tests for SyntheticValveGenerator.

Run with: pytest tests/test_synthetic_valve.py -v
"""


import numpy as np


class TestSyntheticValveGeneratorInit:
    """Tests for SyntheticValveGenerator initialization."""

    def test_default_initialization(self, synthetic_generator):
        """Should initialize with default parameters."""
        assert synthetic_generator.resolution == (1920, 1200)
        assert synthetic_generator.num_markers == 4
        assert synthetic_generator.marker_radius == 15

    def test_custom_initialization(self):
        """Should accept custom parameters."""
        from tests.synthetic_valve import SyntheticValveGenerator

        gen = SyntheticValveGenerator(
            resolution=(640, 480),
            num_markers=3,
            marker_radius=10,
        )

        assert gen.resolution == (640, 480)
        assert gen.num_markers == 3
        assert gen.marker_radius == 10

    def test_marker_count_limits_positions(self):
        """Should only use as many positions as num_markers."""
        from tests.synthetic_valve import SyntheticValveGenerator

        gen = SyntheticValveGenerator(num_markers=2)
        assert len(gen.reference_positions) == 2


class TestSyntheticValveGeneratorFrameGeneration:
    """Tests for single frame generation."""

    def test_generates_correct_shape(self, synthetic_generator):
        """Frame should have correct dimensions."""
        frame = synthetic_generator.generate_frame(cycle_phase=0.0)

        # Note: shape is (height, width) in numpy
        assert frame.shape == (1200, 1920)

    def test_generates_grayscale(self, synthetic_generator):
        """Frame should be single channel grayscale."""
        frame = synthetic_generator.generate_frame(cycle_phase=0.0)

        assert len(frame.shape) == 2  # No color channel dimension
        assert frame.dtype == np.uint8

    def test_frame_has_white_background(self, synthetic_generator):
        """Background should be white (255)."""
        frame = synthetic_generator.generate_frame(cycle_phase=0.0)

        # Most pixels should be white
        white_pixels = np.sum(frame == 255)
        total_pixels = frame.size

        assert white_pixels / total_pixels > 0.95  # >95% white

    def test_frame_has_black_markers(self, synthetic_generator):
        """Frame should contain black (0) pixels for markers."""
        frame = synthetic_generator.generate_frame(cycle_phase=0.0)

        # Should have some black pixels (the markers)
        black_pixels = np.sum(frame == 0)

        assert black_pixels > 0

    def test_different_phases_produce_different_frames(self, synthetic_generator):
        """Different cycle phases should produce different marker positions."""
        frame1 = synthetic_generator.generate_frame(cycle_phase=0.0)
        frame2 = synthetic_generator.generate_frame(cycle_phase=0.5)

        # Frames should not be identical
        assert not np.array_equal(frame1, frame2)

    def test_same_phase_produces_same_frame(self, synthetic_generator):
        """Same cycle phase should produce identical frames."""
        frame1 = synthetic_generator.generate_frame(cycle_phase=0.25)
        frame2 = synthetic_generator.generate_frame(cycle_phase=0.25)

        assert np.array_equal(frame1, frame2)

    def test_displacement_magnitude_affects_motion(self, synthetic_generator):
        """Larger displacement magnitude should move markers more."""
        frame_small = synthetic_generator.generate_frame(
            cycle_phase=0.25,
            displacement_magnitude=5.0,
        )
        frame_large = synthetic_generator.generate_frame(
            cycle_phase=0.25,
            displacement_magnitude=50.0,
        )

        # These should be different due to different displacement
        assert not np.array_equal(frame_small, frame_large)

    def test_zero_displacement_no_motion(self, synthetic_generator):
        """Zero displacement should produce identical frames at all phases."""
        frame1 = synthetic_generator.generate_frame(
            cycle_phase=0.0,
            displacement_magnitude=0.0,
        )
        frame2 = synthetic_generator.generate_frame(
            cycle_phase=0.5,
            displacement_magnitude=0.0,
        )

        assert np.array_equal(frame1, frame2)


class TestSyntheticValveGeneratorVideoGeneration:
    """Tests for video file generation."""

    def test_generates_video_file(self, synthetic_generator_small, tmp_path):
        """Should create a video file."""
        video_path = tmp_path / "test_video.mp4"

        synthetic_generator_small.generate_video(
            str(video_path),
            duration_seconds=0.5,
            fps=30,
            bpm=72,
        )

        assert video_path.exists()
        assert video_path.stat().st_size > 0

    def test_video_has_correct_frame_count(self, synthetic_generator_small, tmp_path):
        """Video should have expected number of frames."""
        import cv2

        video_path = tmp_path / "test_video.mp4"
        duration = 1.0
        fps = 30

        synthetic_generator_small.generate_video(
            str(video_path),
            duration_seconds=duration,
            fps=fps,
            bpm=72,
        )

        cap = cv2.VideoCapture(str(video_path))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        expected_frames = int(duration * fps)
        # Allow small variance due to video encoding
        assert abs(frame_count - expected_frames) <= 2

    def test_video_frames_are_readable(self, synthetic_generator_small, tmp_path):
        """Should be able to read frames from generated video."""
        import cv2

        video_path = tmp_path / "test_video.mp4"

        synthetic_generator_small.generate_video(
            str(video_path),
            duration_seconds=0.5,
            fps=30,
            bpm=72,
        )

        cap = cv2.VideoCapture(str(video_path))
        ret, frame = cap.read()
        cap.release()

        assert ret is True
        assert frame is not None
        assert frame.shape[0] > 0
        assert frame.shape[1] > 0


class TestSyntheticValveGeneratorMarkerDetection:
    """Tests verifying markers are detectable in generated frames."""

    def test_markers_detectable_with_threshold(self, synthetic_generator):
        """Markers should be detectable using simple thresholding."""
        import cv2

        frame = synthetic_generator.generate_frame(cycle_phase=0.0)

        # Threshold to find black markers
        _, binary = cv2.threshold(frame, 50, 255, cv2.THRESH_BINARY_INV)

        # Find contours
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Should find correct number of markers
        assert len(contours) == synthetic_generator.num_markers

    def test_markers_have_reasonable_area(self, synthetic_generator):
        """Detected markers should have area consistent with marker_radius."""
        import cv2

        frame = synthetic_generator.generate_frame(cycle_phase=0.0)

        _, binary = cv2.threshold(frame, 50, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        expected_area = np.pi * synthetic_generator.marker_radius ** 2

        for contour in contours:
            area = cv2.contourArea(contour)
            # Area should be within 20% of expected (circles aren't perfect in pixels)
            assert 0.8 * expected_area < area < 1.2 * expected_area
