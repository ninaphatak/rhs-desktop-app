"""Tests for ControlBar widget changes."""

import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from src.ui.control_bar import ControlBar

# Ensure QApplication exists for widget tests
app = QApplication.instance() or QApplication([])


class TestControlBar:
    """Test ControlBar button layout and status labels."""

    def test_no_start_rhs_button(self) -> None:
        """Start RHS button should not exist."""
        bar = ControlBar()
        assert not hasattr(bar, "_start_rhs_btn")

    def test_review_button_exists(self) -> None:
        """Review button should exist and emit review_clicked signal."""
        bar = ControlBar()
        assert hasattr(bar, "_review_btn")

    def test_review_clicked_signal(self) -> None:
        """Clicking Review should emit review_clicked signal."""
        bar = ControlBar()
        received = []
        bar.review_clicked.connect(lambda: received.append(True))
        QTest.mouseClick(bar._review_btn, Qt.MouseButton.LeftButton)
        assert len(received) == 1

    def test_set_camera_recording_shows_status(self) -> None:
        """set_camera_recording(True) should show camera status text."""
        bar = ControlBar()
        bar.set_camera_recording(True)
        assert "Cameras recording" in bar._camera_status.text()

    def test_set_camera_recording_hides_status(self) -> None:
        """set_camera_recording(False) should hide camera status text."""
        bar = ControlBar()
        bar.set_camera_recording(True)
        bar.set_camera_recording(False)
        assert bar._camera_status.text() == ""

    def test_button_order(self) -> None:
        """Buttons should appear in order: Record, Stop, Plot, Log, Review."""
        bar = ControlBar()
        layout = bar.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]
        button_texts = [w.text() for w in widgets if isinstance(w, QPushButton)]
        assert button_texts == ["Record", "Stop", "Plot", "Log", "Review"]
