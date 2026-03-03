"""Dual camera feed panel — two QLabel frames side by side."""

import logging

import numpy as np
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

from src.core.basler_camera import BaslerCamera

logger = logging.getLogger(__name__)

_PLACEHOLDER_STYLE = """
    QLabel {
        background-color: #2a2a2a;
        color: #666;
        font-size: 16px;
        border: 1px solid #444;
        border-radius: 4px;
    }
"""


class CameraPanel(QWidget):
    """Side-by-side display of two Basler camera feeds."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Left camera
        left_container = QVBoxLayout()
        self._left_title = QLabel("Camera 1")
        self._left_title.setStyleSheet("color: #aaa; font-size: 12px;")
        self._left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_container.addWidget(self._left_title)

        self._left_label = QLabel("No Camera")
        self._left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_label.setStyleSheet(_PLACEHOLDER_STYLE)
        self._left_label.setMinimumSize(320, 200)
        left_container.addWidget(self._left_label, stretch=1)
        layout.addLayout(left_container)

        # Right camera
        right_container = QVBoxLayout()
        self._right_title = QLabel("Camera 2")
        self._right_title.setStyleSheet("color: #aaa; font-size: 12px;")
        self._right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_container.addWidget(self._right_title)

        self._right_label = QLabel("No Camera")
        self._right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_label.setStyleSheet(_PLACEHOLDER_STYLE)
        self._right_label.setMinimumSize(320, 200)
        right_container.addWidget(self._right_label, stretch=1)
        layout.addLayout(right_container)

        # Camera threads
        self._left_camera: BaslerCamera | None = None
        self._right_camera: BaslerCamera | None = None

        self._auto_connect_cameras()

    def _auto_connect_cameras(self) -> None:
        """Detect and connect to available Basler cameras."""
        cameras = BaslerCamera.list_cameras()
        logger.info(f"Found {len(cameras)} Basler camera(s)")

        if len(cameras) >= 1:
            self._left_camera = BaslerCamera()
            if self._left_camera.connect(0):
                self._left_camera.frame_ready.connect(self._update_left)
                self._left_camera.fps_updated.connect(
                    lambda fps: self._left_title.setText(f"Camera 1  ({fps:.0f} FPS)")
                )
                self._left_camera.start()
                self._left_label.setStyleSheet("")

        if len(cameras) >= 2:
            self._right_camera = BaslerCamera()
            if self._right_camera.connect(1):
                self._right_camera.frame_ready.connect(self._update_right)
                self._right_camera.fps_updated.connect(
                    lambda fps: self._right_title.setText(f"Camera 2  ({fps:.0f} FPS)")
                )
                self._right_camera.start()
                self._right_label.setStyleSheet("")

    def _update_left(self, data: dict) -> None:
        self._display_frame(self._left_label, data["frame"])

    def _update_right(self, data: dict) -> None:
        self._display_frame(self._right_label, data["frame"])

    def _display_frame(self, label: QLabel, frame: np.ndarray) -> None:
        """Convert numpy frame to QPixmap and display on label."""
        h, w = frame.shape[:2]
        if frame.ndim == 2:
            # Grayscale
            qimg = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            # Color (BGR → RGB)
            qimg = QImage(frame.data, w, h, w * 3, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def stop_cameras(self) -> None:
        """Stop all camera threads."""
        if self._left_camera:
            self._left_camera.stop()
            self._left_camera.disconnect()
        if self._right_camera:
            self._right_camera.stop()
            self._right_camera.disconnect()
