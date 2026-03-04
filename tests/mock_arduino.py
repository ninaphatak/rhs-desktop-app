"""Mock Arduino — replays bundled CSV sensor data for testing."""

import csv
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal


# Firmware timing: delay_ms = 0.1 * abs(30.0 / BPM) * 1000
# At BPM=60: 0.1 * 0.5 * 1000 = 50 ms → 20 Hz
_MOCK_BPM = 60
_DELAY_SEC = 0.1 * abs(30.0 / _MOCK_BPM)  # 0.05 s

_CSV_PATH = Path(__file__).resolve().parent / "mock_data.csv"

_FIELD_MAP = {
    "Pressure 1 (mmHg)": "p1",
    "Pressure 2 (mmHg)": "p2",
    "Flow Rate (mL/s)": "flow",
    "Heart Rate (BPM)": "hr",
    "Ventricle Temperature 1 (C)": "vt1",
    "Ventricle Temperature 2 (C)": "vt2",
    "Atrium Temperature (C)": "at1",
}


class MockArduino(QThread):
    """Replays CSV sensor data at firmware-derived timing (~20 Hz at 60 BPM)."""

    data_received = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        self._rows: list[dict[str, float]] = []
        self._load_csv()

    def _load_csv(self) -> None:
        """Load mock_data.csv rows into memory."""
        with open(_CSV_PATH, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                parsed = {}
                for csv_col, field in _FIELD_MAP.items():
                    parsed[field] = float(row[csv_col])
                self._rows.append(parsed)

    def get_sample(self, idx: int = 0) -> dict:
        """Return a single data row with a live timestamp (for testing)."""
        row = dict(self._rows[idx % len(self._rows)])
        row["timestamp"] = time.time()
        return row

    def run(self) -> None:
        """Emit CSV rows at firmware timing, looping when exhausted."""
        self._running = True
        self.connection_changed.emit(True)
        idx = 0

        while self._running:
            row = self._rows[idx]
            row["timestamp"] = time.time()
            self.data_received.emit(row)

            idx = (idx + 1) % len(self._rows)
            time.sleep(_DELAY_SEC)

        self.connection_changed.emit(False)

    def stop(self) -> None:
        """Stop the replay thread."""
        self._running = False
        self.wait(2000)
