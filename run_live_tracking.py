"""
Run Live Tracking - Entry point for live camera tracking with LK optical flow

Usage:
    python run_live_tracking.py              # Start with Basler camera
    python run_live_tracking.py --mock       # Start with mock camera (no hardware)

Workflow:
    1. Launch app → see live camera feed with detected dots
    2. Click "Set Reference" to capture rest positions
    3. Displacement vectors appear as valve moves
    4. Click "Start Recording" to capture data to CSV
    5. Click "Stop Recording" to save and export
    6. Click "Reset Tracker" to clear state
"""

import sys
import time
import argparse
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import pyqtSlot

from src.core.dot_tracker import DotTracker
from src.core.basler_camera import BaslerCamera
from src.ui.camera_panel import CameraPanel
from src.utils.config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class LiveTrackingApp(QMainWindow):
    """Main window for live camera tracking with LK optical flow."""

    def __init__(self, use_mock: bool = False):
        super().__init__()
        self.setWindowTitle("RHS Valve Tracking - Lucas-Kanade")

        # Load tracking config
        tracking_cfg = DEFAULT_CONFIG["tracking"]

        # Components
        if use_mock:
            from tests.mock_camera import MockCamera
            self.camera = MockCamera()
        else:
            self.camera = BaslerCamera()

        self.tracker = DotTracker(
            threshold=tracking_cfg["threshold"],
            min_area=tracking_cfg["min_area"],
            max_area=tracking_cfg["max_area"],
            use_optical_flow=tracking_cfg["use_optical_flow"],
            lk_window_size=tracking_cfg["lk_window_size"],
            lk_max_level=tracking_cfg["lk_max_level"],
            lk_match_radius=tracking_cfg["lk_match_radius"],
            max_lost_frames=tracking_cfg["max_lost_frames"],
            circularity_threshold=tracking_cfg["circularity_threshold"],
        )
        self.camera_panel = CameraPanel()

        # Setup UI
        self.setCentralWidget(self.camera_panel)
        self.resize(1024, 800)

        # Connect signals: Camera → processing pipeline
        self.camera.frame_ready.connect(self._on_frame_received)
        self.camera.fps_updated.connect(self.camera_panel.update_fps)

        # Connect UI controls → Tracker
        self.camera_panel.reference_set_requested.connect(self.tracker.set_reference)
        self.camera_panel.tracker_reset_requested.connect(self.tracker.reset)
        self.camera_panel.threshold_changed.connect(self.tracker.set_threshold)
        self.camera_panel.recording_toggled.connect(self._on_recording_toggled)

        # Recording state
        self._recording = False
        self._recorded_data: list[dict] = []

    def start_camera(self, camera_index: int = 0):
        """Connect and start camera."""
        if self.camera.connect(camera_index):
            self.camera.start()

    def stop_camera(self):
        """Stop and disconnect camera."""
        self.camera.stop()
        self.camera.disconnect()

    @pyqtSlot(dict)
    def _on_frame_received(self, frame_data: dict):
        """Handle frame from camera — run LK tracking and update display."""
        frame = frame_data["frame"]

        # Run LK tracking on live frame
        tracking_result = self.tracker.detect(frame)

        # Annotate frame with dots and displacement vectors
        annotated = self.tracker.annotate_frame(
            frame,
            tracking_result["dots"],
            show_ids=self.camera_panel.show_ids_checkbox.isChecked(),
            show_displacement=self.camera_panel.show_displacement_checkbox.isChecked()
        )

        # Update display with live annotated video
        self.camera_panel.update_frame(annotated)
        self.camera_panel.update_tracking_info(tracking_result)

        # Record data if recording active
        if self._recording:
            self._recorded_data.append({
                "timestamp": tracking_result["timestamp"],
                "frame_number": frame_data["frame_number"],
                "dots": tracking_result["dots"],
            })

    @pyqtSlot(bool)
    def _on_recording_toggled(self, is_recording: bool):
        """Handle recording toggle."""
        self._recording = is_recording
        if is_recording:
            self._recorded_data = []
        else:
            if self._recorded_data:
                self._save_to_csv()

    def _save_to_csv(self):
        """Save recorded tracking data to CSV."""
        import pandas as pd

        rows = []
        for entry in self._recorded_data:
            for dot in entry["dots"]:
                rows.append({
                    "timestamp": entry["timestamp"],
                    "frame_number": entry["frame_number"],
                    "dot_id": dot["id"],
                    "x": dot["x"],
                    "y": dot["y"],
                    "dx": dot["dx"],
                    "dy": dot["dy"],
                    "area": dot["area"],
                })

        df = pd.DataFrame(rows)
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        filename = output_dir / f"tracking_{int(time.time())}.csv"
        df.to_csv(filename, index=False)
        logger.info(f"Saved {len(rows)} tracking points to {filename}")

    def closeEvent(self, event):
        """Clean shutdown on window close."""
        self.stop_camera()
        event.accept()


def main():
    """Entry point for live tracking application."""
    parser = argparse.ArgumentParser(description="RHS Valve Tracking")
    parser.add_argument("--mock", action="store_true", help="Use mock camera (no hardware)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    window = LiveTrackingApp(use_mock=args.mock)
    window.show()
    window.start_camera(0)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
