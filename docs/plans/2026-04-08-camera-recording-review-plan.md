# Camera Recording & Review Dialog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add synchronized AVI recording from both Basler cameras alongside CSV recording, plus an in-app review dialog for synced video + sensor data playback.

**Architecture:** Video recording is added to `BaslerCamera` using OpenCV's `VideoWriter` (MJPG codec). The recording flow lives in `MainWindow` — it prompts the user via `QMessageBox` when 2 cameras are connected, then starts/stops camera recording in lockstep with CSV. A new `ReviewDialog` uses OpenCV `VideoCapture` + pyqtgraph for synced playback with a shared timeline.

**Tech Stack:** PySide6, OpenCV (`cv2.VideoWriter` / `cv2.VideoCapture`), pyqtgraph, pandas, numpy

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/utils/config.py` | Modify | Add `VIDEOS_DIR` constant |
| `src/core/basler_camera.py` | Modify | Add `start_recording()` / `stop_recording()` using `cv2.VideoWriter` |
| `src/ui/control_bar.py` | Modify | Remove Start RHS button, add Review button + `review_clicked` signal, add camera status label |
| `src/ui/main_window.py` | Modify | Wire popup logic, start/stop camera recording, wire Review button |
| `src/ui/review_dialog.py` | Create | Synced video + graph playback dialog |
| `outputs/videos/.gitkeep` | Create | Ensure video output directory exists in repo |
| `tests/test_data_recorder_video.py` | Create | Tests for camera recording integration and session discovery |

---

### Task 1: Add `VIDEOS_DIR` config constant

**Files:**
- Modify: `src/utils/config.py:47-49`

- [ ] **Step 1: Add VIDEOS_DIR to config**

In `src/utils/config.py`, add after the `OUTPUTS_DIR` line (line 48):

```python
VIDEOS_DIR = OUTPUTS_DIR / "videos"
```

- [ ] **Step 2: Create outputs/videos/.gitkeep**

```bash
mkdir -p outputs/videos
touch outputs/videos/.gitkeep
```

- [ ] **Step 3: Update .gitignore to preserve videos/.gitkeep**

Add to `.gitignore` after the existing `outputs/*` / `!outputs/.gitkeep` lines:

```
!outputs/videos/
outputs/videos/*
!outputs/videos/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add src/utils/config.py outputs/videos/.gitkeep .gitignore
git commit -m "Add VIDEOS_DIR config constant and outputs/videos directory"
```

---

### Task 2: Add video recording to BaslerCamera

**Files:**
- Modify: `src/core/basler_camera.py`
- Test: `tests/test_basler_recording.py`

- [ ] **Step 1: Write failing tests for BaslerCamera recording API**

Create `tests/test_basler_recording.py`:

```python
"""Tests for BaslerCamera video recording methods."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.core.basler_camera import BaslerCamera


class TestBaslerCameraRecording:
    """Test the start/stop recording API on BaslerCamera."""

    def test_start_recording_sets_state(self, tmp_path: Path) -> None:
        """start_recording should set is_recording=True and create a VideoWriter."""
        cam = BaslerCamera()
        output_path = tmp_path / "test.avi"
        # Need a frame size to init the writer — simulate by setting it
        cam._last_frame_size = (640, 480)
        cam.start_recording(str(output_path))
        assert cam.is_recording is True
        cam.stop_recording()

    def test_stop_recording_clears_state(self, tmp_path: Path) -> None:
        """stop_recording should set is_recording=False."""
        cam = BaslerCamera()
        cam._last_frame_size = (640, 480)
        cam.start_recording(str(tmp_path / "test.avi"))
        cam.stop_recording()
        assert cam.is_recording is False

    def test_stop_recording_when_not_recording(self) -> None:
        """stop_recording when not recording should be a no-op."""
        cam = BaslerCamera()
        cam.stop_recording()  # Should not raise
        assert cam.is_recording is False

    def test_start_recording_without_frame_size_raises(self, tmp_path: Path) -> None:
        """start_recording without a known frame size should raise ValueError."""
        cam = BaslerCamera()
        with pytest.raises(ValueError, match="frame size"):
            cam.start_recording(str(tmp_path / "test.avi"))

    def test_write_frame_writes_to_video(self, tmp_path: Path) -> None:
        """_write_frame should write a frame to the VideoWriter when recording."""
        cam = BaslerCamera()
        cam._last_frame_size = (640, 480)
        output_path = tmp_path / "test.avi"
        cam.start_recording(str(output_path))
        # Create a fake grayscale frame
        frame = np.zeros((480, 640), dtype=np.uint8)
        cam._write_frame(frame)
        cam.stop_recording()
        # File should exist and have some content
        assert output_path.exists()
        assert output_path.stat().st_size > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_basler_recording.py -v
```

Expected: FAIL — `BaslerCamera` has no `start_recording`, `stop_recording`, `_write_frame`, `is_recording`, or `_last_frame_size`.

- [ ] **Step 3: Implement recording methods on BaslerCamera**

Add these imports at the top of `src/core/basler_camera.py`:

```python
import cv2
```

Add these instance variables in `__init__`, after `self._frame_count = 0`:

```python
self._video_writer: Optional[cv2.VideoWriter] = None
self._is_recording = False
self._last_frame_size: tuple[int, int] | None = None
```

Add an `is_recording` property after the existing `is_connected` property:

```python
@property
def is_recording(self) -> bool:
    return self._is_recording
```

Add `start_recording`, `stop_recording`, and `_write_frame` methods before `run()`:

```python
def start_recording(self, output_path: str) -> None:
    """Start recording frames to an AVI file (MJPG codec).

    Args:
        output_path: Full path for the output .avi file.

    Raises:
        ValueError: If no frame size is known yet (no frames grabbed).
    """
    if self._is_recording:
        self.stop_recording()
    if self._last_frame_size is None:
        raise ValueError("Cannot start recording: frame size unknown (no frames grabbed yet)")
    w, h = self._last_frame_size
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    self._video_writer = cv2.VideoWriter(output_path, fourcc, self.target_fps, (w, h), isColor=False)
    self._is_recording = True
    logger.info(f"Camera recording started: {output_path}")

def stop_recording(self) -> None:
    """Stop recording and release the VideoWriter."""
    if not self._is_recording:
        return
    self._is_recording = False
    if self._video_writer:
        self._video_writer.release()
        self._video_writer = None
    logger.info("Camera recording stopped")

def _write_frame(self, frame: "np.ndarray") -> None:
    """Write a single frame to the video file if recording."""
    if not self._is_recording or self._video_writer is None:
        return
    self._video_writer.write(frame)
```

In `run()`, update the frame grab section. After `frame = grab.Array.copy()` (line ~125), add:

```python
self._last_frame_size = (frame.shape[1], frame.shape[0])
self._write_frame(frame)
```

In `stop()`, add a call to `stop_recording()` before `self._running = False`:

```python
def stop(self) -> None:
    self.stop_recording()
    self._running = False
    if self.isRunning():
        self.wait(2000)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_basler_recording.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/core/basler_camera.py tests/test_basler_recording.py
git commit -m "Add AVI recording capability to BaslerCamera"
```

---

### Task 3: Update ControlBar — remove Start RHS, add Review button, add camera status

**Files:**
- Modify: `src/ui/control_bar.py`
- Test: `tests/test_control_bar.py`

- [ ] **Step 1: Write failing tests for new ControlBar features**

Create `tests/test_control_bar.py`:

```python
"""Tests for ControlBar widget changes."""

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from src.ui.control_bar import ControlBar

# Ensure QApplication exists for widget tests
app = QApplication.instance() or QApplication([])


class TestControlBar:
    """Test ControlBar button layout and status labels."""

    def test_no_start_rhs_button(self) -> None:
        """Start RHS button should not exist."""
        bar = ControlBar()
        assert not hasattr(bar, "_start_rhs_btn")

    def test_review_button_exists(self) -> None:
        """Review button should exist and emit review_clicked signal."""
        bar = ControlBar()
        assert hasattr(bar, "_review_btn")

    def test_review_clicked_signal(self) -> None:
        """Clicking Review should emit review_clicked signal."""
        bar = ControlBar()
        received = []
        bar.review_clicked.connect(lambda: received.append(True))
        QTest.mouseClick(bar._review_btn, Qt.MouseButton.LeftButton)
        assert len(received) == 1

    def test_set_camera_recording_shows_status(self) -> None:
        """set_camera_recording(True) should show camera status text."""
        bar = ControlBar()
        bar.set_camera_recording(True)
        assert "Cameras recording" in bar._camera_status.text()

    def test_set_camera_recording_hides_status(self) -> None:
        """set_camera_recording(False) should hide camera status text."""
        bar = ControlBar()
        bar.set_camera_recording(True)
        bar.set_camera_recording(False)
        assert bar._camera_status.text() == ""

    def test_button_order(self) -> None:
        """Buttons should appear in order: Record, Stop, Plot, Log, Review."""
        bar = ControlBar()
        layout = bar.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]
        button_texts = [w.text() for w in widgets if hasattr(w, "text") and isinstance(w, type(bar._record_btn))]
        assert button_texts == ["Record", "Stop", "Plot", "Log", "Review"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_control_bar.py -v
```

Expected: FAIL — no `_review_btn`, no `review_clicked`, no `set_camera_recording`, `_start_rhs_btn` still exists.

- [ ] **Step 3: Rewrite ControlBar**

Replace the full content of `src/ui/control_bar.py`:

```python
"""Control bar widget: Record, Stop, Plot, Log, Review buttons + status labels."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal


class ControlBar(QWidget):
    """Horizontal bar with action buttons and status labels."""

    record_clicked = Signal()
    stop_clicked = Signal()
    plot_clicked = Signal()
    log_clicked = Signal()
    review_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._record_btn = QPushButton("Record")
        self._stop_btn = QPushButton("Stop")
        self._plot_btn = QPushButton("Plot")
        self._log_btn = QPushButton("Log")
        self._review_btn = QPushButton("Review")

        self._stop_btn.setEnabled(False)

        btn_style = """
            QPushButton {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 18px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #555; }
            QPushButton:disabled { color: #666; background-color: #2a2a2a; }
        """
        for btn in [self._record_btn, self._stop_btn, self._plot_btn,
                     self._log_btn, self._review_btn]:
            btn.setStyleSheet(btn_style)
            layout.addWidget(btn)

        # Status labels (stacked vertically)
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        self._status = QLabel("Not recording")
        self._status.setStyleSheet("color: #aaa; font-size: 13px; margin-left: 12px;")
        status_layout.addWidget(self._status)

        self._camera_status = QLabel("")
        self._camera_status.setStyleSheet("color: #ff4444; font-size: 13px; margin-left: 12px;")
        status_layout.addWidget(self._camera_status)

        layout.addLayout(status_layout, stretch=1)

        # Connect signals
        self._record_btn.clicked.connect(self.record_clicked)
        self._stop_btn.clicked.connect(self.stop_clicked)
        self._plot_btn.clicked.connect(self.plot_clicked)
        self._log_btn.clicked.connect(self.log_clicked)
        self._review_btn.clicked.connect(self.review_clicked)

    def set_recording(self, filename: str) -> None:
        """Update UI to recording state."""
        self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status.setText(f"Recording: {filename}")
        self._status.setStyleSheet("color: #ff4444; font-size: 13px; margin-left: 12px;")

    def set_stopped(self) -> None:
        """Update UI to idle state."""
        self._record_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText("Not recording")
        self._status.setStyleSheet("color: #aaa; font-size: 13px; margin-left: 12px;")
        self.set_camera_recording(False)

    def set_camera_recording(self, active: bool) -> None:
        """Show or hide the camera recording status label."""
        if active:
            self._camera_status.setText("Cameras recording")
        else:
            self._camera_status.setText("")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_control_bar.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/control_bar.py tests/test_control_bar.py
git commit -m "Update ControlBar: remove Start RHS, add Review button and camera status"
```

---

### Task 4: Wire recording popup and camera recording in MainWindow

**Files:**
- Modify: `src/ui/main_window.py`
- Modify: `src/ui/camera_panel.py` (expose camera connection state + recording control)

- [ ] **Step 1: Add camera access methods to CameraPanel**

Add these methods to `CameraPanel` in `src/ui/camera_panel.py`:

```python
@property
def both_cameras_connected(self) -> bool:
    """Return True if both cameras are connected and running."""
    return (
        self._left_camera is not None
        and self._left_camera.is_connected
        and self._right_camera is not None
        and self._right_camera.is_connected
    )

def start_recording(self, cam1_path: str, cam2_path: str) -> None:
    """Start recording on both cameras.

    Args:
        cam1_path: Output path for camera 1 (left) AVI.
        cam2_path: Output path for camera 2 (right) AVI.
    """
    if self._left_camera:
        self._left_camera.start_recording(cam1_path)
    if self._right_camera:
        self._right_camera.start_recording(cam2_path)

def stop_recording(self) -> None:
    """Stop recording on both cameras."""
    if self._left_camera:
        self._left_camera.stop_recording()
    if self._right_camera:
        self._right_camera.stop_recording()
```

- [ ] **Step 2: Update MainWindow._on_record() with popup logic**

Replace `_on_record` and `_on_stop` in `src/ui/main_window.py`. Add imports at the top:

```python
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox
from src.utils.config import VIDEOS_DIR
```

Replace the recording methods:

```python
def _on_record(self) -> None:
    """Start CSV recording, and optionally camera recording."""
    filename = self._data_recorder.start_recording()
    self._control_bar.set_recording(filename)

    # Offer camera recording if both cameras are connected
    if self._camera_panel.both_cameras_connected:
        reply = QMessageBox.question(
            self,
            "Record Cameras",
            "Also record camera videos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            # Extract timestamp from CSV filename: rhs_YYYY-MM-DD_HH-MM-SS.csv
            timestamp = filename.replace("rhs_", "").replace(".csv", "")
            cam1_path = str(VIDEOS_DIR / f"camera1_{timestamp}.avi")
            cam2_path = str(VIDEOS_DIR / f"camera2_{timestamp}.avi")
            self._camera_panel.start_recording(cam1_path, cam2_path)
            self._control_bar.set_camera_recording(True)

def _on_stop(self) -> None:
    """Stop CSV recording and camera recording."""
    self._data_recorder.stop_recording()
    self._camera_panel.stop_recording()
    self._control_bar.set_stopped()
```

- [ ] **Step 3: Wire the review_clicked signal in MainWindow.__init__**

Add after the existing `self._control_bar.log_clicked.connect(self._on_log)` line:

```python
self._control_bar.review_clicked.connect(self._on_review)
```

Add the handler method:

```python
def _on_review(self) -> None:
    from src.ui.review_dialog import ReviewDialog
    dlg = ReviewDialog(self)
    dlg.exec()
```

- [ ] **Step 4: Update closeEvent to stop camera recording**

In `closeEvent`, add `self._camera_panel.stop_recording()` before `self._camera_panel.stop_cameras()`:

```python
def closeEvent(self, event) -> None:
    """Gracefully stop threads on window close."""
    self._data_recorder.stop_recording()
    self._camera_panel.stop_recording()
    self._camera_panel.stop_cameras()
    if self._serial_reader:
        self._serial_reader.stop()
    if self._mock_arduino:
        self._mock_arduino.stop()
    super().closeEvent(event)
```

- [ ] **Step 5: Verify app launches with --mock**

```bash
timeout 5 bash run.sh --mock || true
```

Expected: App launches without errors (will timeout after 5s which is fine).

- [ ] **Step 6: Commit**

```bash
git add src/ui/main_window.py src/ui/camera_panel.py
git commit -m "Wire camera recording popup and synchronized start/stop in MainWindow"
```

---

### Task 5: Build the ReviewDialog — session discovery and layout

**Files:**
- Create: `src/ui/review_dialog.py`
- Test: `tests/test_review_dialog.py`

- [ ] **Step 1: Write failing tests for session discovery**

Create `tests/test_review_dialog.py`:

```python
"""Tests for ReviewDialog session discovery."""

import pytest
from pathlib import Path

from src.ui.review_dialog import discover_sessions


class TestSessionDiscovery:
    """Test discover_sessions finds matching CSV + video triples."""

    def test_discovers_complete_session(self, tmp_path: Path) -> None:
        """A session with CSV + 2 videos should be discovered."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        (tmp_path / "rhs_2026-04-08_14-30-00.csv").touch()
        (videos_dir / "camera1_2026-04-08_14-30-00.avi").touch()
        (videos_dir / "camera2_2026-04-08_14-30-00.avi").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 1
        assert sessions[0]["timestamp"] == "2026-04-08_14-30-00"

    def test_ignores_csv_without_videos(self, tmp_path: Path) -> None:
        """A CSV without matching videos should not appear."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        (tmp_path / "rhs_2026-04-08_14-30-00.csv").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 0

    def test_ignores_partial_videos(self, tmp_path: Path) -> None:
        """A CSV with only one matching video should not appear."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        (tmp_path / "rhs_2026-04-08_14-30-00.csv").touch()
        (videos_dir / "camera1_2026-04-08_14-30-00.avi").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 0

    def test_multiple_sessions_sorted_newest_first(self, tmp_path: Path) -> None:
        """Multiple sessions should be returned newest first."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        for ts in ["2026-04-08_14-30-00", "2026-04-08_15-00-00"]:
            (tmp_path / f"rhs_{ts}.csv").touch()
            (videos_dir / f"camera1_{ts}.avi").touch()
            (videos_dir / f"camera2_{ts}.avi").touch()

        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 2
        assert sessions[0]["timestamp"] == "2026-04-08_15-00-00"

    def test_session_contains_all_paths(self, tmp_path: Path) -> None:
        """Each session dict should contain csv, cam1, cam2 paths."""
        videos_dir = tmp_path / "videos"
        videos_dir.mkdir()
        ts = "2026-04-08_14-30-00"
        (tmp_path / f"rhs_{ts}.csv").touch()
        (videos_dir / f"camera1_{ts}.avi").touch()
        (videos_dir / f"camera2_{ts}.avi").touch()

        session = discover_sessions(tmp_path)[0]
        assert session["csv"] == tmp_path / f"rhs_{ts}.csv"
        assert session["cam1"] == videos_dir / f"camera1_{ts}.avi"
        assert session["cam2"] == videos_dir / f"camera2_{ts}.avi"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_review_dialog.py -v
```

Expected: FAIL — `review_dialog` module doesn't exist.

- [ ] **Step 3: Create review_dialog.py with session discovery and full dialog**

Create `src/ui/review_dialog.py`:

```python
"""Synced video + sensor data review dialog."""

import logging
import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, QTimer

from src.utils.config import OUTPUTS_DIR, VIDEOS_DIR, CAMERA_FPS, COLORS

logger = logging.getLogger(__name__)


def discover_sessions(outputs_dir: Path | None = None) -> list[dict]:
    """Find recording sessions that have CSV + both camera videos.

    Args:
        outputs_dir: Directory containing CSV files (default: OUTPUTS_DIR).

    Returns:
        List of session dicts sorted newest-first, each containing:
        - timestamp: str
        - csv: Path
        - cam1: Path
        - cam2: Path
    """
    if outputs_dir is None:
        outputs_dir = OUTPUTS_DIR

    videos_dir = outputs_dir / "videos"
    if not videos_dir.is_dir():
        return []

    sessions = []
    pattern = re.compile(r"^rhs_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.csv$")
    for csv_path in sorted(outputs_dir.glob("rhs_*.csv")):
        match = pattern.match(csv_path.name)
        if not match:
            continue
        ts = match.group(1)
        cam1 = videos_dir / f"camera1_{ts}.avi"
        cam2 = videos_dir / f"camera2_{ts}.avi"
        if cam1.exists() and cam2.exists():
            sessions.append({
                "timestamp": ts,
                "csv": csv_path,
                "cam1": cam1,
                "cam2": cam2,
            })

    # Newest first
    sessions.sort(key=lambda s: s["timestamp"], reverse=True)
    return sessions


class ReviewDialog(QDialog):
    """Synced playback of two camera videos alongside sensor data graphs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Recording")
        self.resize(1200, 800)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; color: white; }")

        self._cap1: Optional[cv2.VideoCapture] = None
        self._cap2: Optional[cv2.VideoCapture] = None
        self._df: Optional[pd.DataFrame] = None
        self._total_frames = 0
        self._current_frame = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._build_ui()
        self._load_sessions()

    def _build_ui(self) -> None:
        """Construct the dialog layout."""
        layout = QVBoxLayout(self)

        # Session selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Session:"))
        self._session_combo = QComboBox()
        self._session_combo.setStyleSheet(
            "QComboBox { background: #333; color: white; padding: 4px; }"
        )
        self._session_combo.currentIndexChanged.connect(self._on_session_changed)
        selector_layout.addWidget(self._session_combo, stretch=1)
        layout.addLayout(selector_layout)

        # Video frames — side by side
        video_layout = QHBoxLayout()
        self._left_label = QLabel("Camera 1")
        self._left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_label.setMinimumSize(400, 250)
        self._left_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._left_label.setStyleSheet(
            "background-color: #2a2a2a; color: #666; border: 1px solid #444;"
        )

        self._right_label = QLabel("Camera 2")
        self._right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_label.setMinimumSize(400, 250)
        self._right_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._right_label.setStyleSheet(
            "background-color: #2a2a2a; color: #666; border: 1px solid #444;"
        )

        video_layout.addWidget(self._left_label)
        video_layout.addWidget(self._right_label)
        layout.addLayout(video_layout, stretch=2)

        # Graph — pyqtgraph
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#2a2a2a")
        self._plot_widget.setLabel("bottom", "Time (s)")
        self._plot_widget.addLegend(offset=(10, 10))
        self._cursor_line = pg.InfiniteLine(
            pos=0, angle=90, pen=pg.mkPen("w", width=1, style=Qt.PenStyle.DashLine)
        )
        self._plot_widget.addItem(self._cursor_line)
        layout.addWidget(self._plot_widget, stretch=1)

        # Transport controls
        transport_layout = QHBoxLayout()

        self._play_btn = QPushButton("Play")
        self._play_btn.clicked.connect(self._toggle_play)

        self._back_btn = QPushButton("<<")
        self._back_btn.clicked.connect(self._step_back)

        self._forward_btn = QPushButton(">>")
        self._forward_btn.clicked.connect(self._step_forward)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._on_slider_changed)

        self._time_label = QLabel("0.00 / 0.00 s")
        self._time_label.setStyleSheet("color: #aaa; font-size: 12px;")

        btn_style = """
            QPushButton {
                background-color: #333; color: white;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px 14px; font-size: 13px;
            }
            QPushButton:hover { background-color: #444; }
        """
        for btn in [self._play_btn, self._back_btn, self._forward_btn]:
            btn.setStyleSheet(btn_style)

        transport_layout.addWidget(self._play_btn)
        transport_layout.addWidget(self._back_btn)
        transport_layout.addWidget(self._slider, stretch=1)
        transport_layout.addWidget(self._forward_btn)
        transport_layout.addWidget(self._time_label)
        layout.addLayout(transport_layout)

    def _load_sessions(self) -> None:
        """Populate the session dropdown."""
        self._sessions = discover_sessions()
        self._session_combo.clear()
        if not self._sessions:
            self._session_combo.addItem("No sessions found")
            self._session_combo.setEnabled(False)
            return
        for s in self._sessions:
            self._session_combo.addItem(f"rhs_{s['timestamp']}")
        self._on_session_changed(0)

    def _on_session_changed(self, index: int) -> None:
        """Load the selected session's data and videos."""
        self._stop_playback()
        self._release_captures()

        if not self._sessions or index < 0 or index >= len(self._sessions):
            return

        session = self._sessions[index]

        # Load CSV
        try:
            self._df = pd.read_csv(session["csv"])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read CSV:\n{e}")
            return

        # Open video captures
        self._cap1 = cv2.VideoCapture(str(session["cam1"]))
        self._cap2 = cv2.VideoCapture(str(session["cam2"]))

        if not self._cap1.isOpened() or not self._cap2.isOpened():
            QMessageBox.critical(self, "Error", "Failed to open video files.")
            self._release_captures()
            return

        self._total_frames = min(
            int(self._cap1.get(cv2.CAP_PROP_FRAME_COUNT)),
            int(self._cap2.get(cv2.CAP_PROP_FRAME_COUNT)),
        )

        # Setup slider
        self._slider.setMaximum(max(0, self._total_frames - 1))
        self._slider.setValue(0)
        self._current_frame = 0

        # Plot CSV data
        self._plot_csv()

        # Show first frame
        self._seek_and_display(0)

    def _plot_csv(self) -> None:
        """Plot all CSV channels on the pyqtgraph widget."""
        self._plot_widget.clear()
        self._plot_widget.addItem(self._cursor_line)

        if self._df is None or "Time (s)" not in self._df.columns:
            return

        t = self._df["Time (s)"].values

        column_map = {
            "Pressure 1 (mmHg)": "p1",
            "Pressure 2 (mmHg)": "p2",
            "Flow Rate (mL/s)": "flow",
            "Heart Rate (BPM)": "hr",
            "Ventricle Temperature 1 (C)": "vt1",
            "Ventricle Temperature 2 (C)": "vt2",
            "Atrium Temperature (C)": "at1",
        }

        for col, key in column_map.items():
            if col in self._df.columns:
                color = COLORS.get(key, (200, 200, 200))
                self._plot_widget.plot(
                    t, self._df[col].values, pen=pg.mkPen(color, width=1), name=key
                )

    def _seek_and_display(self, frame_idx: int) -> None:
        """Seek both videos to frame_idx and display the frames."""
        if not self._cap1 or not self._cap2:
            return

        self._current_frame = frame_idx

        self._cap1.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        self._cap2.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

        ret1, frame1 = self._cap1.read()
        ret2, frame2 = self._cap2.read()

        if ret1:
            self._show_frame(self._left_label, frame1)
        if ret2:
            self._show_frame(self._right_label, frame2)

        # Update cursor on graph
        current_time = frame_idx / CAMERA_FPS
        self._cursor_line.setValue(current_time)

        total_time = (self._total_frames - 1) / CAMERA_FPS if self._total_frames > 0 else 0
        self._time_label.setText(f"{current_time:.2f} / {total_time:.2f} s")

    def _show_frame(self, label: QLabel, frame: np.ndarray) -> None:
        """Convert an OpenCV frame to QPixmap and display on a QLabel."""
        h, w = frame.shape[:2]
        if frame.ndim == 2:
            qimg = QImage(frame.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def _on_slider_changed(self, value: int) -> None:
        """Handle slider drag — seek to the frame."""
        if value != self._current_frame:
            self._seek_and_display(value)

    def _toggle_play(self) -> None:
        """Toggle play/pause."""
        if self._playing:
            self._stop_playback()
        else:
            self._playing = True
            self._play_btn.setText("Pause")
            interval_ms = int(1000 / CAMERA_FPS)
            self._timer.start(interval_ms)

    def _stop_playback(self) -> None:
        """Stop playback."""
        self._playing = False
        self._timer.stop()
        self._play_btn.setText("Play")

    def _advance_frame(self) -> None:
        """Advance one frame during playback."""
        next_frame = self._current_frame + 1
        if next_frame >= self._total_frames:
            self._stop_playback()
            return
        self._slider.setValue(next_frame)

    def _step_back(self) -> None:
        """Step back one frame."""
        if self._current_frame > 0:
            self._slider.setValue(self._current_frame - 1)

    def _step_forward(self) -> None:
        """Step forward one frame."""
        if self._current_frame < self._total_frames - 1:
            self._slider.setValue(self._current_frame + 1)

    def _release_captures(self) -> None:
        """Release any open video captures."""
        if self._cap1:
            self._cap1.release()
            self._cap1 = None
        if self._cap2:
            self._cap2.release()
            self._cap2 = None

    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self._stop_playback()
        self._release_captures()
        super().closeEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_review_dialog.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/review_dialog.py tests/test_review_dialog.py
git commit -m "Add ReviewDialog with synced video + sensor data playback"
```

---

### Task 6: Integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass, including the new ones from tasks 2, 3, and 5.

- [ ] **Step 2: Launch the app with --mock and verify UI**

```bash
timeout 5 bash run.sh --mock || true
```

Verify:
- Control bar shows: Record, Stop, Plot, Log, Review (no Start RHS)
- Review button is clickable
- Record/Stop work without errors (no cameras in mock mode → no popup)

- [ ] **Step 3: Commit any fixes if needed**

Only if something broke in integration. Otherwise skip.

---

## Summary of Commits

1. `Add VIDEOS_DIR config constant and outputs/videos directory`
2. `Add AVI recording capability to BaslerCamera`
3. `Update ControlBar: remove Start RHS, add Review button and camera status`
4. `Wire camera recording popup and synchronized start/stop in MainWindow`
5. `Add ReviewDialog with synced video + sensor data playback`
6. (Integration fixes if needed)
