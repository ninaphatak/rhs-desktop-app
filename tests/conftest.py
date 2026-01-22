"""
Shared test fixtures for RHS Desktop App tests.

Fixtures defined here are automatically available to all test files.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# =============================================================================
# Frame Fixtures
# =============================================================================

@pytest.fixture
def sample_frame() -> np.ndarray:
    """Generate a blank white test frame (1920x1200)."""
    return np.ones((1200, 1920), dtype=np.uint8) * 255


@pytest.fixture
def sample_frame_small() -> np.ndarray:
    """Generate a smaller blank white test frame (640x480) for faster tests."""
    return np.ones((480, 640), dtype=np.uint8) * 255


@pytest.fixture
def sample_frame_with_dots() -> np.ndarray:
    """
    Generate a test frame with 4 black dots in asymmetric pattern.

    Dot positions (in 1920x1200 frame):
        - Marker 0: (960, 360)  - top center
        - Marker 1: (672, 720)  - bottom left
        - Marker 2: (1248, 720) - bottom right
        - Marker 3: (960, 900)  - bottom center
    """
    frame = np.ones((1200, 1920), dtype=np.uint8) * 255

    dots = [
        (960, 360),   # Top center
        (672, 720),   # Bottom left
        (1248, 720),  # Bottom right
        (960, 900),   # Bottom center
    ]

    for x, y in dots:
        cv2.circle(frame, (x, y), 15, 0, -1)

    return frame


@pytest.fixture
def sample_frame_with_dots_small() -> np.ndarray:
    """Generate a smaller test frame with 4 black dots for faster tests."""
    frame = np.ones((480, 640), dtype=np.uint8) * 255

    dots = [
        (320, 120),  # Top center
        (224, 288),  # Bottom left
        (416, 288),  # Bottom right
        (320, 360),  # Bottom center
    ]

    for x, y in dots:
        cv2.circle(frame, (x, y), 10, 0, -1)

    return frame


# =============================================================================
# Synthetic Data Fixtures
# =============================================================================

@pytest.fixture
def synthetic_generator():
    """Provide a configured SyntheticValveGenerator."""
    from tests.synthetic_valve import SyntheticValveGenerator
    return SyntheticValveGenerator(num_markers=4)


@pytest.fixture
def synthetic_generator_small():
    """Provide a smaller SyntheticValveGenerator for faster tests."""
    from tests.synthetic_valve import SyntheticValveGenerator
    return SyntheticValveGenerator(
        resolution=(640, 480),
        num_markers=4,
        marker_radius=10,
    )


# =============================================================================
# Tracker Fixtures
# =============================================================================

@pytest.fixture
def dot_tracker():
    """Provide a configured DotTracker with default settings."""
    from src.core.dot_tracker import DotTracker
    return DotTracker(threshold=50, min_area=100, max_area=2000)


@pytest.fixture
def dot_tracker_small():
    """Provide a DotTracker configured for smaller test frames."""
    from src.core.dot_tracker import DotTracker
    return DotTracker(threshold=50, min_area=30, max_area=500)


# =============================================================================
# Mock Hardware Fixtures
# =============================================================================

@pytest.fixture
def mock_sensor_data() -> dict:
    """Provide sample sensor data matching Arduino output format."""
    return {
        "timestamp": 1709312456.123,
        "p1": 8.2,
        "p2": 25.1,
        "flow_rate": 1.45,
        "heart_rate": 72,
    }


@pytest.fixture
def mock_sensor_data_sequence() -> list[dict]:
    """Provide a sequence of sensor data for testing time series."""
    import time
    base_time = time.time()

    return [
        {"timestamp": base_time + i * 0.033, "p1": 8.0 + i * 0.1, "p2": 25.0, "flow_rate": 1.45, "heart_rate": 72}
        for i in range(30)  # ~1 second at 30Hz
    ]


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================

@pytest.fixture
def output_dir(tmp_path) -> Path:
    """Provide a temporary output directory for test files."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def test_video_path(tmp_path, synthetic_generator_small) -> Path:
    """Generate a short test video and return its path."""
    video_path = tmp_path / "test_video.mp4"
    synthetic_generator_small.generate_video(
        str(video_path),
        duration_seconds=1.0,
        fps=30,
        bpm=72,
    )
    return video_path
