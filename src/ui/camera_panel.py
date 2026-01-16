"""
Docstring for camera_panel
**Purpose:** Display camera feed with dot overlay

**Class Structure:**
```
CameraPanel(QWidget)
│
├── Attributes:
│   ├── video_label: QLabel          # Frame display
│   ├── fps_label: QLabel            # FPS counter
│   ├── dot_labels: list[QLabel]     # Dot position displays
│   └── show_overlay: bool           # Toggle dot circles
│
├── Methods:
│   ├── update_frame(frame_data: dict)    # Display new frame
│   ├── update_tracking(tracking: dict)   # Update dot positions
│   ├── set_overlay_visible(visible: bool)
│   └── _convert_frame(frame: ndarray) → QPixmap
```

"""