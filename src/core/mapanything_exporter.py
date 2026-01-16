"""
Docstring for mapanything_exporter
### `src/core/mapanything_exporter.py`

**Purpose:** Package recorded data for MapAnything processing

**Input:**
- Session folder with CSV and frames

**Output:**
```
session_20250301_143022/
├── frames/
│   ├── frame_000000.jpg
│   ├── frame_000001.jpg
│   └── ...
├── sensor_data.csv
└── metadata.json
```

**Class Structure:**
```
MapAnythingExporter
│
├── Methods:
│   ├── export(session_path: Path) → Path    # Package for MapAnything
│   ├── generate_metadata(session_path) → dict
│   └── validate_export(export_path) → bool
│
└── Internal:
    └── _create_metadata_json(session_path)

    

metadata.json format: 
{
    "camera": {
        "model": "Basler ace 2 a2A1920-160umBAS",
        "resolution": [1920, 1200],
        "fps": 60,
        "lens": "16mm"
    },
    "session": {
        "start_time": "2025-03-01T14:30:22",
        "duration_seconds": 45.2,
        "frame_count": 2712
    },
    "frames": [
        {
            "filename": "frames/frame_000000.jpg",
            "timestamp": 1709312456.123,
            "dots": [
                {"id": 0, "x": 523, "y": 412},
                {"id": 1, "x": 891, "y": 398}
            ]
        }
    ]
}
"""