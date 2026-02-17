"""
Standalone demo application for manual dot selection.

This is a working PyQt6 application that demonstrates the manual dot selection
feature without requiring MainWindow. It can be run directly with:

    python tests/test_manual_dot_selection.py

Features demonstrated:
- Live camera feed (MockCamera for testing, BaslerCamera if available)
- Manual dot selection by clicking (raw positions, no refinement)
- Displacement visualization
- Three-mode state machine (VIEW, SELECT, TRACKING)

This serves as both a development test tool and a reference implementation
for integrating manual dot selection into MainWindow.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from src.core.dot_tracker import DotTracker
from src.ui.camera_panel import CameraPanel, ViewMode
from tests.mock_camera import MockCamera

# Try to import BaslerCamera
try:
    from src.core.basler_camera import BaslerCamera

    BASLER_AVAILABLE = True
except ImportError:
    BASLER_AVAILABLE = False
    BaslerCamera = None


# Setup logging
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ManualDotSelectionApp(QMainWindow):
    """
    Standalone app to test manual dot selection feature.

    Demonstrates complete integration of:
    - CameraPanel (UI)
    - DotTracker (manual mode)
    - Raw click positions (no refinement)
    """

    def __init__(self, use_real_camera: bool = False):
        """
        Initialize demo app.

        Args:
            use_real_camera: If True, use BaslerCamera (requires hardware).
                           If False, use MockCamera (simulated frames).
        """
        super().__init__()

        self.setWindowTitle("RHS Manual Dot Selection Demo")
        self.setGeometry(100, 100, 1400, 900)

        # Core components
        if use_real_camera and BASLER_AVAILABLE:
            logger.info("Using real Basler camera")
            self.camera = BaslerCamera()
        else:
            logger.info("Using MockCamera (simulated frames)")
            self.camera = MockCamera()

        self.tracker = DotTracker(mode="manual")

        # UI
        self.camera_panel = CameraPanel()
        self.setCentralWidget(self.camera_panel)

        # Connect signals
        self._connect_signals()

        # Start camera
        if isinstance(self.camera, MockCamera):
            self.camera.start()
        else:
            # BaslerCamera requires connection first
            cameras = BaslerCamera.list_cameras()
            if cameras:
                logger.info(f"Found cameras: {cameras}")
                self.camera.connect(0)
                self.camera.start()
            else:
                logger.error("No Basler cameras found")

        logger.info("Manual dot selection app started")

    def _connect_signals(self):
        """Connect signals between components."""
        # Camera → Panel (display frames)
        self.camera.frame_ready.connect(self._on_frame_received)

        # Panel → App (user actions)
        self.camera_panel.dot_added.connect(self._on_user_add_dot)
        self.camera_panel.dot_removed.connect(self._on_user_remove_dot)
        self.camera_panel.mode_changed.connect(self._on_mode_changed)
        self.camera_panel.reference_set.connect(self._on_reference_set)
        self.camera_panel.tracking_started.connect(self._on_tracking_started)

    @pyqtSlot(dict)
    def _on_frame_received(self, frame_data: dict):
        """
        Handle new frame from camera.

        Args:
            frame_data: Dict with "frame" (numpy array), "timestamp", "fps"
        """
        # Update panel display
        self.camera_panel.update_frame(frame_data)

        # Run tracking if in TRACKING mode
        if self.camera_panel.mode == ViewMode.TRACKING:
            frame = frame_data["frame"]
            tracking_result = self.tracker.detect(frame)
            self.camera_panel.update_tracking(tracking_result)

    @pyqtSlot(int, int)
    def _on_user_add_dot(self, x: int, y: int):
        """
        Handle user clicking to add a dot.

        Uses raw click position directly — no OpenCV refinement.

        Args:
            x: Click X in image coordinates
            y: Click Y in image coordinates
        """
        # Use raw click position directly
        dot_data = {
            "x": x,
            "y": y,
            "radius": 5.0,
            "area": 78.5,  # pi * 5^2
        }

        # Add to tracker
        dot_id = self.tracker.add_manual_seed(x, y, dot_data["radius"])

        # Add visual to panel
        self.camera_panel.add_dot_visual(dot_data, dot_id)

    @pyqtSlot(int)
    def _on_user_remove_dot(self, dot_id: int):
        """
        Handle user removing a dot.

        Args:
            dot_id: ID of dot to remove
        """
        logger.info(f"User removed dot #{dot_id}")
        self.tracker.remove_manual_seed(dot_id)

    @pyqtSlot(str)
    def _on_mode_changed(self, mode: str):
        """
        Handle mode change.

        Args:
            mode: New mode ("view", "select", "tracking")
        """
        logger.info(f"Mode changed to: {mode}")

        if mode == "select":
            # Entering SELECT mode - ensure tracker is in manual mode
            if self.tracker.mode != "manual":
                self.tracker.set_mode("manual")

    @pyqtSlot()
    def _on_reference_set(self):
        """Handle user setting reference position (t=0)."""
        logger.info("User set reference position")
        self.tracker.set_reference()

    @pyqtSlot()
    def _on_tracking_started(self):
        """Handle tracking mode started."""
        logger.info("Tracking started")

        # Ensure tracker has seeds
        seeds = self.tracker.get_manual_seeds()
        if not seeds:
            logger.warning("No dots selected - tracking will have no dots")

    def closeEvent(self, event):
        """Handle window close."""
        logger.info("Shutting down camera...")

        # Stop camera thread
        if isinstance(self.camera, MockCamera):
            self.camera.stop()
        else:
            self.camera.stop()
            self.camera.disconnect()

        event.accept()


def main():
    """Run standalone demo app."""
    import argparse

    parser = argparse.ArgumentParser(description="Manual Dot Selection Demo")
    parser.add_argument(
        "--real-camera",
        action="store_true",
        help="Use real Basler camera instead of MockCamera",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    window = ManualDotSelectionApp(use_real_camera=args.real_camera)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
