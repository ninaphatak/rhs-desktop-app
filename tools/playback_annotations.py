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

    # Render the overlaid playback to an MP4 (non-interactive, no window):
    python tools/playback_annotations.py path/to/recording.mp4 \
        --save path/to/recording.playback.mp4

    # Save a 2D plot of vector length (px) vs time (s) to outputs/:
    python tools/playback_annotations.py path/to/recording.mp4 --plot
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


def _vector_length_px(state: OverlayState) -> float | None:
    """Euclidean distance from origin to the most recent labeled point."""
    if state.origin is None or state.current is None:
        return None
    ox, oy = state.origin
    cx, cy = state.current
    return float(np.hypot(cx - ox, cy - oy))


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
    length = _vector_length_px(state)
    if length is not None:
        cv2.putText(
            frame, f"length={length:.1f} px",
            (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
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


def _save_length_vs_time_plot(
    by_frame: dict[int, Annotation],
    fps: float,
    video_path: Path,
    out_dir: Path,
) -> Path:
    """Write a discrete time-vs-length plot for the labeled trajectory.

    Time is `frame_idx / fps`, so samples land at the actual time the
    annotated frames were captured. Length is the Euclidean distance from
    the first labeled point (origin) to each subsequent labeled point.
    """
    import matplotlib
    matplotlib.use("Agg")  # headless, no Qt
    import matplotlib.pyplot as plt

    if len(by_frame) < 2:
        raise ValueError(
            f"Need at least 2 annotations to plot length vs time; got {len(by_frame)}"
        )

    sorted_frames = sorted(by_frame.keys())
    origin = (by_frame[sorted_frames[0]].point_x, by_frame[sorted_frames[0]].point_y)
    times = [f / fps for f in sorted_frames]
    lengths = [
        float(np.hypot(by_frame[f].point_x - origin[0], by_frame[f].point_y - origin[1]))
        for f in sorted_frames
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video_path.stem}_displacement.png"

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, lengths, "-", color="#888888", linewidth=0.8, alpha=0.7)
    ax.plot(times, lengths, "o", color="#cc4444", markersize=3.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Vector length from origin (px)")
    ax.set_title(f"Landmark displacement vs time — {video_path.name}")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=times[0])
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def _render_to_file(
    cap: cv2.VideoCapture,
    by_frame: dict[int, Annotation],
    total_frames: int,
    fps: float,
    out_path: Path,
) -> None:
    """Walk frames 0..total_frames-1 in order and write the overlaid video."""
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height), isColor=True)
    if not writer.isOpened():
        print(f"Cannot open VideoWriter for {out_path}")
        sys.exit(1)

    state = OverlayState()
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    written = 0
    for frame_idx in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx in by_frame:
            state.update(by_frame[frame_idx])
        overlaid = draw_overlay(frame, state)
        _draw_hud(overlaid, frame_idx, total_frames, state, paused=False)
        writer.write(overlaid)
        written += 1
        if written % 60 == 0:
            print(f"  rendered {written}/{total_frames}")
    writer.release()
    print(f"Wrote {out_path}  ({written} frames @ {fps:g} fps)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--annotations", type=Path, default=None)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument(
        "--save", type=Path, default=None,
        help="Render the overlaid playback to this MP4 path (no interactive window).",
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Save a 2D plot of vector length (px) vs time (s) to outputs/.",
    )
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

    if args.plot:
        outputs_dir = Path(__file__).resolve().parent.parent / "outputs"
        plot_path = _save_length_vs_time_plot(by_frame, fps, args.video, outputs_dir)
        print(f"Saved displacement plot to {plot_path}")

    if args.save is not None:
        _render_to_file(cap, by_frame, total_frames, fps, args.save)
        cap.release()
        return

    print("Controls: SPACE=play/pause  RIGHT=step  LEFT=back  r=restart  q=quit")

    # Auto-loop bounds: replay between the first and last annotated frame so the
    # moving vector is always on screen. Without annotations, fall back to the
    # full video range.
    if by_frame:
        loop_start = min(by_frame.keys())
        loop_end = max(by_frame.keys())
    else:
        loop_start = 0
        loop_end = total_frames - 1

    state = OverlayState()
    frame_idx = loop_start
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
            frame_idx = loop_start
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
            if frame_idx >= loop_end:
                # Wrap back to the first annotated frame and keep looping.
                frame_idx = loop_start
                state = rebuild_state_up_to(frame_idx)
            else:
                frame_idx += 1
            new_frame = _seek(cap, frame_idx)
            if new_frame is not None:
                frame = new_frame

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
