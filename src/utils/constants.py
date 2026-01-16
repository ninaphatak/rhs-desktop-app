"""
Docstring for constants

Purpose: Application-wide constants
"""

APP_NAME = "RHS Desktop"
APP_VERSION = "1.0.0"

# Sensor ranges (from technical specs)
PRESSURE_RANGE = (0, 258)          # mmHg (PT5PSI max)
FLOW_RATE_TARGET = 1.5             # L/min
HEART_RATE_RANGE = (60, 100)       # BPM

# Arduino
ARDUINO_BAUD_RATE = 31250
ARDUINO_DATA_FIELDS = ["p1", "p2", "flow_rate", "heart_rate"]

# Camera
CAMERA_RESOLUTION = (1920, 1200)
CAMERA_DEFAULT_FPS = 60
CAMERA_DEFAULT_EXPOSURE = 1000     # microseconds

# Display
GRAPH_TIME_WINDOW = 5              # seconds

