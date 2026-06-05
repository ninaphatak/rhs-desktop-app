"""Dual-camera landmark annotator for stereo metric displacement.

Shows synchronized frames from cam0 and cam1 side-by-side. The user
clicks the SAME physical landmark in both views, then types a phase
label, then advances to the next frame. Output is a stereo CSV that
feeds directly into tools/triangulate.py.

Usage:
    python tools/annotate_stereo_point.py CAM0_VIDEO CAM1_VIDEO
    python tools/annotate_stereo_point.py CAM0 CAM1 --output point6.csv --step 3

Controls (in the OpenCV window):
    Left-click in cam0 pane    Set landmark in cam0 (red marker = confirmed)
    Left-click in cam1 pane    Set landmark in cam1
    1 / 2 / 3 / 4              Set phase: open / opening / closing / closed
    RIGHT arrow or 'd'         Advance by --step frames (carries forward prior annotation)
    LEFT arrow or 'a'          Go back by --step frames (carries forward as well)
    'u'                        Undo current frame's annotation (clears both points + phase)
    's'                        Save annotations CSV
    'q'                        Quit (prompts to save if dirty)

Carry-forward behavior (added for sparse labeling + interpolation pipeline):
    When you advance to a frame that has no annotation yet, the previous
    frame's (u0, v0, u1, v1, phase) is auto-populated as a YELLOW marker
    ("carried"). Click to move the points or hit a phase key to change
    phase — the marker turns RED ("confirmed") once you touch it. Carried
    annotations save too, so you only need to adjust the ones that
    actually moved between frames.

Output CSV (one row per fully-annotated frame, sparse):
    frame_idx, u0, v0, u1, v1, phase

Default output path: <cam0_video>.stereo_annotations.csv (alongside cam0 video).
Use --output to specify a different path (required when annotating multiple
points in separate sessions).

Auto-resumes from the output CSV if it exists.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


WINDOW = "Stereo Annotator (cam0 | cam1)"
PHASE_HOTKEYS = {ord("1"): "open", ord("2"): "opening",
                 ord("3"): "closing", ord("4"): "closed"}
PHASES = {"open", "opening", "closing", "closed"}

DISPLAY_MAX_WIDTH = 1900       # combined width in pixels (cam0 + cam1 stacked horizontally)


@dataclass
class StereoAnnotation:
    frame_idx: int
    u0: float | None = None
    v0: float | None = None
    u1: float | None = None
    v1: float | None = None
    phase: str = ""
    carried: bool = False  # GUI-only: True if auto-populated from a previous frame and not yet touched

    @property
    def complete(self) -> bool:
        return (self.u0 is not None and self.u1 is not None
                and self.phase in PHASES)


@dataclass
class State:
    by_frame: dict[int, StereoAnnotation] = field(default_factory=dict)
    frame_idx: int = 0
    dirty: bool = False
    scale: float = 1.0   # display scale (each pane scaled by this for screen fit)
    pane_w_disp: int = 0  # width of one camera pane in display coords


def read_stereo_csv(path: Path) -> list[StereoAnnotation]:
    out: list[StereoAnnotation] = []
    if not path.exists():
        return out
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            out.append(StereoAnnotation(
                frame_idx=int(r["frame_idx"]),
                u0=float(r["u0"]) if r["u0"] else None,
                v0=float(r["v0"]) if r["v0"] else None,
                u1=float(r["u1"]) if r["u1"] else None,
                v1=float(r["v1"]) if r["v1"] else None,
                phase=r.get("phase", "").strip(),
            ))
    return out


def write_stereo_csv(path: Path, annotations: list[StereoAnnotation]) -> None:
    annotations = sorted(annotations, key=lambda a: a.frame_idx)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_idx", "u0", "v0", "u1", "v1", "phase"])
        for a in annotations:
            if not a.complete:
                continue
            w.writerow([a.frame_idx,
                        f"{a.u0:.2f}", f"{a.v0:.2f}",
                        f"{a.u1:.2f}", f"{a.v1:.2f}",
                        a.phase])


def _on_mouse(event: int, x: int, y: int, flags: int, state: State) -> None:
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    # x, y are in DISPLAY coordinates. Convert to source-frame pixel coords.
    # The display has cam0 on the left, cam1 on the right, each scaled by state.scale.
    inv = 1.0 / state.scale if state.scale else 1.0
    if x < state.pane_w_disp:
        # Click in cam0 pane
        u0 = x * inv
        v0 = y * inv
        ann = state.by_frame.setdefault(state.frame_idx, StereoAnnotation(state.frame_idx))
        ann.u0, ann.v0 = u0, v0
    else:
        # Click in cam1 pane
        u1 = (x - state.pane_w_disp) * inv
        v1 = y * inv
        ann = state.by_frame.setdefault(state.frame_idx, StereoAnnotation(state.frame_idx))
        ann.u1, ann.v1 = u1, v1
    ann.carried = False
    state.dirty = True


def _draw_pane(frame: np.ndarray, ann: StereoAnnotation, side: str, state: State) -> np.ndarray:
    """Annotate one camera pane (side='cam0' or 'cam1') and resize for display."""
    out = frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    u, v = (ann.u0, ann.v0) if side == "cam0" else (ann.u1, ann.v1)
    if u is not None and v is not None:
        # Yellow if this annotation was carried from a previous frame and the user
        # hasn't touched it yet; red once confirmed by a click/phase keypress.
        color = (0, 220, 255) if ann.carried else (0, 0, 255)
        cv2.drawMarker(out, (int(u), int(v)), color,
                       markerType=cv2.MARKER_CROSS, markerSize=24, thickness=2)
        cv2.circle(out, (int(u), int(v)), 6, color, 2)
    cv2.putText(out, side, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    h, w = out.shape[:2]
    new_w = int(w * state.scale)
    new_h = int(h * state.scale)
    return cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _render(cam0_frame, cam1_frame, ann: StereoAnnotation, state: State,
            n_total: int, n_done: int, n_carried: int, step: int) -> np.ndarray:
    left = _draw_pane(cam0_frame, ann, "cam0", state)
    right = _draw_pane(cam1_frame, ann, "cam1", state)
    combined = np.hstack([left, right])
    status = "carried" if ann.carried else ("confirmed" if ann.complete else "-")
    txt = (f"frame {state.frame_idx}/{n_total - 1}  step={step}  "
           f"phase={ann.phase or '-'}  "
           f"cam0={'set' if ann.u0 is not None else '-'}  "
           f"cam1={'set' if ann.u1 is not None else '-'}  "
           f"status={status}  "
           f"saved={n_done} ({n_carried} carried){' *' if state.dirty else ''}")
    cv2.putText(combined, txt, (12, combined.shape[0] - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return combined


def _seek(cap: cv2.VideoCapture, frame_idx: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def _carry_forward(state: State, src_frame: int, dst_frame: int) -> None:
    """If dst_frame has no annotation, seed it from src_frame's annotation as carried."""
    if dst_frame in state.by_frame:
        return
    src = state.by_frame.get(src_frame)
    if src is None or (src.u0 is None and src.u1 is None and not src.phase):
        return
    state.by_frame[dst_frame] = StereoAnnotation(
        frame_idx=dst_frame,
        u0=src.u0, v0=src.v0,
        u1=src.u1, v1=src.v1,
        phase=src.phase,
        carried=True,
    )
    state.dirty = True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cam0_video", type=Path)
    ap.add_argument("cam1_video", type=Path)
    ap.add_argument("--output", type=Path, default=None,
                    help="Output CSV path (default: <cam0_video>.stereo_annotations.csv). "
                         "Required when annotating multiple points in separate sessions.")
    ap.add_argument("--step", type=int, default=1,
                    help="Frames to advance/retreat on d/a (default 1). "
                         "Use a larger value (e.g. 3) to label sparsely; "
                         "tools/splice_manual_into_tracks.py interpolates between labels.")
    args = ap.parse_args()

    if not args.cam0_video.exists() or not args.cam1_video.exists():
        print("Video file not found"); sys.exit(1)
    if args.step < 1:
        print("--step must be >= 1"); sys.exit(1)

    csv_path = args.output if args.output else args.cam0_video.with_suffix(args.cam0_video.suffix + ".stereo_annotations.csv")
    cap0 = cv2.VideoCapture(str(args.cam0_video))
    cap1 = cv2.VideoCapture(str(args.cam1_video))
    if not (cap0.isOpened() and cap1.isOpened()):
        print("Cannot open videos"); sys.exit(1)

    n0 = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT))
    n1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
    n_total = min(n0, n1)
    if n0 != n1:
        print(f"WARNING: cam0 has {n0} frames, cam1 has {n1}; iterating over min={n_total}")

    src_w = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
    state = State()
    # Fit two panes side-by-side under DISPLAY_MAX_WIDTH
    state.scale = min(1.0, (DISPLAY_MAX_WIDTH / 2) / src_w)
    state.pane_w_disp = int(src_w * state.scale)
    print(f"Source frame: {src_w}x{src_h} per cam; display scale={state.scale:.2f}; "
          f"combined window: {state.pane_w_disp * 2}x{int(src_h * state.scale)}")

    # Resume from existing CSV
    for ann in read_stereo_csv(csv_path):
        state.by_frame[ann.frame_idx] = ann
    print(f"Loaded {len(state.by_frame)} prior annotations from {csv_path}")
    print("Controls: click cam0/cam1 to set landmark | 1=open 2=opening 3=closing 4=closed | "
          ">/d=next, </a=back, u=undo, s=save, q=quit")

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, _on_mouse, state)

    frame0 = _seek(cap0, 0); frame1 = _seek(cap1, 0)
    if frame0 is None or frame1 is None:
        print("Cannot read first frame"); sys.exit(1)

    while True:
        ann = state.by_frame.get(state.frame_idx, StereoAnnotation(state.frame_idx))
        n_done = sum(1 for a in state.by_frame.values() if a.complete)
        n_carried = sum(1 for a in state.by_frame.values() if a.complete and a.carried)
        cv2.imshow(WINDOW, _render(frame0, frame1, ann, state, n_total, n_done, n_carried, args.step))
        key = cv2.waitKey(20) & 0xFF

        if key == ord("q"):
            if state.dirty:
                print("\nUnsaved changes. Press 'q' again to quit without saving, or 's' to save.")
                k2 = cv2.waitKey(0) & 0xFF
                if k2 == ord("s"):
                    write_stereo_csv(csv_path, list(state.by_frame.values()))
                    print(f"Saved {sum(1 for a in state.by_frame.values() if a.complete)} annotations to {csv_path}")
                elif k2 != ord("q"):
                    continue
            break
        elif key == ord("s"):
            write_stereo_csv(csv_path, list(state.by_frame.values()))
            state.dirty = False
            print(f"Saved {sum(1 for a in state.by_frame.values() if a.complete)} annotations to {csv_path}")
        elif key in PHASE_HOTKEYS:
            ann = state.by_frame.setdefault(state.frame_idx, StereoAnnotation(state.frame_idx))
            ann.phase = PHASE_HOTKEYS[key]
            ann.carried = False
            state.dirty = True
        elif key == ord("u"):
            state.by_frame.pop(state.frame_idx, None)
            state.dirty = True
        elif key in (83, ord("d")) and state.frame_idx + args.step < n_total:  # right
            src = state.frame_idx
            state.frame_idx += args.step
            _carry_forward(state, src, state.frame_idx)
            new0 = _seek(cap0, state.frame_idx)
            new1 = _seek(cap1, state.frame_idx)
            if new0 is not None: frame0 = new0
            if new1 is not None: frame1 = new1
        elif key in (81, ord("a")) and state.frame_idx - args.step >= 0:  # left
            src = state.frame_idx
            state.frame_idx -= args.step
            _carry_forward(state, src, state.frame_idx)
            new0 = _seek(cap0, state.frame_idx)
            new1 = _seek(cap1, state.frame_idx)
            if new0 is not None: frame0 = new0
            if new1 is not None: frame1 = new1

    cap0.release(); cap1.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
