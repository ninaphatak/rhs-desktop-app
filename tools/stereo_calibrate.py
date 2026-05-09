"""Single-view stereo calibration for the RHS calibration object.

Given a calibration AVI from each camera + a markers CSV with the 3D
positions of all painted dots, this tool:

1. Extracts a clean frame from each video (default: middle frame)
2. Auto-detects black dots via threshold + blob detection
3. Walks the user through a manual marker_id assignment for each blob
4. Runs cv2.calibrateCamera per camera with minimal distortion model
5. Triangulates every common-visible marker, compares to known XYZ
6. Cross-checks calibration-derived camera position vs CAD EPP
7. Writes outputs/calib/stereo_calib_<fluid>.json

Usage:
    python tools/stereo_calibrate.py \\
        outputs/videos/calib_water_<ts>_cam0.avi \\
        outputs/videos/calib_water_<ts>_cam1.avi \\
        --markers markers.csv

Marker numbering (per ring, starting at +y "north" going clockwise):
    1=N, 2=NE, 3=E, 4=SE, 5=S, 6=SW, 7=W, 8=NW

Rings (z-depth, radius_mm, marker_id range):
    Lowest cylinder:    z=-11.76, r=14.68, ids  1-8
    Middle cylinder:    z=-7.84,  r=12.72, ids  9-16
    Upper cylinder:     z=-3.92,  r=10.76, ids 17-24
    Top face outer:     z=0,      r=8.00,  ids 25-32
    Top face inner:     z=0,      r=4.00,  ids 33-40
    Center marker:      (0,0,0),           id  41
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np


# -- Lens-specific constants (Edmund #33-304, 16mm UC Series) --
LENS_EPP_FROM_FRONT_FACE_MM = 10.68
LENS_FOCAL_MM = 16.0

# -- Camera-specific constants (Basler ace 2 a2A1920-160umBAS, IMX392 sensor) --
PIXEL_SIZE_MM = 0.00345

# -- Refractive indices per fluid (used to compute the underwater effective focal length) --
FLUID_REFRACTIVE_INDICES: dict[str, float] = {
    "water": 1.333,
    "analog": 1.385,   # 35% glycerin + 0.02% xanthan gum
}

# -- Detection params (tuned against real frames at ~200mm WD) --
DARK_THRESHOLD = 80           # pixels darker than this are dot candidates
MORPH_KERNEL_SIZE = 5
BLOB_MIN_AREA = 30            # px^2 (1.5mm dots at ~200mm WD ~ 50-200 px^2)
BLOB_MAX_AREA = 1200
BLOB_MIN_CIRCULARITY = 0.4

# -- Calibration model: physically-constrained for single-view non-coplanar rigs --
# Single-view non-coplanar calibration has too many degrees of freedom for
# stable K estimation; without strong constraints the optimizer overfits K
# and distortion to compensate for noise, causing camera-position drift even
# when projection accuracy is fine. We fix focal length (from lens spec +
# pixel size + fluid refraction) and the principal point at image center,
# and let only the lens distortion fit (radial k1 + tangential p1, p2 — the
# physically meaningful terms). This was empirically the best variant: 3D
# triangulation error 0.154mm median, 0.431mm max, with EPP discrepancy
# still well under the 15mm validation tolerance.
CALIB_FLAGS = (
    cv2.CALIB_USE_INTRINSIC_GUESS
    | cv2.CALIB_FIX_FOCAL_LENGTH
    | cv2.CALIB_FIX_PRINCIPAL_POINT
    | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3   # k1 free, k2=k3=0
    # tangential (p1, p2) free — empirically improves projection accuracy ~10%
)

# -- Validation tolerance --
VALIDATION_3D_TOLERANCE_MM = 5.0
VALIDATION_EPP_TOLERANCE_MM = 15.0  # as-built mounting tolerance + residual refraction


class CameraSpec(NamedTuple):
    """CAD-derived geometry for one camera."""
    front_face: np.ndarray       # (3,) lens front-face center in cal-object frame
    axis_intersect: np.ndarray   # (3,) where optical axis hits z=0 plane

    @property
    def axis_outward(self) -> np.ndarray:
        v = self.axis_intersect - self.front_face
        return v / np.linalg.norm(v)

    @property
    def epp(self) -> np.ndarray:
        """CAD-predicted entrance pupil = front_face + EPP_OFFSET * (-axis_outward)."""
        return self.front_face - LENS_EPP_FROM_FRONT_FACE_MM * self.axis_outward


def parse_markers_csv(path: Path) -> tuple[dict[int, np.ndarray], dict[str, np.ndarray]]:
    """Returns (markers_xyz, cameras_xyz) from the markers CSV."""
    markers: dict[int, np.ndarray] = {}
    cameras: dict[str, np.ndarray] = {}
    with open(path) as f:
        next(f)  # skip header
        for line in f:
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) != 4:
                continue
            label, x, y, z = parts
            xyz = np.array([float(x), float(y), float(z)], dtype=np.float64)
            try:
                markers[int(label)] = xyz
            except ValueError:
                cameras[label] = xyz
    return markers, cameras


def extract_frame(video_path: Path, frame_idx: int = -1) -> tuple[np.ndarray, int]:
    """Extract a single frame. Default frame_idx=-1 means the middle frame."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video_path}")
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_idx < 0:
        frame_idx = n_frames // 2
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Cannot read frame {frame_idx} from {video_path}")
    return frame, frame_idx


