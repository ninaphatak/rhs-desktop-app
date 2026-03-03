"""
Docstring for config

Purpose: Load/save application settings

Default Config:
"""
DEFAULT_CONFIG = {
    "arduino": {
        "baud_rate": 31250,
        "timeout": 1.0,
        "last_port": None,
    },
    "camera": {
        "fps": 60,
        "exposure_us": 1000,
        "last_index": 0,
    },
    "tracking": {
        "threshold": 50,
        "min_area": 30,
        "max_area": 500,
    },
    "display": {
        "time_window_seconds": 5,
        "show_dot_overlay": True,
    },
    "output": {
        "directory": "output",
    },
}