# Point Annotator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manual point + per-frame phase annotator for valve videos, plus playback visualization and cardiac-cycle CV analysis tools — implementing the design at `docs/plans/2026-05-04-point-annotator-design.md`.

**Architecture:** Three CLI tools in `tools/` sharing a small `_annotations.py` CSV I/O module. Annotator and playback use OpenCV windows; analyzer is a non-GUI script with two modes — Mode A (cycle period + per-cycle displacement + CV) and Mode B (Farneback dense-flow vs manual displacement, sampled at the labeled point).

**Tech Stack:** Python 3.11, OpenCV (`cv2`), NumPy, pytest. All deps already in the `rhs-app` conda env (run.sh handles activation). Activate with `conda activate rhs-app` before running tests manually.

---

## File Structure

| File | Responsibility |
|---|---|
| `tools/_annotations.py` | `Annotation` dataclass + valid phase constants + CSV read/write |
| `tools/annotate_point.py` | Click-to-label OpenCV GUI |
| `tools/playback_annotations.py` | Pure overlay-render function + playback loop |
| `tools/analyze_annotations.py` | Cycle detection + per-cycle metrics + CV aggregation + Mode B (Farneback) |
| `tests/test_annotations_io.py` | CSV round-trip + malformed-input rejection |
| `tests/test_playback_render.py` | Overlay-render pixel assertions on synthetic frames |
| `tests/test_analyze_annotations.py` | Cycle detection + metrics + CV + Mode B math |

No automated tests for the annotator GUI loop or the playback main loop (require a display). Testable logic is pulled out of those scripts into pure helper functions.

---

## Task 1: Annotation row dataclass + phase constants

**Files:**
- Create: `tools/_annotations.py`
- Test: `tests/test_annotations_io.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_annotations_io.py` with:

```python
"""Tests for tools/_annotations.py — annotation CSV I/O."""

import sys
from pathlib import Path

# Allow `from tools._annotations import ...`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools._annotations import Annotation, VALID_PHASES


def test_valid_phases_are_the_four_documented_tokens():
    assert VALID_PHASES == ("open", "opening", "closing", "closed")


def test_annotation_construction():
    a = Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening")
    assert a.frame_idx == 12
    assert a.point_x == 412
    assert a.point_y == 305
    assert a.phase == "opening"
```

- [ ] **Step 2: Run test to verify it fails**

```
conda activate rhs-app
pytest tests/test_annotations_io.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tools._annotations'`.

- [ ] **Step 3: Implement `_annotations.py` minimally**

Create `tools/_annotations.py`:

```python
"""Annotation row dataclass and CSV I/O for the point-annotator tools.

Shared by tools/annotate_point.py, tools/playback_annotations.py, and
tools/analyze_annotations.py. Keep this module free of cv2/GUI deps so
analysis can run headless.
"""

from __future__ import annotations

from dataclasses import dataclass


VALID_PHASES: tuple[str, ...] = ("open", "opening", "closing", "closed")


@dataclass(frozen=True)
class Annotation:
    """One labeled frame: a tracked landmark position and a cardiac phase.

    Attributes:
        frame_idx: 0-based index of the frame in the source video.
        point_x: x pixel coordinate of the labeled landmark.
        point_y: y pixel coordinate of the labeled landmark.
        phase: one of VALID_PHASES.
    """

    frame_idx: int
    point_x: int
    point_y: int
    phase: str
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_annotations_io.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add tools/_annotations.py tests/test_annotations_io.py
git commit -m "Add Annotation dataclass and phase constants"
```

---

## Task 2: CSV writer

**Files:**
- Modify: `tools/_annotations.py`
- Modify: `tests/test_annotations_io.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_annotations_io.py`:

```python
def test_write_annotations_produces_expected_csv(tmp_path):
    from tools._annotations import write_annotations

    rows = [
        Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening"),
        Annotation(frame_idx=14, point_x=418, point_y=312, phase="open"),
    ]
    out = tmp_path / "ann.csv"
    write_annotations(rows, out)

    text = out.read_text()
    assert text.splitlines()[0] == "frame_idx,point_x,point_y,phase"
    assert "12,412,305,opening" in text
    assert "14,418,312,open" in text


def test_write_annotations_sorts_by_frame_idx(tmp_path):
    from tools._annotations import write_annotations

    rows = [
        Annotation(frame_idx=14, point_x=418, point_y=312, phase="open"),
        Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening"),
    ]
    out = tmp_path / "ann.csv"
    write_annotations(rows, out)

    lines = out.read_text().splitlines()
    assert lines[1].startswith("12,")
    assert lines[2].startswith("14,")
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_annotations_io.py -v
```

Expected: 2 new FAILs — `ImportError: cannot import name 'write_annotations'`.

- [ ] **Step 3: Implement `write_annotations`**

Append to `tools/_annotations.py`:

```python
import csv
from pathlib import Path
from typing import Iterable


CSV_HEADER = ("frame_idx", "point_x", "point_y", "phase")


def write_annotations(rows: Iterable[Annotation], path: Path) -> None:
    """Write annotations to CSV at `path`, sorted ascending by frame_idx.

    Overwrites any existing file at the path.
    """
    rows_sorted = sorted(rows, key=lambda r: r.frame_idx)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for r in rows_sorted:
            writer.writerow([r.frame_idx, r.point_x, r.point_y, r.phase])
```

- [ ] **Step 4: Run to verify it passes**

```
pytest tests/test_annotations_io.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add tools/_annotations.py tests/test_annotations_io.py
git commit -m "Add CSV writer for annotations"
```

---

## Task 3: CSV reader

**Files:**
- Modify: `tools/_annotations.py`
- Modify: `tests/test_annotations_io.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_annotations_io.py`:

```python
def test_read_annotations_round_trip(tmp_path):
    from tools._annotations import write_annotations, read_annotations

    rows = [
        Annotation(frame_idx=12, point_x=412, point_y=305, phase="opening"),
        Annotation(frame_idx=14, point_x=418, point_y=312, phase="open"),
        Annotation(frame_idx=20, point_x=425, point_y=320, phase="closing"),
    ]
    out = tmp_path / "ann.csv"
    write_annotations(rows, out)

    loaded = read_annotations(out)
    assert loaded == rows


def test_read_annotations_missing_file_returns_empty_list(tmp_path):
    from tools._annotations import read_annotations
    assert read_annotations(tmp_path / "nope.csv") == []
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_annotations_io.py -v
```

