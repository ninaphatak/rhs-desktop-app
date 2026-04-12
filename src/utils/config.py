"""App configuration constants for RHS Monitor."""

from pathlib import Path

# App metadata
APP_NAME = "RHS Monitor"
APP_VERSION = "2.0.0"

# Serial configuration
BAUD_RATE = 31250
SERIAL_FIELDS = ["p1", "p2", "flow", "hr", "vt1", "vt2", "at1"]
SERIAL_FIELD_COUNT = 7
SERIAL_UPDATE_RATE_HZ = 30

# CSV column headers (matches serial_reader.py output format)
CSV_HEADERS = [
    "Time (s)",
    "Pressure 1 (mmHg)",
    "Pressure 2 (mmHg)",
    "Flow Rate (mL/s)",
    "Heart Rate (BPM)",
    "Ventricle Temperature 1 (C)",
    "Ventricle Temperature 2 (C)",
    "Atrium Temperature (C)",
    "Lap",
]

# Graph configuration
GRAPH_ROLLING_WINDOW_SEC = 5
GRAPH_BUFFER_SIZE = GRAPH_ROLLING_WINDOW_SEC * SERIAL_UPDATE_RATE_HZ  # 150 samples

# Graph colors (R, G, B tuples)
COLORS = {
    "p1": (255, 0, 0),        # Red — Atrium Pressure
    "p2": (0, 100, 255),      # Blue — Ventricle Pressure
    "flow": (255, 255, 0),    # Yellow — Flow Rate
    "hr": (255, 255, 255),    # White — Heart Rate
    "vt1": (255, 0, 255),     # Magenta — Ventricle Temp 1
    "vt2": (0, 255, 255),     # Cyan — Ventricle Temp 2
    "at1": (0, 255, 0),       # Green — Atrium Temp
}

# Camera configuration
CAMERA_FPS = 30
CAMERA_EXPOSURE_US = 25000

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
RUN_LOG_PATH = OUTPUTS_DIR / "run_log.csv"
