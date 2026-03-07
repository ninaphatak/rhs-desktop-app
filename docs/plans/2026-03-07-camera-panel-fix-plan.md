# Camera Panel Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize camera FPS with a sleep-based throttle, remove FPS display, and make camera images fill their labels with crop-to-fill scaling.

**Architecture:** Two files change. `basler_camera.py` gets a frame-rate limiter and loses FPS tracking. `camera_panel.py` loses title labels, gains expanding size policies, and switches from KeepAspectRatio to crop-to-fill scaling.

**Tech Stack:** PySide6, pypylon, numpy

---

### Task 1: Add FPS Throttle and Remove FPS Tracking (`basler_camera.py`)

**Files:**
- Modify: `src/core/basler_camera.py`

**Step 1: Remove FPS-related code**

Remove these from `BaslerCamera`:
- Line 28: `fps_updated = Signal(float)` — delete entire line
- Line 38: `self._frame_times: deque = deque(maxlen=60)` — delete
- Line 40: `self._last_fps_emit = 0.0` — delete
- Line 5: `from collections import deque` — delete (no longer used)
- Lines 118-119: `self._frame_times.clear()` and `self._last_fps_emit = time.time()` — delete
- Line 132: `self._frame_times.append(ts)` — delete
- Lines 138-140: the `if ts - self._last_fps_emit >= 1.0:` block — delete
- Lines 151-155: entire `_calc_fps()` method — delete

**Step 2: Add sleep-based throttle to `run()`**

Add `frame_interval = 1.0 / self.target_fps` before the grab loop. After emitting `frame_ready`, calculate elapsed time and sleep for the remainder of the frame interval:

```python
def run(self) -> None:
    if not self._connected or not self._camera:
        self.error_occurred.emit("Camera not connected")
        return

    self._running = True
    self._frame_count = 0
    frame_interval = 1.0 / self.target_fps

    try:
        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        while self._running and self._camera.IsGrabbing():
            try:
                frame_start = time.time()
                timeout_ms = int(self.exposure_us / 1000) + 1000
                grab = self._camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_Return)
                if grab and grab.GrabSucceeded():
                    ts = time.time()
                    frame = grab.Array.copy()
                    grab.Release()
                    self._frame_count += 1
                    self.frame_ready.emit({
                        "timestamp": ts,
                        "frame": frame,
                        "frame_number": self._frame_count,
                    })
                    elapsed = time.time() - frame_start
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                elif grab:
                    grab.Release()
            except Exception:
                time.sleep(0.01)
    except Exception as e:
        self.error_occurred.emit(f"Grab error: {e}")
    finally:
        if self._camera and self._camera.IsGrabbing():
            self._camera.StopGrabbing()
```

**Step 3: Also remove `fps_updated` from `MockCamera`**

In `tests/mock_camera.py`:
- Line 16: delete `fps_updated = Signal(float)`
- Lines 51-52, 66-70: delete `fps_samples` list and the `fps_updated.emit(...)` block
- Line 52: delete `last_fps_emit = time.time()`

**Step 4: Commit**

```bash
git add src/core/basler_camera.py tests/mock_camera.py
git commit -m "Add FPS throttle, remove FPS tracking from BaslerCamera and MockCamera"
```

---

### Task 2: Remove Title Labels and Fix Layout (`camera_panel.py`)

**Files:**
- Modify: `src/ui/camera_panel.py`

**Step 1: Remove title labels, simplify layout, add size policies**

Replace the `__init__` method. Remove `QVBoxLayout` containers and title labels. Put image labels directly in `QHBoxLayout`. Add `QSizePolicy.Expanding` on both axes. Remove `QVBoxLayout` from imports. Add `QSizePolicy` to imports.

