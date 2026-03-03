"""QThread-based serial reader for the RHS Arduino (7-field protocol)."""

import time
import logging

import serial
from PySide6.QtCore import QThread, Signal

from src.utils.config import BAUD_RATE, SERIAL_FIELD_COUNT, SERIAL_FIELDS
from src.utils.port_detection import find_serial_port

logger = logging.getLogger(__name__)


class SerialReader(QThread):
    """Reads Arduino serial data on a background thread.

    Emits parsed sensor dicts at ~30Hz.
    Protocol: "P1 P2 FLOW HR VT1 VT2 AT1\\n" (space-separated, 31250 baud).
    """

    data_received = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, port: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._port = port
        self._serial: serial.Serial | None = None
        self._running = False

    def run(self) -> None:
        """Thread main loop — connect, read, parse, emit."""
        # Auto-detect port if not specified
        port = self._port or find_serial_port()
        if port is None:
            self.error_occurred.emit("No Arduino found")
            self.connection_changed.emit(False)
            return

        try:
            self._serial = serial.Serial(port, BAUD_RATE, timeout=1)
            # Reset Arduino state
            self._serial.setDTR(False)
            time.sleep(0.5)
            self._serial.flushInput()
            self._serial.setDTR(True)
            time.sleep(0.5)
            self._serial.flushInput()

            self._running = True
            self.connection_changed.emit(True)
            logger.info(f"Connected to Arduino on {port}")

        except serial.SerialException as e:
            self.error_occurred.emit(f"Serial connection failed: {e}")
            self.connection_changed.emit(False)
            return

        while self._running:
            try:
                if self._serial.in_waiting == 0:
                    time.sleep(0.001)
                    continue

                raw = self._serial.readline()
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                values = line.split()
                if len(values) != SERIAL_FIELD_COUNT:
                    continue

                data = {"timestamp": time.time()}
                for key, val_str in zip(SERIAL_FIELDS, values):
                    try:
                        data[key] = round(float(val_str), 2)
                    except ValueError:
                        data[key] = 0.0

                self.data_received.emit(data)

            except serial.SerialException as e:
                self.error_occurred.emit(f"Serial read error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in serial loop: {e}")
                time.sleep(0.01)

        # Cleanup
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        self.connection_changed.emit(False)
        logger.info("Serial reader stopped")

    def stop(self) -> None:
        """Stop the reader thread."""
        self._running = False
        if self.isRunning():
            self.wait(2000)
