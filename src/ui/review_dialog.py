"""Synced video + sensor data review dialog."""

import logging
import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, QTimer

from src.utils.config import OUTPUTS_DIR, VIDEOS_DIR, CAMERA_FPS, COLORS

logger = logging.getLogger(__name__)


def discover_sessions(outputs_dir: Path | None = None) -> list[dict]:
    """Find recording sessions that have CSV + both camera videos.

    Args:
        outputs_dir: Directory containing CSV files (default: OUTPUTS_DIR).

    Returns:
        List of session dicts sorted newest-first, each containing:
        - timestamp: str
        - csv: Path
        - cam1: Path
        - cam2: Path
    """
    if outputs_dir is None:
        outputs_dir = OUTPUTS_DIR

    videos_dir = outputs_dir / "videos"
    if not videos_dir.is_dir():
        return []

    sessions = []
    pattern = re.compile(r"^rhs_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.csv$")
    for csv_path in sorted(outputs_dir.glob("rhs_*.csv")):
        match = pattern.match(csv_path.name)
        if not match:
            continue
        ts = match.group(1)
        cam1 = videos_dir / f"camera1_{ts}.avi"
        cam2 = videos_dir / f"camera2_{ts}.avi"
        if cam1.exists() and cam2.exists():
            sessions.append({
                "timestamp": ts,
                "csv": csv_path,
                "cam1": cam1,
                "cam2": cam2,
            })

    # Newest first
    sessions.sort(key=lambda s: s["timestamp"], reverse=True)
    return sessions


