"""TrackSample dataclass + CSV I/O for the multi-point LK/NCC tracker.

Long-format CSV: one row per (frame_idx, point_id). Parallel to
tools/_annotations.py and tools/triangulate.py's stereo schema, but
extended with a point_id column and per-point health columns.

Headless module — no cv2, no GUI deps — so analysis can run offline.

Consumed by:
    tools/track_intersections.py  (writer)
    tools/playback_tracks.py      (reader)
    tools/analyze_tracks.py       (reader)
    tools/pick_track_seeds.py     (color palette, via POINT_COLORS_RGB)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# Sasha Trubetskoy 20-color qualitative palette (RGB, 0-255).
# Shared canonical per-point color palette: pick_track_seeds.py picks the
# seed in this color, playback_tracks.py draws each track dot in the same
# color, and analyze_tracks.py plots each line in the same color. Index by
# point_id; wraps past 20 points.
POINT_COLORS_RGB: tuple[tuple[int, int, int], ...] = (
    (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48),
    (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60),
    (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40),
    (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0),
    (255, 215, 180), (0, 0, 128), (128, 128, 128), (255, 255, 255),
)


def color_bgr_for_point(point_id: int) -> tuple[int, int, int]:
    """Per-point BGR tuple for cv2 drawing calls."""
    r, g, b = POINT_COLORS_RGB[point_id % len(POINT_COLORS_RGB)]
    return (int(b), int(g), int(r))


def color_mpl_for_point(point_id: int) -> tuple[float, float, float]:
    """Per-point matplotlib-friendly RGB float tuple (each channel in [0, 1])."""
    r, g, b = POINT_COLORS_RGB[point_id % len(POINT_COLORS_RGB)]
    return (r / 255.0, g / 255.0, b / 255.0)


CSV_HEADER: tuple[str, ...] = (
    "frame_idx", "point_id",
    "u0", "v0", "u1", "v1",
    "x_mm", "y_mm", "z_mm",
    "dx_mm", "dy_mm", "dz_mm", "displacement_mm",
    "fb_err_px_cam0", "fb_err_px_cam1",
    "ncc_cam0", "ncc_cam1",
    "healthy", "phase",
)


@dataclass(frozen=True)
class TrackSample:
    """One (frame_idx, point_id) sample from the hybrid LK+NCC tracker.

    Lost samples (healthy=False) carry the last known (u, v) and 3D values
    so consumers can still plot a track segment up to the loss point. The
    `healthy` flag indicates whether this row's measurements were freshly
    computed (True) or carried over (False).

    Attributes:
        frame_idx: cam0's 0-based frame index for this sample.
        point_id: integer id assigned by tools/pick_track_seeds.py in click order.
        u0, v0: pixel position in cam0 (NCC peak position, sub-pixel).
        u1, v1: pixel position in cam1 (NCC peak position, after sync interp).
        x_mm, y_mm, z_mm: 3D position in the calibration-object frame.
        dx_mm, dy_mm, dz_mm: 3D displacement from this point's frame-0 position.
        displacement_mm: Euclidean norm of (dx_mm, dy_mm, dz_mm).
        fb_err_px_cam0, fb_err_px_cam1: LK forward-backward residuals (pixels).
        ncc_cam0, ncc_cam1: NCC peak vs frame-0 anchor patch for each camera.
        healthy: True if both NCC peaks >= threshold this frame.
        phase: optional cardiac phase label (open/opening/closing/closed) or "".
    """

    frame_idx: int
    point_id: int
    u0: float
    v0: float
    u1: float
    v1: float
    x_mm: float
    y_mm: float
    z_mm: float
    dx_mm: float
    dy_mm: float
    dz_mm: float
    displacement_mm: float
    fb_err_px_cam0: float
    fb_err_px_cam1: float
    ncc_cam0: float
    ncc_cam1: float
    healthy: bool
    phase: str = ""


def write_tracks(rows: Iterable[TrackSample], path: Path) -> None:
    """Write track samples to CSV at `path`, sorted by (frame_idx, point_id).

    Overwrites any existing file at the path.
    """
    rows_sorted = sorted(rows, key=lambda r: (r.frame_idx, r.point_id))
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for r in rows_sorted:
            writer.writerow([
                r.frame_idx, r.point_id,
                f"{r.u0:.3f}", f"{r.v0:.3f}", f"{r.u1:.3f}", f"{r.v1:.3f}",
                f"{r.x_mm:.4f}", f"{r.y_mm:.4f}", f"{r.z_mm:.4f}",
                f"{r.dx_mm:.4f}", f"{r.dy_mm:.4f}", f"{r.dz_mm:.4f}",
                f"{r.displacement_mm:.4f}",
                f"{r.fb_err_px_cam0:.3f}", f"{r.fb_err_px_cam1:.3f}",
                f"{r.ncc_cam0:.4f}", f"{r.ncc_cam1:.4f}",
                "1" if r.healthy else "0",
                r.phase,
            ])


def read_tracks(path: Path) -> list[TrackSample]:
    """Read track samples from CSV at `path`.

    Returns [] if the file does not exist. Rows are sorted ascending by
    (frame_idx, point_id). Raises ValueError on malformed input.
    """
    if not Path(path).exists():
        return []

    rows: list[TrackSample] = []
    seen: set[tuple[int, int]] = set()
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if tuple(header or ()) != CSV_HEADER:
            raise ValueError(f"Bad header in {path}: {header!r}")
        for line_no, raw in enumerate(reader, start=2):
            if len(raw) != len(CSV_HEADER):
                raise ValueError(
                    f"{path}:{line_no}: expected {len(CSV_HEADER)} columns, got {len(raw)}")
            try:
                sample = TrackSample(
                    frame_idx=int(raw[0]),
                    point_id=int(raw[1]),
                    u0=float(raw[2]), v0=float(raw[3]),
                    u1=float(raw[4]), v1=float(raw[5]),
                    x_mm=float(raw[6]), y_mm=float(raw[7]), z_mm=float(raw[8]),
                    dx_mm=float(raw[9]), dy_mm=float(raw[10]), dz_mm=float(raw[11]),
                    displacement_mm=float(raw[12]),
                    fb_err_px_cam0=float(raw[13]), fb_err_px_cam1=float(raw[14]),
                    ncc_cam0=float(raw[15]), ncc_cam1=float(raw[16]),
                    healthy=(raw[17] == "1"),
                    phase=raw[18],
                )
            except ValueError as e:
                raise ValueError(f"{path}:{line_no}: bad row: {e}") from e
            key = (sample.frame_idx, sample.point_id)
            if key in seen:
                raise ValueError(f"{path}:{line_no}: duplicate (frame_idx, point_id) {key}")
            seen.add(key)
            rows.append(sample)

    rows.sort(key=lambda r: (r.frame_idx, r.point_id))
    return rows
