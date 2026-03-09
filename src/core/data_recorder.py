"""On-demand CSV data recorder for RHS sensor data."""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import TextIO

from src.utils.config import CSV_HEADERS, OUTPUTS_DIR, SERIAL_FIELDS

logger = logging.getLogger(__name__)


class DataRecorder:
    """Start/stop CSV recording. Each recording gets an auto-named file."""

    def __init__(self) -> None:
        self._file: TextIO | None = None
        self._writer: csv.writer | None = None
        self._recording = False
        self._record_start: float | None = None
        self._current_path: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def current_filename(self) -> str | None:
        if self._current_path:
            return self._current_path.name
        return None

    def start_recording(self) -> str:
        """Begin recording to a new CSV file.

        Returns:
            The filename of the new CSV.
        """
        if self._recording:
            self.stop_recording()

        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"rhs_{timestamp}.csv"
        self._current_path = OUTPUTS_DIR / filename

        self._file = open(self._current_path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(CSV_HEADERS)

        self._record_start = None
        self._recording = True
        logger.info(f"Recording started: {filename}")
        return filename

    def stop_recording(self) -> None:
        """Stop recording and close the file."""
        if not self._recording:
            return

        self._recording = False
        if self._file:
            self._file.close()
            self._file = None
        self._writer = None
        logger.info(f"Recording stopped: {self._current_path}")

    def record_row(self, data: dict) -> None:
        """Write one row of sensor data to the CSV.

        Called by SerialReader.data_received when recording is active.
        """
        if not self._recording or not self._writer:
            return

        # Set t=0 on first sample
        if self._record_start is None:
            self._record_start = data["timestamp"]

        t = round(data["timestamp"] - self._record_start, 4)
        row = [t] + [data.get(field, 0.0) for field in SERIAL_FIELDS if field != "flow"]
        self._writer.writerow(row)
