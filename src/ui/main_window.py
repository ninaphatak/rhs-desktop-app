"""Main application window for RHS Monitor."""

import logging

from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from src.core.serial_reader import SerialReader
from src.ui.graph_panel import GraphPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window: graphs + cameras + control bar."""

    def __init__(self, mock: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._mock = mock
        self.setWindowTitle("RHS Monitor")
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")

        # Central widget & layout
        central = QWidget()
        self._layout = QVBoxLayout(central)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self.setCentralWidget(central)

        # -- Graph panel --
        self._graph_panel = GraphPanel()
        self._layout.addWidget(self._graph_panel, stretch=3)

        # -- Serial reader --
        self._serial_reader: SerialReader | None = None
        self._mock_arduino = None
        self._start_serial()

    # ------------------------------------------------------------------
    # Serial
    # ------------------------------------------------------------------

    def _start_serial(self) -> None:
        """Start the appropriate data source (real or mock)."""
        if self._mock:
            self._start_mock_serial()
        else:
            self._serial_reader = SerialReader()
            self._serial_reader.data_received.connect(self._graph_panel.update_plots)
            self._serial_reader.connection_changed.connect(self._on_serial_connection)
            self._serial_reader.error_occurred.connect(self._on_serial_error)
            self._serial_reader.start()

    def _start_mock_serial(self) -> None:
        """Start the mock Arduino for demo / testing."""
        try:
            from tests.mock_arduino import MockArduino
            self._mock_arduino = MockArduino()
            self._mock_arduino.data_received.connect(self._graph_panel.update_plots)
            self._mock_arduino.connection_changed.connect(self._on_serial_connection)
            self._mock_arduino.start()
            logger.info("Mock Arduino started")
        except ImportError:
            logger.error("MockArduino not available")

    def _on_serial_connection(self, connected: bool) -> None:
        if connected:
            self._graph_panel.show_connected()
        else:
            self._graph_panel.show_no_connection()

    def _on_serial_error(self, msg: str) -> None:
        logger.error(f"Serial error: {msg}")
        self._graph_panel.show_no_connection()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Gracefully stop threads on window close."""
        if self._serial_reader:
            self._serial_reader.stop()
        if self._mock_arduino:
            self._mock_arduino.stop()
        super().closeEvent(event)
