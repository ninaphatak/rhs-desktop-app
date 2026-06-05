"""Tests for the hybrid LK+NCC intersection tracker.

Covers:
    - tools/_tracks.py round-trip + header validation
    - tools/track_intersections.py algorithmic primitives:
        * extract_patch bounds checking
        * track_lk_one_point on synthetic translating gradients
        * parabolic_subpixel against a known sub-pixel Gaussian peak
        * ncc_search against a shifted patch
        * hybrid_step end-to-end synthetic translation (regression vs LK-only drift)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `from tools.* import ...`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pytest

from tools._tracks import CSV_HEADER, TrackSample, read_tracks, write_tracks
from tools.track_intersections import (
    LK_PARAMS,
    TrackState,
    extract_patch,
    hybrid_step,
    ncc_search,
    parabolic_subpixel,
    track_lk_one_point,
)


# ============================================================
# _tracks.py
# ============================================================


def _sample(frame_idx: int, point_id: int, healthy: bool = True, **overrides) -> TrackSample:
    defaults = dict(
        frame_idx=frame_idx, point_id=point_id,
        u0=100.0 + frame_idx, v0=200.0 + frame_idx,
        u1=105.0 + frame_idx, v1=200.5 + frame_idx,
        x_mm=1.0, y_mm=2.0, z_mm=3.0,
        dx_mm=0.1, dy_mm=0.2, dz_mm=0.3,
        displacement_mm=0.374,
        fb_err_px_cam0=0.05, fb_err_px_cam1=0.06,
        ncc_cam0=0.95, ncc_cam1=0.93,
        healthy=healthy, phase="",
    )
    defaults.update(overrides)
    return TrackSample(**defaults)


def test_csv_header_matches_documented_schema():
    expected = (
        "frame_idx", "point_id", "u0", "v0", "u1", "v1",
        "x_mm", "y_mm", "z_mm", "dx_mm", "dy_mm", "dz_mm", "displacement_mm",
        "fb_err_px_cam0", "fb_err_px_cam1", "ncc_cam0", "ncc_cam1",
        "healthy", "phase",
    )
    assert CSV_HEADER == expected


def test_write_then_read_round_trip(tmp_path):
    rows = [
        _sample(0, 0), _sample(0, 1),
        _sample(1, 0), _sample(1, 1),
        _sample(2, 0, healthy=False, ncc_cam0=0.4, ncc_cam1=0.3),
        _sample(2, 1),
    ]
    out = tmp_path / "tracks.csv"
    write_tracks(rows, out)

    loaded = read_tracks(out)
    assert len(loaded) == len(rows)
    # Sort original by (frame_idx, point_id) for comparison
    rows_sorted = sorted(rows, key=lambda r: (r.frame_idx, r.point_id))
    for a, b in zip(loaded, rows_sorted):
        assert a.frame_idx == b.frame_idx
        assert a.point_id == b.point_id
        assert a.healthy == b.healthy
        assert a.phase == b.phase
        # Floats round-trip to printf precision
        for f in ("u0", "v0", "u1", "v1", "x_mm", "y_mm", "z_mm",
                  "dx_mm", "dy_mm", "dz_mm", "displacement_mm",
                  "fb_err_px_cam0", "fb_err_px_cam1",
                  "ncc_cam0", "ncc_cam1"):
            assert getattr(a, f) == pytest.approx(getattr(b, f), abs=1e-3)


def test_read_missing_file_returns_empty(tmp_path):
    assert read_tracks(tmp_path / "nope.csv") == []


def test_read_rejects_bad_header(tmp_path):
    p = tmp_path / "tracks.csv"
    p.write_text("frame_idx,point_id\n0,0\n")
    with pytest.raises(ValueError, match="Bad header"):
        read_tracks(p)


def test_read_rejects_duplicate_frame_point(tmp_path):
    rows = [_sample(0, 0), _sample(0, 0)]
    out = tmp_path / "tracks.csv"
    write_tracks(rows, out)
    # write_tracks sorts but doesn't dedup; reader must reject
    with pytest.raises(ValueError, match="duplicate"):
        read_tracks(out)


def test_healthy_false_round_trips(tmp_path):
    rows = [_sample(0, 0, healthy=True), _sample(1, 0, healthy=False)]
    out = tmp_path / "tracks.csv"
    write_tracks(rows, out)
    loaded = read_tracks(out)
    assert loaded[0].healthy is True
    assert loaded[1].healthy is False


# ============================================================
# Image synthesis helpers
# ============================================================


def _make_corner_image(size: int = 200, cx: float = 100.0, cy: float = 100.0,
                       bg: int = 220) -> np.ndarray:
    """Synthetic image: black inked X-junction at sub-pixel (cx, cy).

    Uses cv2.line's shift parameter (4 bits of fractional precision) so that
    the corner position is truly sub-pixel — important for sub-pixel
    tracking tests where rounding-to-int would otherwise mask drift.
    """
    img = np.full((size, size), bg, dtype=np.uint8)
    shift = 4
    s = 1 << shift  # 16
    cxq, cyq = int(round(cx * s)), int(round(cy * s))
    # Horizontal line (uses cyq for sub-pixel y)
    cv2.line(img, (0, cyq), (size * s, cyq), 30, 2, cv2.LINE_AA, shift)
    # Vertical line (uses cxq for sub-pixel x)
    cv2.line(img, (cxq, 0), (cxq, size * s), 30, 2, cv2.LINE_AA, shift)
    # Diagonal stroke for local pattern asymmetry
    cv2.line(img, (cxq - 30 * s, cyq - 30 * s),
             (cxq + 30 * s, cyq + 30 * s), 60, 1, cv2.LINE_AA, shift)
    return img


def _make_gaussian_ncc_map(size: int, peak_r: float, peak_c: float,
                            sigma: float = 1.0) -> np.ndarray:
    """A 2D Gaussian peaked at sub-pixel (peak_r, peak_c) — for parabolic-fit tests."""
    rs, cs = np.mgrid[0:size, 0:size]
    return np.exp(-((rs - peak_r) ** 2 + (cs - peak_c) ** 2) / (2 * sigma * sigma))


# ============================================================
# extract_patch
# ============================================================


def test_extract_patch_centered_size_is_right():
    img = _make_corner_image()
    p = extract_patch(img, 100.0, 100.0, 21)
    assert p is not None
    assert p.shape == (21, 21)


def test_extract_patch_returns_none_near_edge():
    img = _make_corner_image(size=50)
    assert extract_patch(img, 2.0, 2.0, 21) is None
    assert extract_patch(img, 48.0, 48.0, 21) is None


# ============================================================
# track_lk_one_point
# ============================================================


def test_lk_recovers_small_translation():
    # Build two images: frame0 has the corner at (100, 100); frame1 at (101, 100)
    f0 = _make_corner_image(cx=100.0, cy=100.0)
    f1 = _make_corner_image(cx=101.0, cy=100.0)
    u, v, fb = track_lk_one_point(f0, f1, 100.0, 100.0)
    assert u == pytest.approx(101.0, abs=0.5)
    assert v == pytest.approx(100.0, abs=0.5)
    assert fb < 0.5


def test_lk_fb_error_is_small_on_clean_translation():
    f0 = _make_corner_image(cx=100.0, cy=100.0)
    f1 = _make_corner_image(cx=100.5, cy=100.0)
    _, _, fb = track_lk_one_point(f0, f1, 100.0, 100.0)
    assert fb < 0.2


# ============================================================
# parabolic_subpixel
# ============================================================


def test_parabolic_subpixel_recovers_known_offset():
    # Gaussian peaked at (5.3, 5.0) within a 11x11 grid
    ncc = _make_gaussian_ncc_map(11, peak_r=5.3, peak_c=5.0, sigma=1.0)
    peak_r, peak_c = np.unravel_index(int(np.argmax(ncc)), ncc.shape)
    dr, dc = parabolic_subpixel(ncc, int(peak_r), int(peak_c))
    # Effective peak should be at int_peak + (dr, dc) ≈ (5.3, 5.0)
    assert (int(peak_r) + dr) == pytest.approx(5.3, abs=0.05)
    assert (int(peak_c) + dc) == pytest.approx(5.0, abs=0.05)


def test_parabolic_subpixel_handles_boundary_peak():
    ncc = np.zeros((5, 5))
    ncc[0, 0] = 1.0  # peak at top-left corner
    dr, dc = parabolic_subpixel(ncc, 0, 0)
    assert (dr, dc) == (0.0, 0.0)


# ============================================================
# ncc_search
# ============================================================


def test_ncc_search_recovers_known_shift():
    f0 = _make_corner_image(cx=100.0, cy=100.0)
    template = extract_patch(f0, 100.0, 100.0, 21)
    assert template is not None
    # Frame 1: corner moved to (102, 99)
    f1 = _make_corner_image(cx=102.0, cy=99.0)
    # Predict that it stayed at (100, 100); NCC should find (102, 99) within ±5
    u, v, ncc = ncc_search(f1, template, 100.0, 100.0, half_width=5)
    assert ncc > 0.9
    assert u == pytest.approx(102.0, abs=0.7)
    assert v == pytest.approx(99.0, abs=0.7)


def test_ncc_search_returns_zero_when_out_of_bounds():
    img = _make_corner_image(size=50)
    template = np.full((21, 21), 200, dtype=np.uint8)
    # Predict (2, 2) — template+search window doesn't fit
    u, v, ncc = ncc_search(img, template, 2.0, 2.0, half_width=5)
    assert ncc == 0.0
    assert u == 2.0 and v == 2.0


def test_ncc_search_drops_low_on_different_pattern():
    f0 = _make_corner_image(cx=100.0, cy=100.0)
    template = extract_patch(f0, 100.0, 100.0, 21)
    # An image with NO corner near the predicted location (flat region)
    flat = np.full((200, 200), 220, dtype=np.uint8)
    _, _, ncc = ncc_search(flat, template, 100.0, 100.0, half_width=5)
    assert ncc < 0.3


# ============================================================
# hybrid_step end-to-end synthetic regression test
# ============================================================


def _make_state_from_frame(frame_gray: np.ndarray, point_id: int,
                            u: float, v: float, patch_size: int = 21) -> TrackState:
    t = extract_patch(frame_gray, u, v, patch_size)
    assert t is not None
    return TrackState(
        point_id=point_id,
        template_cam0=t, template_cam1=t.copy(),
        u0_origin=u, v0_origin=v, u1_origin=u, v1_origin=v,
        xyz_origin=np.zeros(3),
        u0_curr=u, v0_curr=v, u1_curr=u, v1_curr=v,
    )


def test_hybrid_step_tracks_translating_corner_without_drift():
    """The regression test for the leaflet_flow_test.py failure mode.

    A corner translates by 0.5 px/frame for 100 frames, plus a slow
    brightness drift that LK alone (without an anchor) would slowly slide
    off. The hybrid tracker should remain within 0.5 px of ground truth
    even at frame 100, because the NCC anchor pins to the frame-0 patch.
    """
    rng = np.random.default_rng(0)
    img0 = _make_corner_image(cx=100.0, cy=100.0)
    state = _make_state_from_frame(img0, point_id=0, u=100.0, v=100.0)

    prev = img0.copy()
    max_err_px = 0.0
    for k in range(1, 101):
        gt_x = 100.0 + 0.5 * k
        # Apply slow intensity drift: shift background brightness over time
        curr = _make_corner_image(cx=gt_x, cy=100.0)
        curr = np.clip(curr.astype(np.int16) + (k // 5), 0, 255).astype(np.uint8)
        fb0, fb1, ncc0, ncc1, ok = hybrid_step(
            state, prev, curr, prev.copy(), curr.copy(),
            fb_threshold=1.0, ncc_threshold=0.6,
            lk_search=5, fallback_search=15,
        )
        assert ok, f"Track lost at frame {k}: ncc0={ncc0:.3f}, ncc1={ncc1:.3f}"
        err = abs(state.u0_curr - gt_x)
        max_err_px = max(max_err_px, err)
        prev = curr

    assert max_err_px < 0.5, f"Tracker drifted by {max_err_px:.2f} px (limit 0.5)"


def test_hybrid_step_marks_lost_when_patch_disappears():
    """When the patch vanishes (replaced with flat background), the track
    must report healthy=False rather than silently drifting to a wrong spot."""
    img0 = _make_corner_image(cx=100.0, cy=100.0)
    state = _make_state_from_frame(img0, point_id=0, u=100.0, v=100.0)
    # Frame 1: pattern is gone — flat image
    flat = np.full_like(img0, 220)
    _, _, ncc0, ncc1, ok = hybrid_step(
        state, img0, flat, img0.copy(), flat.copy(),
        fb_threshold=1.0, ncc_threshold=0.7,
        lk_search=5, fallback_search=15,
    )
    assert ok is False
    assert state.healthy is False
    assert ncc0 < 0.7 or ncc1 < 0.7
