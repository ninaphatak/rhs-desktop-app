"""
Test UI Interactions - User Use Case Validation

Tests the user-facing workflows:
1. Set Reference button triggers DotTracker.set_reference()
2. Start/Stop Recording button toggles data recording
3. Reset Tracker button clears IDs and reference
4. Threshold slider updates DotTracker threshold
5. Displacement vectors displayed correctly after reference set
6. Full end-to-end user workflow
"""

import pytest
import numpy as np
import cv2

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from src.ui.camera_panel import CameraPanel
from src.core.dot_tracker import DotTracker


@pytest.fixture
def camera_panel(qtbot):
    """Create CameraPanel widget."""
    panel = CameraPanel()
    qtbot.addWidget(panel)
    return panel


@pytest.fixture
def tracker():
    """Create DotTracker instance with tuned parameters."""
    return DotTracker(threshold=100, min_area=50, max_area=300)


def _make_dot_frame(dot_positions: list[tuple[int, int]], size=(480, 640)) -> np.ndarray:
    """Create a grayscale test frame with dark dots on light background.

    Dots are radius 8 (~200px area), within the default tracker's
    min_area=50, max_area=300 range.
    """
    frame = np.ones(size, dtype=np.uint8) * 240
    for x, y in dot_positions:
        cv2.circle(frame, (x, y), 8, 20, -1)
    return frame


class TestSetReferenceButton:
    """Test Set Reference button functionality."""

    def test_button_exists(self, camera_panel):
        """Verify Set Reference button exists."""
        assert camera_panel.set_reference_btn is not None
        assert camera_panel.set_reference_btn.text() == "Set Reference"

    def test_button_emits_signal(self, camera_panel, qtbot):
        """Test that clicking Set Reference emits signal."""
        with qtbot.waitSignal(camera_panel.reference_set_requested, timeout=1000):
            QTest.mouseClick(camera_panel.set_reference_btn, Qt.MouseButton.LeftButton)

    def test_status_updates_on_click(self, camera_panel):
        """Test that status label updates when reference is set."""
        QTest.mouseClick(camera_panel.set_reference_btn, Qt.MouseButton.LeftButton)
        assert "Reference set" in camera_panel.status_label.text()

    def test_tracker_reference_actually_set(self, camera_panel, tracker, qtbot):
        """Integration test: Verify tracker.set_reference() is actually called."""
        # Generate test frame with dots
        frame = _make_dot_frame([(100, 100), (200, 200), (300, 300)])

        # Detect dots (first frame)
        result1 = tracker.detect(frame)
        assert result1["dot_count"] == 3

        # Connect panel signal to tracker method
        camera_panel.reference_set_requested.connect(tracker.set_reference)

        # Click button
        QTest.mouseClick(camera_panel.set_reference_btn, Qt.MouseButton.LeftButton)

        # Verify reference was set
        assert len(tracker._reference_positions) == 3

        # Move dots slightly
        frame2 = _make_dot_frame([(105, 105), (205, 205), (305, 305)])

        # Detect on new frame
        result2 = tracker.detect(frame2)

        # Verify displacement is calculated
        has_displacement = any(
            d["dx"] != 0 or d["dy"] != 0 for d in result2["dots"]
        )
        assert has_displacement


class TestRecordingButton:
    """Test Start/Stop Recording button functionality."""

    def test_button_exists(self, camera_panel):
        """Verify Recording button exists."""
        assert camera_panel.record_btn is not None
        assert camera_panel.record_btn.text() == "Start Recording"

    def test_button_is_checkable(self, camera_panel):
        """Verify button is checkable (toggle behavior)."""
        assert camera_panel.record_btn.isCheckable()

    def test_button_emits_signal_on_start(self, camera_panel, qtbot):
        """Test that clicking Start Recording emits signal with True."""
        with qtbot.waitSignal(camera_panel.recording_toggled, timeout=1000) as blocker:
            QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)

        assert blocker.args == [True]

    def test_button_emits_signal_on_stop(self, camera_panel, qtbot):
        """Test that clicking Stop Recording emits signal with False."""
        # Start recording first
        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)

        # Then stop
        with qtbot.waitSignal(camera_panel.recording_toggled, timeout=1000) as blocker:
            QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)

        assert blocker.args == [False]

    def test_button_text_changes(self, camera_panel):
        """Test that button text toggles between Start/Stop."""
        assert camera_panel.record_btn.text() == "Start Recording"

        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)
        assert camera_panel.record_btn.text() == "Stop Recording"

        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)
        assert camera_panel.record_btn.text() == "Start Recording"

    def test_status_label_updates(self, camera_panel):
        """Test that status label shows recording state."""
        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)
        assert "Recording" in camera_panel.status_label.text()

        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)
        assert "stopped" in camera_panel.status_label.text()


