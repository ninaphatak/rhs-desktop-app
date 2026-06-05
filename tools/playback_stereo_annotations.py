"""Animated dual-pane playback of a stereo-labeled landmark trajectory.

Sibling of tools/playback_annotations.py, but for the stereo annotation
format produced by tools/annotate_stereo_point.py:
    frame_idx, u0, v0, u1, v1, phase

Each pane (cam0 left, cam1 right) gets the same overlay set as the
single-camera tool: green crosshair at the first labeled point (origin),
red dot at the current labeled point, yellow displacement arrow, faded
gray trail.

With --calibration, every labeled frame is triangulated to a 3D point
and the HUD shows the metric (mm) displacement from the first labeled
frame. With --cam0-timestamps + --cam1-timestamps, free-run camera sync
is corrected via temporal interpolation (matches tools/triangulate.py
exactly).

Usage:
    # Visual-only playback (no metric, dual-pane):
    python tools/playback_stereo_annotations.py CAM0_VIDEO CAM1_VIDEO

    # With metric (mm) displacement overlay + plot + saved MP4:
    python tools/playback_stereo_annotations.py CAM0_VIDEO CAM1_VIDEO \\
        --calibration outputs/calib/stereo_calib_water.json \\
        --cam0-timestamps CAM0_VIDEO.timestamps.csv \\
        --cam1-timestamps CAM1_VIDEO.timestamps.csv \\
        --plot \\
        --save out.mp4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.annotate_stereo_point import StereoAnnotation, read_stereo_csv
from tools.triangulate import (
    load_calibration,
    load_timestamps,
    interpolate_pixel_at_time,
    triangulate_point,
)


WINDOW = "Stereo Annotation Playback (cam0 | cam1)"

ORIGIN_COLOR = (0, 255, 0)       # green
CURRENT_COLOR = (0, 0, 255)      # red
ARROW_COLOR = (0, 255, 255)      # yellow
TRAIL_COLOR = (180, 180, 180)    # faded gray

DISPLAY_MAX_WIDTH = 1900         # combined width budget for the two panes


class OverlayState:
    """Cumulative overlay state for one camera."""

    def __init__(self) -> None:
        self.origin: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self.last_phase: str = ""
        self.trail: list[tuple[int, int]] = []
        self._trail_idx: dict[int, int] = {}

    def update(self, frame_idx: int, u: float, v: float, phase: str) -> None:
        pt = (int(round(u)), int(round(v)))
        if self.origin is None:
            self.origin = pt
        self.current = pt
        self.last_phase = phase
        if frame_idx in self._trail_idx:
            self.trail[self._trail_idx[frame_idx]] = pt
        else:
            self._trail_idx[frame_idx] = len(self.trail)
            self.trail.append(pt)


def _vector_length_px(state: OverlayState) -> float | None:
    if state.origin is None or state.current is None:
        return None
    ox, oy = state.origin
    cx, cy = state.current
    return float(np.hypot(cx - ox, cy - oy))


def _draw_overlay_on_frame(frame: np.ndarray, state: OverlayState) -> np.ndarray:
    """Apply origin crosshair, trail, arrow, current dot — at SOURCE resolution."""
    out = frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if state.origin is None:
        return out
    if len(state.trail) >= 2:
        pts = np.array(state.trail, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], isClosed=False, color=TRAIL_COLOR, thickness=1)
    if state.current is not None and state.current != state.origin:
        cv2.arrowedLine(out, state.origin, state.current, ARROW_COLOR,
                        thickness=2, tipLength=0.05)
    ox, oy = state.origin
    cv2.line(out, (ox - 6, oy), (ox + 6, oy), ORIGIN_COLOR, 1)
    cv2.line(out, (ox, oy - 6), (ox, oy + 6), ORIGIN_COLOR, 1)
    if state.current is not None:
        cv2.circle(out, state.current, 4, CURRENT_COLOR, -1)
    return out


def _scale_pane(frame: np.ndarray, scale: float, label: str) -> np.ndarray:
    """Resize a fully-overlaid frame for display + stamp the cam label."""
    h, w = frame.shape[:2]
    scaled = cv2.resize(frame, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA)
    cv2.putText(scaled, label, (12, 32), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (0, 255, 0), 2)
    return scaled


def _compose(cam0_frame, cam1_frame, state0: OverlayState, state1: OverlayState,
             frame_idx: int, total_frames: int, paused: bool, scale: float,
             metric_mm: float | None = None) -> np.ndarray:
    """Build the combined display image (overlays in source res, then scale)."""
    overlaid0 = _draw_overlay_on_frame(cam0_frame, state0)
    overlaid1 = _draw_overlay_on_frame(cam1_frame, state1)
    left = _scale_pane(overlaid0, scale, "cam0")
    right = _scale_pane(overlaid1, scale, "cam1")
    combined = np.hstack([left, right])

    parts = [f"frame {frame_idx}/{total_frames - 1}"]
    if metric_mm is not None:
        parts.append(f"displacement={metric_mm:.2f} mm")
    phase = state0.last_phase or state1.last_phase
    if phase:
        parts.append(f"phase={phase}")
    if paused:
        parts.append("PAUSED")
    cv2.putText(combined, "  ".join(parts),
                (12, combined.shape[0] - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return combined


def _precompute_3d_displacements(
    by_frame: dict[int, StereoAnnotation],
    calib: dict | None,
    cam0_times: dict[int, float] | None,
    cam1_times: dict[int, float] | None,
) -> dict[int, float]:
    """If calibration is provided, return frame_idx -> mm displacement from first frame.

    Mirrors tools/triangulate.py's logic: if both cam0 and cam1 timestamps
    are also provided, cam1 pixel positions are linearly interpolated to the
    cam0 frame time before triangulation (free-run sync correction).
    Returns {} if calibration is not provided.
    """
    if calib is None or not by_frame:
        return {}
    do_interp = cam0_times is not None and cam1_times is not None
    cam1_anns: dict[int, tuple[float, float]] = {}
    if do_interp:
        cam1_anns = {f: (a.u1, a.v1) for f, a in by_frame.items() if a.complete}

    sorted_frames = sorted(f for f, a in by_frame.items() if a.complete)
    points_3d: dict[int, np.ndarray] = {}
    for fidx in sorted_frames:
        ann = by_frame[fidx]
        uv0 = (ann.u0, ann.v0)
        if do_interp and fidx in cam0_times:
            target_t = cam0_times[fidx]
            uv1 = interpolate_pixel_at_time(cam1_anns, cam1_times, target_t)
        else:
            uv1 = (ann.u1, ann.v1)
        xyz = triangulate_point(
            calib["cam0"]["K"], calib["cam0"]["dist"],
            calib["cam0"]["rvec"], calib["cam0"]["tvec"],
            calib["cam1"]["K"], calib["cam1"]["dist"],
            calib["cam1"]["rvec"], calib["cam1"]["tvec"],
            uv0, uv1,
        )
        points_3d[fidx] = xyz

    if not points_3d:
        return {}
    origin_xyz = points_3d[sorted_frames[0]]
    return {f: float(np.linalg.norm(xyz - origin_xyz))
            for f, xyz in points_3d.items()}


def _seek(cap: cv2.VideoCapture, frame_idx: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def _build_state_up_to(by_frame: dict[int, StereoAnnotation], target_idx: int,
                       which: int) -> OverlayState:
    """Replay annotations for one camera (which=0 or 1) up to and including target_idx."""
    state = OverlayState()
    for fidx in sorted(by_frame.keys()):
        if fidx > target_idx:
            break
        ann = by_frame[fidx]
        if not ann.complete:
            continue
        u, v = (ann.u0, ann.v0) if which == 0 else (ann.u1, ann.v1)
        state.update(fidx, u, v, ann.phase)
    return state


def _save_metric_displacement_plot(metric_mm: dict[int, float], fps: float,
                                    cam0_video: Path, out_dir: Path) -> Path:
    """Single-line plot of metric (mm) displacement from origin vs time (s)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sorted_frames = sorted(metric_mm.keys())
    if len(sorted_frames) < 2:
        raise ValueError(f"Need 2+ triangulated frames to plot; got {len(sorted_frames)}")

    times = [f / fps for f in sorted_frames]
    mm = [metric_mm[f] for f in sorted_frames]

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{cam0_video.stem}_metric_displacement.png"

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, mm, "-", color="#888888", linewidth=0.8, alpha=0.7)
    ax.plot(times, mm, "o", color="#cc4444", markersize=3.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("3D displacement from origin (mm)")
    ax.set_title(f"Metric landmark displacement vs time — {cam0_video.name}")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=times[0])
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def _render_to_file(cap0: cv2.VideoCapture, cap1: cv2.VideoCapture,
                    by_frame: dict[int, StereoAnnotation],
                    total_frames: int, fps: float, scale: float,
                    out_path: Path,
                    metric_mm: dict[int, float] | None = None) -> None:
    """Walk frames 0..N-1 and write the dual-pane overlaid video."""
    src_w = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
    pane_w = int(src_w * scale)
    pane_h = int(src_h * scale)
    out_w = pane_w * 2
    out_h = pane_h
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (out_w, out_h), isColor=True)
    if not writer.isOpened():
        print(f"Cannot open VideoWriter for {out_path}")
        sys.exit(1)

    state0, state1 = OverlayState(), OverlayState()
    last_mm: float | None = None
    cap0.set(cv2.CAP_PROP_POS_FRAMES, 0)
    cap1.set(cv2.CAP_PROP_POS_FRAMES, 0)
    written = 0
    for frame_idx in range(total_frames):
        ret0, f0 = cap0.read()
        ret1, f1 = cap1.read()
        if not (ret0 and ret1):
            break
        if frame_idx in by_frame and by_frame[frame_idx].complete:
            ann = by_frame[frame_idx]
            state0.update(frame_idx, ann.u0, ann.v0, ann.phase)
            state1.update(frame_idx, ann.u1, ann.v1, ann.phase)
        if metric_mm is not None and frame_idx in metric_mm:
            last_mm = metric_mm[frame_idx]
        composed = _compose(f0, f1, state0, state1, frame_idx, total_frames,
                            paused=False, scale=scale, metric_mm=last_mm)
        writer.write(composed)
        written += 1
        if written % 60 == 0:
            print(f"  rendered {written}/{total_frames}")
    writer.release()
    print(f"Wrote {out_path}  ({written} frames @ {fps:g} fps, {out_w}x{out_h})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cam0_video", type=Path)
    ap.add_argument("cam1_video", type=Path)
    ap.add_argument("--annotations", type=Path, default=None,
                    help="Stereo CSV (default: <cam0_video>.stereo_annotations.csv)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--save", type=Path, default=None,
                    help="Render the dual-pane overlaid playback to this MP4 path.")
    ap.add_argument("--plot", action="store_true",
                    help="Save a 2D plot of metric (mm) displacement vs time to outputs/. "
                         "Requires --calibration.")
    ap.add_argument("--calibration", type=Path, default=None,
                    help="Stereo calibration JSON from tools/stereo_calibrate.py. "
                         "Required to compute and display mm displacement.")
    ap.add_argument("--cam0-timestamps", type=Path, default=None,
                    help="cam0 timestamp sidecar. With --cam1-timestamps, applies "
                         "the temporal-interpolation sync correction during triangulation.")
    ap.add_argument("--cam1-timestamps", type=Path, default=None,
                    help="cam1 timestamp sidecar (paired with --cam0-timestamps).")
    args = ap.parse_args()

    if not args.cam0_video.exists() or not args.cam1_video.exists():
        print("Video file not found"); sys.exit(1)
    csv_path = args.annotations or args.cam0_video.with_suffix(
        args.cam0_video.suffix + ".stereo_annotations.csv")

    cap0 = cv2.VideoCapture(str(args.cam0_video))
    cap1 = cv2.VideoCapture(str(args.cam1_video))
    if not (cap0.isOpened() and cap1.isOpened()):
        print("Cannot open videos"); sys.exit(1)
    n0 = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT))
    n1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
    total_frames = min(n0, n1)
    fps = cap0.get(cv2.CAP_PROP_FPS) or 30.0
    base_delay_ms = max(1, int(1000.0 / (fps * max(args.speed, 0.05))))
    src_w = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    scale = min(1.0, (DISPLAY_MAX_WIDTH / 2) / src_w)

    annotations = read_stereo_csv(csv_path)
    by_frame: dict[int, StereoAnnotation] = {a.frame_idx: a for a in annotations
                                              if a.complete}
    print(f"Loaded {len(by_frame)} complete stereo annotations from {csv_path}")

    # Optional metric pipeline: triangulate every labeled frame to mm
    calib = load_calibration(args.calibration) if args.calibration else None
    cam0_times = load_timestamps(args.cam0_timestamps) if args.cam0_timestamps else None
    cam1_times = load_timestamps(args.cam1_timestamps) if args.cam1_timestamps else None
    metric_mm = _precompute_3d_displacements(by_frame, calib, cam0_times, cam1_times)
    if calib is None:
        print("(no --calibration; HUD will show frame index + phase only — no mm displacement)")
    else:
        do_interp = cam0_times is not None and cam1_times is not None
        print(f"Triangulated {len(metric_mm)} frames to mm "
              f"({'with' if do_interp else 'without'} sync interpolation)")

    if args.plot:
        if not metric_mm:
            print("--plot requires --calibration so we can compute metric displacement"); sys.exit(1)
        outputs_dir = Path(__file__).resolve().parent.parent / "outputs"
        plot_path = _save_metric_displacement_plot(metric_mm, fps, args.cam0_video, outputs_dir)
        print(f"Saved metric displacement plot to {plot_path}")

    if args.save is not None:
        _render_to_file(cap0, cap1, by_frame, total_frames, fps, scale,
                        args.save, metric_mm=metric_mm or None)
        cap0.release(); cap1.release()
        return

    print("Controls: SPACE=play/pause  RIGHT=step  LEFT=back  r=restart  q=quit")

    if by_frame:
        loop_start = min(by_frame.keys())
        loop_end = max(by_frame.keys())
    else:
        loop_start, loop_end = 0, total_frames - 1

    frame_idx = loop_start
    paused = False
    state0 = _build_state_up_to(by_frame, frame_idx, which=0)
    state1 = _build_state_up_to(by_frame, frame_idx, which=1)
    f0 = _seek(cap0, frame_idx); f1 = _seek(cap1, frame_idx)
    if f0 is None or f1 is None:
        print("Cannot read first frame"); sys.exit(1)

    last_mm: float | None = None

    def _last_mm_up_to(target_idx: int) -> float | None:
        """Most recent mm-displacement at or before target_idx (carries forward)."""
        if not metric_mm:
            return None
        candidates = [f for f in metric_mm if f <= target_idx]
        return metric_mm[max(candidates)] if candidates else None

    last_mm = _last_mm_up_to(frame_idx)

    while True:
        if frame_idx in by_frame and by_frame[frame_idx].complete:
            ann = by_frame[frame_idx]
            state0.update(frame_idx, ann.u0, ann.v0, ann.phase)
            state1.update(frame_idx, ann.u1, ann.v1, ann.phase)
        if metric_mm and frame_idx in metric_mm:
            last_mm = metric_mm[frame_idx]
        composed = _compose(f0, f1, state0, state1, frame_idx, total_frames,
                            paused=paused, scale=scale, metric_mm=last_mm)
        cv2.imshow(WINDOW, composed)

        delay = 0 if paused else base_delay_ms
        key = cv2.waitKey(delay) & 0xFF

        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
        elif key == ord("r"):
            frame_idx = loop_start
            state0 = _build_state_up_to(by_frame, frame_idx, which=0)
            state1 = _build_state_up_to(by_frame, frame_idx, which=1)
            last_mm = _last_mm_up_to(frame_idx)
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1
            paused = True
        elif paused and key in (83, ord("d")) and frame_idx + 1 < total_frames:
            frame_idx += 1
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1
        elif paused and key in (81, ord("a")) and frame_idx > 0:
            frame_idx -= 1
            state0 = _build_state_up_to(by_frame, frame_idx, which=0)
            state1 = _build_state_up_to(by_frame, frame_idx, which=1)
            last_mm = _last_mm_up_to(frame_idx)
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1
        elif not paused:
            if frame_idx >= loop_end:
                frame_idx = loop_start
                state0 = _build_state_up_to(by_frame, frame_idx, which=0)
                state1 = _build_state_up_to(by_frame, frame_idx, which=1)
                last_mm = _last_mm_up_to(frame_idx)
            else:
                frame_idx += 1
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1

    cap0.release(); cap1.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
