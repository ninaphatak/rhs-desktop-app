"""DataLogger - Sensor and Tracking Data Recording

Purpose: Record sensor data, dot positions, and frames to disk for analysis.
This is READ-ONLY data logging - no control commands are logged.

Input:
- Output directory path
- Sensor data dict (P1, P2, FLOW, HR)
- Tracking data dict (dot positions)
- Frames (optional, for visualization)

Output:
- CSV file with columns: timestamp, elapsed, p1, p2, flow_rate, heart_rate, dot0_x, dot0_y, dot1_x, dot1_y, ...
- Frames saved as JPG (optional)

Class Structure:
```
DataLogger(QThread)
│
├── Signals:
│   ├── recording_started(str)   # Emitted with filepath
│   ├── recording_stopped(str)   # Emitted with filepath
│   ├── frame_saved(int)         # Emitted with frame count
│   └── error_occurred(str)      # Emitted on error
│
├── Attributes:
│   ├── output_dir: Path
│   ├── _queue: Queue            # Thread-safe data queue
│   ├── _recording: bool
│   ├── _csv_file: file handle
│   ├── _start_time: float
│   └── _frame_count: int
│
├── Methods:
│   ├── start_recording(save_frames: bool) → str  # Begin recording
│   ├── stop_recording() → str                     # End recording
│   ├── log_data(sensor: dict, tracking: dict, frame: ndarray)
│   ├── run()                    # Thread loop: write from queue
│   └── stop()                   # Stop thread
│
└── Internal:
    ├── _create_session_folder() → Path
    ├── _write_csv_header()
    ├── _write_csv_row(data: dict)
    └── _save_frame(frame: ndarray, index: int)
```

Example usage:
```python
from PyQt6.QtCore import QThread, pyqtSignal as Signal
from queue import Queue
import time

class DataLogger(QThread):
    recording_started = Signal(str)
    recording_stopped = Signal(str)
    frame_saved = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, output_dir):
        super().__init__()
        self.output_dir = output_dir
        self._queue = Queue()
        self._recording = False
        self._csv_file = None
        self._start_time = None
        self._frame_count = 0

    def log_data(self, sensor: dict, tracking: dict, frame=None):
        # Queue data for writing (sensor data only, no control commands)
        if self._recording:
            elapsed = time.time() - self._start_time if self._start_time else 0
            row = {
                'timestamp': sensor.get('timestamp', time.time()),
                'elapsed': elapsed,
                'p1': sensor.get('P1', 0),
                'p2': sensor.get('P2', 0),
                'flow_rate': sensor.get('FLOW', 0),
                'heart_rate': sensor.get('HR', 0),
                **tracking  # dot positions
            }
            self._queue.put(('data', row))
            if frame is not None:
                self._queue.put(('frame', frame))
```
"""