class TestResetTrackerButton:
    """Test Reset Tracker button functionality."""

    def test_button_exists(self, camera_panel):
        """Verify Reset button exists."""
        assert camera_panel.reset_btn is not None
        assert camera_panel.reset_btn.text() == "Reset Tracker"

    def test_button_emits_signal(self, camera_panel, qtbot):
        """Test that clicking Reset emits signal."""
        with qtbot.waitSignal(camera_panel.tracker_reset_requested, timeout=1000):
            QTest.mouseClick(camera_panel.reset_btn, Qt.MouseButton.LeftButton)

    def test_tracker_actually_resets(self, camera_panel, tracker, qtbot):
        """Integration test: Verify tracker.reset() clears state."""
        # Setup: detect dots and set reference
        frame = _make_dot_frame([(100, 100), (200, 200)])
        tracker.detect(frame)
        tracker.set_reference()

        # Verify state exists
        assert len(tracker._previous_dots) == 2
        assert len(tracker._reference_positions) == 2
        assert tracker._next_id > 0

        # Connect signal
        camera_panel.tracker_reset_requested.connect(tracker.reset)

        # Click reset button
        QTest.mouseClick(camera_panel.reset_btn, Qt.MouseButton.LeftButton)

        # Verify state cleared
        assert len(tracker._previous_dots) == 0
        assert len(tracker._reference_positions) == 0
        assert tracker._next_id == 0
        assert tracker._previous_frame_gray is None


class TestThresholdSlider:
    """Test threshold slider functionality."""

    def test_slider_exists(self, camera_panel):
        """Verify threshold slider exists."""
        assert camera_panel.threshold_slider is not None

    def test_slider_range(self, camera_panel):
        """Verify slider has correct range (0-255)."""
        assert camera_panel.threshold_slider.minimum() == 0
        assert camera_panel.threshold_slider.maximum() == 255

    def test_slider_default_value(self, camera_panel):
        """Verify slider starts at 100 (updated default)."""
        assert camera_panel.threshold_slider.value() == 100

    def test_slider_emits_signal(self, camera_panel, qtbot):
        """Test that moving slider emits threshold_changed signal."""
        with qtbot.waitSignal(camera_panel.threshold_changed, timeout=1000) as blocker:
            camera_panel.threshold_slider.setValue(150)

        assert blocker.args == [150]

    def test_label_updates(self, camera_panel):
        """Test that label shows current threshold value."""
        camera_panel.threshold_slider.setValue(120)
        assert "120" in camera_panel.threshold_label.text()

    def test_tracker_threshold_updates(self, camera_panel, tracker, qtbot):
        """Integration test: Verify tracker threshold actually changes."""
        camera_panel.threshold_changed.connect(tracker.set_threshold)
        camera_panel.threshold_slider.setValue(180)
        assert tracker.threshold == 180


class TestDisplacementVectorDisplay:
    """Test displacement vector visualization."""

    def test_displacement_checkbox_exists(self, camera_panel):
        """Verify displacement checkbox exists."""
        assert camera_panel.show_displacement_checkbox is not None

    def test_displacement_default_enabled(self, camera_panel):
        """Verify displacement vectors are shown by default."""
        assert camera_panel.show_displacement_checkbox.isChecked()

    def test_displacement_vectors_rendered(self, tracker):
        """Test that displacement vectors are calculated and rendered."""
        # Frame 1: Rest position
        frame1 = _make_dot_frame([(100, 100), (200, 200), (300, 300)])
        result1 = tracker.detect(frame1)
        assert result1["dot_count"] == 3

        # Set reference
        tracker.set_reference()

        # Frame 2: Displaced position
        frame2 = _make_dot_frame([(110, 115), (210, 215), (310, 315)])
        result2 = tracker.detect(frame2)

        # Verify displacement calculated
        dots = result2["dots"]
        assert len(dots) == 3
        has_displacement = any(d["dx"] != 0 or d["dy"] != 0 for d in dots)
        assert has_displacement

        # Render annotated frame
        annotated = tracker.annotate_frame(
            frame2, dots, show_ids=True, show_displacement=True
        )

        # Verify frame is BGR (annotated)
        assert len(annotated.shape) == 3
        assert annotated.shape[2] == 3

        # Verify frame contains colored pixels (arrows drawn)
        # Orange arrows: high R, medium G, low B in BGR = (low B, medium G, high R)
        has_orange = np.any(
            (annotated[:, :, 0] > 0) &   # B > 0
            (annotated[:, :, 1] > 100) &  # G > 100
            (annotated[:, :, 2] > 200)    # R > 200
        )
        assert has_orange, "No displacement arrows found in annotated frame"