Expected: 2 new FAILs — `ImportError: cannot import name 'read_annotations'`.

- [ ] **Step 3: Implement `read_annotations`**

Append to `tools/_annotations.py`:

```python
def read_annotations(path: Path) -> list[Annotation]:
    """Read annotations from CSV at `path`.

    Returns an empty list if the file does not exist. Rows are returned
    in ascending frame_idx order. Raises ValueError on malformed input.
    """
    if not Path(path).exists():
        return []

    rows: list[Annotation] = []
    seen_frames: set[int] = set()
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if tuple(header or ()) != CSV_HEADER:
            raise ValueError(f"Bad header in {path}: {header!r}")
        for line_no, raw in enumerate(reader, start=2):
            if len(raw) != 4:
                raise ValueError(f"{path}:{line_no}: expected 4 columns, got {len(raw)}")
            try:
                frame_idx = int(raw[0])
                px = int(raw[1])
                py = int(raw[2])
            except ValueError as e:
                raise ValueError(f"{path}:{line_no}: non-integer field: {e}") from e
            phase = raw[3]
            if phase not in VALID_PHASES:
                raise ValueError(f"{path}:{line_no}: invalid phase {phase!r}")
            if frame_idx in seen_frames:
                raise ValueError(f"{path}:{line_no}: duplicate frame_idx {frame_idx}")
            seen_frames.add(frame_idx)
            rows.append(Annotation(frame_idx=frame_idx, point_x=px, point_y=py, phase=phase))

    rows.sort(key=lambda r: r.frame_idx)
    return rows
```

- [ ] **Step 4: Run to verify it passes**

```
pytest tests/test_annotations_io.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add tools/_annotations.py tests/test_annotations_io.py
git commit -m "Add CSV reader for annotations"
```

---

## Task 4: CSV reader malformed-input rejection

**Files:**
- Modify: `tests/test_annotations_io.py`

(Reader validation is already implemented in Task 3; this task adds the tests that prove it.)

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_annotations_io.py`:

```python
def test_read_rejects_bad_phase(tmp_path):
    from tools._annotations import read_annotations

    p = tmp_path / "ann.csv"
    p.write_text("frame_idx,point_x,point_y,phase\n12,1,2,wibble\n")
    with pytest.raises(ValueError, match="invalid phase"):
        read_annotations(p)


def test_read_rejects_non_int_frame_idx(tmp_path):
    from tools._annotations import read_annotations

    p = tmp_path / "ann.csv"
    p.write_text("frame_idx,point_x,point_y,phase\nabc,1,2,open\n")
    with pytest.raises(ValueError, match="non-integer"):
        read_annotations(p)


