"""
Tests for dot refinement utility.

Tests:
1. Refinement on perfect synthetic dots
2. Refinement accuracy (within 2 pixels)
3. Edge cases: click on white space, edge of frame, invalid inputs
4. Multiple dots: refinement selects closest
5. Various thresholds and noise levels
"""

import numpy as np
import pytest

from src.utils.dot_refinement import refine_dot_at_click, create_synthetic_dot_frame


class TestDotRefinement:
    """Test suite for OpenCV dot refinement."""

    def test_refine_perfect_dot(self):
        """Test refinement on a perfect synthetic dot."""
        # Create frame with single dot at (100, 100) with radius 10
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Click near the dot
        refined = refine_dot_at_click(frame, 105, 98)

        assert refined is not None
        assert abs(refined["x"] - 100) < 2  # Within 2 pixels
        assert abs(refined["y"] - 100) < 2
        assert 8 < refined["radius"] < 12  # Radius should be close to 10

    def test_refine_exact_center(self):
        """Test refinement when clicking exactly at dot center."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(200, 150, 12)],  # Radius 12 → area ~452, within default max_area
        )

        refined = refine_dot_at_click(frame, 200, 150)

        assert refined is not None
        assert abs(refined["x"] - 200) < 2
        assert abs(refined["y"] - 150) < 2

    def test_refine_multiple_dots_selects_closest(self):
        """Test that refinement selects the closest dot when multiple exist."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[
                (100, 100, 10),
                (200, 200, 12),
                (300, 100, 8),
            ],
        )

        # Click near first dot
        refined = refine_dot_at_click(frame, 105, 105)
        assert refined is not None
        assert abs(refined["x"] - 100) < 5
        assert abs(refined["y"] - 100) < 5

        # Click near second dot
        refined = refine_dot_at_click(frame, 195, 205)
        assert refined is not None
        assert abs(refined["x"] - 200) < 5
        assert abs(refined["y"] - 200) < 5

        # Click near third dot
        refined = refine_dot_at_click(frame, 302, 98)
        assert refined is not None
        assert abs(refined["x"] - 300) < 5
        assert abs(refined["y"] - 100) < 5

    def test_refine_click_on_white_space(self):
        """Test refinement returns None when clicking on white space."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Click far from any dot
        refined = refine_dot_at_click(frame, 400, 400)
        assert refined is None

    def test_refine_at_frame_edge(self):
        """Test refinement near frame edges."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(10, 10, 8), (630, 470, 8)],
        )

        # Click near top-left corner dot
        refined = refine_dot_at_click(frame, 12, 12)
        assert refined is not None

        # Click near bottom-right corner dot
        refined = refine_dot_at_click(frame, 628, 468)
        assert refined is not None

    def test_refine_invalid_inputs(self):
        """Test refinement handles invalid inputs gracefully."""
        # None frame
        refined = refine_dot_at_click(None, 100, 100)
        assert refined is None

        # Empty frame
        empty = np.array([], dtype=np.uint8)
        refined = refine_dot_at_click(empty, 100, 100)
        assert refined is None

    def test_refine_with_bgr_frame(self):
        """Test refinement works with BGR frame (converts to grayscale)."""
        # Create BGR frame
        gray = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )
        bgr = np.stack([gray, gray, gray], axis=-1)

        refined = refine_dot_at_click(bgr, 105, 98)
        assert refined is not None
        assert abs(refined["x"] - 100) < 2
        assert abs(refined["y"] - 100) < 2

    def test_refine_out_of_bounds_click(self):
        """Test refinement clamps out-of-bounds clicks to frame."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Click outside frame bounds (should be clamped)
        refined = refine_dot_at_click(frame, -50, -50)
        # Should not crash, may or may not find dot

        refined = refine_dot_at_click(frame, 1000, 1000)
        # Should not crash

    def test_refine_search_radius(self):
        """Test that search radius affects results."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        # Small search radius, click far from dot
        refined = refine_dot_at_click(frame, 125, 125, search_radius=10)
        assert refined is None  # Too far

        # Large search radius, same click
        refined = refine_dot_at_click(frame, 125, 125, search_radius=50)
        assert refined is not None  # Should find it

    def test_refine_area_filtering(self):
        """Test that min/max area filters work."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[
                (100, 100, 3),   # Small dot (area ~28)
                (200, 200, 15),  # Large dot (area ~707)
            ],
        )

        # Filter out small dots
        refined = refine_dot_at_click(
            frame, 100, 100,
            min_area=50,
            max_area=500
        )
        assert refined is None  # Small dot filtered out

        # Filter out large dots
        refined = refine_dot_at_click(
            frame, 200, 200,
            min_area=10,
            max_area=500
        )
        assert refined is None  # Large dot filtered out

        # Accept medium dots
        refined = refine_dot_at_click(
            frame, 200, 200,
            min_area=10,
            max_area=1000
        )
        assert refined is not None

    def test_refine_varying_brightness(self):
        """Test refinement with varying background brightness."""
        # Bright background
        frame_bright = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
            background_intensity=250,
            dot_intensity=50,
        )
        refined = refine_dot_at_click(frame_bright, 105, 98)
        assert refined is not None

        # Dark background
        frame_dark = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
            background_intensity=100,
            dot_intensity=20,
        )
        refined = refine_dot_at_click(frame_dark, 105, 98)
        assert refined is not None

    def test_refine_returns_correct_structure(self):
        """Test that refinement returns the expected dictionary structure."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
        )

        refined = refine_dot_at_click(frame, 100, 100)

        assert refined is not None
        assert "x" in refined
        assert "y" in refined
        assert "radius" in refined
        assert "area" in refined

        assert isinstance(refined["x"], int)
        assert isinstance(refined["y"], int)
        assert isinstance(refined["radius"], float)
        assert isinstance(refined["area"], float)


class TestSyntheticFrameCreation:
    """Test synthetic frame creation utility."""

    def test_create_empty_frame(self):
        """Test creating frame with no dots."""
        frame = create_synthetic_dot_frame(width=640, height=480, dots=[])

        assert frame.shape == (480, 640)
        assert frame.dtype == np.uint8

    def test_create_frame_with_dots(self):
        """Test creating frame with multiple dots."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10), (200, 200, 15)],
        )

        assert frame.shape == (480, 640)

        # Check that dots are darker than background
        assert frame[100, 100] < 100  # Dot pixel should be dark
        assert frame[50, 50] > 150    # Background pixel should be light

    def test_create_frame_custom_intensities(self):
        """Test creating frame with custom intensities."""
        frame = create_synthetic_dot_frame(
            width=640,
            height=480,
            dots=[(100, 100, 10)],
            background_intensity=255,
            dot_intensity=0,
        )

        assert frame[50, 50] == 255  # Background is white
        assert frame[100, 100] < 50  # Dot is very dark
