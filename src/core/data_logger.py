"""
Docstring for data_logger
---

### `src/core/data_logger.py`

**Purpose:** Record sensor data, dot positions, and frames to disk

**Input:**
- Output directory path
- Sensor data dict
- Tracking data dict
- Frames (optional, for MapAnything export)

**Output:**
- CSV file with columns: timestamp, elapsed, p1, p2, flow_rate, heart_rate, dot0_x, dot0_y, dot1_x, dot1_y, ...
- Frames saved as JPG (when recording for MapAnything)

**Class Structure:**
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
"""