def test_read_rejects_duplicate_frame_idx(tmp_path):
    from tools._annotations import read_annotations

    p = tmp_path / "ann.csv"
    p.write_text(
        "frame_idx,point_x,point_y,phase\n"
        "12,1,2,open\n12,3,4,closed\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        read_annotations(p)


def test_read_rejects_bad_header(tmp_path):
    from tools._annotations import read_annotations

    p = tmp_path / "ann.csv"
    p.write_text("idx,x,y,phase\n12,1,2,open\n")
    with pytest.raises(ValueError, match="Bad header"):
        read_annotations(p)
```

- [ ] **Step 2: Run to verify they pass**

```
pytest tests/test_annotations_io.py -v
```

Expected: 10 passed (the validation logic was already implemented in Task 3).

- [ ] **Step 3: Commit**

```
git add tests/test_annotations_io.py
git commit -m "Add malformed-input tests for annotation CSV reader"
```

---

## Task 5: Annotator GUI — `tools/annotate_point.py`

**Files:**
- Create: `tools/annotate_point.py`

This task has no automated test (would need a display server). Manual smoke test instructions are in Step 3.

- [ ] **Step 1: Write the script**

Create `tools/annotate_point.py`:

```python
"""Manual point + per-frame phase annotator for valve videos.

Click to label the same anatomical landmark on each frame. Number keys
1/2/3/4 set the cardiac phase (open/opening/closing/closed). Output is
a sparse CSV next to the input video.

Usage:
    python tools/annotate_point.py path/to/recording.mp4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# Allow running as `python tools/annotate_point.py ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._annotations import (
    Annotation,
    VALID_PHASES,
    read_annotations,
    write_annotations,
)


PHASE_HOTKEYS = {ord("1"): "open", ord("2"): "opening", ord("3"): "closing", ord("4"): "closed"}
WINDOW = "Point Annotator"


class AnnotatorState:
    """Mutable state for the annotator session."""

    def __init__(self, total_frames: int) -> None:
        self.frame_idx: int = 0
        self.total_frames: int = total_frames
        self.by_frame: dict[int, Annotation] = {}
        self.dirty: bool = False
        self.click: tuple[int, int] | None = None  # consumed each loop iteration


def render(frame: np.ndarray, state: AnnotatorState) -> np.ndarray:
    """Return a copy of `frame` with the saved point + HUD drawn on top."""
    out = frame.copy()
    ann = state.by_frame.get(state.frame_idx)
    if ann is not None:
        cv2.circle(out, (ann.point_x, ann.point_y), 4, (0, 0, 255), -1)
    phase = ann.phase if ann is not None else ""
    n_labeled = len(state.by_frame)
    cv2.putText(
        out, f"Frame {state.frame_idx}/{state.total_frames - 1}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
    )
    cv2.putText(
        out, f"phase={phase}",
        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )
    cv2.putText(
        out, f"labeled={n_labeled}{' *' if state.dirty else ''}",
        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )
    return out


def _on_mouse(event: int, x: int, y: int, flags: int, state: AnnotatorState) -> None:
    if event == cv2.EVENT_LBUTTONDOWN:
        state.click = (x, y)


def _seek(cap: cv2.VideoCapture, frame_idx: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    args = parser.parse_args()

    if not args.video.exists():
        print(f"File not found: {args.video}")
        sys.exit(1)

    csv_path = args.video.with_suffix(args.video.suffix + ".annotations.csv")
    # Filename ends up like recording.mp4.annotations.csv; if the user prefers
    # recording.annotations.csv, they can rename it manually.

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"Cannot open video: {args.video}")
        sys.exit(1)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    state = AnnotatorState(total_frames=total_frames)
    for ann in read_annotations(csv_path):
        state.by_frame[ann.frame_idx] = ann

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, _on_mouse, state)

    print(
        "Controls: LEFT-CLICK=set point  1/2/3/4=open/opening/closing/closed  "
        "RIGHT/d=next  LEFT/a=prev  u=undo  s=save  q=quit"
    )

    frame = _seek(cap, state.frame_idx)
    if frame is None:
        print("Cannot read first frame")
        sys.exit(1)

    while True:
        cv2.imshow(WINDOW, render(frame, state))
        key = cv2.waitKey(20) & 0xFF

        # Handle clicks first (they don't move the frame).
        if state.click is not None:
            x, y = state.click
            existing = state.by_frame.get(state.frame_idx)
            phase = existing.phase if existing else "open"
            state.by_frame[state.frame_idx] = Annotation(
                frame_idx=state.frame_idx, point_x=x, point_y=y, phase=phase,
            )
            state.dirty = True
            state.click = None
            continue

        if key == ord("q"):
            if state.dirty:
                print("Unsaved changes. Press 's' to save first, or 'q' again to discard.")
                if (cv2.waitKey(0) & 0xFF) == ord("q"):
                    break
            else:
                break
        elif key == ord("s"):
            write_annotations(state.by_frame.values(), csv_path)
            state.dirty = False
            print(f"Saved {len(state.by_frame)} annotations to {csv_path}")
        elif key == ord("u"):
            if state.frame_idx in state.by_frame:
                del state.by_frame[state.frame_idx]
                state.dirty = True
        elif key in PHASE_HOTKEYS:
            phase = PHASE_HOTKEYS[key]
            existing = state.by_frame.get(state.frame_idx)
            if existing is None:
                # Phase without a point — skip; user must click first.
                continue
            state.by_frame[state.frame_idx] = Annotation(
                frame_idx=existing.frame_idx,
                point_x=existing.point_x,
                point_y=existing.point_y,
                phase=phase,
            )
            state.dirty = True
        elif key in (83, ord("d")) and state.frame_idx + 1 < total_frames:  # right
            state.frame_idx += 1
            new_frame = _seek(cap, state.frame_idx)
            if new_frame is not None:
                frame = new_frame
        elif key in (81, ord("a")) and state.frame_idx > 0:  # left
            state.frame_idx -= 1
            new_frame = _seek(cap, state.frame_idx)
            if new_frame is not None:
                frame = new_frame

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-import to catch syntax / import errors**

```
conda activate rhs-app
python -c "import tools.annotate_point"
```

Expected: no output, exit code 0.

- [ ] **Step 3: Manual smoke test (briefly verify the GUI runs)**

```
python tools/annotate_point.py outputs/<some_recording>.mp4
```

(If `outputs/` is empty, skip this step — the script is structurally fine, and the I/O path is covered by the unit tests for `_annotations.py`.)

Verify:
- Window opens showing the first frame.
- `d` advances; `a` goes back.
- Left-click places a red dot.
- `2` sets phase to opening; HUD updates.
- `s` writes a CSV next to the video; close and reopen — the dot is restored.
- `q` exits cleanly.

- [ ] **Step 4: Commit**

```
git add tools/annotate_point.py
git commit -m "Add point + phase annotator GUI"
```

---

## Task 6: Playback overlay render function

**Files:**
- Create: `tools/playback_annotations.py`
- Create: `tests/test_playback_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_playback_render.py`:

```python
"""Pixel-level tests for tools/playback_annotations.py overlay rendering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from tools._annotations import Annotation
from tools.playback_annotations import draw_overlay, OverlayState


def _blank(shape=(200, 300, 3)) -> np.ndarray:
    return np.zeros(shape, dtype=np.uint8)


def test_origin_marker_drawn_on_every_frame_after_first_label():
    state = OverlayState()
    state.update(Annotation(frame_idx=0, point_x=50, point_y=80, phase="closed"))
    out = draw_overlay(_blank(), state)
    # Origin crosshair pixel should be non-black at P0.
    assert tuple(out[80, 50]) != (0, 0, 0)


def test_current_marker_drawn_at_current_point():
    state = OverlayState()
    state.update(Annotation(frame_idx=0, point_x=50, point_y=80, phase="closed"))
    state.update(Annotation(frame_idx=5, point_x=120, point_y=140, phase="opening"))
    out = draw_overlay(_blank(), state)
    # Red dot center pixel.
    assert tuple(out[140, 120]) != (0, 0, 0)


def test_no_origin_drawn_before_first_annotation():
    state = OverlayState()
    out = draw_overlay(_blank(), state)
    assert (out == 0).all()


def test_trail_grows_with_updates():
    state = OverlayState()
    state.update(Annotation(frame_idx=0, point_x=10, point_y=10, phase="closed"))
    assert len(state.trail) == 1
    state.update(Annotation(frame_idx=1, point_x=20, point_y=20, phase="opening"))
    assert len(state.trail) == 2
    # Same frame_idx update replaces, does not append.
    state.update(Annotation(frame_idx=1, point_x=21, point_y=21, phase="opening"))
    assert len(state.trail) == 2
    assert state.trail[-1] == (21, 21)
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_playback_render.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tools.playback_annotations'`.

- [ ] **Step 3: Implement the render function + state**

Create `tools/playback_annotations.py`:

```python
"""Animated playback of a manually-labeled landmark on a valve video.

Draws a green crosshair at the first annotated frame's point (origin),
a red dot at the current frame's annotated point, a yellow displacement
arrow from origin to current, and a faded-gray trail through every
labeled point seen so far.

Usage:
    python tools/playback_annotations.py path/to/recording.mp4
    python tools/playback_annotations.py path/to/recording.mp4 \
        --annotations path/to/recording.mp4.annotations.csv \
        --speed 0.5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._annotations import Annotation, read_annotations


WINDOW = "Annotation Playback"

ORIGIN_COLOR = (0, 255, 0)       # green
CURRENT_COLOR = (0, 0, 255)      # red
ARROW_COLOR = (0, 255, 255)      # yellow
TRAIL_COLOR = (180, 180, 180)    # faded gray


class OverlayState:
    """Cumulative state for the playback overlay."""

    def __init__(self) -> None:
        self.origin: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self.last_phase: str = ""
        self.trail: list[tuple[int, int]] = []
        # Map frame_idx -> position-in-trail to support same-frame replacement.
        self._trail_idx: dict[int, int] = {}

    def update(self, ann: Annotation) -> None:
        if self.origin is None:
            self.origin = (ann.point_x, ann.point_y)
        self.current = (ann.point_x, ann.point_y)
        self.last_phase = ann.phase
        if ann.frame_idx in self._trail_idx:
            self.trail[self._trail_idx[ann.frame_idx]] = (ann.point_x, ann.point_y)
        else:
            self._trail_idx[ann.frame_idx] = len(self.trail)
            self.trail.append((ann.point_x, ann.point_y))


def draw_overlay(frame: np.ndarray, state: OverlayState) -> np.ndarray:
    """Return a copy of `frame` with the playback overlay drawn on top."""
    out = frame.copy()
    if state.origin is None:
        return out
    # Trail polyline.
    if len(state.trail) >= 2:
        pts = np.array(state.trail, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], isClosed=False, color=TRAIL_COLOR, thickness=1)
    # Displacement arrow (origin -> current).
    if state.current is not None and state.current != state.origin:
        cv2.arrowedLine(
            out, state.origin, state.current,
            ARROW_COLOR, thickness=2, tipLength=0.05,
        )
    # Origin crosshair.
    ox, oy = state.origin
    cv2.line(out, (ox - 6, oy), (ox + 6, oy), ORIGIN_COLOR, 1)
    cv2.line(out, (ox, oy - 6), (ox, oy + 6), ORIGIN_COLOR, 1)
    # Current dot.
    if state.current is not None:
        cv2.circle(out, state.current, 4, CURRENT_COLOR, -1)
    return out
```

- [ ] **Step 4: Run to verify the tests pass**

```
pytest tests/test_playback_render.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add tools/playback_annotations.py tests/test_playback_render.py
git commit -m "Add playback overlay render function"
```

---

## Task 7: Playback main loop

**Files:**
- Modify: `tools/playback_annotations.py`

This task adds the CLI loop around the already-tested `draw_overlay`. No new automated tests.

- [ ] **Step 1: Append the main loop**

Append to `tools/playback_annotations.py`:

```python
def _draw_hud(
    frame: np.ndarray,
    frame_idx: int,
    total_frames: int,
    state: OverlayState,
    paused: bool,
) -> None:
    n = len(state.trail)
    cv2.putText(
        frame, f"Frame {frame_idx}/{total_frames - 1}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
    )
    cv2.putText(
        frame, f"labeled_seen={n}",
        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )
    if state.last_phase:
        cv2.putText(
            frame, f"phase={state.last_phase}",
            (frame.shape[1] - 220, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
        )
    if paused:
        cv2.putText(
            frame, "PAUSED", (frame.shape[1] - 120, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 200), 2,
        )


def _seek(cap: cv2.VideoCapture, frame_idx: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--annotations", type=Path, default=None)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    if not args.video.exists():
        print(f"File not found: {args.video}")
        sys.exit(1)
    csv_path = args.annotations or args.video.with_suffix(args.video.suffix + ".annotations.csv")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"Cannot open video: {args.video}")
        sys.exit(1)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    base_delay_ms = max(1, int(1000.0 / (fps * max(args.speed, 0.05))))

    annotations = read_annotations(csv_path)
    by_frame: dict[int, Annotation] = {a.frame_idx: a for a in annotations}
    print(f"Loaded {len(annotations)} annotations from {csv_path}")
    print("Controls: SPACE=play/pause  RIGHT=step  LEFT=back  r=restart  q=quit")

    state = OverlayState()
    frame_idx = 0
    paused = False

    def rebuild_state_up_to(target_idx: int) -> OverlayState:
        s = OverlayState()
        for i in sorted(by_frame.keys()):
            if i > target_idx:
                break
            s.update(by_frame[i])
        return s

    frame = _seek(cap, frame_idx)
    if frame is None:
        print("Cannot read first frame")
        sys.exit(1)
    state = rebuild_state_up_to(frame_idx)

    while True:
        if frame_idx in by_frame:
            state.update(by_frame[frame_idx])
        overlaid = draw_overlay(frame, state)
        _draw_hud(overlaid, frame_idx, total_frames, state, paused)
        cv2.imshow(WINDOW, overlaid)

        delay = 0 if paused else base_delay_ms
        key = cv2.waitKey(delay) & 0xFF

        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
        elif key == ord("r"):
            frame_idx = 0
            state = rebuild_state_up_to(frame_idx)
            new_frame = _seek(cap, frame_idx)
            if new_frame is not None:
                frame = new_frame
            paused = True
        elif paused and key in (83, ord("d")) and frame_idx + 1 < total_frames:
            frame_idx += 1
            new_frame = _seek(cap, frame_idx)
            if new_frame is not None:
                frame = new_frame
        elif paused and key in (81, ord("a")) and frame_idx > 0:
            frame_idx -= 1
            state = rebuild_state_up_to(frame_idx)
            new_frame = _seek(cap, frame_idx)
            if new_frame is not None:
                frame = new_frame
        elif not paused:
            if frame_idx + 1 >= total_frames:
                paused = True
                continue
            frame_idx += 1
            new_frame = _seek(cap, frame_idx)
            if new_frame is not None:
                frame = new_frame

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-import**

```
python -c "import tools.playback_annotations"
```

Expected: no output, exit code 0.

- [ ] **Step 3: Re-run all tests**

```
pytest tests/ -v
```

Expected: all tests still pass — adding the main loop did not regress the overlay tests.

- [ ] **Step 4: Manual smoke test**

If you have an MP4 + matching annotations CSV from a Task 5 session:

```
python tools/playback_annotations.py outputs/<recording>.mp4
```

Verify:
- Origin crosshair appears at first labeled frame.
- Yellow arrow follows the current point.
- Trail grows in gray as playback advances.
- `SPACE` pauses; `→`/`←` step; `r` restarts; `q` quits.

- [ ] **Step 5: Commit**

```
git add tools/playback_annotations.py
git commit -m "Add playback main loop with arrow + trail overlay"
```

---

## Task 8: Cycle detection

**Files:**
- Create: `tools/analyze_annotations.py`
- Create: `tests/test_analyze_annotations.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyze_annotations.py`:

```python
"""Tests for tools/analyze_annotations.py — cycle detection + metrics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math

import pytest

from tools._annotations import Annotation
from tools.analyze_annotations import detect_cycles, Cycle


def _ann(i: int, x: int, y: int, p: str) -> Annotation:
    return Annotation(frame_idx=i, point_x=x, point_y=y, phase=p)


def test_detect_cycles_finds_two_complete_cycles():
    # closed -> opening -> open -> closing -> closed -> opening -> open -> closing -> closed
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "open"),
        _ann(6, 0, 0, "closing"),
        _ann(8, 0, 0, "closed"),    # cycle 1 ends + cycle 2 starts
        _ann(10, 0, 0, "opening"),
        _ann(12, 0, 0, "open"),
        _ann(14, 0, 0, "closing"),
        _ann(16, 0, 0, "closed"),   # cycle 2 ends
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 2
    assert cycles[0].start_frame == 0
    assert cycles[0].end_frame == 8
    assert cycles[1].start_frame == 8
    assert cycles[1].end_frame == 16


def test_detect_cycles_drops_leading_partial_cycle():
    # Starts mid-opening — no leading closed → first cycle not yet started.
    rows = [
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "open"),
        _ann(6, 0, 0, "closing"),
        _ann(8, 0, 0, "closed"),    # could only act as start of next cycle
        _ann(10, 0, 0, "opening"),
        _ann(12, 0, 0, "open"),
        _ann(14, 0, 0, "closing"),
        _ann(16, 0, 0, "closed"),   # one complete cycle: 8 -> 16
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 1
    assert cycles[0].start_frame == 8
    assert cycles[0].end_frame == 16


def test_detect_cycles_drops_trailing_incomplete_cycle():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "open"),
        _ann(6, 0, 0, "closing"),
        _ann(8, 0, 0, "closed"),    # one complete cycle
        _ann(10, 0, 0, "opening"),  # trailing partial — no terminating closed
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 1


def test_detect_cycles_skips_out_of_order_phase_sequence():
    # opening -> closing without an `open` in between => invalid; cycle skipped.
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(2, 0, 0, "opening"),
        _ann(4, 0, 0, "closing"),   # missing `open`
        _ann(6, 0, 0, "closed"),
        _ann(8, 0, 0, "opening"),
        _ann(10, 0, 0, "open"),
        _ann(12, 0, 0, "closing"),
        _ann(14, 0, 0, "closed"),   # one valid cycle: 6 -> 14
    ]
    cycles = detect_cycles(rows)
    assert len(cycles) == 1
    assert cycles[0].start_frame == 6
    assert cycles[0].end_frame == 14
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tools.analyze_annotations'`.

- [ ] **Step 3: Implement `detect_cycles`**

Create `tools/analyze_annotations.py`:

```python
"""Cycle detection + per-cycle metrics + CV aggregation for valve annotations.

Mode A (default): runs only on the annotations CSV.
Mode B (--video): additionally compares Farneback dense flow at each
annotated point to the manual frame-to-frame displacement.

Usage:
    python tools/analyze_annotations.py path/to/recording.mp4.annotations.csv
    python tools/analyze_annotations.py path/to/recording.mp4.annotations.csv \
        --video path/to/recording.mp4 --fps 30
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._annotations import Annotation, read_annotations


@dataclass
class Cycle:
    """One complete cardiac cycle: closed -> opening -> open -> closing -> closed."""

    start_frame: int
    end_frame: int
    rows: list[Annotation] = field(default_factory=list)


# Required phase sequence inside a cycle, including both endpoint `closed` frames.
_PHASE_SEQUENCE: tuple[str, ...] = ("closed", "opening", "open", "closing", "closed")


def detect_cycles(rows: Sequence[Annotation]) -> list[Cycle]:
    """Detect complete cardiac cycles from a phase-labeled annotation list.

    A cycle starts at a `closed` annotation and ends at the next `closed`
    annotation, having passed through `opening`, `open`, and `closing` in
    that order. Multiple consecutive frames sharing the same phase are
    allowed (treated as repeats). Out-of-order or missing tokens cause the
    in-progress cycle attempt to be abandoned; cycle search then resumes
    from the next row after the failed start.
    """
    rows = sorted(rows, key=lambda r: r.frame_idx)
    cycles: list[Cycle] = []
    i = 0
    n = len(rows)

    while i < n:
        # Find the next `closed` annotation — the candidate cycle start.
        while i < n and rows[i].phase != "closed":
            i += 1
        if i >= n:
            break
        start_idx = i

        # Walk through _PHASE_SEQUENCE, consuming repeats of the current and
        # previous phase tokens. Token at index 0 is the leading `closed`
        # we already matched at start_idx, so begin searching for token 1.
        token_idx = 1
        j = start_idx + 1
        ok = True
        while token_idx < len(_PHASE_SEQUENCE):
            if j >= n:
                ok = False
                break
            phase = rows[j].phase
            if phase == _PHASE_SEQUENCE[token_idx]:
                token_idx += 1
                j += 1
            elif phase == _PHASE_SEQUENCE[token_idx - 1]:
                # Repeat of the phase we just consumed — allow it.
                j += 1
            else:
                ok = False
                break

        if ok:
            cycle_rows = rows[start_idx:j]
            cycles.append(
                Cycle(
                    start_frame=rows[start_idx].frame_idx,
                    end_frame=rows[j - 1].frame_idx,
                    rows=list(cycle_rows),
                )
            )
            # Terminating `closed` of cycle N is the leading `closed` of
            # cycle N+1, so resume search from j-1.
            i = j - 1
        else:
            # This `closed` did not start a valid cycle — try the next row.
            i = start_idx + 1

    return cycles
```

- [ ] **Step 4: Run to verify the tests pass**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add tools/analyze_annotations.py tests/test_analyze_annotations.py
git commit -m "Add cycle detection from phase-labeled annotations"
```

---

## Task 9: Per-cycle metrics

**Files:**
- Modify: `tools/analyze_annotations.py`
- Modify: `tests/test_analyze_annotations.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_analyze_annotations.py`:

```python
from tools.analyze_annotations import (
    cycle_period_ms,
    path_length_px,
    peak_displacement_px,
)


def test_cycle_period_ms_at_30fps():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(15, 0, 0, "opening"),
        _ann(30, 0, 0, "open"),
        _ann(45, 0, 0, "closing"),
        _ann(60, 0, 0, "closed"),
    ]
    c = detect_cycles(rows)[0]
    # 60 frames at 30 fps -> 2000 ms
    assert math.isclose(cycle_period_ms(c, fps=30.0), 2000.0)


def test_path_length_px_sums_consecutive_distances():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(1, 3, 4, "opening"),    # +5 px (3-4-5 triangle)
        _ann(2, 6, 8, "open"),       # +5 px
        _ann(3, 6, 8, "closing"),    # +0 px
        _ann(4, 0, 0, "closed"),     # +10 px
    ]
    c = detect_cycles(rows)[0]
    assert math.isclose(path_length_px(c), 5.0 + 5.0 + 0.0 + 10.0)


def test_peak_displacement_px_is_max_distance_from_start():
    rows = [
        _ann(0, 0, 0, "closed"),
        _ann(1, 3, 4, "opening"),    # 5 from start
        _ann(2, 6, 8, "open"),       # 10 from start (peak)
        _ann(3, 3, 4, "closing"),    # 5 from start
        _ann(4, 0, 0, "closed"),     # 0 from start
    ]
    c = detect_cycles(rows)[0]
    assert math.isclose(peak_displacement_px(c), 10.0)
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: 3 new FAILs — `ImportError` for the metric functions.

- [ ] **Step 3: Implement the metrics**

Append to `tools/analyze_annotations.py`:

```python
def cycle_period_ms(cycle: Cycle, fps: float) -> float:
    """Cycle duration in milliseconds, given the source-video frame rate."""
    frames = cycle.end_frame - cycle.start_frame
    return (frames / fps) * 1000.0


def path_length_px(cycle: Cycle) -> float:
    """Sum of pixel distances between consecutive annotated points in the cycle."""
    total = 0.0
    for a, b in zip(cycle.rows, cycle.rows[1:]):
        total += math.hypot(b.point_x - a.point_x, b.point_y - a.point_y)
    return total


def peak_displacement_px(cycle: Cycle) -> float:
    """Max distance from the cycle-start point to any point in the cycle."""
    if not cycle.rows:
        return 0.0
    sx, sy = cycle.rows[0].point_x, cycle.rows[0].point_y
    return max(math.hypot(r.point_x - sx, r.point_y - sy) for r in cycle.rows)
```

- [ ] **Step 4: Run to verify they pass**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: all 7 passed.

- [ ] **Step 5: Commit**

```
git add tools/analyze_annotations.py tests/test_analyze_annotations.py
git commit -m "Add per-cycle metrics: period, path length, peak displacement"
```

---

## Task 10: CV aggregation + Mode A CLI

**Files:**
- Modify: `tools/analyze_annotations.py`
- Modify: `tests/test_analyze_annotations.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_analyze_annotations.py`:

```python
from tools.analyze_annotations import aggregate_cycles


def test_cv_zero_for_identical_cycles():
    # Build identical 30-frame cycles. Each iteration appends the inner
    # phase rows for one cycle (closed/opening/open/closing); the final
    # `closed` after the loop terminates the last cycle. With 4 iterations
    # plus the trailing closed, we get four `closed` boundaries spaced
    # 30 frames apart -> 4 complete cycles, all with identical kinematics.
    rows: list[Annotation] = []
    for cycle_idx in range(4):
        start = cycle_idx * 30
        rows.extend([
            _ann(start + 0, 0, 0, "closed"),
            _ann(start + 7, 3, 4, "opening"),
            _ann(start + 15, 6, 8, "open"),
            _ann(start + 22, 3, 4, "closing"),
        ])
    rows.append(_ann(120, 0, 0, "closed"))

    cycles = detect_cycles(rows)
    assert len(cycles) >= 3

    agg = aggregate_cycles(cycles, fps=30.0)
    assert agg["n_cycles_complete"] >= 3
    assert math.isclose(agg["cv_cycle_period_ms"], 0.0, abs_tol=1e-9)
    assert math.isclose(agg["cv_peak_displacement_px"], 0.0, abs_tol=1e-9)


def test_cv_nonzero_for_varied_periods():
    rows = []
    # Cycle 1: 30 frames; Cycle 2: 60 frames.
    for start, length in [(0, 30), (30, 60)]:
        rows.extend([
            _ann(start, 0, 0, "closed"),
            _ann(start + length // 4, 3, 4, "opening"),
            _ann(start + length // 2, 6, 8, "open"),
            _ann(start + 3 * length // 4, 3, 4, "closing"),
        ])
    rows.append(_ann(90, 0, 0, "closed"))
    cycles = detect_cycles(rows)
    assert len(cycles) == 2
    agg = aggregate_cycles(cycles, fps=30.0)
    assert agg["cv_cycle_period_ms"] > 0.0
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: 2 new FAILs — `ImportError: cannot import name 'aggregate_cycles'`.

- [ ] **Step 3: Implement `aggregate_cycles` and the Mode A CLI**

Append to `tools/analyze_annotations.py`:

```python
def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var)


def _cv(mean: float, std: float) -> float:
    return 0.0 if mean == 0 else std / mean


def aggregate_cycles(cycles: Sequence[Cycle], fps: float) -> dict:
    """Aggregate per-cycle metrics across complete cycles."""
    periods = [cycle_period_ms(c, fps) for c in cycles]
    peaks = [peak_displacement_px(c) for c in cycles]
    paths = [path_length_px(c) for c in cycles]

    p_mean, p_std = _mean_std(periods)
    pk_mean, pk_std = _mean_std(peaks)
    pl_mean, pl_std = _mean_std(paths)

    return {
        "n_cycles_complete": len(cycles),
        "mean_cycle_period_ms": p_mean,
        "std_cycle_period_ms": p_std,
        "cv_cycle_period_ms": _cv(p_mean, p_std),
        "mean_peak_displacement_px": pk_mean,
        "std_peak_displacement_px": pk_std,
        "cv_peak_displacement_px": _cv(pk_mean, pk_std),
        "mean_path_length_px": pl_mean,
        "std_path_length_px": pl_std,
        "cv_path_length_px": _cv(pl_mean, pl_std),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path,
                        help="Path to the annotations CSV.")
    parser.add_argument("--video", type=Path, default=None,
                        help="Source MP4 (enables Mode B Farneback comparison).")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="Frame rate for period calculation (default 30).")
    args = parser.parse_args()

    if not args.annotations.exists():
        print(f"Annotations CSV not found: {args.annotations}")
        sys.exit(1)
    rows = read_annotations(args.annotations)
    cycles = detect_cycles(rows)
    agg = aggregate_cycles(cycles, fps=args.fps)

    print("=== Mode A: cycle metrics ===")
    print(f"n_cycles_complete = {agg['n_cycles_complete']}")
    print(f"cycle_period_ms      mean={agg['mean_cycle_period_ms']:.1f}  "
          f"std={agg['std_cycle_period_ms']:.1f}  CV={agg['cv_cycle_period_ms']:.4f}")
    print(f"peak_displacement_px mean={agg['mean_peak_displacement_px']:.2f}  "
          f"std={agg['std_peak_displacement_px']:.2f}  CV={agg['cv_peak_displacement_px']:.4f}")
    print(f"path_length_px       mean={agg['mean_path_length_px']:.2f}  "
          f"std={agg['std_path_length_px']:.2f}  CV={agg['cv_path_length_px']:.4f}")

    out_json = args.annotations.with_suffix(".analysis.json")
    out_json.write_text(json.dumps(agg, indent=2))
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```

Expected: all 19 tests pass.

- [ ] **Step 5: Commit**

```
git add tools/analyze_annotations.py tests/test_analyze_annotations.py
git commit -m "Add CV aggregation and Mode A analyzer CLI"
```

---

## Task 11: Farneback flow at point (Mode B helper)

**Files:**
- Modify: `tools/analyze_annotations.py`
- Modify: `tests/test_analyze_annotations.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_analyze_annotations.py`:

```python
import numpy as np

from tools.analyze_annotations import sample_flow_at_point


def test_sample_flow_at_point_bilinear():
    # Build a 10x10 flow field where flow[y, x] = (x, y).
    h, w = 10, 10
    flow = np.zeros((h, w, 2), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            flow[y, x] = (float(x), float(y))

    # At an exact pixel.
    fx, fy = sample_flow_at_point(flow, 5, 7)
    assert math.isclose(fx, 5.0)
    assert math.isclose(fy, 7.0)

    # At a sub-pixel location: flow varies linearly with x and y, so bilinear
    # interpolation should give the exact (x, y).
    fx, fy = sample_flow_at_point(flow, 5.25, 7.75)
    assert math.isclose(fx, 5.25, abs_tol=1e-6)
    assert math.isclose(fy, 7.75, abs_tol=1e-6)


def test_sample_flow_at_point_clamps_to_bounds():
    flow = np.zeros((10, 10, 2), dtype=np.float32)
    flow[:, :] = (1.0, 2.0)
    # Out-of-bounds: should clamp rather than crash.
    fx, fy = sample_flow_at_point(flow, -5, -5)
    assert math.isclose(fx, 1.0)
    assert math.isclose(fy, 2.0)
    fx, fy = sample_flow_at_point(flow, 100, 100)
    assert math.isclose(fx, 1.0)
    assert math.isclose(fy, 2.0)
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: 2 new FAILs — `ImportError: cannot import name 'sample_flow_at_point'`.

- [ ] **Step 3: Implement `sample_flow_at_point`**

Append to `tools/analyze_annotations.py` (above `def main()`):

```python
def sample_flow_at_point(flow: "np.ndarray", x: float, y: float) -> tuple[float, float]:
    """Bilinearly sample a 2-channel flow field at sub-pixel `(x, y)`.

    `flow` is shape (H, W, 2) with channel 0 = dx, channel 1 = dy. Out-of-bounds
    coordinates are clamped to the nearest in-bounds pixel.
    """
    import numpy as np
    h, w = flow.shape[:2]
    # Clamp to [0, w-1] x [0, h-1].
    x = max(0.0, min(float(x), w - 1))
    y = max(0.0, min(float(y), h - 1))
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    x1 = min(x0 + 1, w - 1)
    y1 = min(y0 + 1, h - 1)
    tx = x - x0
    ty = y - y0
    f00 = flow[y0, x0]
    f10 = flow[y0, x1]
    f01 = flow[y1, x0]
    f11 = flow[y1, x1]
    fx = (1 - ty) * ((1 - tx) * f00[0] + tx * f10[0]) + ty * ((1 - tx) * f01[0] + tx * f11[0])
    fy = (1 - ty) * ((1 - tx) * f00[1] + tx * f10[1]) + ty * ((1 - tx) * f01[1] + tx * f11[1])
    return float(fx), float(fy)
```

- [ ] **Step 4: Run to verify they pass**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add tools/analyze_annotations.py tests/test_analyze_annotations.py
git commit -m "Add bilinear flow sampling at sub-pixel points"
```

---

## Task 12: Mode B integration — Farneback vs manual displacement

**Files:**
- Modify: `tools/analyze_annotations.py`
- Modify: `tests/test_analyze_annotations.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_analyze_annotations.py`:

```python
from tools.analyze_annotations import compare_flow_to_manual


def test_compare_flow_to_manual_zero_error_when_flow_matches():
    """A flow field that exactly matches the manual displacement gives zero error."""
    # Two consecutive annotations: point moves (5, 3) px.
    rows = [
        _ann(0, 100, 100, "closed"),
        _ann(1, 105, 103, "opening"),
    ]
    h, w = 200, 200
    # flow_pair[i] is the flow field that takes frame i -> frame i+1.
    flow = np.full((h, w, 2), [5.0, 3.0], dtype=np.float32)
    flow_provider = {(0, 1): flow}
    result = compare_flow_to_manual(rows, flow_provider)
    assert result["n_pairs"] == 1
    assert result["n_pairs_skipped_nonconsecutive"] == 0
    assert math.isclose(result["median_error_px"], 0.0, abs_tol=1e-6)


def test_compare_flow_to_manual_known_offset():
    """Flow off by (1, 0) -> per-pair error == 1 px."""
    rows = [
        _ann(0, 100, 100, "closed"),
        _ann(1, 105, 103, "opening"),
    ]
    h, w = 200, 200
    flow = np.full((h, w, 2), [4.0, 3.0], dtype=np.float32)  # off by (-1, 0)
    flow_provider = {(0, 1): flow}
    result = compare_flow_to_manual(rows, flow_provider)
    assert math.isclose(result["median_error_px"], 1.0, abs_tol=1e-6)


def test_compare_flow_to_manual_skips_nonconsecutive_pairs():
    rows = [
        _ann(0, 100, 100, "closed"),
        _ann(5, 110, 100, "opening"),  # non-consecutive (gap of 5 frames)
    ]
    flow_provider: dict = {}
    result = compare_flow_to_manual(rows, flow_provider)
    assert result["n_pairs"] == 0
    assert result["n_pairs_skipped_nonconsecutive"] == 1
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_analyze_annotations.py -v
```

Expected: 3 new FAILs — `ImportError: cannot import name 'compare_flow_to_manual'`.

- [ ] **Step 3: Implement `compare_flow_to_manual`**

Append to `tools/analyze_annotations.py` (above `def main()`):

```python
def compare_flow_to_manual(
    rows: Sequence[Annotation],
    flow_provider: "dict[tuple[int, int], np.ndarray]",
) -> dict:
    """Compare Farneback flow at each labeled point to the manual displacement.

    `flow_provider` maps `(prev_frame_idx, curr_frame_idx)` -> flow field of
    shape (H, W, 2). The caller is responsible for computing/loading these
    flow fields lazily (they are large). Only consecutive frame pairs
    (curr - prev == 1) are evaluated.

    Returns a dict with `n_pairs`, `n_pairs_skipped_nonconsecutive`,
    `median_error_px`, `p95_error_px`.
    """
    import numpy as np
    rows = sorted(rows, key=lambda r: r.frame_idx)
    errors: list[float] = []
    skipped = 0

    for a, b in zip(rows, rows[1:]):
        if b.frame_idx - a.frame_idx != 1:
            skipped += 1
            continue
        manual_dx = b.point_x - a.point_x
        manual_dy = b.point_y - a.point_y
        flow = flow_provider.get((a.frame_idx, b.frame_idx))
        if flow is None:
            skipped += 1
            continue
        fx, fy = sample_flow_at_point(flow, a.point_x, a.point_y)
        err = math.hypot(fx - manual_dx, fy - manual_dy)
        errors.append(err)

    if not errors:
        return {
            "n_pairs": 0,
            "n_pairs_skipped_nonconsecutive": skipped,
            "median_error_px": 0.0,
            "p95_error_px": 0.0,
        }
    arr = np.array(errors)
    return {
        "n_pairs": len(errors),
        "n_pairs_skipped_nonconsecutive": skipped,
        "median_error_px": float(np.median(arr)),
        "p95_error_px": float(np.percentile(arr, 95)),
    }
```

- [ ] **Step 4: Wire Mode B into `main()`**

Modify `tools/analyze_annotations.py`'s `main()`. After the Mode A summary block (the three `print(...)` lines for cycle_period / peak_displacement / path_length) and before `out_json = args.annotations.with_suffix(...)`, insert:

```python
    if args.video is not None:
        if not args.video.exists():
            print(f"Video not found: {args.video}")
            sys.exit(1)
        import cv2
        cap = cv2.VideoCapture(str(args.video))
        if not cap.isOpened():
            print(f"Cannot open video: {args.video}")
            sys.exit(1)

        # Build a flow_provider lazily, only for consecutive labeled pairs.
        FARNEBACK_PARAMS = dict(
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
        )
        consecutive_pairs = [
            (a.frame_idx, b.frame_idx)
            for a, b in zip(rows, rows[1:])
            if b.frame_idx - a.frame_idx == 1
        ]
        flow_provider: dict = {}
        for prev_idx, curr_idx in consecutive_pairs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, prev_idx)
            ret_p, prev_frame = cap.read()
            cap.set(cv2.CAP_PROP_POS_FRAMES, curr_idx)
            ret_c, curr_frame = cap.read()
            if not (ret_p and ret_c):
                continue
            prev_g = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
            curr_g = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
            flow_provider[(prev_idx, curr_idx)] = cv2.calcOpticalFlowFarneback(
                prev_g, curr_g, None, **FARNEBACK_PARAMS,
            )
        cap.release()

        flow_result = compare_flow_to_manual(rows, flow_provider)
        agg["mode_b"] = flow_result

        print("\n=== Mode B: dense-flow point-tracking accuracy ===")
        print(f"n_pairs                      = {flow_result['n_pairs']}")
        print(f"n_pairs_skipped_nonconsec    = {flow_result['n_pairs_skipped_nonconsecutive']}")
        print(f"median_error_px              = {flow_result['median_error_px']:.3f}")
        print(f"p95_error_px                 = {flow_result['p95_error_px']:.3f}")
```

- [ ] **Step 5: Run all tests**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Manual smoke test (optional, requires a real recording)**

If you have a recording with annotations:

```
python tools/analyze_annotations.py outputs/<recording>.mp4.annotations.csv \
    --video outputs/<recording>.mp4 --fps 30
```

Verify both Mode A and Mode B sections print, and `<recording>.mp4.analysis.json` contains a `mode_b` key.

- [ ] **Step 7: Commit**

```
git add tools/analyze_annotations.py tests/test_analyze_annotations.py
git commit -m "Add Mode B: Farneback dense-flow vs manual displacement"
```

---

## Task 13: Update PRD and CLAUDE.md to reflect the new tools

**Files:**
- Modify: `docs/PRD.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Inspect what each currently says about CV pipeline state**

```
grep -n "annot\|flow_export\|validation" docs/PRD.md CLAUDE.md
```

Read the matching sections to understand the surrounding text — do not rewrite anything that wasn't directly affected by this plan.

- [ ] **Step 2: Update PRD §12 build-state table (or equivalent)**

Add the three new tools (annotator, playback, analyzer) and mark them as built. Reference the design doc and this plan.

- [ ] **Step 3: Update CLAUDE.md "CV Pipeline — Current State" section**

Reflect that the validation strategy is now point-displacement + phase-timing CV, not polygon IoU + cycle-period FFT. Reference `docs/plans/2026-05-04-point-annotator-design.md` and this plan.

- [ ] **Step 4: Run all tests to make sure nothing regressed**

```
pytest tests/ -v
```

Expected: all tests still pass.

- [ ] **Step 5: Commit**

```
git add docs/PRD.md CLAUDE.md
git commit -m "Update PRD and CLAUDE.md for point-annotator pipeline"
```

---

## Task 14: Final integration check

**Files:** none (manual verification).

- [ ] **Step 1: Run the full test suite**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Smoke-import every new module**

```
python -c "import tools._annotations; import tools.annotate_point; import tools.playback_annotations; import tools.analyze_annotations"
```

Expected: no output, exit code 0.

- [ ] **Step 3: Verify the CLI surfaces of all three tools**

```
python tools/annotate_point.py --help
python tools/playback_annotations.py --help
python tools/analyze_annotations.py --help
```

Expected: each prints argparse help text and exits 0.

- [ ] **Step 4: Branch is clean**

```
git status
```

Expected: clean working tree, on `feature/flow-export`.

---
