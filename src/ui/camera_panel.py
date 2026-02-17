"""
Camera Panel - PyQt6 UI for live camera tracking with user controls

Purpose: Display camera feed with dot overlay and provide user interaction
         for setting reference, recording data, and tuning detection parameters.

Class Structure:
    CameraPanel(QWidget)
    │
    ├── Attributes:
    │   ├── video_label: QLabel              # Frame display
    │   ├── set_reference_btn: QPushButton   # Set reference positions
    │   ├── record_btn: QPushButton          # Toggle recording
    │   ├── reset_btn: QPushButton           # Reset tracker
    │   ├── threshold_slider: QSlider        # Adjust threshold
    │   ├── show_ids_checkbox: QCheckBox     # Toggle ID display
    │   ├── show_displacement_checkbox: QCheckBox  # Toggle displacement vectors
    │   ├── status_label: QLabel             # Current status
    │   ├── fps_label: QLabel                # FPS counter
    │   └── dot_count_label: QLabel          # Number of dots tracked
    │
    ├── Signals:
    │   ├── reference_set_requested()
    │   ├── recording_toggled(bool)
    │   ├── tracker_reset_requested()
    │   └── threshold_changed(int)
    │
    └── Methods:
        ├── update_frame(frame: ndarray)
        ├── update_tracking_info(tracking_data: dict)
        └── update_fps(fps: float)
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QCheckBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap
import numpy as np


class CameraPanel(QWidget):
    """Camera tracking panel with user controls."""

    # Signals
    reference_set_requested = pyqtSignal()
    recording_toggled = pyqtSignal(bool)
    tracker_reset_requested = pyqtSignal()
    threshold_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._setup_ui()

        # State
        self._is_recording = False

    def _setup_ui(self):
        """Setup UI layout with all controls."""
        layout = QVBoxLayout()

        # Video display
        self.video_label = QLabel()
        self.video_label.setMinimumSize(800, 600)
        self.video_label.setStyleSheet("border: 1px solid gray;")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setText("Camera feed will appear here")
        layout.addWidget(self.video_label)

        # Control buttons
        button_layout = QHBoxLayout()

        self.set_reference_btn = QPushButton("Set Reference")
        self.set_reference_btn.setToolTip("Set current dot positions as reference for displacement tracking")
        self.set_reference_btn.clicked.connect(self._on_set_reference_clicked)
        button_layout.addWidget(self.set_reference_btn)

        self.record_btn = QPushButton("Start Recording")
        self.record_btn.setCheckable(True)
        self.record_btn.setToolTip("Start/stop recording tracking data to CSV")
        self.record_btn.clicked.connect(self._on_record_clicked)
        button_layout.addWidget(self.record_btn)

        self.reset_btn = QPushButton("Reset Tracker")
        self.reset_btn.setToolTip("Clear dot IDs and reference positions")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        # Threshold control
        threshold_group = QGroupBox("Blob Detection Threshold")
        threshold_layout = QVBoxLayout()

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(255)
        self.threshold_slider.setValue(100)
        self.threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.threshold_slider.setTickInterval(25)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider)

        self.threshold_label = QLabel("Threshold: 100")
        threshold_layout.addWidget(self.threshold_label)

        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)

        # Display options
        display_layout = QHBoxLayout()

        self.show_ids_checkbox = QCheckBox("Show Dot IDs")
        self.show_ids_checkbox.setChecked(True)
        display_layout.addWidget(self.show_ids_checkbox)

        self.show_displacement_checkbox = QCheckBox("Show Displacement Vectors")
        self.show_displacement_checkbox.setChecked(True)
        display_layout.addWidget(self.show_displacement_checkbox)

        layout.addLayout(display_layout)

        # Status display
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label)

        self.fps_label = QLabel("FPS: --")
        layout.addWidget(self.fps_label)

        self.dot_count_label = QLabel("Dots: 0")
        layout.addWidget(self.dot_count_label)

        self.setLayout(layout)

    @pyqtSlot()
    def _on_set_reference_clicked(self):
        """Handle Set Reference button click."""
        self.reference_set_requested.emit()
        self.status_label.setText("Status: Reference set!")
        self.status_label.setStyleSheet("color: green;")

    @pyqtSlot()
    def _on_record_clicked(self):
        """Handle Record button toggle."""
        self._is_recording = self.record_btn.isChecked()

        if self._is_recording:
            self.record_btn.setText("Stop Recording")
            self.status_label.setText("Status: Recording...")
            self.status_label.setStyleSheet("color: red;")
        else:
            self.record_btn.setText("Start Recording")
            self.status_label.setText("Status: Recording stopped")
            self.status_label.setStyleSheet("color: blue;")

        self.recording_toggled.emit(self._is_recording)

    @pyqtSlot()
    def _on_reset_clicked(self):
        """Handle Reset button click."""
        self.tracker_reset_requested.emit()
        self.status_label.setText("Status: Tracker reset")
        self.status_label.setStyleSheet("color: orange;")

    @pyqtSlot(int)
    def _on_threshold_changed(self, value):
        """Handle threshold slider change."""
        self.threshold_label.setText(f"Threshold: {value}")
        self.threshold_changed.emit(value)

    def update_frame(self, frame: np.ndarray):
        """Update video display with annotated frame."""
        if frame is None:
            return

        # Convert numpy array to QPixmap
        if len(frame.shape) == 2:
            # Grayscale
            height, width = frame.shape
            bytes_per_line = width
            q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        else:
            # BGR to RGB
            height, width, channels = frame.shape
            bytes_per_line = channels * width
            rgb_frame = frame[:, :, ::-1].copy()  # BGR to RGB
            q_image = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(q_image)
        self.video_label.setPixmap(pixmap.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def update_tracking_info(self, tracking_data: dict):
        """Update tracking information display."""
        self.dot_count_label.setText(f"Dots: {tracking_data['dot_count']}")

    def update_fps(self, fps: float):
        """Update FPS display."""
        self.fps_label.setText(f"FPS: {fps:.1f}")
