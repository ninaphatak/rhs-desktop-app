"""Dual camera feed panel — two QLabel frames side by side."""

import logging
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
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
        self._left_label = QLabel("No Camera")
        self._left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_label.setStyleSheet(_PLACEHOLDER_STYLE)
        self._left_label.setMinimumSize(320, 200)
        self._left_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._left_label)

        # Right camera
        self._right_label = QLabel("No Camera")
        self._right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_label.setStyleSheet(_PLACEHOLDER_STYLE)
        self._right_label.setMinimumSize(320, 200)
        self._right_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._right_label)

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
                self._left_camera.start()
                self._left_label.setStyleSheet("")

        if len(cameras) >= 2:
            self._right_camera = BaslerCamera()
            if self._right_camera.connect(1):
                self._right_camera.frame_ready.connect(self._update_right)
                self._right_camera.start()
                self._right_label.setStyleSheet("")

    def _update_left(self, data: dict) -> None:
        self._display_frame(self._left_label, data["frame"])

    def _update_right(self, data: dict) -> None:
        self._display_frame(self._right_label, data["frame"])

    def _display_frame(self, label: QLabel, frame: np.ndarray) -> None:
        """Convert numpy frame to QPixmap and crop-to-fill the label."""
        h, w = frame.shape[:2]
        if frame.ndim == 2:
            qimg = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            qimg = QImage(frame.data, w, h, w * 3, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(qimg)
        label_w, label_h = label.width(), label.height()
        if label_w <= 0 or label_h <= 0:
            return

        # Scale to cover: use the larger scale factor so no gaps remain
        scale_w = label_w / pixmap.width()
        scale_h = label_h / pixmap.height()
        scale = max(scale_w, scale_h)
        scaled = pixmap.scaled(
            int(pixmap.width() * scale),
            int(pixmap.height() * scale),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # Center-crop to label size
        x = (scaled.width() - label_w) // 2
        y = (scaled.height() - label_h) // 2
        cropped = scaled.copy(x, y, label_w, label_h)
        label.setPixmap(cropped)

    def start_recording(self, camera_index: int, output_path: Path,
                        duration_sec: float = 10.0, fps: float = 60.0) -> None:
        """Start AVI recording on the specified camera.

        If the requested FPS exceeds the camera's current target_fps,
        the camera frame rate is bumped to match so the AVI isn't
        under-sampled.
        """
        cam = self._left_camera if camera_index == 0 else self._right_camera
        if cam is None:
            logger.error(f"Camera {camera_index} not connected — cannot record")
            return
        if fps > cam.target_fps:
            cam.target_fps = fps
            cam._configure()
            logger.info(f"Camera {camera_index} FPS raised to {fps} for recording")
        cam.start_recording(output_path, duration_sec, fps)

    def stop_cameras(self) -> None:
        """Stop all camera threads."""
        if self._left_camera:
            self._left_camera.stop()
            self._left_camera.disconnect()
        if self._right_camera:
            self._right_camera.stop()
            self._right_camera.disconnect()