class TestLKTrackingIntegration:
    """Test Lucas-Kanade optical flow tracking integration."""

    def test_lk_maintains_ids_through_motion(self):
        """LK tracking should maintain dot IDs through small frame-to-frame motion."""
        tracker = DotTracker(threshold=100, min_area=50, max_area=300)

        # Frame 1: detect dots
        frame1 = _make_dot_frame([(100, 100), (200, 200), (300, 300)])
        result1 = tracker.detect(frame1)
        assert result1["dot_count"] == 3
        ids_frame1 = {d["id"] for d in result1["dots"]}

        # Frame 2: small displacement
        frame2 = _make_dot_frame([(103, 103), (203, 203), (303, 303)])
        result2 = tracker.detect(frame2)
        ids_frame2 = {d["id"] for d in result2["dots"]}

        # IDs should be preserved
        assert ids_frame1 == ids_frame2

    def test_lk_with_optical_flow_disabled(self):
        """Tracker should still work when optical flow is disabled."""
        tracker = DotTracker(
            threshold=100, min_area=50, max_area=300,
            use_optical_flow=False
        )

        frame = _make_dot_frame([(100, 100), (200, 200)])
        result = tracker.detect(frame)
        assert result["dot_count"] == 2

    def test_first_frame_uses_blob_detection(self):
        """First frame should use blob detection (no previous frame for LK)."""
        tracker = DotTracker(threshold=100, min_area=50, max_area=300)

        assert tracker._previous_frame_gray is None

        frame = _make_dot_frame([(100, 100), (200, 200)])
        result = tracker.detect(frame)

        assert result["dot_count"] == 2
        assert tracker._previous_frame_gray is not None

    def test_reset_clears_frame_buffer(self):
        """Reset should clear the previous frame buffer."""
        tracker = DotTracker(threshold=100, min_area=50, max_area=300)

        frame = _make_dot_frame([(100, 100)])
        tracker.detect(frame)
        assert tracker._previous_frame_gray is not None

        tracker.reset()
        assert tracker._previous_frame_gray is None
        assert len(tracker._lost_dots) == 0


class TestFullUserWorkflow:
    """End-to-end test of complete user workflow."""

    def test_complete_tracking_session(self, camera_panel, tracker, qtbot):
        """
        Simulate a complete user session:
        1. Detect dots in rest position
        2. Click Set Reference
        3. Move valve (detect displaced dots)
        4. Verify displacement vectors appear
        5. Click Start Recording
        6. Click Stop Recording
        7. Click Reset
        8. Verify tracker cleared
        """
        # Connect panel signals to tracker
        camera_panel.reference_set_requested.connect(tracker.set_reference)
        camera_panel.tracker_reset_requested.connect(tracker.reset)
        camera_panel.threshold_changed.connect(tracker.set_threshold)

        # Step 1: Detect dots in rest position
        frame_rest = _make_dot_frame([(100, 100), (200, 200), (300, 300)])
        result = tracker.detect(frame_rest)
        camera_panel.update_tracking_info(result)

        assert result["dot_count"] == 3
        assert camera_panel.dot_count_label.text() == "Dots: 3"

        # Step 2: Set reference
        QTest.mouseClick(camera_panel.set_reference_btn, Qt.MouseButton.LeftButton)
        assert len(tracker._reference_positions) == 3

        # Step 3-4: Move valve and verify displacement
        frame_displaced = _make_dot_frame([(110, 110), (210, 210), (310, 310)])
        result = tracker.detect(frame_displaced)

        # Verify dots have displacement
        has_displacement = any(
            abs(d["dx"]) > 0 and abs(d["dy"]) > 0 for d in result["dots"]
        )
        assert has_displacement

        # Render displacement vectors
        annotated = tracker.annotate_frame(
            frame_displaced, result["dots"], show_displacement=True
        )
        camera_panel.update_frame(annotated)

        # Step 5: Start recording
        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)
        assert camera_panel._is_recording is True
        assert "Recording" in camera_panel.status_label.text()

        # Step 6: Stop recording
        QTest.mouseClick(camera_panel.record_btn, Qt.MouseButton.LeftButton)
        assert camera_panel._is_recording is False

        # Step 7-8: Reset tracker
        QTest.mouseClick(camera_panel.reset_btn, Qt.MouseButton.LeftButton)
        assert len(tracker._previous_dots) == 0
        assert len(tracker._reference_positions) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