def detect_blobs(frame: np.ndarray) -> list[tuple[float, float]]:
    """Detect dark dots; return list of (x, y) pixel centroids."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    _, binary = cv2.threshold(gray, DARK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    params = cv2.SimpleBlobDetector_Params()
    params.filterByColor = True
    params.blobColor = 255  # detecting white blobs in the inverted binary image
    params.filterByArea = True
    params.minArea = BLOB_MIN_AREA
    params.maxArea = BLOB_MAX_AREA
    params.filterByCircularity = True
    params.minCircularity = BLOB_MIN_CIRCULARITY
    params.filterByConvexity = False
    params.filterByInertia = False
    detector = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(cleaned)
    # Sort top-to-bottom, left-to-right for predictable iteration
    pts = sorted(((kp.pt[0], kp.pt[1]) for kp in keypoints), key=lambda p: (p[1], p[0]))
    return pts


def _to_bgr(frame: np.ndarray) -> np.ndarray:
    return frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)


def manual_id_assignment(
    frame: np.ndarray,
    blobs: list[tuple[float, float]],
    cam_label: str,
) -> dict[int, tuple[float, float]]:
    """Walk the user through assigning a CAD marker_id to each detected blob.

    Image stays open in a window while the user types marker_ids in the
    terminal. Per-blob options:
        <integer 1-41> = assign this marker_id
        s = skip this blob (false positive / unidentifiable)
        b = back up to previous blob
        q = quit (discard all assignments for this camera)
    """
    print(f"\n=== {cam_label}: assigning {len(blobs)} blobs to marker IDs ===")
    print("Per blob: type marker_id (1-41), 's' to skip, 'b' to go back, 'q' to quit.\n")

    win = f"{cam_label} - dot identification (terminal: type marker_id)"
    correspondences: dict[int, tuple[float, float]] = {}
    blob_to_marker: dict[int, int] = {}  # blob_idx -> marker_id (for back-up)
    i = 0
    while i < len(blobs):
        cx, cy = blobs[i]
        annotated = _to_bgr(frame)
        for j, (bx, by) in enumerate(blobs):
            if j == i:
                cv2.circle(annotated, (int(bx), int(by)), 16, (0, 0, 255), 3)  # red ring around current
            elif j in blob_to_marker:
                cv2.circle(annotated, (int(bx), int(by)), 10, (255, 200, 0), 2)
                cv2.putText(annotated, str(blob_to_marker[j]),
                            (int(bx) + 10, int(by) + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)
            else:
                cv2.circle(annotated, (int(bx), int(by)), 8, (0, 200, 0), 1)
        cv2.putText(annotated, f"{cam_label}  blob {i+1}/{len(blobs)}  assigned: {len(correspondences)}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow(win, annotated)
        cv2.waitKey(1)

        try:
            user_input = input(f"  Blob {i+1}/{len(blobs)} at ({cx:.0f},{cy:.0f}) -> marker_id: ").strip().lower()
        except EOFError:
            user_input = "q"
        if user_input == "s":
            i += 1
            continue
        if user_input == "b":
            if i == 0:
                print("    already at first blob")
                continue
            i -= 1
            # remove the previous blob's assignment if any
            if i in blob_to_marker:
                old_mid = blob_to_marker.pop(i)
                correspondences.pop(old_mid, None)
            continue
        if user_input == "q":
            cv2.destroyWindow(win)
            return {}
        try:
            marker_id = int(user_input)
        except ValueError:
            print("    invalid; try again")
            continue
        if not (1 <= marker_id <= 41):
            print("    out of range (1-41); try again")
            continue
        if marker_id in correspondences:
            print(f"    marker {marker_id} was already assigned; overwriting")
            # remove the older blob -> marker mapping
            for old_blob, old_mid in list(blob_to_marker.items()):
                if old_mid == marker_id:
                    blob_to_marker.pop(old_blob)
        correspondences[marker_id] = (cx, cy)
        blob_to_marker[i] = marker_id
        i += 1
    cv2.destroyWindow(win)
    return correspondences


def initial_camera_matrix(image_size: tuple[int, int], refractive_index: float = 1.0) -> np.ndarray:
    """Initial K. Effective underwater focal length = lens_focal * fluid_n.

    For underwater calibration through a flat acrylic interface, the
    apparent magnification scales with the fluid's refractive index.
    Pre-multiplying focal length by n gives an initial guess close to
    the optimum, so a strict CALIB_FIX_FOCAL_LENGTH solve converges to
    physically meaningful extrinsics.
    """
    w, h = image_size
    f_px = (LENS_FOCAL_MM / PIXEL_SIZE_MM) * refractive_index
    return np.array([[f_px, 0,    w / 2],
                     [0,    f_px, h / 2],
                     [0,    0,    1   ]], dtype=np.float64)


def load_correspondences(path: Path) -> tuple[dict[int, tuple[float, float]], dict[int, tuple[float, float]], int | None]:
    """Load correspondences from a previously-saved JSON file."""
    data = json.loads(path.read_text())
    cam0 = {int(k): (float(v[0]), float(v[1])) for k, v in data["cam0"].items()}
    cam1 = {int(k): (float(v[0]), float(v[1])) for k, v in data["cam1"].items()}
    frame_idx = data.get("frame_index")
    return cam0, cam1, frame_idx


def save_correspondences(
    path: Path,
    cam0_corr: dict[int, tuple[float, float]],
    cam1_corr: dict[int, tuple[float, float]],
    cam0_video: Path,
    cam1_video: Path,
    frame_idx: int,
) -> None:
    """Save correspondences to JSON so a subsequent crash doesn't lose them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cam0_video": str(cam0_video),
        "cam1_video": str(cam1_video),
        "frame_index": frame_idx,
        "cam0": {str(mid): [float(x), float(y)] for mid, (x, y) in cam0_corr.items()},
        "cam1": {str(mid): [float(x), float(y)] for mid, (x, y) in cam1_corr.items()},
    }
    path.write_text(json.dumps(payload, indent=2))
    print(f"Saved correspondences to {path}")


