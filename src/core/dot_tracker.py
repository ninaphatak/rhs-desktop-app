"""
Dot Tracker - OpenCV-based dot detection with persistent ID tracking

Purpose: Detect black dots on white valve using grayscale thresholding (automatic mode)
         or user-provided seed positions (manual mode), maintain consistent dot IDs
         across frames for displacement tracking.

Modes:
- Automatic: Global thresholding, detects all dots automatically
- Manual: User clicks to select dots, positions used directly, frame-to-frame tracking

Input:
- Frame (numpy array, grayscale)
- Mode: "automatic" or "manual"
- Threshold value (0-255, dots darker than this) - automatic mode only
- Min/max dot area (filter noise and large blobs)

Output:
{
    "timestamp": float,
    "dots": [
        {"id": 0, "x": 523, "y": 412, "area": 156, "dx": 0, "dy": 0, "lost": False},
        {"id": 1, "x": 891, "y": 398, "area": 142, "dx": 5, "dy": -2, "lost": True},
    ],
    "dot_count": int,
    "binary_mask": numpy.ndarray,  # For debugging/tuning UI
}

Class Structure:
    DotTracker
    │
    ├── Methods:
    │   ├── detect(frame) → dict             # Find dots in frame
    │   ├── set_mode(mode: str)              # Switch between automatic/manual
    │   ├── add_manual_seed(x, y, radius)    # Add manual dot (manual mode)
    │   ├── remove_manual_seed(seed_id)      # Remove manual dot
    │   ├── clear_manual_seeds()             # Clear all manual dots
    │   ├── annotate_frame(frame, dots) → ndarray  # Draw circles on dots
    │   ├── set_threshold(value: int)        # Adjust threshold (automatic mode)
    │   ├── set_area_range(min, max)         # Adjust size filter
    │   ├── set_reference()                  # Set current positions as reference
    │   ├── calculate_displacement(dots, reference) → list
    │   └── reset()                          # Clear ID continuity
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrackedDot:
    """Represents a single tracked dot with persistent ID."""

    id: int
    x: int
    y: int
    area: float
    ref_x: Optional[int] = None
    ref_y: Optional[int] = None


class DotTracker:
    """
    OpenCV-based dot detector with persistent ID tracking.

    Detects black dots on white/light background using thresholding.
    Maintains consistent dot IDs across frames using nearest-neighbor matching.

    Usage:
        tracker = DotTracker()
        result = tracker.detect(grayscale_frame)
        annotated = tracker.annotate_frame(frame, result["dots"])

        # Set reference for displacement calculation
        tracker.set_reference()

        # Later frames will show displacement from reference
        result = tracker.detect(new_frame)
        # result["dots"][0]["dx"], ["dy"] show displacement
    """

    def __init__(
        self,
        mode: str = "automatic",
        threshold: int = 50,
        min_area: int = 30,
        max_area: int = 500,
        max_displacement: int = 100,
        manual_search_radius: int = 100,
    ):
        """
        Initialize tracker.

        Args:
            mode: Detection mode - "automatic" or "manual"
            threshold: Binary threshold (0-255). Pixels darker than this are "dots"
            min_area: Minimum contour area in pixels
            max_area: Maximum contour area in pixels
            max_displacement: Max pixels a dot can move between frames for ID matching
            manual_search_radius: Search radius for manual tracking (pixels)

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in ("automatic", "manual"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'automatic' or 'manual'")

        self.mode = mode
        self.threshold = threshold
        self.min_area = min_area
        self.max_area = max_area
        self.max_displacement = max_displacement
        self.manual_search_radius = manual_search_radius

        # State for ID persistence
        self._previous_dots: list[TrackedDot] = []
        self._next_id = 0

        # Reference positions for displacement calculation
        self._reference_positions: dict[int, tuple[int, int]] = {}

        # Manual mode: user-provided seed positions
        self._manual_seeds: dict[
            int, dict
        ] = {}  # {id: {"x": int, "y": int, "radius": float}}
        self._manual_seeds_changed = False
        self._lost_dot_frames: dict[int, int] = {}  # Track lost dots: {id: frames_lost}

    def detect(self, frame: np.ndarray) -> dict:
        """
        Detect dots in frame and assign persistent IDs.

        Args:
            frame: Grayscale numpy array (uint8)

        Returns:
            Dict with timestamp, dots list, dot_count, and binary_mask
        """
        timestamp = time.time()

        # Validate input
        if frame is None or frame.size == 0:
            return self._empty_result(timestamp)

        # Ensure grayscale
        if len(frame.shape) == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Dispatch to mode-specific detection
        if self.mode == "automatic":
            return self._detect_automatic(frame, timestamp)
        else:  # manual mode
            return self._detect_manual(frame, timestamp)

    def _detect_automatic(self, frame: np.ndarray, timestamp: float) -> dict:
        """
        Automatic detection using global thresholding.

        Args:
            frame: Grayscale frame
            timestamp: Frame timestamp

        Returns:
            Detection result dict
        """
        # Step 1: Threshold (black dots on white background → THRESH_BINARY_INV)
        _, binary = cv2.threshold(frame, self.threshold, 255, cv2.THRESH_BINARY_INV)

        # Step 2: Find contours
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Step 3: Filter contours by area and extract centroids
        raw_dots = []
        for contour in contours:
            area = cv2.contourArea(contour)

            if self.min_area < area < self.max_area:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    raw_dots.append(
                        {
                            "x": cx,
                            "y": cy,
                            "area": area,
                        }
                    )

        # Step 4: Assign persistent IDs
        tracked_dots = self._assign_ids(raw_dots)

        # Step 5: Calculate displacement from reference
        dots_with_displacement = self._add_displacement(tracked_dots)

        # Update state for next frame
        self._previous_dots = tracked_dots

        return {
            "timestamp": timestamp,
            "dots": dots_with_displacement,
            "dot_count": len(tracked_dots),
            "binary_mask": binary,
        }

    def _track_dot_in_roi(
        self, frame: np.ndarray, prev_x: int, prev_y: int
    ) -> tuple[int, int]:
        """
        Track a dot by computing intensity-weighted centroid in a small ROI.

        Searches a window around the previous position and finds the most
        prominent feature using intensity weighting. Auto-detects whether
        the dot is bright-on-dark or dark-on-light.

        Args:
            frame: Grayscale frame (uint8)
            prev_x: Previous dot X coordinate
            prev_y: Previous dot Y coordinate

        Returns:
            (x, y) tracked position, or (prev_x, prev_y) if no feature found
        """
        r = self.manual_search_radius
        h, w = frame.shape[:2]

        # Clamp ROI to frame bounds
        x0 = max(0, prev_x - r)
        y0 = max(0, prev_y - r)
        x1 = min(w, prev_x + r)
        y1 = min(h, prev_y + r)

        roi = frame[y0:y1, x0:x1].astype(np.float64)
        if roi.size == 0:
            return prev_x, prev_y

        # Check if there's enough contrast in the ROI to track
        roi_min = float(np.min(roi))
        roi_max = float(np.max(roi))
        if (roi_max - roi_min) < 15:
            return prev_x, prev_y

        # Background is the edge intensity (dot is interior)
        edge_vals = np.concatenate([roi[0, :], roi[-1, :], roi[:, 0], roi[:, -1]])
        background = float(np.mean(edge_vals))

        # Weight = |pixel - background|^2, emphasizes dot core
        weights = (roi - background) ** 2

        total = np.sum(weights)
        if total == 0:
            return prev_x, prev_y

        # Weighted centroid in ROI coordinates
        ys, xs = np.mgrid[0 : roi.shape[0], 0 : roi.shape[1]]
        cx = np.sum(xs * weights) / total
        cy = np.sum(ys * weights) / total

        # Convert back to frame coordinates
        tracked_x = int(round(cx + x0))
        tracked_y = int(round(cy + y0))

        return tracked_x, tracked_y

    def _detect_manual(self, frame: np.ndarray, timestamp: float) -> dict:
        """
        Manual detection using user-provided seed positions with frame-to-frame tracking.

        First frame: uses seed positions directly.
        Subsequent frames: tracks each dot by searching near its previous position.

        Args:
            frame: Grayscale frame
            timestamp: Frame timestamp

        Returns:
            Detection result dict with "lost" field added to dots
        """
        raw_dots = []

        if not self._previous_dots:
            # First frame: use seed positions directly
            for seed_id, seed in self._manual_seeds.items():
                raw_dots.append(
                    {
                        "x": seed["x"],
                        "y": seed["y"],
                        "area": 78.5,  # Fixed area (pi * 5^2) for display
                    }
                )
        else:
            # Subsequent frames: track from previous positions
            for prev_dot in self._previous_dots:
                tx, ty = self._track_dot_in_roi(frame, prev_dot.x, prev_dot.y)
                raw_dots.append(
                    {
                        "x": tx,
                        "y": ty,
                        "area": 78.5,
                    }
                )

        # Assign persistent IDs
        tracked_dots = self._assign_ids(raw_dots)

        # Calculate displacement from reference
        dots_with_displacement = self._add_displacement(tracked_dots)

        # Update state for next frame
        self._previous_dots = tracked_dots

        # Create binary mask (empty for manual mode)
        binary = np.zeros(frame.shape, dtype=np.uint8)

        return {
            "timestamp": timestamp,
            "dots": dots_with_displacement,
            "dot_count": len(tracked_dots),
            "binary_mask": binary,
        }

    def _handle_lost_dots(self, tracked_dots: list[TrackedDot]) -> list[TrackedDot]:
        """
        Track lost dots and remove them after threshold.

        A dot is "lost" if it couldn't be refined in the current frame.
        Keep lost dots for up to 10 frames, then remove.

        Args:
            tracked_dots: Dots successfully tracked in current frame

        Returns:
            Tracked dots with lost dots appended
        """
        MAX_LOST_FRAMES = 10

        tracked_ids = {d.id for d in tracked_dots}
        result = list(tracked_dots)

        # Check which previous dots are now lost
        for prev_dot in self._previous_dots:
            if prev_dot.id not in tracked_ids:
                # Dot is lost
                if prev_dot.id not in self._lost_dot_frames:
                    self._lost_dot_frames[prev_dot.id] = 1
                else:
                    self._lost_dot_frames[prev_dot.id] += 1

                # Keep for up to MAX_LOST_FRAMES
                if self._lost_dot_frames[prev_dot.id] <= MAX_LOST_FRAMES:
                    # Use ref_x = -1 as a marker for lost dots
                    lost_dot = TrackedDot(
                        id=prev_dot.id,
                        x=prev_dot.x,
                        y=prev_dot.y,
                        area=prev_dot.area,
                        ref_x=-1,  # Marker for lost
                        ref_y=-1,
                    )
                    result.append(lost_dot)
                else:
                    # Remove from lost tracking
                    del self._lost_dot_frames[prev_dot.id]

        # Clear lost tracking for dots that were found
        for dot_id in tracked_ids:
            if dot_id in self._lost_dot_frames:
                del self._lost_dot_frames[dot_id]

        return result

    def _assign_ids(self, raw_dots: list[dict]) -> list[TrackedDot]:
        """
        Assign consistent IDs using nearest-neighbor matching.

        Strategy:
        1. For each new dot, find the closest previous dot within max_displacement
        2. If found, reuse that ID
        3. If not found, assign a new ID
        """
        if not self._previous_dots:
            # First frame: assign sequential IDs
            return [
                TrackedDot(
                    id=self._get_next_id(),
                    x=d["x"],
                    y=d["y"],
                    area=d["area"],
                )
                for d in raw_dots
            ]

        tracked = []
        used_prev_ids = set()

        # Sort by distance to nearest previous dot (assign closest matches first)
        def min_distance_to_prev(dot):
            return min(
                (self._distance(dot, p) for p in self._previous_dots),
                default=float("inf"),
            )

        sorted_dots = sorted(raw_dots, key=min_distance_to_prev)

        for dot in sorted_dots:
            best_match = None
            best_distance = float("inf")

            for prev in self._previous_dots:
                if prev.id in used_prev_ids:
                    continue

                dist = self._distance(dot, prev)
                if dist < best_distance and dist < self.max_displacement:
                    best_distance = dist
                    best_match = prev

            if best_match:
                # Reuse previous ID
                used_prev_ids.add(best_match.id)
                tracked.append(
                    TrackedDot(
                        id=best_match.id,
                        x=dot["x"],
                        y=dot["y"],
                        area=dot["area"],
                        ref_x=best_match.ref_x,
                        ref_y=best_match.ref_y,
                    )
                )
            else:
                # New dot: assign new ID
                tracked.append(
                    TrackedDot(
                        id=self._get_next_id(),
                        x=dot["x"],
                        y=dot["y"],
                        area=dot["area"],
                    )
                )

        return tracked

    def _distance(self, dot: dict, prev: TrackedDot) -> float:
        """Euclidean distance between dot positions."""
        return np.sqrt((dot["x"] - prev.x) ** 2 + (dot["y"] - prev.y) ** 2)

    def _get_next_id(self) -> int:
        """Get next available ID."""
        id = self._next_id
        self._next_id += 1
        return id

    def _add_displacement(self, dots: list[TrackedDot]) -> list[dict]:
        """Add displacement (dx, dy) from reference position and lost flag."""
        result = []
        for dot in dots:
            # Check if dot is lost (marked with ref_x = -1)
            is_lost = dot.ref_x == -1

            d = {
                "id": dot.id,
                "x": dot.x,
                "y": dot.y,
                "area": dot.area,
                "dx": 0,
                "dy": 0,
                "lost": is_lost,
            }

            if not is_lost and dot.id in self._reference_positions:
                ref_x, ref_y = self._reference_positions[dot.id]
                d["dx"] = dot.x - ref_x
                d["dy"] = dot.y - ref_y

            result.append(d)

        return result

    def set_mode(self, mode: str):
        """
        Set detection mode.

        Args:
            mode: "automatic" or "manual"

        Raises:
            ValueError: If mode is invalid
        """
        if mode not in ("automatic", "manual"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'automatic' or 'manual'")

        if mode != self.mode:
            logger.info(f"Switching tracker mode: {self.mode} → {mode}")
            self.mode = mode

            # Reset tracking state when switching modes
            self.reset()

    def add_manual_seed(self, x: int, y: int, radius: float) -> int:
        """
        Add a manual seed position for manual tracking mode.

        Args:
            x: Seed X coordinate (image space)
            y: Seed Y coordinate (image space)
            radius: Approximate dot radius (for display)

        Returns:
            Seed ID (which will become the dot ID)

        Example:
            >>> tracker = DotTracker(mode="manual")
            >>> seed_id = tracker.add_manual_seed(523, 412, 10.5)
            >>> print(f"Added seed #{seed_id}")
        """
        seed_id = self._get_next_id()
        self._manual_seeds[seed_id] = {
            "x": x,
            "y": y,
            "radius": radius,
        }
        self._manual_seeds_changed = True
        logger.info(f"Added manual seed #{seed_id} at ({x}, {y})")
        return seed_id

    def remove_manual_seed(self, seed_id: int):
        """
        Remove a manual seed by ID.

        Args:
            seed_id: ID of seed to remove
        """
        if seed_id in self._manual_seeds:
            del self._manual_seeds[seed_id]
            self._manual_seeds_changed = True
            logger.info(f"Removed manual seed #{seed_id}")

            # Also remove from reference positions if present
            if seed_id in self._reference_positions:
                del self._reference_positions[seed_id]

    def clear_manual_seeds(self):
        """Clear all manual seeds."""
        count = len(self._manual_seeds)
        self._manual_seeds.clear()
        self._manual_seeds_changed = True
        self._lost_dot_frames.clear()
        logger.info(f"Cleared {count} manual seeds")

    def get_manual_seeds(self) -> dict:
        """
        Get current manual seeds.

        Returns:
            Dict of {seed_id: {"x": int, "y": int, "radius": float}}
        """
        return dict(self._manual_seeds)

    def set_reference(self):
        """
        Set current dot positions as reference for displacement calculation.
        Call this when user clicks "Set Reference" button.
        """
        self._reference_positions = {
            dot.id: (dot.x, dot.y)
            for dot in self._previous_dots
            if dot.ref_x != -1  # Don't set reference for lost dots
        }
        logger.info(f"Reference set for {len(self._reference_positions)} dots")

    def clear_reference(self):
        """Clear reference positions."""
        self._reference_positions.clear()

    def annotate_frame(
        self,
        frame: np.ndarray,
        dots: list[dict],
        show_ids: bool = True,
        show_displacement: bool = True,
    ) -> np.ndarray:
        """
        Draw annotations on frame.

        Args:
            frame: Original frame (grayscale or BGR)
            dots: List of dot dicts from detect()
            show_ids: Draw ID numbers
            show_displacement: Draw displacement vectors

        Returns:
            Annotated BGR frame
        """
        # Convert to BGR if grayscale
        if len(frame.shape) == 2:
            annotated = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            annotated = frame.copy()

        for dot in dots:
            x, y = dot["x"], dot["y"]

            # Draw circle around dot
            cv2.circle(annotated, (x, y), 15, (0, 255, 0), 2)  # Green

            # Draw center point
            cv2.circle(annotated, (x, y), 3, (0, 0, 255), -1)  # Red filled

            if show_ids:
                label = f"#{dot['id']}"
                cv2.putText(
                    annotated,
                    label,
                    (x + 20, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 0),  # Cyan
                    2,
                )

            if show_displacement and (dot["dx"] != 0 or dot["dy"] != 0):
                dx, dy = dot["dx"], dot["dy"]

                # Arrow from reference to current
                ref_x = x - dx
                ref_y = y - dy
                cv2.arrowedLine(
                    annotated,
                    (ref_x, ref_y),
                    (x, y),
                    (0, 165, 255),  # Orange
                    2,
                    tipLength=0.3,
                )

                # Displacement text
                disp_label = f"d({dx},{dy})"
                cv2.putText(
                    annotated,
                    disp_label,
                    (x + 20, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 165, 0),  # Orange
                    1,
                )

        return annotated

    def set_threshold(self, value: int):
        """Set binary threshold (0-255)."""
        self.threshold = max(0, min(255, value))

    def set_area_range(self, min_area: int, max_area: int):
        """Set valid dot area range."""
        self.min_area = max(1, min_area)
        self.max_area = max(self.min_area + 1, max_area)

    def reset(self):
        """Reset tracker state (clears ID continuity and manual seeds)."""
        self._previous_dots.clear()
        self._next_id = 0
        self._reference_positions.clear()
        self._manual_seeds.clear()
        self._manual_seeds_changed = False
        self._lost_dot_frames.clear()

    def _empty_result(self, timestamp: float) -> dict:
        """Return empty result for invalid input."""
        return {
            "timestamp": timestamp,
            "dots": [],
            "dot_count": 0,
            "binary_mask": None,
        }

    def get_dot_by_id(self, dot_id: int) -> Optional[dict]:
        """Get most recent position of a dot by ID."""
        for dot in self._previous_dots:
            if dot.id == dot_id:
                return {
                    "id": dot.id,
                    "x": dot.x,
                    "y": dot.y,
                    "area": dot.area,
                }
        return None

    def calculate_strain_between_dots(
        self, dot_id_1: int, dot_id_2: int
    ) -> Optional[dict]:
        """
        Calculate strain between two dots.

        Strain = (L - L0) / L0 where L is current distance, L0 is reference.

        Returns:
            {
                "current_distance": float,
                "reference_distance": float,
                "strain": float,  # dimensionless
            }
            or None if reference not set or dots not found
        """
        if (
            dot_id_1 not in self._reference_positions
            or dot_id_2 not in self._reference_positions
        ):
            return None

        # Get current positions
        dot1 = self.get_dot_by_id(dot_id_1)
        dot2 = self.get_dot_by_id(dot_id_2)

        if not dot1 or not dot2:
            return None

        # Current distance
        L = np.sqrt((dot2["x"] - dot1["x"]) ** 2 + (dot2["y"] - dot1["y"]) ** 2)

        # Reference distance
        ref1 = self._reference_positions[dot_id_1]
        ref2 = self._reference_positions[dot_id_2]
        L0 = np.sqrt((ref2[0] - ref1[0]) ** 2 + (ref2[1] - ref1[1]) ** 2)

        if L0 == 0:
            return None

        strain = (L - L0) / L0

        return {
            "current_distance": L,
            "reference_distance": L0,
            "strain": strain,
        }
