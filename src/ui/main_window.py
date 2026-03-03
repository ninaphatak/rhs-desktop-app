"""Main application window for RHS Monitor."""

from PySide6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):
    """Top-level window — will be populated in later phases."""

    def __init__(self, mock: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.mock = mock
        self.setWindowTitle("RHS Monitor")

        # Placeholder content — replaced in Phase 2+
        central = QWidget()
        layout = QVBoxLayout(central)
        label = QLabel("RHS Monitor — ready")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 24px; color: white;")
        layout.addWidget(label)
        self.setCentralWidget(central)

        # Dark theme
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")
