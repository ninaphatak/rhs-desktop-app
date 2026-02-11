"""
Tests for DotTracker manual mode.

Tests:
1. Mode switching
2. Seed addition/removal
3. Manual detection with known positions
4. ID persistence across frames
5. Lost dot handling and recovery
6. Reference position setting
"""

import numpy as np
import pytest

from src.core.dot_tracker import DotTracker
from src.utils.dot_refinement import create_synthetic_dot_frame


class TestManualMode:
    """Test suite for DotTracker manual mode."""

    def test_initialization_manual_mode(self):
        """Test tracker initializes in manual mode."""
        tracker = DotTracker(mode="manual")

        assert tracker.mode == "manual"
        assert len(tracker.get_manual_seeds()) == 0

    def test_mode_switching(self):
        """Test switching between automatic and manual modes."""
        tracker = DotTracker(mode="automatic")

        assert tracker.mode == "automatic"

        tracker.set_mode("manual")
        assert tracker.mode == "manual"

        tracker.set_mode("automatic")
        assert tracker.mode == "automatic"

    def test_invalid_mode_raises_error(self):
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError):
            tracker = DotTracker(mode="invalid")

        tracker = DotTracker(mode="manual")
        with pytest.raises(ValueError):
            tracker.set_mode("invalid")

    def test_add_manual_seed(self):
        """Test adding manual seeds."""
        tracker = DotTracker(mode="manual")

        seed_id = tracker.add_manual_seed(100, 200, 10.5)

        assert seed_id == 0
        seeds = tracker.get_manual_seeds()
        assert len(seeds) == 1
        assert seeds[0]["x"] == 100
        assert seeds[0]["y"] == 200
        assert seeds[0]["radius"] == 10.5

    def test_add_multiple_seeds(self):
        """Test adding multiple manual seeds."""
        tracker = DotTracker(mode="manual")

        id1 = tracker.add_manual_seed(100, 100, 10)
        id2 = tracker.add_manual_seed(200, 200, 12)
        id3 = tracker.add_manual_seed(300, 300, 8)

        assert id1 == 0
        assert id2 == 1
        assert id3 == 2

        seeds = tracker.get_manual_seeds()
        assert len(seeds) == 3

    def test_remove_manual_seed(self):
        """Test removing manual seeds."""
        tracker = DotTracker(mode="manual")

        id1 = tracker.add_manual_seed(100, 100, 10)
        id2 = tracker.add_manual_seed(200, 200, 12)

        tracker.remove_manual_seed(id1)

        seeds = tracker.get_manual_seeds()
        assert len(seeds) == 1
        assert id2 in seeds
        assert id1 not in seeds

    def test_clear_manual_seeds(self):
        """Test clearing all manual seeds."""
        tracker = DotTracker(mode="manual")

        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)
        tracker.add_manual_seed(300, 300, 8)

        tracker.clear_manual_seeds()

        seeds = tracker.get_manual_seeds()
        assert len(seeds) == 0

    def test_manual_detection_first_frame(self):
        """Test manual detection on first frame."""
        # Create frame with known dots
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)

        result = tracker.detect(frame)

        assert result["dot_count"] == 2
        assert len(result["dots"]) == 2

        # Check that dots are near seed positions
        dots = result["dots"]
        positions = {(d["x"], d["y"]) for d in dots}

        # Should be within a few pixels of seed positions
        assert any(abs(x - 100) < 5 and abs(y - 100) < 5 for x, y in positions)
        assert any(abs(x - 200) < 5 and abs(y - 200) < 5 for x, y in positions)

    def test_manual_detection_maintains_ids(self):
        """Test that manual detection maintains IDs across frames."""
        # Create two frames with dots in slightly different positions
        frame1 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )
        frame2 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(105, 102, 10), (198, 203, 12)],  # Dots moved slightly
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)

        result1 = tracker.detect(frame1)
        result2 = tracker.detect(frame2)

        # IDs should be consistent
        ids1 = {d["id"] for d in result1["dots"]}
        ids2 = {d["id"] for d in result2["dots"]}

        assert ids1 == ids2
        assert len(ids1) == 2

    def test_manual_detection_lost_dot(self):
        """Test lost dot handling when dot disappears."""
        # Frame 1: dot present
        frame1 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Frame 2: dot disappears (white background only)
        frame2 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        result1 = tracker.detect(frame1)
        assert result1["dot_count"] == 1
        assert not result1["dots"][0]["lost"]

        result2 = tracker.detect(frame2)
        # Dot should still be reported but marked as lost
        assert result2["dot_count"] == 1
        assert result2["dots"][0]["lost"]

    def test_manual_detection_lost_dot_recovery(self):
        """Test that lost dots are removed after threshold frames."""
        # Frame with dot
        frame_with_dot = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Frame without dot
        frame_no_dot = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        # First frame: dot found
        result = tracker.detect(frame_with_dot)
        assert result["dot_count"] == 1
        assert not result["dots"][0]["lost"]

        # Next 10 frames: dot lost but still tracked
        for _ in range(10):
            result = tracker.detect(frame_no_dot)
            assert result["dot_count"] == 1
            assert result["dots"][0]["lost"]

        # Frame 11: dot should be removed
        result = tracker.detect(frame_no_dot)
        assert result["dot_count"] == 0

    def test_manual_detection_displacement_calculation(self):
        """Test displacement calculation in manual mode."""
        # Frame 1: dots at reference positions
        frame1 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )

        # Frame 2: dots moved
        frame2 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(110, 105, 10), (195, 210, 12)],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)

        # Detect first frame and set reference
        result1 = tracker.detect(frame1)
        tracker.set_reference()

        # Detect second frame - should show displacement
        result2 = tracker.detect(frame2)

        # All dots should have non-zero displacement
        for dot in result2["dots"]:
            # At least one displacement component should be non-zero
            assert dot["dx"] != 0 or dot["dy"] != 0

    def test_manual_mode_empty_seeds(self):
        """Test manual detection with no seeds returns empty result."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        tracker = DotTracker(mode="manual")

        result = tracker.detect(frame)

        assert result["dot_count"] == 0
        assert len(result["dots"]) == 0

    def test_manual_mode_seed_outside_dot(self):
        """Test manual detection when seed is not near any dot."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        tracker = DotTracker(mode="manual")
        # Add seed far from actual dot
        tracker.add_manual_seed(500, 500, 10)

        result = tracker.detect(frame)

        # Should not find any dots (seed is too far)
        assert result["dot_count"] == 0

    def test_mode_switching_resets_state(self):
        """Test that mode switching resets tracker state."""
        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        seeds = tracker.get_manual_seeds()
        assert len(seeds) == 1

        # Switch to automatic - should reset
        tracker.set_mode("automatic")

        # Seeds should be cleared
        seeds = tracker.get_manual_seeds()
        assert len(seeds) == 0

    def test_reference_not_set_for_lost_dots(self):
        """Test that lost dots don't affect reference positions."""
        frame_with_dot = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        frame_no_dot = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        # First frame: dot found
        tracker.detect(frame_with_dot)

        # Second frame: dot lost
        tracker.detect(frame_no_dot)

        # Try to set reference with lost dot - should not include it
        tracker.set_reference()

        # Reference should be empty (lost dot not included)
        assert len(tracker._reference_positions) == 0

    def test_manual_detection_with_noise(self):
        """Test manual detection is more robust to noise than automatic."""
        # Create frame with dots and noise (random dark pixels)
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )

        # Add random noise
        np.random.seed(42)
        noise_mask = np.random.random(frame.shape) < 0.1  # 10% noise
        frame[noise_mask] = 50  # Dark noise pixels

        # Manual mode with seeds
        tracker_manual = DotTracker(mode="manual")
        tracker_manual.add_manual_seed(100, 100, 10)
        tracker_manual.add_manual_seed(200, 200, 12)

        result_manual = tracker_manual.detect(frame)

        # Should find both dots despite noise
        assert result_manual["dot_count"] == 2