```python
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy

# In __init__:
def __init__(self, parent=None) -> None:
    super().__init__(parent)
    layout = QHBoxLayout(self)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(8)

    # Left camera
    self._left_label = QLabel("No Camera")
    self._left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._left_label.setStyleSheet(_PLACEHOLDER_STYLE)
    self._left_label.setMinimumSize(320, 200)
    self._left_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout.addWidget(self._left_label)

    # Right camera
    self._right_label = QLabel("No Camera")
    self._right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._right_label.setStyleSheet(_PLACEHOLDER_STYLE)
    self._right_label.setMinimumSize(320, 200)
    self._right_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout.addWidget(self._right_label)

    # Camera threads
    self._left_camera: BaslerCamera | None = None
    self._right_camera: BaslerCamera | None = None

    self._auto_connect_cameras()
```

**Step 2: Remove FPS signal connections from `_auto_connect_cameras`**

Delete lines 77-79 (left camera `fps_updated` connection) and lines 87-89 (right camera `fps_updated` connection). Also delete the `self._left_title` / `self._right_title` references since those widgets no longer exist.

```python
def _auto_connect_cameras(self) -> None:
    """Detect and connect to available Basler cameras."""
    cameras = BaslerCamera.list_cameras()
    logger.info(f"Found {len(cameras)} Basler camera(s)")

    if len(cameras) >= 1:
        self._left_camera = BaslerCamera()
        if self._left_camera.connect(0):
            self._left_camera.frame_ready.connect(self._update_left)
            self._left_camera.start()
            self._left_label.setStyleSheet("")

    if len(cameras) >= 2:
        self._right_camera = BaslerCamera()
        if self._right_camera.connect(1):
            self._right_camera.frame_ready.connect(self._update_right)
            self._right_camera.start()
            self._right_label.setStyleSheet("")
```

**Step 3: Commit**

```bash
git add src/ui/camera_panel.py
git commit -m "Remove camera title labels, add expanding size policy"
```

---

### Task 3: Implement Crop-to-Fill Scaling (`camera_panel.py`)

**Files:**
- Modify: `src/ui/camera_panel.py`

**Step 1: Replace `_display_frame` with crop-to-fill logic**

The new method scales the image up so it covers the label entirely (using the larger of the two scale factors), then center-crops to the label dimensions.

```python
def _display_frame(self, label: QLabel, frame: np.ndarray) -> None:
    """Convert numpy frame to QPixmap and crop-to-fill the label."""
    h, w = frame.shape[:2]
    if frame.ndim == 2:
        qimg = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
    else:
        qimg = QImage(frame.data, w, h, w * 3, QImage.Format.Format_RGB888)

    pixmap = QPixmap.fromImage(qimg)
    label_w, label_h = label.width(), label.height()
    if label_w <= 0 or label_h <= 0:
        return

    # Scale to cover: use the larger scale factor so no gaps remain
    scale_w = label_w / pixmap.width()
    scale_h = label_h / pixmap.height()
    scale = max(scale_w, scale_h)
    scaled = pixmap.scaled(
        int(pixmap.width() * scale),
        int(pixmap.height() * scale),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # Center-crop to label size
    x = (scaled.width() - label_w) // 2
    y = (scaled.height() - label_h) // 2
    cropped = scaled.copy(x, y, label_w, label_h)
    label.setPixmap(cropped)
```

**Step 2: Commit**

```bash
git add src/ui/camera_panel.py
git commit -m "Implement crop-to-fill scaling for camera display"
```

---

### Task 4: Run Tests and Verify

**Step 1: Run existing tests**

```bash
pytest tests/ -v
```

Expected: all 17 tests pass (no camera tests exist, but ensure nothing broke).

**Step 2: Visual verification**

```bash
bash run.sh --mock
```

Verify:
- No "Camera 1" / "Camera 2" titles visible
- Mock camera images fill their label areas completely (no dead space)
- No FPS text displayed anywhere

**Step 3: Final commit (if any fixups needed)**

```bash
git add -A && git commit -m "Fix: camera panel adjustments after testing"
```
