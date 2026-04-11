"""Control bar widget: Record, Stop, Plot, Log, Review buttons + status labels."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, QTimer, QElapsedTimer


class ControlBar(QWidget):
    """Horizontal bar with action buttons and status labels."""

    record_clicked = Signal()
    stop_clicked = Signal()
    plot_clicked = Signal()
    log_clicked = Signal()
    review_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._record_btn = QPushButton("Record")
        self._stop_btn = QPushButton("Stop")
        self._plot_btn = QPushButton("Plot")
        self._log_btn = QPushButton("Log")
        self._review_btn = QPushButton("Review")

        self._stop_btn.setEnabled(False)

        btn_style = """
            QPushButton {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #555; }
            QPushButton:disabled { color: #666; background-color: #2a2a2a; }
        """
        for btn in [self._record_btn, self._stop_btn, self._plot_btn,
                     self._log_btn, self._review_btn]:
            btn.setStyleSheet(btn_style)
            layout.addWidget(btn)

        # Status labels (stacked vertically)
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        self._status = QLabel("Not recording")
        self._status.setStyleSheet("color: #aaa; font-size: 13px; margin-left: 12px;")
        status_layout.addWidget(self._status)

        self._camera_status = QLabel("")
        self._camera_status.setStyleSheet("color: #ff4444; font-size: 13px; margin-left: 12px;")
        status_layout.addWidget(self._camera_status)

        layout.addLayout(status_layout, stretch=1)

        # Stopwatch label
        self._stopwatch_label = QLabel("")
        self._stopwatch_label.setStyleSheet(
            "color: #ff4444; font-size: 14px; font-family: monospace; margin-right: 8px;"
        )
        layout.addWidget(self._stopwatch_label)

        # Stopwatch timer (fires every 1s to update the label)
        self._elapsed_timer = QElapsedTimer()
        self._stopwatch_tick = QTimer(self)
        self._stopwatch_tick.setInterval(1000)
        self._stopwatch_tick.timeout.connect(self._update_stopwatch)

        # Connect signals
        self._record_btn.clicked.connect(self.record_clicked)
        self._stop_btn.clicked.connect(self.stop_clicked)
        self._plot_btn.clicked.connect(self.plot_clicked)
        self._log_btn.clicked.connect(self.log_clicked)
        self._review_btn.clicked.connect(self.review_clicked)

    def set_recording(self, filename: str) -> None:
        """Update UI to recording state."""
        self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status.setText(f"Recording: {filename}")
        self._status.setStyleSheet("color: #ff4444; font-size: 13px; margin-left: 12px;")
        self._elapsed_timer.start()
        self._stopwatch_label.setText("00:00:00")
        self._stopwatch_tick.start()

    def set_stopped(self) -> None:
        """Update UI to idle state."""
        self._record_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText("Not recording")
        self._status.setStyleSheet("color: #aaa; font-size: 13px; margin-left: 12px;")
        self._stopwatch_tick.stop()
        self._stopwatch_label.setText("")
        self.set_camera_recording(False)

    def set_camera_recording(self, active: bool) -> None:
        """Show or hide the camera recording status label."""
        if active:
            self._camera_status.setText("Cameras recording")
        else:
            self._camera_status.setText("")

    def _update_stopwatch(self) -> None:
        """Update the stopwatch label from the elapsed timer."""
        total_secs = self._elapsed_timer.elapsed() // 1000
        h = total_secs // 3600
        m = (total_secs % 3600) // 60
        s = total_secs % 60
        self._stopwatch_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