class ReviewDialog(QDialog):
    """Synced playback of two camera videos alongside sensor data graphs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Recording")
        self.resize(1200, 800)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; color: white; }")

        self._cap1: Optional[cv2.VideoCapture] = None
        self._cap2: Optional[cv2.VideoCapture] = None
        self._df: Optional[pd.DataFrame] = None
        self._total_frames = 0
        self._current_frame = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._build_ui()
        self._load_sessions()

    def _build_ui(self) -> None:
        """Construct the dialog layout."""
        layout = QVBoxLayout(self)

        # Session selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Session:"))
        self._session_combo = QComboBox()
        self._session_combo.setStyleSheet(
            "QComboBox { background: #333; color: white; padding: 4px; }"
        )
        self._session_combo.currentIndexChanged.connect(self._on_session_changed)
        selector_layout.addWidget(self._session_combo, stretch=1)
        layout.addLayout(selector_layout)

        # Video frames — side by side
        video_layout = QHBoxLayout()
        self._left_label = QLabel("Camera 1")
        self._left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_label.setMinimumSize(400, 250)
        self._left_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._left_label.setStyleSheet(
            "background-color: #2a2a2a; color: #666; border: 1px solid #444;"
        )

        self._right_label = QLabel("Camera 2")
        self._right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_label.setMinimumSize(400, 250)
        self._right_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._right_label.setStyleSheet(
            "background-color: #2a2a2a; color: #666; border: 1px solid #444;"
        )

        video_layout.addWidget(self._left_label)
        video_layout.addWidget(self._right_label)
        layout.addLayout(video_layout, stretch=2)

        # Graph — pyqtgraph
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#2a2a2a")
        self._plot_widget.setLabel("bottom", "Time (s)")
        self._plot_widget.addLegend(offset=(10, 10))
        self._cursor_line = pg.InfiniteLine(
            pos=0, angle=90, pen=pg.mkPen("w", width=1, style=Qt.PenStyle.DashLine)
        )
        self._plot_widget.addItem(self._cursor_line)
        layout.addWidget(self._plot_widget, stretch=1)

        # Transport controls
        transport_layout = QHBoxLayout()

        self._play_btn = QPushButton("Play")
        self._play_btn.clicked.connect(self._toggle_play)

        self._back_btn = QPushButton("<<")
        self._back_btn.clicked.connect(self._step_back)

        self._forward_btn = QPushButton(">>")
        self._forward_btn.clicked.connect(self._step_forward)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._on_slider_changed)

        self._time_label = QLabel("0.00 / 0.00 s")
        self._time_label.setStyleSheet("color: #aaa; font-size: 12px;")

        btn_style = """
            QPushButton {
                background-color: #333; color: white;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px 14px; font-size: 13px;
            }
            QPushButton:hover { background-color: #444; }
        """
        for btn in [self._play_btn, self._back_btn, self._forward_btn]:
            btn.setStyleSheet(btn_style)

        transport_layout.addWidget(self._play_btn)
        transport_layout.addWidget(self._back_btn)
        transport_layout.addWidget(self._slider, stretch=1)
        transport_layout.addWidget(self._forward_btn)
        transport_layout.addWidget(self._time_label)
        layout.addLayout(transport_layout)

    def _load_sessions(self) -> None:
        """Populate the session dropdown."""
        self._sessions = discover_sessions()
        self._session_combo.clear()
        if not self._sessions:
            self._session_combo.addItem("No sessions found")
            self._session_combo.setEnabled(False)
            return
        for s in self._sessions:
            self._session_combo.addItem(f"rhs_{s['timestamp']}")
        self._on_session_changed(0)

    def _on_session_changed(self, index: int) -> None:
        """Load the selected session's data and videos."""
        self._stop_playback()
        self._release_captures()

        if not self._sessions or index < 0 or index >= len(self._sessions):
            return

        session = self._sessions[index]

        # Load CSV
        try:
            self._df = pd.read_csv(session["csv"])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read CSV:\n{e}")
            return

        # Open video captures
        self._cap1 = cv2.VideoCapture(str(session["cam1"]))
        self._cap2 = cv2.VideoCapture(str(session["cam2"]))

        if not self._cap1.isOpened() or not self._cap2.isOpened():
            QMessageBox.critical(self, "Error", "Failed to open video files.")
            self._release_captures()
            return

        self._total_frames = min(
            int(self._cap1.get(cv2.CAP_PROP_FRAME_COUNT)),
            int(self._cap2.get(cv2.CAP_PROP_FRAME_COUNT)),
        )

        # Setup slider
        self._slider.setMaximum(max(0, self._total_frames - 1))
        self._slider.setValue(0)
        self._current_frame = 0

        # Plot CSV data
        self._plot_csv()

        # Show first frame
        self._seek_and_display(0)

    def _plot_csv(self) -> None:
        """Plot all CSV channels on the pyqtgraph widget."""
        self._plot_widget.clear()
        self._plot_widget.addItem(self._cursor_line)

        if self._df is None or "Time (s)" not in self._df.columns:
            return

        t = self._df["Time (s)"].values

        column_map = {
            "Pressure 1 (mmHg)": "p1",
            "Pressure 2 (mmHg)": "p2",
            "Flow Rate (mL/s)": "flow",
            "Heart Rate (BPM)": "hr",
            "Ventricle Temperature 1 (C)": "vt1",
            "Ventricle Temperature 2 (C)": "vt2",
            "Atrium Temperature (C)": "at1",
        }

        for col, key in column_map.items():
            if col in self._df.columns:
                color = COLORS.get(key, (200, 200, 200))
                self._plot_widget.plot(
                    t, self._df[col].values, pen=pg.mkPen(color, width=1), name=key
                )

    def _seek_and_display(self, frame_idx: int) -> None:
        """Seek both videos to frame_idx and display the frames."""
        if not self._cap1 or not self._cap2:
            return

        self._current_frame = frame_idx

        self._cap1.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        self._cap2.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

        ret1, frame1 = self._cap1.read()
        ret2, frame2 = self._cap2.read()

        if ret1:
            self._show_frame(self._left_label, frame1)
        if ret2:
            self._show_frame(self._right_label, frame2)

        # Update cursor on graph
        current_time = frame_idx / CAMERA_FPS
        self._cursor_line.setValue(current_time)

        total_time = (self._total_frames - 1) / CAMERA_FPS if self._total_frames > 0 else 0
        self._time_label.setText(f"{current_time:.2f} / {total_time:.2f} s")

    def _show_frame(self, label: QLabel, frame: np.ndarray) -> None:
        """Convert an OpenCV frame to QPixmap and display on a QLabel."""
        h, w = frame.shape[:2]
        if frame.ndim == 2:
            qimg = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def _on_slider_changed(self, value: int) -> None:
        """Handle slider drag — seek to the frame."""
        if value != self._current_frame:
            self._seek_and_display(value)

    def _toggle_play(self) -> None:
        """Toggle play/pause."""
        if self._playing:
            self._stop_playback()
        else:
            self._playing = True
            self._play_btn.setText("Pause")
            interval_ms = int(1000 / CAMERA_FPS)
            self._timer.start(interval_ms)

    def _stop_playback(self) -> None:
        """Stop playback."""
        self._playing = False
        self._timer.stop()
        self._play_btn.setText("Play")

    def _advance_frame(self) -> None:
        """Advance one frame during playback."""
        next_frame = self._current_frame + 1
        if next_frame >= self._total_frames:
            self._stop_playback()
            return
        self._slider.setValue(next_frame)

    def _step_back(self) -> None:
        """Step back one frame."""
        if self._current_frame > 0:
            self._slider.setValue(self._current_frame - 1)

    def _step_forward(self) -> None:
        """Step forward one frame."""
        if self._current_frame < self._total_frames - 1:
            self._slider.setValue(self._current_frame + 1)

    def _release_captures(self) -> None:
        """Release any open video captures."""
        if self._cap1:
            self._cap1.release()
            self._cap1 = None
        if self._cap2:
            self._cap2.release()
            self._cap2 = None

    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self._stop_playback()
        self._release_captures()
        super().closeEvent(event)
