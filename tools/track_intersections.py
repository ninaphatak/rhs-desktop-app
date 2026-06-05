"""Hybrid LK + frame-0 NCC anchor tracker for inked-valve intersections.

For each seed point (clicked once in frame 0 in both cameras), this tool
walks the dual-camera video and locates the same intersection in every
frame. The algorithm is intentionally NOT pure Lucas-Kanade — pure LK
failed in `tools/leaflet_flow_test.py` because LK alone accumulates
drift, especially when patches deform with the leaflet. Here, LK is only
a *search prior*; the actual position each frame is the NCC peak against
the frame-0 anchor patch, which never updates.

Algorithm per frame, per point, per camera:

    1. LK forward+backward from previous frame → current frame.
       If FB residual <= --fb-threshold:  use LK prediction (±lk-search window).
       Else:                              use previous-frame position (±fallback-search window).

    2. NCC search the window against the frame-0 anchor patch
       (cv2.matchTemplate, TM_CCOEFF_NORMED). The final (u, v) is the
       NCC peak with parabolic sub-pixel refinement.

    3. If NCC peak < --ncc-threshold for either camera, mark the track
       lost FROM THIS FRAME ONWARD. Subsequent frames carry the last
       healthy (u, v) with healthy=False; no recovery.

After tracking, cam1 pixel positions are linearly interpolated to cam0
frame times (using timestamp sidecars, same as tools/triangulate.py)
before per-frame stereo triangulation.

Usage:
    python tools/track_intersections.py \\
        --seeds <recording>.track_seeds.json \\
        --calib outputs/calib/stereo_calib_water.json \\
        [--cam0-timestamps <cam0_video>.timestamps.csv] \\
        [--cam1-timestamps <cam1_video>.timestamps.csv] \\
        [--output <recording>.tracks.csv] \\
        [--patch-size 21] [--lk-search 5] [--fallback-search 15] \\
        [--fb-threshold 1.0] [--ncc-threshold 0.7] \\
        [--max-frames N]

Output CSV columns (long format, one row per frame × point):
    frame_idx, point_id, u0, v0, u1, v1, x_mm, y_mm, z_mm,
    dx_mm, dy_mm, dz_mm, displacement_mm,
    fb_err_px_cam0, fb_err_px_cam1, ncc_cam0, ncc_cam1, healthy, phase
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._tracks import TrackSample, write_tracks
from tools.triangulate import (
    load_calibration,
    load_timestamps,
    interpolate_pixel_at_time,
    triangulate_point,
)


LK_PARAMS = dict(
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    minEigThreshold=1e-4,
)


@dataclass
class TrackState:
    """Mutable per-point state during tracking.

    template_cam0/template_cam1 are the frame-0 anchor patches — NEVER updated.
    u*_curr/v*_curr is the last healthy (or freshly tracked) position.
    Once `healthy=False`, no further tracking is attempted for this point.
    """
    point_id: int
    template_cam0: np.ndarray
    template_cam1: np.ndarray
    u0_origin: float
    v0_origin: float
    u1_origin: float
    v1_origin: float
    xyz_origin: np.ndarray
    u0_curr: float
    v0_curr: float
    u1_curr: float
    v1_curr: float
    healthy: bool = True
    last_ncc_cam0: float = 1.0
    last_ncc_cam1: float = 1.0


# ---------- algorithmic primitives (also imported by tests) ----------


def extract_patch(gray: np.ndarray, u: float, v: float, patch_size: int) -> np.ndarray | None:
    """Return a `patch_size × patch_size` patch centered on int(round(u, v)).

    Returns None if the patch would extend outside the image.
    """
    h, w = gray.shape[:2]
    cu, cv_ = int(round(u)), int(round(v))
    half = patch_size // 2
    x0, y0 = cu - half, cv_ - half
    x1, y1 = x0 + patch_size, y0 + patch_size
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        return None
    return gray[y0:y1, x0:x1].copy()


def track_lk_one_point(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
    u_prev: float,
    v_prev: float,
) -> tuple[float, float, float]:
    """Forward + backward LK on a single point. Returns (u, v, fb_err_px).

    Falls back to (u_prev, v_prev, inf) if either LK call fails.
    """
    p_prev = np.array([[[u_prev, v_prev]]], dtype=np.float32)
    p_forward, _, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p_prev, None, **LK_PARAMS)
    if p_forward is None:
        return u_prev, v_prev, float("inf")
    p_backward, _, _ = cv2.calcOpticalFlowPyrLK(curr_gray, prev_gray, p_forward, None, **LK_PARAMS)
    if p_backward is None:
        return float(p_forward[0, 0, 0]), float(p_forward[0, 0, 1]), float("inf")
    fb_err = float(np.linalg.norm(p_backward[0, 0] - p_prev[0, 0]))
    return float(p_forward[0, 0, 0]), float(p_forward[0, 0, 1]), fb_err


def parabolic_subpixel(ncc_map: np.ndarray, peak_r: int, peak_c: int) -> tuple[float, float]:
    """Sub-pixel parabolic refinement of an NCC peak.

    Returns (dr, dc) offsets clamped to (-0.5, 0.5). Returns (0, 0) if the
    peak is on the boundary or the parabola is degenerate.
    """
    h, w = ncc_map.shape
    if peak_r <= 0 or peak_r >= h - 1 or peak_c <= 0 or peak_c >= w - 1:
        return 0.0, 0.0
    s = ncc_map
    sym, s00, syp = s[peak_r - 1, peak_c], s[peak_r, peak_c], s[peak_r + 1, peak_c]
    denom_r = sym - 2.0 * s00 + syp
    dr = 0.5 * (sym - syp) / denom_r if denom_r != 0 else 0.0
    sxm, sxp = s[peak_r, peak_c - 1], s[peak_r, peak_c + 1]
    denom_c = sxm - 2.0 * s00 + sxp
    dc = 0.5 * (sxm - sxp) / denom_c if denom_c != 0 else 0.0
    return max(-0.5, min(0.5, float(dr))), max(-0.5, min(0.5, float(dc)))


def ncc_search(
    gray: np.ndarray,
    template: np.ndarray,
    u_pred: float,
    v_pred: float,
    half_width: int,
) -> tuple[float, float, float]:
    """Search a (2·half_width+1)² NCC map around (u_pred, v_pred).

    Returns (u, v, ncc_peak). The position is sub-pixel refined. If the
    search region extends outside the image, returns (u_pred, v_pred, 0.0).
    """
    h, w = gray.shape[:2]
    ph, pw = template.shape[:2]
    half_t_x, half_t_y = pw // 2, ph // 2
    cu, cv_ = int(round(u_pred)), int(round(v_pred))
    x0 = cu - half_t_x - half_width
    y0 = cv_ - half_t_y - half_width
    x1 = x0 + pw + 2 * half_width
    y1 = y0 + ph + 2 * half_width
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        return u_pred, v_pred, 0.0
    search_region = gray[y0:y1, x0:x1]
    ncc_map = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
    peak_idx = np.unravel_index(int(np.argmax(ncc_map)), ncc_map.shape)
    peak_r, peak_c = int(peak_idx[0]), int(peak_idx[1])
    peak_val = float(ncc_map[peak_r, peak_c])
    dr, dc = parabolic_subpixel(ncc_map, peak_r, peak_c)
    u_match = float(cu) + float(peak_c - half_width) + dc
    v_match = float(cv_) + float(peak_r - half_width) + dr
    return u_match, v_match, peak_val


def hybrid_step(
    state: TrackState,
    prev_g0: np.ndarray,
    curr_g0: np.ndarray,
    prev_g1: np.ndarray,
    curr_g1: np.ndarray,
    fb_threshold: float,
    ncc_threshold: float,
    lk_search: int,
    fallback_search: int,
) -> tuple[float, float, float, float, bool]:
    """Process one frame for one point. Mutates state on success.

    Returns (fb_err_cam0, fb_err_cam1, ncc_cam0, ncc_cam1, healthy_this_frame).
    """
    # cam0: LK predicts, NCC anchors
    u0_lk, v0_lk, fb0 = track_lk_one_point(prev_g0, curr_g0, state.u0_curr, state.v0_curr)
    if fb0 <= fb_threshold:
        u0_pred, v0_pred, half0 = u0_lk, v0_lk, lk_search
    else:
        u0_pred, v0_pred, half0 = state.u0_curr, state.v0_curr, fallback_search
    u0_final, v0_final, ncc0 = ncc_search(curr_g0, state.template_cam0, u0_pred, v0_pred, half0)

    # cam1: LK predicts, NCC anchors
    u1_lk, v1_lk, fb1 = track_lk_one_point(prev_g1, curr_g1, state.u1_curr, state.v1_curr)
    if fb1 <= fb_threshold:
        u1_pred, v1_pred, half1 = u1_lk, v1_lk, lk_search
    else:
        u1_pred, v1_pred, half1 = state.u1_curr, state.v1_curr, fallback_search
    u1_final, v1_final, ncc1 = ncc_search(curr_g1, state.template_cam1, u1_pred, v1_pred, half1)

    if ncc0 < ncc_threshold or ncc1 < ncc_threshold:
        state.healthy = False
        state.last_ncc_cam0 = ncc0
        state.last_ncc_cam1 = ncc1
        return fb0, fb1, ncc0, ncc1, False

    state.u0_curr, state.v0_curr = u0_final, v0_final
    state.u1_curr, state.v1_curr = u1_final, v1_final
    state.last_ncc_cam0, state.last_ncc_cam1 = ncc0, ncc1
    return fb0, fb1, ncc0, ncc1, True


# ---------- top-level orchestration ----------


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def _read_frame(cap: cv2.VideoCapture) -> np.ndarray | None:
    ret, frame = cap.read()
    return frame if ret else None


def _load_seeds(path: Path) -> dict:
    data = json.loads(path.read_text())
    required = {"cam0_video", "cam1_video", "frame_idx", "points"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"Seeds file {path} missing keys: {missing}")
    for p in data["points"]:
        for k in ("point_id", "u0", "v0", "u1", "v1"):
            if k not in p:
                raise ValueError(f"Seed point missing key {k!r}: {p}")
    return data


def _initialize_states(
    seeds: list[dict],
    g0_frame0: np.ndarray,
    g1_frame0: np.ndarray,
    calib: dict,
    patch_size: int,
) -> list[TrackState]:
    states: list[TrackState] = []
    for s in seeds:
        t0 = extract_patch(g0_frame0, s["u0"], s["v0"], patch_size)
        t1 = extract_patch(g1_frame0, s["u1"], s["v1"], patch_size)
        if t0 is None or t1 is None:
            print(f"  WARNING: seed point_id={s['point_id']} too close to image edge — skipping")
            continue
        xyz0 = triangulate_point(
            calib["cam0"]["K"], calib["cam0"]["dist"],
            calib["cam0"]["rvec"], calib["cam0"]["tvec"],
            calib["cam1"]["K"], calib["cam1"]["dist"],
            calib["cam1"]["rvec"], calib["cam1"]["tvec"],
            (s["u0"], s["v0"]), (s["u1"], s["v1"]),
        )
        states.append(TrackState(
            point_id=int(s["point_id"]),
            template_cam0=t0, template_cam1=t1,
            u0_origin=float(s["u0"]), v0_origin=float(s["v0"]),
            u1_origin=float(s["u1"]), v1_origin=float(s["v1"]),
            xyz_origin=xyz0,
            u0_curr=float(s["u0"]), v0_curr=float(s["v0"]),
            u1_curr=float(s["u1"]), v1_curr=float(s["v1"]),
        ))
    return states


def _triangulate_with_sync(
    pix: dict,
    point_id: int,
    frame_idx: int,
    cam1_history: dict[int, tuple[float, float]] | None,
    cam0_times: dict[int, float] | None,
    cam1_times: dict[int, float] | None,
    calib: dict,
) -> np.ndarray:
    """Triangulate (u0, v0, u1, v1) into 3D mm with optional sync interp."""
    if cam1_history is not None and cam0_times is not None and cam1_times is not None:
        target_t = cam0_times.get(frame_idx)
        if target_t is not None and cam1_history:
            uv1 = interpolate_pixel_at_time(cam1_history, cam1_times, target_t)
        else:
            uv1 = (pix["u1"], pix["v1"])
    else:
        uv1 = (pix["u1"], pix["v1"])
    return triangulate_point(
        calib["cam0"]["K"], calib["cam0"]["dist"],
        calib["cam0"]["rvec"], calib["cam0"]["tvec"],
        calib["cam1"]["K"], calib["cam1"]["dist"],
        calib["cam1"]["rvec"], calib["cam1"]["tvec"],
        (pix["u0"], pix["v0"]), uv1,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=Path, required=True,
                    help="JSON from tools/pick_track_seeds.py")
    ap.add_argument("--calib", type=Path, required=True,
                    help="Stereo calibration JSON")
    ap.add_argument("--cam0-timestamps", type=Path, default=None,
                    help="cam0 timestamp sidecar (.timestamps.csv). Auto-detected from cam0 video path if omitted.")
    ap.add_argument("--cam1-timestamps", type=Path, default=None,
                    help="cam1 timestamp sidecar. Auto-detected if omitted.")
    ap.add_argument("--output", type=Path, default=None,
                    help="Output CSV path (default: <seeds>.tracks.csv next to seeds file)")
    ap.add_argument("--patch-size", type=int, default=31,
                    help="NCC anchor template size in pixels (must be odd). "
                         "Larger = more white-space context = more locally unique, "
                         "at the cost of being less tolerant of patch deformation.")
    ap.add_argument("--lk-search", type=int, default=10,
                    help="NCC search half-width when LK is reliable (px/frame motion tolerance)")
    ap.add_argument("--fallback-search", type=int, default=30,
                    help="NCC search half-width when LK FB residual exceeds threshold "
                         "(px/frame tolerance for fast or non-smooth motion, e.g. leaflet snap-open)")
    ap.add_argument("--fb-threshold", type=float, default=1.0,
                    help="Max LK forward-backward residual (px) to trust LK prediction")
    ap.add_argument("--ncc-threshold", type=float, default=0.7,
                    help="Min NCC peak vs frame-0 patch to keep track healthy")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="Process only the first N frames (for smoke tests)")
    args = ap.parse_args()

    seeds_data = _load_seeds(args.seeds)
    seeds = seeds_data["points"]
    anchor_frame = int(seeds_data["frame_idx"])
    if anchor_frame != 0:
        print(f"NOTE: seeds anchored to frame_idx={anchor_frame}; tracking forward from there")

    seeds_dir = args.seeds.parent
    cam0_video = (seeds_dir / seeds_data["cam0_video"]).resolve()
    cam1_video = (seeds_dir / seeds_data["cam1_video"]).resolve()
    if not cam0_video.exists() or not cam1_video.exists():
        print(f"Video file not found: {cam0_video} or {cam1_video}")
        sys.exit(1)

    ts0_path = args.cam0_timestamps or Path(str(cam0_video) + ".timestamps.csv")
    ts1_path = args.cam1_timestamps or Path(str(cam1_video) + ".timestamps.csv")
    cam0_times = load_timestamps(ts0_path) if ts0_path.exists() else None
    cam1_times = load_timestamps(ts1_path) if ts1_path.exists() else None
    sync_interp = cam0_times is not None and cam1_times is not None
    if sync_interp:
        print(f"Using sync interpolation (cam0_times={len(cam0_times)}, cam1_times={len(cam1_times)})")
    else:
        print("No timestamp sidecars — naive frame-N pairing (no sync correction)")

    calib = load_calibration(args.calib)
    print(f"Loaded calibration: {args.calib}")

    cap0 = cv2.VideoCapture(str(cam0_video))
    cap1 = cv2.VideoCapture(str(cam1_video))
    if not (cap0.isOpened() and cap1.isOpened()):
        print("Cannot open videos"); sys.exit(1)
    n0 = int(cap0.get(cv2.CAP_PROP_FRAME_COUNT))
    n1 = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))
    end_frame = min(n0, n1)
    if args.max_frames is not None:
        end_frame = min(end_frame, anchor_frame + args.max_frames)
    n_frames_to_track = end_frame - anchor_frame
    if n_frames_to_track <= 0:
        print(f"Anchor frame {anchor_frame} is beyond video end ({min(n0, n1)})")
        sys.exit(1)
    print(f"Tracking frames [{anchor_frame}..{end_frame - 1}] ({n_frames_to_track} frames, "
          f"{len(seeds)} seed points, patch={args.patch_size}px, "
          f"lk_search=±{args.lk_search}px, fallback_search=±{args.fallback_search}px, "
          f"fb_thresh={args.fb_threshold}px, ncc_thresh={args.ncc_threshold})")

    # Seek both videos to the anchor frame
    cap0.set(cv2.CAP_PROP_POS_FRAMES, anchor_frame)
    cap1.set(cv2.CAP_PROP_POS_FRAMES, anchor_frame)
    f0 = _read_frame(cap0)
    f1 = _read_frame(cap1)
    if f0 is None or f1 is None:
        print(f"Cannot read anchor frame {anchor_frame}"); sys.exit(1)
    g0 = _to_gray(f0)
    g1 = _to_gray(f1)
    states = _initialize_states(seeds, g0, g1, calib, args.patch_size)
    if not states:
        print("No usable seeds (all too close to edge)"); sys.exit(1)
    print(f"Initialized {len(states)} track states")

    # Phase 1: tracking — store raw per-frame pixel positions + health diagnostics
    # in memory. Triangulation happens in Phase 2 so we can apply sync interp.
    pixels: dict[tuple[int, int], dict] = {}
    for st in states:
        pixels[(anchor_frame, st.point_id)] = dict(
            u0=st.u0_curr, v0=st.v0_curr, u1=st.u1_curr, v1=st.v1_curr,
            fb_err_px_cam0=0.0, fb_err_px_cam1=0.0,
            ncc_cam0=1.0, ncc_cam1=1.0, healthy=True,
        )

    prev_g0, prev_g1 = g0, g1
    t_start = time.time()
    for frame_idx in range(anchor_frame + 1, end_frame):
        f0 = _read_frame(cap0)
        f1 = _read_frame(cap1)
        if f0 is None or f1 is None:
            print(f"  truncated at frame {frame_idx}: short read")
            end_frame = frame_idx
            break
        g0 = _to_gray(f0)
        g1 = _to_gray(f1)
        for st in states:
            if st.healthy:
                fb0, fb1, ncc0, ncc1, ok = hybrid_step(
                    st, prev_g0, g0, prev_g1, g1,
                    args.fb_threshold, args.ncc_threshold,
                    args.lk_search, args.fallback_search,
                )
            else:
                fb0, fb1, ncc0, ncc1, ok = 0.0, 0.0, st.last_ncc_cam0, st.last_ncc_cam1, False
            pixels[(frame_idx, st.point_id)] = dict(
                u0=st.u0_curr, v0=st.v0_curr, u1=st.u1_curr, v1=st.v1_curr,
                fb_err_px_cam0=fb0, fb_err_px_cam1=fb1,
                ncc_cam0=ncc0, ncc_cam1=ncc1, healthy=ok,
            )
        prev_g0, prev_g1 = g0, g1
        n_done = frame_idx - anchor_frame + 1
        if n_done % 100 == 0:
            elapsed = time.time() - t_start
            healthy_count = sum(1 for st in states if st.healthy)
            print(f"  frame {frame_idx}/{end_frame - 1}  "
                  f"healthy={healthy_count}/{len(states)}  "
                  f"({n_done / elapsed:.1f} fps)")
    cap0.release(); cap1.release()
    print(f"Phase 1 (tracking) done in {time.time() - t_start:.1f}s; "
          f"final healthy={sum(1 for st in states if st.healthy)}/{len(states)}")

    # Phase 2: triangulation with optional sync interp
    cam1_histories: dict[int, dict[int, tuple[float, float]]] = {}
    if sync_interp:
        for (fidx, pid), px in pixels.items():
            if px["healthy"]:
                cam1_histories.setdefault(pid, {})[fidx] = (px["u1"], px["v1"])

    state_by_id = {st.point_id: st for st in states}
    samples: list[TrackSample] = []
    for (frame_idx, point_id) in sorted(pixels.keys()):
        px = pixels[(frame_idx, point_id)]
        st = state_by_id[point_id]
        if px["healthy"]:
            xyz = _triangulate_with_sync(
                px, point_id, frame_idx,
                cam1_histories.get(point_id) if sync_interp else None,
                cam0_times, cam1_times, calib,
            )
        else:
            # Carry over the last healthy xyz: re-triangulate at the carried (u, v).
            # (st.xyz_origin if never moved; otherwise the last healthy position is
            #  already stored in u*_curr.)
            xyz = _triangulate_with_sync(
                px, point_id, frame_idx, None, None, None, calib,
            )
        d = xyz - st.xyz_origin
        sample = TrackSample(
            frame_idx=frame_idx, point_id=point_id,
            u0=px["u0"], v0=px["v0"], u1=px["u1"], v1=px["v1"],
            x_mm=float(xyz[0]), y_mm=float(xyz[1]), z_mm=float(xyz[2]),
            dx_mm=float(d[0]), dy_mm=float(d[1]), dz_mm=float(d[2]),
            displacement_mm=float(np.linalg.norm(d)),
            fb_err_px_cam0=px["fb_err_px_cam0"], fb_err_px_cam1=px["fb_err_px_cam1"],
            ncc_cam0=px["ncc_cam0"], ncc_cam1=px["ncc_cam1"],
            healthy=px["healthy"],
            phase="",
        )
        samples.append(sample)

    out_path = args.output or args.seeds.with_suffix(".tracks.csv")
    write_tracks(samples, out_path)

    # Per-point summary
    print(f"\nWrote {out_path} ({len(samples)} rows)")
    print("Per-point summary:")
    for pid in sorted(state_by_id.keys()):
        pt_samples = [s for s in samples if s.point_id == pid]
        n_healthy = sum(1 for s in pt_samples if s.healthy)
        n = len(pt_samples)
        last_healthy = max((s.frame_idx for s in pt_samples if s.healthy), default=-1)
        peak_disp = max((s.displacement_mm for s in pt_samples if s.healthy), default=0.0)
        print(f"  point_id={pid:2d}  healthy={n_healthy:4d}/{n:4d}  "
              f"last_healthy_frame={last_healthy:4d}  peak_displacement={peak_disp:.3f}mm")


if __name__ == "__main__":
    main()