class TestManualModeIntegration:
    """Integration tests for manual mode with realistic scenarios."""

    def test_complete_workflow(self):
        """Test complete workflow: add seeds, track, set reference, measure displacement."""
        # Create sequence of frames with moving dot
        frames = [
            create_synthetic_dot_frame(640, 480, [(100, 100, 10)]),
            create_synthetic_dot_frame(640, 480, [(105, 102, 10)]),
            create_synthetic_dot_frame(640, 480, [(110, 105, 10)]),
            create_synthetic_dot_frame(640, 480, [(115, 108, 10)]),
        ]

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        # Process first frame and set reference
        result = tracker.detect(frames[0])
        assert result["dot_count"] == 1
        tracker.set_reference()

        # Process subsequent frames
        for frame in frames[1:]:
            result = tracker.detect(frame)
            assert result["dot_count"] == 1
            assert not result["dots"][0]["lost"]

            # Should have displacement from reference
            dot = result["dots"][0]
            displacement_magnitude = np.sqrt(dot["dx"]**2 + dot["dy"]**2)
            assert displacement_magnitude > 0

    def test_multiple_dots_tracking(self):
        """Test tracking multiple dots simultaneously."""
        # Create frames with 3 dots moving in different directions
        frame1 = create_synthetic_dot_frame(
            640, 480,
            [(100, 100, 10), (300, 200, 12), (500, 300, 8)]
        )
        frame2 = create_synthetic_dot_frame(
            640, 480,
            [(105, 105, 10), (295, 202, 12), (505, 295, 8)]
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(300, 200, 12)
        tracker.add_manual_seed(500, 300, 8)

        result1 = tracker.detect(frame1)
        assert result1["dot_count"] == 3

        result2 = tracker.detect(frame2)
        assert result2["dot_count"] == 3

        # All IDs should be preserved
        ids1 = {d["id"] for d in result1["dots"]}
        ids2 = {d["id"] for d in result2["dots"]}
        assert ids1 == ids2
