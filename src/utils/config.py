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
        "threshold": 100,           # Increased from 50 (dots very dark in real images)
        "min_area": 50,             # Tightened from 30
        "max_area": 300,            # Tightened from 500
        "use_optical_flow": True,   # Enable LK tracking
        "lk_window_size": 15,       # LK window (matches dot diameter)
        "lk_max_level": 2,          # Pyramid levels for ~45px displacement
        "lk_match_radius": 15,      # Max distance for LK-detection association
        "max_lost_frames": 10,      # Frames before dot permanently lost
        "circularity_threshold": 0.5,  # Relaxed from 0.7 (irregular dots)
    },
    "display": {
        "time_window_seconds": 5,
        "show_dot_overlay": True,
    },
    "output": {
        "directory": "output",
    },
}