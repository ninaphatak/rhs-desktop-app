"""Dual-camera playback with multi-point track overlay.

Reads a `.tracks.csv` produced by `tools/track_intersections.py` and
animates the cam0 + cam1 videos side-by-side with every tracked point
drawn on top. Each point gets a distinct color from the shared palette
in tools/_tracks.py — matching pick_track_seeds.py and analyze_tracks.py
so the same point is the same color in every view. Healthy frames are
drawn as a filled dot; lost frames as a hollow ring in the same color
(so identity is always visible).

Usage:
    python tools/playback_tracks.py CAM0_VIDEO CAM1_VIDEO \\
        [--tracks <cam0_video>.track_seeds.tracks.csv] \\
        [--trail 30] [--vector] [--save out.mp4]

Controls:
    SPACE   play/pause
    RIGHT / d   step forward (paused)
    LEFT  / a   step back (paused)
    r       restart
    q       quit
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._tracks import TrackSample, color_bgr_for_point, read_tracks


WINDOW = "Track Playback (cam0 | cam1)"
DISPLAY_MAX_WIDTH = 1900

YELLOW = (0, 255, 255)
BLACK = (0, 0, 0)
TRAIL_BASE = (200, 200, 200)

# Marker / label sizing — drawn on the full-res source frame BEFORE the
# display scales it down to ~50%, so values here are intentionally chunky.
DOT_RADIUS = 11
DOT_OUTLINE_RADIUS = 13
LOST_RING_THICKNESS = 3
TRAIL_THICKNESS = 3
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
ID_SCALE = 0.7
ID_THICKNESS = 2
VEC_SCALE = 0.55
VEC_THICKNESS = 2  # bumped for a bolder stroke
VEC_COLOR = (0, 0, 255)  # BGR red
LABEL_GAP_PX = 8  # vertical gap between the dot and the first label line
LABEL_LINE_GAP_PX = 10  # vertical gap between the id line and the vector line


def _draw_text_outline(img: np.ndarray, text: str, org: tuple[int, int],
                       scale: float, color: tuple[int, int, int],
                       thickness: int) -> None:
    """Draw text with a black outline so it stays readable on any background."""
    cv2.putText(img, text, org, LABEL_FONT, scale, BLACK,
                thickness + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, LABEL_FONT, scale, color,
                thickness, cv2.LINE_AA)


def _draw_point_label(out: np.ndarray, center: tuple[int, int],
                      color: tuple[int, int, int], r: TrackSample) -> None:
    """Draw the 'ptN' line + live (dx, dy, dz) vector text directly under the dot.

    Each line is horizontally centered on the dot's x. If the stack would
    overflow the bottom edge, it flips to above the dot.
    """
    h_frame, w_frame = out.shape[:2]
    id_text = f"pt{r.point_id}"
    vec_text = f"({r.dx_mm:+.2f}, {r.dy_mm:+.2f}, {r.dz_mm:+.2f}) mm"

    (id_w, id_h), _ = cv2.getTextSize(id_text, LABEL_FONT, ID_SCALE, ID_THICKNESS)
    (vec_w, vec_h), _ = cv2.getTextSize(vec_text, LABEL_FONT, VEC_SCALE, VEC_THICKNESS)

    cx, cy = center
    total_h = id_h + LABEL_LINE_GAP_PX + vec_h

    # Default: below the dot
    id_y = cy + DOT_OUTLINE_RADIUS + LABEL_GAP_PX + id_h
    vec_y = id_y + LABEL_LINE_GAP_PX + vec_h
    if vec_y > h_frame - 5:
        # Flip above the dot
        vec_y = cy - DOT_OUTLINE_RADIUS - LABEL_GAP_PX
        id_y = vec_y - LABEL_LINE_GAP_PX - vec_h

    id_x = max(5, min(cx - id_w // 2, w_frame - id_w - 5))
    vec_x = max(5, min(cx - vec_w // 2, w_frame - vec_w - 5))

    _draw_text_outline(out, id_text, (id_x, id_y), ID_SCALE, color, ID_THICKNESS)
    cv2.putText(out, vec_text, (vec_x, vec_y), LABEL_FONT, VEC_SCALE,
                VEC_COLOR, VEC_THICKNESS, cv2.LINE_AA)


def _to_bgr(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return frame.copy()


def _draw_overlay(
    frame_bgr: np.ndarray,
    rows_this_frame: list[TrackSample],
    history_per_point: dict[int, list[tuple[int, int]]],
    which: int,
    trail: int,
    draw_vector: bool,
    origins: dict[int, tuple[int, int]],
) -> np.ndarray:
    out = frame_bgr
    for r in rows_this_frame:
        u, v = (r.u0, r.v0) if which == 0 else (r.u1, r.v1)
        center = (int(round(u)), int(round(v)))
        color = color_bgr_for_point(r.point_id)
        if trail > 0:
            hist = history_per_point.get(r.point_id, [])
            tail = hist[-trail:]
            if len(tail) >= 2:
                pts = np.array(tail, dtype=np.int32).reshape(-1, 1, 2)
                cv2.polylines(out, [pts], isClosed=False, color=TRAIL_BASE,
                              thickness=TRAIL_THICKNESS, lineType=cv2.LINE_AA)
        if draw_vector and r.point_id in origins:
            ox, oy = origins[r.point_id]
            if (ox, oy) != center:
                cv2.arrowedLine(out, (ox, oy), center, YELLOW,
                                thickness=2, tipLength=0.05, line_type=cv2.LINE_AA)
        # Black outline ring for contrast against the underwater scene
        cv2.circle(out, center, DOT_OUTLINE_RADIUS, BLACK, 1, cv2.LINE_AA)
        # Healthy = filled dot; lost = hollow ring. Same per-point color either way.
        thickness = -1 if r.healthy else LOST_RING_THICKNESS
        cv2.circle(out, center, DOT_RADIUS, color, thickness, cv2.LINE_AA)
        _draw_point_label(out, center, color, r)
    return out


def _scale_pane(frame: np.ndarray, scale: float, label: str) -> np.ndarray:
    h, w = frame.shape[:2]
    scaled = cv2.resize(frame, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA)
    cv2.putText(scaled, label, (12, 32), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (0, 255, 0), 2)
    return scaled


def _compose(
    cam0_frame, cam1_frame,
    rows_this_frame: list[TrackSample],
    history0: dict[int, list[tuple[int, int]]],
    history1: dict[int, list[tuple[int, int]]],
    origins0: dict[int, tuple[int, int]],
    origins1: dict[int, tuple[int, int]],
    frame_idx: int, total_frames: int, paused: bool, scale: float,
    trail: int, draw_vector: bool, cam: str = "both",
) -> np.ndarray:
    panes = []
    if cam in ("both", "0") and cam0_frame is not None:
        overlay0 = _draw_overlay(_to_bgr(cam0_frame), rows_this_frame, history0,
                                  which=0, trail=trail, draw_vector=draw_vector,
                                  origins=origins0)
        panes.append(_scale_pane(overlay0, scale, "cam0"))
    if cam in ("both", "1") and cam1_frame is not None:
        overlay1 = _draw_overlay(_to_bgr(cam1_frame), rows_this_frame, history1,
                                  which=1, trail=trail, draw_vector=draw_vector,
                                  origins=origins1)
        panes.append(_scale_pane(overlay1, scale, "cam1"))
    combined = np.hstack(panes) if len(panes) > 1 else panes[0]
    n_healthy = sum(1 for r in rows_this_frame if r.healthy)
    n_total = len(rows_this_frame)
    if rows_this_frame and n_healthy > 0:
        mean_disp = float(np.mean([r.displacement_mm for r in rows_this_frame if r.healthy]))
    else:
        mean_disp = 0.0
    parts = [f"frame {frame_idx}/{total_frames - 1}",
             f"healthy={n_healthy}/{n_total}",
             f"mean disp={mean_disp:.2f} mm"]
    if paused:
        parts.append("PAUSED")
    hud_text = "  ".join(parts)
    # Black outline + yellow on top, larger than before
    org = (12, combined.shape[0] - 18)
    cv2.putText(combined, hud_text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.85,
                (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(combined, hud_text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.85,
                (0, 255, 255), 2, cv2.LINE_AA)
    return combined


def _seek(cap: cv2.VideoCapture, frame_idx: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def _index_tracks(samples: list[TrackSample]) -> tuple[
    dict[int, list[TrackSample]],
    dict[int, tuple[int, int]],
    dict[int, tuple[int, int]],
]:
    """Group samples by frame_idx and compute per-point origins."""
    by_frame: dict[int, list[TrackSample]] = defaultdict(list)
    for s in samples:
        by_frame[s.frame_idx].append(s)
    origins0: dict[int, tuple[int, int]] = {}
    origins1: dict[int, tuple[int, int]] = {}
    seen = set()
    for s in sorted(samples, key=lambda r: (r.point_id, r.frame_idx)):
        if s.point_id in seen:
            continue
        origins0[s.point_id] = (int(round(s.u0)), int(round(s.v0)))
        origins1[s.point_id] = (int(round(s.u1)), int(round(s.v1)))
        seen.add(s.point_id)
    return by_frame, origins0, origins1


def _build_history_up_to(
    by_frame: dict[int, list[TrackSample]],
    target_frame: int,
    which: int,
) -> dict[int, list[tuple[int, int]]]:
    """Replay history of healthy positions for each point up to (and including) target_frame."""
    history: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for fidx in sorted(by_frame.keys()):
        if fidx > target_frame:
            break
        for s in by_frame[fidx]:
            if s.healthy:
                u, v = (s.u0, s.v0) if which == 0 else (s.u1, s.v1)
                history[s.point_id].append((int(round(u)), int(round(v))))
    return history


def _render_to_file(
    cap0, cap1, start_frame, end_frame_exclusive, fps, scale,
    by_frame, origins0, origins1, trail, draw_vector, out_path,
    cam: str = "both",
) -> None:
    src_cap = cap0 if cam in ("both", "0") else cap1
    src_w = int(src_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(src_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    pane_w = int(src_w * scale)
    pane_h = int(src_h * scale)
    n_panes = 2 if cam == "both" else 1
    out_w = pane_w * n_panes
    out_h = pane_h
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (out_w, out_h), isColor=True)
    if not writer.isOpened():
        print(f"Cannot open VideoWriter for {out_path}"); sys.exit(1)

    history0: dict[int, list[tuple[int, int]]] = defaultdict(list)
    history1: dict[int, list[tuple[int, int]]] = defaultdict(list)
    if cam in ("both", "0"):
        cap0.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    if cam in ("both", "1"):
        cap1.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    n_to_write = end_frame_exclusive - start_frame
    written = 0
    for frame_idx in range(start_frame, end_frame_exclusive):
        f0 = f1 = None
        if cam in ("both", "0"):
            ret0, f0 = cap0.read()
            if not ret0:
                break
        if cam in ("both", "1"):
            ret1, f1 = cap1.read()
            if not ret1:
                break
        rows = by_frame.get(frame_idx, [])
        for s in rows:
            if s.healthy:
                history0[s.point_id].append((int(round(s.u0)), int(round(s.v0))))
                history1[s.point_id].append((int(round(s.u1)), int(round(s.v1))))
        composed = _compose(f0, f1, rows, history0, history1,
                            origins0, origins1, frame_idx, end_frame_exclusive,
                            paused=False, scale=scale, trail=trail,
                            draw_vector=draw_vector, cam=cam)
        writer.write(composed)
        written += 1
        if written % 60 == 0:
            print(f"  rendered {written}/{n_to_write}")
    writer.release()
    print(f"Wrote {out_path}  ({written} frames, range [{start_frame}..{start_frame + written - 1}])")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cam0_video", type=Path)
    ap.add_argument("cam1_video", type=Path)
    ap.add_argument("--tracks", type=Path, default=None,
                    help="Tracks CSV (default: <cam0_video>.track_seeds.tracks.csv)")
    ap.add_argument("--trail", type=int, default=30,
                    help="Number of recent positions to draw as a polyline trail (0 disables)")
    ap.add_argument("--vector", action="store_true",
                    help="Draw a yellow arrow from each point's frame-0 origin to its current position")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--cam", choices=["both", "0", "1"], default="both",
                    help="Which camera pane to render: 'both' (default), '0' = cam0 only, "
                         "'1' = cam1 only.")
    ap.add_argument("--save", type=Path, default=None,
                    help="Render the overlaid playback to this MP4 path.")
    args = ap.parse_args()

    if not args.cam0_video.exists() or not args.cam1_video.exists():
        print("Video file not found"); sys.exit(1)
    tracks_path = args.tracks or args.cam0_video.with_suffix(
        args.cam0_video.suffix + ".track_seeds.tracks.csv")
    if not tracks_path.exists():
        print(f"Tracks CSV not found: {tracks_path}"); sys.exit(1)

    samples = read_tracks(tracks_path)
    if not samples:
        print(f"No samples in {tracks_path}"); sys.exit(1)
    by_frame, origins0, origins1 = _index_tracks(samples)
    print(f"Loaded {len(samples)} samples ({len(by_frame)} frames, "
          f"{len(origins0)} points) from {tracks_path}")

    cap0 = cv2.VideoCapture(str(args.cam0_video))
    cap1 = cv2.VideoCapture(str(args.cam1_video))
    if not (cap0.isOpened() and cap1.isOpened()):
        print("Cannot open videos"); sys.exit(1)
    n0 = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT))
    n1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
    total_frames = min(n0, n1)
    fps = cap0.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
    scale = min(1.0, (DISPLAY_MAX_WIDTH / 2) / src_w)
    base_delay_ms = max(1, int(1000.0 / (fps * max(args.speed, 0.05))))

    # Loop between the first and last tracked frame so the user never sees
    # a black/overlay-free prelude when the seeds were anchored mid-video.
    loop_start = min(by_frame.keys()) if by_frame else 0
    loop_end = max(by_frame.keys()) if by_frame else total_frames - 1
    print(f"Tracked frame range: [{loop_start}..{loop_end}]")

    if args.save is not None:
        _render_to_file(cap0, cap1, loop_start, loop_end + 1, fps, scale,
                        by_frame, origins0, origins1, args.trail, args.vector,
                        args.save, cam=args.cam)
        cap0.release(); cap1.release()
        return

    print("Controls: SPACE=play/pause RIGHT=step LEFT=back r=restart q=quit")
    frame_idx = loop_start
    paused = False
    history0 = _build_history_up_to(by_frame, frame_idx, which=0)
    history1 = _build_history_up_to(by_frame, frame_idx, which=1)
    f0 = _seek(cap0, frame_idx); f1 = _seek(cap1, frame_idx)
    if f0 is None or f1 is None:
        print(f"Cannot read first tracked frame {loop_start}"); sys.exit(1)

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    while True:
        rows = by_frame.get(frame_idx, [])
        composed = _compose(f0, f1, rows, history0, history1,
                            origins0, origins1, frame_idx, total_frames,
                            paused=paused, scale=scale, trail=args.trail, cam=args.cam,
                            draw_vector=args.vector)
        cv2.imshow(WINDOW, composed)
        delay = 0 if paused else base_delay_ms
        key = cv2.waitKey(delay) & 0xFF

        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
        elif key == ord("r"):
            frame_idx = loop_start
            history0 = _build_history_up_to(by_frame, frame_idx, which=0)
            history1 = _build_history_up_to(by_frame, frame_idx, which=1)
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1
            paused = True
        elif paused and key in (83, ord("d")) and frame_idx + 1 <= loop_end:
            frame_idx += 1
            for s in by_frame.get(frame_idx, []):
                if s.healthy:
                    history0[s.point_id].append((int(round(s.u0)), int(round(s.v0))))
                    history1[s.point_id].append((int(round(s.u1)), int(round(s.v1))))
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1
        elif paused and key in (81, ord("a")) and frame_idx > loop_start:
            frame_idx -= 1
            history0 = _build_history_up_to(by_frame, frame_idx, which=0)
            history1 = _build_history_up_to(by_frame, frame_idx, which=1)
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1
        elif not paused:
            if frame_idx >= loop_end:
                frame_idx = loop_start
                history0 = _build_history_up_to(by_frame, frame_idx, which=0)
                history1 = _build_history_up_to(by_frame, frame_idx, which=1)
            else:
                frame_idx += 1
                for s in by_frame.get(frame_idx, []):
                    if s.healthy:
                        history0[s.point_id].append((int(round(s.u0)), int(round(s.v0))))
                        history1[s.point_id].append((int(round(s.u1)), int(round(s.v1))))
            new0 = _seek(cap0, frame_idx); new1 = _seek(cap1, frame_idx)
            if new0 is not None: f0 = new0
            if new1 is not None: f1 = new1

    cap0.release(); cap1.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
