"""Frame-aware dual-camera seed picker for the intersection tracker.

Lets you scrub through frames until you find a clean reference frame
(e.g. fully closed valve) before clicking. The frame where you place
the FIRST point becomes the anchor frame for the tracker; subsequent
clicks must land on the same frame. Press 'r' to clear all points and
unlock frame navigation again.

Output: <cam0_video>.track_seeds.json
The output's frame_idx field is the anchor frame chosen above, which
tools/track_intersections.py uses as the starting frame for tracking.

Usage:
    python tools/pick_track_seeds.py CAM0_VIDEO CAM1_VIDEO [--frame N]

Controls:
    LEFT  / a       Previous frame  (locked once any points are placed)
    RIGHT / d       Next frame       (locked once any points are placed)
    SHIFT+LEFT      Back 10 frames
    SHIFT+RIGHT     Forward 10 frames
    HOME            Jump to frame 0
    Left-click cam0 Place / advance the next cam0 seed (locks the anchor frame)
    Left-click cam1 Place / advance the next cam1 seed
    u               Undo last click
    r               Reset: clear all points, unlock navigation
    s               Save and continue (cam0/cam1 counts must match)
    q               Quit (prompts to save if dirty)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._tracks import color_bgr_for_point


WINDOW = "Seed Picker (cam0 | cam1)"
DISPLAY_MAX_WIDTH = 1900


@dataclass
class State:
    current_frame_idx: int = 0
    anchor_frame_idx: int | None = None  # set on first click; None means unlocked
    cam0_points: list[tuple[float, float]] = field(default_factory=list)
    cam1_points: list[tuple[float, float]] = field(default_factory=list)
    last_pane: str = ""
    scale: float = 1.0
    pane_w_disp: int = 0
    dirty: bool = False

    @property
    def locked(self) -> bool:
        return self.anchor_frame_idx is not None


def _on_mouse(event: int, x: int, y: int, flags: int, state: State) -> None:
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    # First click locks the anchor to the currently-displayed frame.
    if state.anchor_frame_idx is None:
        state.anchor_frame_idx = state.current_frame_idx
    elif state.current_frame_idx != state.anchor_frame_idx:
        # Should not be reachable in practice — navigation is blocked once locked.
        print(f"  click ignored: anchor frame is {state.anchor_frame_idx}, "
              f"current is {state.current_frame_idx}. Press 'r' to reset.")
        return

    inv = 1.0 / state.scale if state.scale else 1.0
    if x < state.pane_w_disp:
        u, v = x * inv, y * inv
        state.cam0_points.append((u, v))
        state.last_pane = "cam0"
    else:
        u, v = (x - state.pane_w_disp) * inv, y * inv
        state.cam1_points.append((u, v))
        state.last_pane = "cam1"
    state.dirty = True


def _draw_pane(frame: np.ndarray, points: list[tuple[float, float]],
               side: str, state: State, show_points: bool) -> np.ndarray:
    out = frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if show_points:
        for pid, (u, v) in enumerate(points):
            color = color_bgr_for_point(pid)
            center = (int(round(u)), int(round(v)))
            cv2.drawMarker(out, center, color, markerType=cv2.MARKER_CROSS,
                           markerSize=24, thickness=2)
            cv2.circle(out, center, 8, color, 2)
            cv2.putText(out, str(pid), (center[0] + 10, center[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.putText(out, side, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    h, w = out.shape[:2]
    return cv2.resize(out, (int(w * state.scale), int(h * state.scale)),
                      interpolation=cv2.INTER_AREA)


def _render(cam0_frame, cam1_frame, state: State, n_total: int) -> np.ndarray:
    # Only show point overlays when the currently displayed frame IS the anchor frame
    on_anchor = (state.anchor_frame_idx is None
                 or state.anchor_frame_idx == state.current_frame_idx)
    left = _draw_pane(cam0_frame, state.cam0_points, "cam0", state, on_anchor)
    right = _draw_pane(cam1_frame, state.cam1_points, "cam1", state, on_anchor)
    combined = np.hstack([left, right])
    n0, n1 = len(state.cam0_points), len(state.cam1_points)

    if state.locked:
        anchor_str = f"anchor=frame {state.anchor_frame_idx}  [locked]"
    else:
        anchor_str = "anchor=unset  [navigate freely; first click locks anchor]"
    parts = [f"frame {state.current_frame_idx}/{n_total - 1}",
             anchor_str,
             f"cam0={n0}",
             f"cam1={n1}"]
    if n0 != n1:
        parts.append("(counts differ)")
    if state.dirty:
        parts.append("*")
    cv2.putText(combined, "  ".join(parts),
                (12, combined.shape[0] - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return combined


def _seek(cap0, cap1, frame_idx: int) -> tuple[np.ndarray | None, np.ndarray | None]:
    cap0.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    cap1.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret0, f0 = cap0.read()
    ret1, f1 = cap1.read()
    return (f0 if ret0 else None, f1 if ret1 else None)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cam0_video", type=Path)
    ap.add_argument("cam1_video", type=Path)
    ap.add_argument("--frame", type=int, default=0,
                    help="Initial frame to display (default 0). The anchor frame "
                         "is determined by your first click, not this arg.")
    args = ap.parse_args()

    if not args.cam0_video.exists() or not args.cam1_video.exists():
        print("Video file not found"); sys.exit(1)

    cap0 = cv2.VideoCapture(str(args.cam0_video))
    cap1 = cv2.VideoCapture(str(args.cam1_video))
    if not (cap0.isOpened() and cap1.isOpened()):
        print("Cannot open videos"); sys.exit(1)
    n_total = min(int(cap0.get(cv2.CAP_PROP_FRAME_COUNT)),
                  int(cap1.get(cv2.CAP_PROP_FRAME_COUNT)))

    state = State()
    state.current_frame_idx = max(0, min(args.frame, n_total - 1))

    out_path = args.cam0_video.with_suffix(args.cam0_video.suffix + ".track_seeds.json")
    if out_path.exists():
        print(f"Resuming from {out_path}")
        data = json.loads(out_path.read_text())
        state.anchor_frame_idx = int(data["frame_idx"])
        state.current_frame_idx = state.anchor_frame_idx
        for p in data.get("points", []):
            state.cam0_points.append((float(p["u0"]), float(p["v0"])))
            state.cam1_points.append((float(p["u1"]), float(p["v1"])))
        print(f"  loaded {len(state.cam0_points)} points, anchor=frame {state.anchor_frame_idx}")

    frame0, frame1 = _seek(cap0, cap1, state.current_frame_idx)
    if frame0 is None or frame1 is None:
        print(f"Cannot read frame {state.current_frame_idx}"); sys.exit(1)

    src_w = frame0.shape[1]
    state.scale = min(1.0, (DISPLAY_MAX_WIDTH / 2) / src_w)
    state.pane_w_disp = int(src_w * state.scale)
    print(f"Source: {src_w}x{frame0.shape[0]}; display scale {state.scale:.2f}; {n_total} frames")
    print("Controls: LEFT/RIGHT step; SHIFT+arrows skip 10; HOME=0; click to place "
          "(first click locks anchor); u=undo r=reset s=save q=quit")

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, _on_mouse, state)

    # Mutable cell so helpers can update frame0/frame1 from the enclosing scope
    cell = [frame0, frame1]

    def _set_frames(f0, f1):
        if f0 is not None: cell[0] = f0
        if f1 is not None: cell[1] = f1

    def _try_navigate(delta: int) -> None:
        if state.locked:
            print(f"  cannot navigate: anchor locked to frame {state.anchor_frame_idx}. "
                  "Press 'r' to reset and unlock.")
            return
        new_idx = max(0, min(state.current_frame_idx + delta, n_total - 1))
        if new_idx != state.current_frame_idx:
            state.current_frame_idx = new_idx
            f0, f1 = _seek(cap0, cap1, state.current_frame_idx)
            _set_frames(f0, f1)

    while True:
        frame0, frame1 = cell[0], cell[1]
        cv2.imshow(WINDOW, _render(frame0, frame1, state, n_total))
        key = cv2.waitKeyEx(20)
        if key < 0:
            continue
        # waitKeyEx returns full key; lower 8 bits == ASCII
        k = key & 0xFF

        if k == ord("q"):
            if state.dirty:
                print("Unsaved changes. Press q again to discard, s to save.")
                k2 = cv2.waitKeyEx(0) & 0xFF
                if k2 == ord("s"):
                    # Fall through to save below by setting k = 's'
                    k = ord("s")
                elif k2 == ord("q"):
                    break
                else:
                    continue
            else:
                break

        if k == ord("s"):
            if len(state.cam0_points) != len(state.cam1_points):
                print(f"Cannot save: cam0 has {len(state.cam0_points)} points, "
                      f"cam1 has {len(state.cam1_points)}. Place equal counts first.")
                continue
            if not state.cam0_points:
                print("No points placed yet. Click some intersections first.")
                continue
            anchor = state.anchor_frame_idx
            assert anchor is not None  # implied by len(points) > 0
            payload = {
                "cam0_video": args.cam0_video.name,
                "cam1_video": args.cam1_video.name,
                "frame_idx": anchor,
                "points": [
                    {"point_id": i,
                     "u0": float(u0), "v0": float(v0),
                     "u1": float(u1), "v1": float(v1),
                     "label": ""}
                    for i, ((u0, v0), (u1, v1)) in enumerate(
                        zip(state.cam0_points, state.cam1_points))
                ],
            }
            out_path.write_text(json.dumps(payload, indent=2))
            print(f"Saved {len(payload['points'])} seed points to {out_path} "
                  f"(anchor=frame {anchor})")
            state.dirty = False
        elif k == ord("u"):
            if state.last_pane == "cam0" and state.cam0_points:
                state.cam0_points.pop()
            elif state.last_pane == "cam1" and state.cam1_points:
                state.cam1_points.pop()
            elif state.cam0_points or state.cam1_points:
                if len(state.cam0_points) >= len(state.cam1_points):
                    state.cam0_points and state.cam0_points.pop()
                else:
                    state.cam1_points and state.cam1_points.pop()
            # If all points are gone, unlock navigation
            if not state.cam0_points and not state.cam1_points:
                state.anchor_frame_idx = None
            state.dirty = True
        elif k == ord("r"):
            state.cam0_points.clear()
            state.cam1_points.clear()
            state.anchor_frame_idx = None
            state.dirty = True
            print("  reset: navigation unlocked")
        elif k in (ord("d"),):  # right
            _try_navigate(+1)
        elif k in (ord("a"),):  # left
            _try_navigate(-1)
        else:
            # waitKeyEx returns platform-specific codes for arrows; check the high bits too
            if key in (63235, 2555904):     # right arrow (macOS Cocoa / Windows)
                _try_navigate(+1)
            elif key in (63234, 2424832):   # left arrow
                _try_navigate(-1)
            elif key in (63232, 2490368):   # up
                _try_navigate(+10)
            elif key in (63233, 2621440):   # down
                _try_navigate(-10)
            elif key in (63273, 2359296):   # home
                if not state.locked:
                    state.current_frame_idx = 0
                    f0, f1 = _seek(cap0, cap1, 0)
                    _set_frames(f0, f1)
                else:
                    print(f"  cannot navigate: anchor locked to frame {state.anchor_frame_idx}.")
            elif key in (63275, 2293760):   # end
                if not state.locked:
                    state.current_frame_idx = n_total - 1
                    f0, f1 = _seek(cap0, cap1, state.current_frame_idx)
                    _set_frames(f0, f1)
                else:
                    print(f"  cannot navigate: anchor locked to frame {state.anchor_frame_idx}.")

    cap0.release(); cap1.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
