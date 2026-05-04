"""Manual point + per-frame phase annotator for valve videos.

Click to label the same anatomical landmark on each frame. Number keys
1/2/3/4 set the cardiac phase (open/opening/closing/closed). Output is
a sparse CSV next to the input video.

Usage:
    python tools/annotate_point.py path/to/recording.mp4

Note: a click without a subsequent phase keypress defaults to phase=closed
to keep half-labeled CSVs conservative for downstream cycle analysis.
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
            phase = existing.phase if existing else "closed"
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
