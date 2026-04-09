"""Synced video + sensor data review dialog — mirrors the main UI layout."""

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
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QMessageBox,
    QSizePolicy,
    QWidget,
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, QTimer

from src.utils.config import OUTPUTS_DIR, VIDEOS_DIR, CAMERA_FPS, COLORS

logger = logging.getLogger(__name__)

# Playback step size in seconds for << and >> buttons
STEP_SECONDS = 5


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

    sessions.sort(key=lambda s: s["timestamp"], reverse=True)
    return sessions


class ReviewDialog(QDialog):
    """Synced playback of two camera videos alongside sensor data graphs.

    Layout mirrors the main UI: 2x2 graph grid on top, dual camera feeds
    in the middle, transport controls at the bottom.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Recording")
        self.resize(1400, 900)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; color: white; }")

        self._cap1: Optional[cv2.VideoCapture] = None
        self._cap2: Optional[cv2.VideoCapture] = None
        self._df: Optional[pd.DataFrame] = None
        self._time_arr: Optional[np.ndarray] = None
        self._total_time = 0.0
        self._current_time = 0.0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_tick)

        self._build_ui()
        self._load_sessions()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct the dialog layout to mirror the main UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # -- Session selector --
        selector_layout = QHBoxLayout()
        selector_label = QLabel("Session:")
        selector_label.setStyleSheet("color: white; font-size: 14px;")
        selector_layout.addWidget(selector_label)
        self._session_combo = QComboBox()
        self._session_combo.setStyleSheet(
            "QComboBox { background: #333; color: white; padding: 4px; font-size: 14px; }"
        )
        self._session_combo.currentIndexChanged.connect(self._on_session_changed)
        selector_layout.addWidget(self._session_combo, stretch=1)
        layout.addLayout(selector_layout)

        # -- 2x2 Graph grid (matches GraphPanel) --
        self._build_graphs(layout)

        # -- Camera feeds (matches CameraPanel) --
        self._build_cameras(layout)

        # -- Transport controls --
        self._build_transport(layout)

    def _build_graphs(self, parent_layout: QVBoxLayout) -> None:
        """Build the 2x2 graph grid matching GraphPanel styling."""
        graph_widget = QWidget()
        grid = QGridLayout(graph_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(4)

        tick_font = pg.QtGui.QFont()
        tick_font.setPixelSize(20)
        label_style = {"font-size": "20px", "color": "white"}

        # -- Pressure (top-left) --
        self._pressure_plot = pg.PlotWidget(title="Pressure")
        self._pressure_plot.setLabel("left", "mmHg", **label_style)
        self._pressure_plot.setLabel("bottom", "Time (s)", **label_style)
        self._pressure_plot.addLegend(labelTextSize="14pt")
        self._p1_curve = self._pressure_plot.plot(
            pen=pg.mkPen(COLORS["p1"], width=2), name="P1 (Atrium)",
            symbol="o", symbolSize=5, symbolBrush=COLORS["p1"],
        )
        self._p2_curve = self._pressure_plot.plot(
            pen=pg.mkPen(COLORS["p2"], width=2), name="P2 (Ventricle)",
            symbol="o", symbolSize=5, symbolBrush=COLORS["p2"],
        )
        grid.addWidget(self._pressure_plot, 0, 0)

        # -- Flow rate (top-right) --
        self._flow_plot = pg.PlotWidget(title="Flow Rate")
        self._flow_plot.setLabel("left", "mL/s", **label_style)
        self._flow_plot.setLabel("bottom", "Time (s)", **label_style)
        self._flow_plot.addLegend(labelTextSize="14pt")
        self._flow_curve = self._flow_plot.plot(
            pen=pg.mkPen(COLORS["flow"], width=2), name="Flow",
            symbol="o", symbolSize=5, symbolBrush=COLORS["flow"],
        )
        grid.addWidget(self._flow_plot, 0, 1)

        # -- Heart rate (bottom-left) --
        self._hr_plot = pg.PlotWidget(title="Heart Rate")
        self._hr_plot.setLabel("left", "BPM", **label_style)
        self._hr_plot.setLabel("bottom", "Time (s)", **label_style)
        self._hr_plot.addLegend(labelTextSize="14pt")
        self._hr_curve = self._hr_plot.plot(
            pen=pg.mkPen(COLORS["hr"], width=2), name="HR",
            symbol="o", symbolSize=5, symbolBrush=COLORS["hr"],
        )
        grid.addWidget(self._hr_plot, 1, 0)

        # -- Temperature (bottom-right) --
        self._temp_plot = pg.PlotWidget(title="Temperature")
        self._temp_plot.setLabel("left", "C", **label_style)
        self._temp_plot.setLabel("bottom", "Time (s)", **label_style)
        self._temp_plot.addLegend(labelTextSize="14pt")
        self._vt1_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["vt1"], width=2), name="VT1",
            symbol="o", symbolSize=5, symbolBrush=COLORS["vt1"],
        )
        self._vt2_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["vt2"], width=2), name="VT2",
            symbol="o", symbolSize=5, symbolBrush=COLORS["vt2"],
        )
        self._at1_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["at1"], width=2), name="AT1",
            symbol="o", symbolSize=5, symbolBrush=COLORS["at1"],
        )
        grid.addWidget(self._temp_plot, 1, 1)

        # Apply dark theme + tick font to all plots, add cursor lines
        self._plots = [self._pressure_plot, self._flow_plot, self._hr_plot, self._temp_plot]
        self._cursor_lines = []
        for plot in self._plots:
            plot.setBackground("#1e1e1e")
            for axis_name in ("bottom", "left"):
                plot.getAxis(axis_name).setTickFont(tick_font)
                plot.getAxis(axis_name).setTextPen("white")
            cursor = pg.InfiniteLine(
                pos=0, angle=90,
                pen=pg.mkPen("w", width=1, style=Qt.PenStyle.DashLine),
            )
            plot.addItem(cursor)
            self._cursor_lines.append(cursor)

        parent_layout.addWidget(graph_widget, stretch=3)

    def _build_cameras(self, parent_layout: QVBoxLayout) -> None:
        """Build side-by-side camera labels matching CameraPanel styling."""
        camera_widget = QWidget()
        cam_layout = QHBoxLayout(camera_widget)
        cam_layout.setContentsMargins(4, 4, 4, 4)
        cam_layout.setSpacing(8)

        placeholder_style = """
            QLabel {
                background-color: #2a2a2a;
                color: #666;
                font-size: 16px;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """

        self._left_label = QLabel("Camera 1")
        self._left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_label.setStyleSheet(placeholder_style)
        self._left_label.setMinimumSize(320, 200)
        self._left_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        cam_layout.addWidget(self._left_label)

        self._right_label = QLabel("Camera 2")
        self._right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_label.setStyleSheet(placeholder_style)
        self._right_label.setMinimumSize(320, 200)
        self._right_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        cam_layout.addWidget(self._right_label)

        parent_layout.addWidget(camera_widget, stretch=2)

    def _build_transport(self, parent_layout: QVBoxLayout) -> None:
        """Build transport controls: play/pause, -5s/+5s, slider, time."""
        transport_layout = QHBoxLayout()
        transport_layout.setContentsMargins(8, 4, 8, 4)

        btn_style = """
            QPushButton {
                background-color: #333; color: white;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px 18px; font-size: 14px;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #555; }
        """

        self._play_btn = QPushButton("Play")
        self._play_btn.setStyleSheet(btn_style)
        self._play_btn.clicked.connect(self._toggle_play)
        transport_layout.addWidget(self._play_btn)

        self._back_btn = QPushButton("-5s")
        self._back_btn.setStyleSheet(btn_style)
        self._back_btn.clicked.connect(self._step_back)
        transport_layout.addWidget(self._back_btn)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        transport_layout.addWidget(self._slider, stretch=1)

        self._forward_btn = QPushButton("+5s")
        self._forward_btn.setStyleSheet(btn_style)
        self._forward_btn.clicked.connect(self._step_forward)
        transport_layout.addWidget(self._forward_btn)

        self._time_label = QLabel("0.00 / 0.00 s")
        self._time_label.setStyleSheet("color: #aaa; font-size: 14px; margin-left: 12px;")
        transport_layout.addWidget(self._time_label)

        parent_layout.addLayout(transport_layout)

    # ------------------------------------------------------------------
    # Session loading
    # ------------------------------------------------------------------

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

        if "Time (s)" not in self._df.columns:
            QMessageBox.critical(self, "Error", "CSV missing 'Time (s)' column.")
            return

        self._time_arr = self._df["Time (s)"].values
        self._total_time = float(self._time_arr[-1]) if len(self._time_arr) > 0 else 0.0

        # Open video captures
        self._cap1 = cv2.VideoCapture(str(session["cam1"]))
        self._cap2 = cv2.VideoCapture(str(session["cam2"]))

        if not self._cap1.isOpened() or not self._cap2.isOpened():
            QMessageBox.critical(self, "Error", "Failed to open video files.")
            self._release_captures()
            return

        # Setup slider (in centiseconds for smooth scrubbing)
        self._slider.setMaximum(int(self._total_time * 100))
        self._slider.setValue(0)
        self._current_time = 0.0

        # Plot full CSV data
        self._plot_csv()

        # Show initial state
        self._update_display(0.0)

    # ------------------------------------------------------------------
    # Graph plotting
    # ------------------------------------------------------------------

    def _plot_csv(self) -> None:
        """Plot all CSV channels on the 2x2 graph grid."""
        if self._df is None or self._time_arr is None:
            return

        t = self._time_arr

        col = self._df
        if "Pressure 1 (mmHg)" in col.columns:
            self._p1_curve.setData(t, col["Pressure 1 (mmHg)"].values)
        if "Pressure 2 (mmHg)" in col.columns:
            self._p2_curve.setData(t, col["Pressure 2 (mmHg)"].values)
        if "Flow Rate (mL/s)" in col.columns:
            self._flow_curve.setData(t, col["Flow Rate (mL/s)"].values)
        if "Heart Rate (BPM)" in col.columns:
            self._hr_curve.setData(t, col["Heart Rate (BPM)"].values)
        if "Ventricle Temperature 1 (C)" in col.columns:
            self._vt1_curve.setData(t, col["Ventricle Temperature 1 (C)"].values)
        if "Ventricle Temperature 2 (C)" in col.columns:
            self._vt2_curve.setData(t, col["Ventricle Temperature 2 (C)"].values)
        if "Atrium Temperature (C)" in col.columns:
            self._at1_curve.setData(t, col["Atrium Temperature (C)"].values)

        # Disable Y auto-range so scroll-wheel zoom on Y axes persists
        # (X range is controlled by the sliding 5s window in _update_display)
        for plot in self._plots:
            plot.enableAutoRange(axis="x", enable=False)
            plot.enableAutoRange(axis="y", enable=False)
            plot.setAutoVisible(y=True)

    # ------------------------------------------------------------------
    # Display update (single method syncs everything)
    # ------------------------------------------------------------------

    def _update_display(self, time_sec: float) -> None:
        """Update graphs, videos, and time label to match time_sec."""
        self._current_time = max(0.0, min(time_sec, self._total_time))

        # Update rolling 5s graph window + cursor lines
        for plot in self._plots:
            plot.setXRange(self._current_time - 5, self._current_time, padding=0)
        for cursor in self._cursor_lines:
            cursor.setValue(self._current_time)

        # Seek video frames
        frame_idx = int(self._current_time * CAMERA_FPS)
        self._show_video_frame(self._cap1, self._left_label, frame_idx)
        self._show_video_frame(self._cap2, self._right_label, frame_idx)

        # Update time label
        self._time_label.setText(f"{self._current_time:.2f} / {self._total_time:.2f} s")

    def _show_video_frame(self, cap: Optional[cv2.VideoCapture],
                          label: QLabel, frame_idx: int) -> None:
        """Seek a video capture to frame_idx and display it on a QLabel."""
        if cap is None or not cap.isOpened():
            return

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            return

        h, w = frame.shape[:2]
        if frame.ndim == 2:
            qimg = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(qimg)

        label_w, label_h = label.width(), label.height()
        if label_w <= 0 or label_h <= 0:
            label.setPixmap(pixmap)
            return

        scaled = pixmap.scaled(
            label_w, label_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        label.setPixmap(scaled)

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------

    def _on_slider_changed(self, value: int) -> None:
        """Handle slider drag — value is in centiseconds."""
        time_sec = value / 100.0
        if abs(time_sec - self._current_time) > 0.005:
            self._update_display(time_sec)

    def _toggle_play(self) -> None:
        """Toggle play/pause."""
        if self._playing:
            self._stop_playback()
        else:
            self._playing = True
            self._play_btn.setText("Pause")
            # Tick at ~30Hz to match camera FPS
            self._timer.start(int(1000 / CAMERA_FPS))

    def _stop_playback(self) -> None:
        """Pause playback."""
        self._playing = False
        self._timer.stop()
        self._play_btn.setText("Play")

    def _advance_tick(self) -> None:
        """Advance playback by one frame interval."""
        new_time = self._current_time + (1.0 / CAMERA_FPS)
        if new_time >= self._total_time:
            self._stop_playback()
            return
        self._slider.blockSignals(True)
        self._slider.setValue(int(new_time * 100))
        self._slider.blockSignals(False)
        self._update_display(new_time)

    def _step_back(self) -> None:
        """Jump back 5 seconds."""
        new_time = max(0.0, self._current_time - STEP_SECONDS)
        self._slider.setValue(int(new_time * 100))

    def _step_forward(self) -> None:
        """Jump forward 5 seconds."""
        new_time = min(self._total_time, self._current_time + STEP_SECONDS)
        self._slider.setValue(int(new_time * 100))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

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
