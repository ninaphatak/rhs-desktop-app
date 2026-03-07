# Camera Panel Fix — Design Doc
_2026-03-07_

## Problem
1. **FPS fluctuates** — the grab loop has no throttle, so actual frame rate varies with system load. The FPS is displayed in the title label and visibly jumps around.
2. **Camera image too small** — title labels ("Camera 1", "Camera 2") consume vertical space, image labels lack expanding size policies, and `KeepAspectRatio` scaling leaves dead space around the image.

## Design

### 1. FPS Throttle (`basler_camera.py`)
- Add sleep-based frame-rate limiter in the grab loop: `sleep(max(0, frame_interval - elapsed))`
- Remove `fps_updated` signal, `_calc_fps()`, `_frame_times` deque, and `_last_fps_emit` — FPS is no longer displayed.

### 2. Remove Title Labels (`camera_panel.py`)
- Delete "Camera 1" / "Camera 2" QLabel widgets and their QVBoxLayout containers.
- Place image labels directly into the main QHBoxLayout.
- Remove `fps_updated` signal connections.

### 3. Fix Size Policies (`camera_panel.py`)
- Set `QSizePolicy(Expanding, Expanding)` on both image labels so they claim all available space.

### 4. Crop-to-Fill Scaling (`camera_panel.py`)
- Replace `KeepAspectRatio` scaling with crop-to-fill:
  1. Scale pixmap so it **covers** the label (use the larger scale factor).
  2. Center-crop to the label's exact dimensions.
  3. Set the cropped pixmap on the label.

## Files Changed
- `src/core/basler_camera.py`
- `src/ui/camera_panel.py`

## Not Changed
- `src/ui/main_window.py` — keep 3:2 graph:camera stretch ratio
- No new files or dependencies
