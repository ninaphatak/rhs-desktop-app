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
        """Test manual detection on first frame uses exact seed positions."""
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

        # Dots should be at exact seed positions (no refinement)
        dots = result["dots"]
        positions = {(d["x"], d["y"]) for d in dots}

        assert (100, 100) in positions
        assert (200, 200) in positions

    def test_manual_detection_maintains_ids(self):
        """Test that manual detection maintains IDs across frames."""
        frame1 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )
        frame2 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(105, 102, 10), (198, 203, 12)],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)

        result1 = tracker.detect(frame1)
        result2 = tracker.detect(frame2)

        # IDs should be consistent (raw positions don't change)
        ids1 = {d["id"] for d in result1["dots"]}
        ids2 = {d["id"] for d in result2["dots"]}

        assert ids1 == ids2
        assert len(ids1) == 2

    def test_manual_detection_dot_always_present(self):
        """Test that dot falls back to previous position on blank frame (no contrast)."""
        # Frame with dot
        frame1 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Blank frame — no contrast, tracker falls back to previous position
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

        # Dot falls back to previous position (no contrast in blank frame)
        result2 = tracker.detect(frame2)
        assert result2["dot_count"] == 1
        assert not result2["dots"][0]["lost"]

    def test_manual_detection_displacement_nonzero_when_dots_move(self):
        """Test that displacement is nonzero when dots move between frames."""
        frame1 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )

        frame2 = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(110, 105, 10), (195, 210, 12)],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)

        # Detect first frame and set reference
        tracker.detect(frame1)
        tracker.set_reference()

        # Detect second frame — dots should track to new positions
        result2 = tracker.detect(frame2)

        # At least one dot should show nonzero displacement
        any_moved = any(d["dx"] != 0 or d["dy"] != 0 for d in result2["dots"])
        assert any_moved, "Expected dots to track to new positions and show displacement"

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

    def test_manual_mode_seed_anywhere(self):
        """Test that manual seed is placed at exact position regardless of frame content."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        tracker = DotTracker(mode="manual")
        # Add seed far from actual dot — still placed at raw position
        tracker.add_manual_seed(500, 500, 10)

        result = tracker.detect(frame)

        assert result["dot_count"] == 1
        assert result["dots"][0]["x"] == 500
        assert result["dots"][0]["y"] == 500

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

    def test_reference_set_for_all_dots(self):
        """Test that reference is set for all seed-based dots."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        # Detect and set reference
        tracker.detect(frame)
        tracker.set_reference()

        # Reference should include the dot
        assert len(tracker._reference_positions) == 1

    def test_manual_detection_unaffected_by_noise(self):
        """Test manual detection is unaffected by noise (uses raw positions)."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 12)],
        )

        # Add random noise
        np.random.seed(42)
        noise_mask = np.random.random(frame.shape) < 0.1
        frame[noise_mask] = 50

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)
        tracker.add_manual_seed(200, 200, 12)

        result = tracker.detect(frame)

        # Raw positions are always returned regardless of noise
        assert result["dot_count"] == 2
        positions = {(d["x"], d["y"]) for d in result["dots"]}
        assert (100, 100) in positions
        assert (200, 200) in positions


class TestManualModeIntegration:
    """Integration tests for manual mode with realistic scenarios."""

    def test_complete_workflow(self):
        """Test complete workflow: add seeds, detect, track, show displacement."""
        frames = [
            create_synthetic_dot_frame(640, 480, [(100, 100, 10)]),
            create_synthetic_dot_frame(640, 480, [(105, 102, 10)]),
            create_synthetic_dot_frame(640, 480, [(110, 105, 10)]),
        ]

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        # Process first frame and set reference
        result = tracker.detect(frames[0])
        assert result["dot_count"] == 1
        tracker.set_reference()

        # Process subsequent frames — dots should track to new positions
        last_result = None
        for frame in frames[1:]:
            result = tracker.detect(frame)
            assert result["dot_count"] == 1
            assert not result["dots"][0]["lost"]
            last_result = result

        # After tracking through moving frames, displacement should be nonzero
        dot = last_result["dots"][0]
        assert dot["dx"] != 0 or dot["dy"] != 0, "Dot should show displacement after tracking"

    def test_multiple_dots_tracking(self):
        """Test multiple dots track to new positions across frames."""
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

        # Dots should have tracked — positions should NOT all be original seeds
        positions2 = {(d["x"], d["y"]) for d in result2["dots"]}
        original_seeds = {(100, 100), (300, 200), (500, 300)}
        assert positions2 != original_seeds, "Dots should have tracked to new positions"


class TestFrameToFrameTracking:
    """Tests for intensity-weighted centroid tracking in manual mode."""

    def test_tracking_follows_moving_dot(self):
        """Test that tracker follows a dot that moves between frames."""
        frame1 = create_synthetic_dot_frame(640, 480, [(100, 100, 10)])
        frame2 = create_synthetic_dot_frame(640, 480, [(110, 105, 10)])

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        result1 = tracker.detect(frame1)
        assert result1["dots"][0]["x"] == 100
        assert result1["dots"][0]["y"] == 100

        result2 = tracker.detect(frame2)
        # Should have tracked toward (110, 105)
        dot = result2["dots"][0]
        assert abs(dot["x"] - 110) < 5, f"Expected x near 110, got {dot['x']}"
        assert abs(dot["y"] - 105) < 5, f"Expected y near 105, got {dot['y']}"

    def test_tracking_bright_dot_on_dark(self):
        """Test tracking a bright dot on dark background (MockCamera style)."""
        frame1 = create_synthetic_dot_frame(
            640, 480, [(200, 200, 12)],
            background_intensity=30, dot_intensity=220,
        )
        frame2 = create_synthetic_dot_frame(
            640, 480, [(208, 195, 12)],
            background_intensity=30, dot_intensity=220,
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(200, 200, 12)

        tracker.detect(frame1)
        result2 = tracker.detect(frame2)

        dot = result2["dots"][0]
        assert abs(dot["x"] - 208) < 5, f"Expected x near 208, got {dot['x']}"
        assert abs(dot["y"] - 195) < 5, f"Expected y near 195, got {dot['y']}"

    def test_tracking_dark_dot_on_light(self):
        """Test tracking a dark dot on light background (real camera style)."""
        frame1 = create_synthetic_dot_frame(
            640, 480, [(150, 250, 10)],
            background_intensity=200, dot_intensity=40,
        )
        frame2 = create_synthetic_dot_frame(
            640, 480, [(155, 245, 10)],
            background_intensity=200, dot_intensity=40,
        )

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(150, 250, 10)

        tracker.detect(frame1)
        result2 = tracker.detect(frame2)

        dot = result2["dots"][0]
        assert abs(dot["x"] - 155) < 5, f"Expected x near 155, got {dot['x']}"
        assert abs(dot["y"] - 245) < 5, f"Expected y near 245, got {dot['y']}"

    def test_tracking_fallback_no_contrast(self):
        """Test that tracker falls back to previous position on blank/uniform frame."""
        frame1 = create_synthetic_dot_frame(640, 480, [(100, 100, 10)])
        # Uniform frame — no features
        frame2 = np.full((480, 640), 128, dtype=np.uint8)

        tracker = DotTracker(mode="manual")
        tracker.add_manual_seed(100, 100, 10)

        tracker.detect(frame1)
        result2 = tracker.detect(frame2)

        # Should fall back to previous position
        dot = result2["dots"][0]
        assert dot["x"] == 100
        assert dot["y"] == 100