def interactive_edit(
    frame: np.ndarray,
    correspondences: dict[int, tuple[float, float]],
    cam_label: str,
) -> dict[int, tuple[float, float]] | None:
    """Open an interactive editor to add, modify, or delete marker assignments.

    Click on empty space to add a marker (terminal prompts for marker_id).
    Click near an existing marker to edit/delete it.
    Press SPACE to commit changes. Press ESC to cancel.
    Returns updated correspondences, or None if cancelled.
    """
    print(f"\n=== {cam_label}: editing correspondences ===")
    print(f"  Loaded {len(correspondences)} markers; missing: {sorted(set(range(1, 42)) - set(correspondences.keys()))}")
    print("  Click on an unmarked dot to add it. Click on an existing marker to edit/delete.")
    print("  Press SPACE in the image window to commit, ESC to cancel.\n")

    correspondences = dict(correspondences)
    win = f"{cam_label} - edit (SPACE=done, ESC=cancel)"
    last_click: list = [None]

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            last_click[0] = (x, y)

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)

    while True:
        annotated = _to_bgr(frame)
        for mid, (x, y) in correspondences.items():
            cv2.circle(annotated, (int(x), int(y)), 10, (255, 200, 0), 2)
            cv2.putText(annotated, str(mid), (int(x) + 12, int(y) + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)
        missing = sorted(set(range(1, 42)) - set(correspondences.keys()))
        cv2.putText(annotated,
                    f"{cam_label}  {len(correspondences)}/41 markers  missing: {missing}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(annotated, "click=add/edit  SPACE=done  ESC=cancel",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.imshow(win, annotated)
        key = cv2.waitKey(50) & 0xFF

        if key == 27:  # ESC
            cv2.destroyWindow(win)
            return None
        if key == ord(" "):
            cv2.destroyWindow(win)
            return correspondences

        if last_click[0] is not None:
            cx, cy = last_click[0]
            last_click[0] = None
            # Find nearest existing marker
            nearest_mid = None
            nearest_dist = float("inf")
            for mid, (mx, my) in correspondences.items():
                d = ((cx - mx) ** 2 + (cy - my) ** 2) ** 0.5
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_mid = mid

            if nearest_mid is not None and nearest_dist < 20:
                user_input = input(f"  marker {nearest_mid} at ({correspondences[nearest_mid][0]:.0f}, {correspondences[nearest_mid][1]:.0f}) - new id (or 'd' to delete, ENTER to keep): ").strip().lower()
                if user_input == "d":
                    del correspondences[nearest_mid]
                    print(f"    deleted marker {nearest_mid}")
                elif user_input == "":
                    pass
                else:
                    try:
                        new_id = int(user_input)
                        if 1 <= new_id <= 41:
                            xy = correspondences.pop(nearest_mid)
                            correspondences[new_id] = xy
                            print(f"    relabeled {nearest_mid} -> {new_id}")
                        else:
                            print("    out of range; no change")
                    except ValueError:
                        print("    invalid; no change")
            else:
                user_input = input(f"  add marker at ({cx},{cy}) - id (1-41, or ENTER to skip): ").strip()
                if not user_input:
                    continue
                try:
                    new_id = int(user_input)
                    if 1 <= new_id <= 41:
                        if new_id in correspondences:
                            print(f"    marker {new_id} already exists; overwriting")
                        correspondences[new_id] = (float(cx), float(cy))
                        print(f"    added marker {new_id} at ({cx},{cy})")
                    else:
                        print("    out of range; not added")
                except ValueError:
                    print("    invalid; not added")


def calibrate_camera(
    markers_xyz: dict[int, np.ndarray],
    correspondences: dict[int, tuple[float, float]],
    image_size: tuple[int, int],
    refractive_index: float = 1.0,
) -> dict:
    """Run cv2.calibrateCamera with the given correspondences."""
    common_ids = sorted(set(markers_xyz.keys()) & set(correspondences.keys()))
    if len(common_ids) < 6:
        raise RuntimeError(f"Only {len(common_ids)} correspondences; need 6+")
    obj_pts = np.array([markers_xyz[mid] for mid in common_ids], dtype=np.float32).reshape(-1, 1, 3)
    img_pts = np.array([correspondences[mid] for mid in common_ids], dtype=np.float32).reshape(-1, 1, 2)
    K_init = initial_camera_matrix(image_size, refractive_index)
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objectPoints=[obj_pts],
        imagePoints=[img_pts],
        imageSize=image_size,
        cameraMatrix=K_init,
        distCoeffs=None,
        flags=CALIB_FLAGS,
    )
    return {
        "K": K, "dist": dist, "rvec": rvecs[0], "tvec": tvecs[0],
        "reprojection_rms_px": float(rms),
        "common_ids": common_ids,
    }


def camera_position_in_world(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """Camera optical center expressed in the calibration-object frame."""
    R, _ = cv2.Rodrigues(rvec)
    return (-R.T @ tvec).ravel()


def triangulate(
    K0, dist0, rvec0, tvec0,
    K1, dist1, rvec1, tvec1,
    uv0, uv1,
) -> np.ndarray:
    """Triangulate one 3D point from two camera observations (returns mm)."""
    pts0 = cv2.undistortPoints(np.array([[uv0]], dtype=np.float32), K0, dist0, P=K0)
    pts1 = cv2.undistortPoints(np.array([[uv1]], dtype=np.float32), K1, dist1, P=K1)
    R0, _ = cv2.Rodrigues(rvec0)
    R1, _ = cv2.Rodrigues(rvec1)
    P0 = K0 @ np.hstack([R0, tvec0.reshape(3, 1)])
    P1 = K1 @ np.hstack([R1, tvec1.reshape(3, 1)])
    pt_4d = cv2.triangulatePoints(P0, P1, pts0[0].T, pts1[0].T)
    return (pt_4d[:3] / pt_4d[3]).ravel()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cam0_video", type=Path)
    ap.add_argument("cam1_video", type=Path)
    ap.add_argument("--markers", type=Path, required=True,
                    help="CSV with marker_id,X,Y,Z + cam0/cam1/optical_axis rows")
    ap.add_argument("--frame", type=int, default=-1,
                    help="Frame index to use (default: middle)")
    ap.add_argument("--output", type=Path, default=None,
                    help="Output JSON path (default: outputs/calib/stereo_calib_<label>.json)")
    ap.add_argument("--load", type=Path, default=None,
                    help="Load correspondences from a previously-saved JSON instead of detecting+assigning")
    ap.add_argument("--edit", action="store_true",
                    help="Open the interactive editor (after loading or detecting) to add/modify markers")
    args = ap.parse_args()

    # ---- Load inputs ----
    print(f"Loading markers from {args.markers}")
    markers_xyz, cameras_cad = parse_markers_csv(args.markers)
    print(f"  {len(markers_xyz)} markers, {len(cameras_cad)} camera reference points")

    for required in ("cam0", "cam1", "cam0_optical_axis", "cam1_optical_axis"):
        if required not in cameras_cad:
            raise RuntimeError(f"Missing '{required}' row in markers.csv")

    cam0_spec = CameraSpec(cameras_cad["cam0"], cameras_cad["cam0_optical_axis"])
    cam1_spec = CameraSpec(cameras_cad["cam1"], cameras_cad["cam1_optical_axis"])
    print(f"  cam0 CAD EPP: ({cam0_spec.epp[0]:.2f}, {cam0_spec.epp[1]:.2f}, {cam0_spec.epp[2]:.2f})")
    print(f"  cam1 CAD EPP: ({cam1_spec.epp[0]:.2f}, {cam1_spec.epp[1]:.2f}, {cam1_spec.epp[2]:.2f})")

    # ---- Extract frames ----
    # If loading, use the saved frame_index unless overridden
    requested_frame = args.frame
    if args.load is not None:
        loaded_cam0, loaded_cam1, loaded_frame = load_correspondences(args.load)
        if requested_frame < 0 and loaded_frame is not None:
            requested_frame = loaded_frame
            print(f"  Using saved frame_index={loaded_frame}")
    cam0_frame, cam0_frame_idx = extract_frame(args.cam0_video, requested_frame)
    cam1_frame, cam1_frame_idx = extract_frame(args.cam1_video, requested_frame)
    h, w = cam0_frame.shape[:2]
    print(f"  cam0 frame {cam0_frame_idx}: {w}x{h}")
    print(f"  cam1 frame {cam1_frame_idx}: {w}x{h}")

    if args.load is not None:
        # ---- Load correspondences from JSON ----
        cam0_corr = loaded_cam0
        cam1_corr = loaded_cam1
        print(f"  Loaded cam0={len(cam0_corr)} markers, cam1={len(cam1_corr)} markers from {args.load}")
    else:
        # ---- Detect blobs + manually assign ----
        cam0_blobs = detect_blobs(cam0_frame)
        cam1_blobs = detect_blobs(cam1_frame)
        print(f"  cam0: detected {len(cam0_blobs)} blobs")
        print(f"  cam1: detected {len(cam1_blobs)} blobs")
        if len(cam0_blobs) < 6 or len(cam1_blobs) < 6:
            print("ERROR: too few blobs detected. Adjust DARK_THRESHOLD or BLOB_MIN_AREA in this script.")
            sys.exit(1)
        cam0_corr = manual_id_assignment(cam0_frame, cam0_blobs, "cam0")
        if not cam0_corr:
            print("Aborted by user"); sys.exit(1)
        cam1_corr = manual_id_assignment(cam1_frame, cam1_blobs, "cam1")
        if not cam1_corr:
            print("Aborted by user"); sys.exit(1)

    # ---- Optional interactive editor (--edit) ----
    if args.edit:
        edited = interactive_edit(cam0_frame, cam0_corr, "cam0")
        if edited is None:
            print("cam0 edit cancelled; aborting"); sys.exit(1)
        cam0_corr = edited
        edited = interactive_edit(cam1_frame, cam1_corr, "cam1")
        if edited is None:
            print("cam1 edit cancelled; aborting"); sys.exit(1)
        cam1_corr = edited

    print(f"\nFinal: cam0={len(cam0_corr)} markers, cam1={len(cam1_corr)} markers")

    # ---- Save correspondences NOW (before calibration) so a crash here is recoverable ----
    fluid_label = args.cam0_video.stem.split("_")[1] if len(args.cam0_video.stem.split("_")) > 1 else "unknown"
    ts_label = "_".join(args.cam0_video.stem.split("_")[2:-1]) or "0"
    corr_path = Path("outputs/calib") / f"correspondences_{fluid_label}_{ts_label}.json"
    save_correspondences(corr_path, cam0_corr, cam1_corr, args.cam0_video, args.cam1_video, cam0_frame_idx)

    # ---- Per-camera calibration (refractive index from fluid label) ----
    refractive_index = FLUID_REFRACTIVE_INDICES.get(fluid_label, 1.333)
    print(f"\nRunning per-camera calibration (fluid={fluid_label}, n={refractive_index})...")
    cam0_calib = calibrate_camera(markers_xyz, cam0_corr, (w, h), refractive_index)
    cam1_calib = calibrate_camera(markers_xyz, cam1_corr, (w, h), refractive_index)
    print(f"  cam0: reprojection RMS = {cam0_calib['reprojection_rms_px']:.3f} px ({len(cam0_calib['common_ids'])} markers)")
    print(f"  cam1: reprojection RMS = {cam1_calib['reprojection_rms_px']:.3f} px ({len(cam1_calib['common_ids'])} markers)")

    # ---- 3D triangulation validation ----
    common_ids = sorted(set(cam0_corr.keys()) & set(cam1_corr.keys()))
    print(f"\n3D triangulation validation ({len(common_ids)} markers visible to both cameras):")
    if len(common_ids) < 3:
        print("  WARNING: too few common markers for meaningful validation")
        triangulation_errors = np.array([])
    else:
        triangulation_errors = []
        for mid in common_ids:
            true_xyz = markers_xyz[mid]
            tri = triangulate(
                cam0_calib["K"], cam0_calib["dist"], cam0_calib["rvec"], cam0_calib["tvec"],
                cam1_calib["K"], cam1_calib["dist"], cam1_calib["rvec"], cam1_calib["tvec"],
                cam0_corr[mid], cam1_corr[mid],
            )
            triangulation_errors.append(float(np.linalg.norm(tri - true_xyz)))
        triangulation_errors = np.array(triangulation_errors)
        passed = "PASS" if np.median(triangulation_errors) < VALIDATION_3D_TOLERANCE_MM else "FAIL"
        print(f"  median: {np.median(triangulation_errors):.3f} mm   [{passed}, threshold {VALIDATION_3D_TOLERANCE_MM} mm]")
        print(f"  mean:   {np.mean(triangulation_errors):.3f} mm")
        print(f"  max:    {np.max(triangulation_errors):.3f} mm")

    # ---- Camera position cross-check ----
    cam0_pos_calib = camera_position_in_world(cam0_calib["rvec"], cam0_calib["tvec"])
    cam1_pos_calib = camera_position_in_world(cam1_calib["rvec"], cam1_calib["tvec"])
    cam0_disc = float(np.linalg.norm(cam0_pos_calib - cam0_spec.epp))
    cam1_disc = float(np.linalg.norm(cam1_pos_calib - cam1_spec.epp))
    print(f"\nCamera position cross-check (calibration vs CAD EPP):")
    cam0_status = "PASS" if cam0_disc < VALIDATION_EPP_TOLERANCE_MM else "FAIL"
    cam1_status = "PASS" if cam1_disc < VALIDATION_EPP_TOLERANCE_MM else "FAIL"
    print(f"  cam0:")
    print(f"    CAD EPP:    ({cam0_spec.epp[0]:.2f}, {cam0_spec.epp[1]:.2f}, {cam0_spec.epp[2]:.2f}) mm")
    print(f"    Calibrated: ({cam0_pos_calib[0]:.2f}, {cam0_pos_calib[1]:.2f}, {cam0_pos_calib[2]:.2f}) mm")
    print(f"    Discrepancy: {cam0_disc:.2f} mm   [{cam0_status}, threshold {VALIDATION_EPP_TOLERANCE_MM} mm]")
    print(f"  cam1:")
    print(f"    CAD EPP:    ({cam1_spec.epp[0]:.2f}, {cam1_spec.epp[1]:.2f}, {cam1_spec.epp[2]:.2f}) mm")
    print(f"    Calibrated: ({cam1_pos_calib[0]:.2f}, {cam1_pos_calib[1]:.2f}, {cam1_pos_calib[2]:.2f}) mm")
    print(f"    Discrepancy: {cam1_disc:.2f} mm   [{cam1_status}, threshold {VALIDATION_EPP_TOLERANCE_MM} mm]")

    # ---- Save calibration JSON (fluid_label already derived above) ----
    out_path = args.output or Path("outputs/calib") / f"stereo_calib_{fluid_label}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def cam_dict(calib, spec, pos_calib, discrepancy, frame_idx):
        return {
            "K": calib["K"].tolist(),
            "dist": calib["dist"].tolist(),
            "rvec": calib["rvec"].tolist(),
            "tvec": calib["tvec"].tolist(),
            "reprojection_rms_px": calib["reprojection_rms_px"],
            "n_correspondences": len(calib["common_ids"]),
            "marker_ids_used": calib["common_ids"],
            "calibrated_position_mm": pos_calib.tolist(),
            "cad_epp_mm": spec.epp.tolist(),
            "discrepancy_mm": discrepancy,
            "frame_index_used": frame_idx,
        }

    output = {
        "fluid_label": fluid_label,
        "lens_epp_offset_mm": LENS_EPP_FROM_FRONT_FACE_MM,
        "image_size_wh": [w, h],
        "cam0": cam_dict(cam0_calib, cam0_spec, cam0_pos_calib, cam0_disc, cam0_frame_idx),
        "cam1": cam_dict(cam1_calib, cam1_spec, cam1_pos_calib, cam1_disc, cam1_frame_idx),
        "validation": {
            "n_common_markers": len(common_ids),
            "common_marker_ids": common_ids,
            "triangulation_error_mm": {
                "median": float(np.median(triangulation_errors)) if len(triangulation_errors) else None,
                "mean": float(np.mean(triangulation_errors)) if len(triangulation_errors) else None,
                "max": float(np.max(triangulation_errors)) if len(triangulation_errors) else None,
                "per_marker": {str(mid): float(e) for mid, e in zip(common_ids, triangulation_errors)} if len(triangulation_errors) else {},
            },
        },
    }
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
