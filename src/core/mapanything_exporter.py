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
"""