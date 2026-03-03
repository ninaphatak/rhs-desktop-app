"""Control bar widget: Record, Stop, Plot, Log buttons + status label."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal


class ControlBar(QWidget):
    """Horizontal bar with action buttons and a status label."""

    record_clicked = Signal()
    stop_clicked = Signal()
    plot_clicked = Signal()
    log_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._record_btn = QPushButton("Record")
        self._stop_btn = QPushButton("Stop")
        self._plot_btn = QPushButton("Plot")
        self._log_btn = QPushButton("Log")

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
        for btn in [self._record_btn, self._stop_btn, self._plot_btn, self._log_btn]:
            btn.setStyleSheet(btn_style)
            layout.addWidget(btn)

        # Solenoid control (disabled — requires firmware update)
        self._start_rhs_btn = QPushButton("Start RHS")
        self._start_rhs_btn.setEnabled(False)
        self._start_rhs_btn.setToolTip("Requires firmware update — see docs/solenoid_protocol.md")
        self._start_rhs_btn.setStyleSheet(btn_style)
        layout.addWidget(self._start_rhs_btn)

        # Spacer + status
        self._status = QLabel("Not recording")
        self._status.setStyleSheet("color: #aaa; font-size: 13px; margin-left: 12px;")
        layout.addWidget(self._status, stretch=1)

        # Connect signals
        self._record_btn.clicked.connect(self.record_clicked)
        self._stop_btn.clicked.connect(self.stop_clicked)
        self._plot_btn.clicked.connect(self.plot_clicked)
        self._log_btn.clicked.connect(self.log_clicked)

    def set_recording(self, filename: str) -> None:
        """Update UI to recording state."""
        self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status.setText(f"Recording: {filename}")
        self._status.setStyleSheet("color: #ff4444; font-size: 13px; margin-left: 12px;")

    def set_stopped(self) -> None:
        """Update UI to idle state."""
        self._record_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText("Not recording")
        self._status.setStyleSheet("color: #aaa; font-size: 13px; margin-left: 12px;")
