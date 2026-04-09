# Camera Recording & Review Dialog — Design Spec

**Date:** 2026-04-08
**Branch:** `feature/record_videos_inUI`
**Status:** Approved

## Goal

Add synchronized AVI video recording from both Basler cameras alongside CSV recording, with an in-app review dialog for synced playback of videos + sensor data.

## Recording Flow

### Trigger

When the user clicks **Record**:

1. App checks if **2 cameras** are connected (via `CameraPanel`)
2. **If 2 cameras connected**: show `QMessageBox` — "Also record camera videos?" (Yes / No)
   - **Yes**: start CSV recording + both cameras record AVI simultaneously
   - **No**: start CSV recording only
3. **If 0 or 1 cameras connected**: start CSV recording only, no popup

Both-or-nothing: no option to record just one camera.

### Stop

When the user clicks **Stop**: stop CSV recording and (if active) stop both camera recordings in lockstep.

### File Output

```
outputs/
  rhs_2026-04-08_14-30-00.csv
  videos/
    camera1_2026-04-08_14-30-00.avi
    camera2_2026-04-08_14-30-00.avi
```

- Matching timestamp ties the three files together as one session
- Video format: AVI with MJPG codec (already implemented in `BaslerCamera.start_recording()`)
- Camera naming: `camera1` and `camera2` (not by serial number or index)
- `outputs/videos/` directory created at app startup if it doesn't exist

### Status Indicators

The control bar status area shows two lines when both are active:
- `"Recording: rhs_2026-04-08_14-30-00.csv"` in red (existing behavior)
- `"Cameras recording"` in red (new, only when video recording is active)

When video recording stops, the camera status line disappears. When CSV recording stops, the CSV status line disappears (existing behavior).

## Control Bar Changes

### Button Layout

Remove the disabled "Start RHS" button. New layout:

**Record | Stop | Plot | Log | Review**

Analysis buttons (Plot, Log, Review) are grouped together.

### Review Button

- New `review_clicked` signal on `ControlBar`
- Enabled when at least one complete session exists (CSV + 2 matching videos)
- Disabled otherwise

## Review Dialog

A new `ReviewDialog` (`src/ui/review_dialog.py`) — a `QDialog` for synced playback.

### Layout

```
+-----------------------------------------------+
|  [Session selector dropdown]                   |
+----------------------+------------------------+
|                      |                        |
|   Camera 1 frame     |   Camera 2 frame      |
|   (QLabel/QPixmap)   |   (QLabel/QPixmap)     |
|                      |                        |
+----------------------+------------------------+
|                                               |
|   pyqtgraph plot (full CSV, all channels)     |
|   with vertical cursor line at current time   |
|                                               |
+-----------------------------------------------+
| [Play/Pause]  [<<] [timeline slider] [>>]     |
+-----------------------------------------------+
```

### Components

- **Session selector**: dropdown listing available sessions (detected by matching timestamps)
- **Video frames**: two `QLabel` widgets showing frames as `QPixmap`, side-by-side
- **Graph**: `pyqtgraph.PlotWidget` with full CSV data, standard pan/zoom, vertical `InfiniteLine` cursor marking current playback position
- **Timeline scrubber**: `QSlider` spanning full recording duration
- **Play/Pause**: toggles playback at recorded speed (30 FPS)
- **Step buttons** (`<<` / `>>`): step forward/backward one frame

### Sync Mechanism

- CSV rows have timestamps (elapsed seconds from recording start)
- Video frames are at known FPS (30). Frame N corresponds to time `N / 30.0` seconds
- Scrubbing the slider updates: video frames (seek to nearest frame) + graph cursor position
- During playback: a `QTimer` fires at ~33ms intervals, advancing the frame index and updating all three displays

### Session Discovery

Scan `outputs/` for CSV files. For each CSV, check if `outputs/videos/camera1_<timestamp>.avi` and `outputs/videos/camera2_<timestamp>.avi` both exist. Only sessions with all three files appear in the dropdown.

## Files Changed

| File | Change |
|------|--------|
| `src/ui/control_bar.py` | Add Review button + `review_clicked` signal, remove Start RHS button, add camera recording status label |
| `src/ui/main_window.py` | Wire Review button, add camera popup logic in `_on_record()`, start/stop camera recording with CSV |
| `src/ui/review_dialog.py` | **New** — synced video + graph review dialog |
| `src/utils/config.py` | Add `VIDEOS_DIR = OUTPUTS_DIR / "videos"` |
| `outputs/videos/.gitkeep` | **New** — ensure directory exists in repo |

## What This Does NOT Include

- Recording only one camera
- MP4/H.264 encoding
- Screen recording
- Standalone video playback tool
- Any changes to the camera panel or camera connection logic
