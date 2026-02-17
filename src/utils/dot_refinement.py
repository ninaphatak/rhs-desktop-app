"""
OpenCV-based dot refinement for manual dot selection.

Purpose: Refine user click positions to precise dot boundaries using local thresholding.

Given a click position on the camera image, this module:
1. Extracts a small ROI (region of interest) around the click
2. Applies adaptive thresholding to handle varying brightness
3. Finds contours in the ROI
4. Selects the contour closest to the click point
5. Calculates centroid and area
6. Returns refined position in full-frame coordinates

This is used in manual dot selection mode where users click on dots and
OpenCV refines the click to the actual dot boundary.
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def refine_dot_at_click(
    frame: np.ndarray,
    click_x: int,
    click_y: int,
    search_radius: int = 30,
    min_area: int = 10,
    max_area: int = 500,
) -> Optional[dict]:
    """
    Refine a user click to the nearest dot boundary using local thresholding.

    Args:
        frame: Grayscale numpy array (H, W) or BGR array (H, W, 3)
        click_x: User click X coordinate in full frame
        click_y: User click Y coordinate in full frame
        search_radius: Search radius in pixels around click point
        min_area: Minimum contour area to consider as a dot
        max_area: Maximum contour area to consider as a dot

    Returns:
        Dict with refined position and properties:
        {
            "x": int,        # Refined centroid X in full-frame coords
            "y": int,        # Refined centroid Y in full-frame coords
            "radius": float, # Equivalent radius from area (sqrt(area/pi))
            "area": float,   # Contour area in pixels
        }

        Returns None if no valid dot found near click position.

    Example:
        >>> refined = refine_dot_at_click(frame, 523, 412)
        >>> if refined:
        ...     print(f"Dot at ({refined['x']}, {refined['y']})")
        ... else:
        ...     print("No dot found")
    """
    # Validate input
    if frame is None or frame.size == 0:
        logger.warning("refine_dot_at_click: Invalid frame (None or empty)")
        return None

    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    height, width = frame.shape

    # Clamp click coordinates to frame bounds
    click_x = max(0, min(width - 1, click_x))
    click_y = max(0, min(height - 1, click_y))

    # Define ROI bounds (clamp to frame)
    x_min = max(0, click_x - search_radius)
    x_max = min(width, click_x + search_radius)
    y_min = max(0, click_y - search_radius)
    y_max = min(height, click_y + search_radius)

    # Extract ROI
    roi = frame[y_min:y_max, x_min:x_max]

    if roi.size == 0:
        logger.warning(f"refine_dot_at_click: Empty ROI at ({click_x}, {click_y})")
        return None

    # Apply Otsu's thresholding in ROI
    # Black dots on white background → THRESH_BINARY_INV
    _, binary = cv2.threshold(
        roi,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # Find contours in ROI
    contours, _ = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None

    # Click position in ROI coordinates
    roi_click_x = click_x - x_min
    roi_click_y = click_y - y_min

    # Find contour closest to click point
    best_contour = None
    best_distance = float('inf')
    best_area = 0

    for contour in contours:
        area = cv2.contourArea(contour)

        # Filter by area
        if not (min_area < area < max_area):
            continue

        # Calculate centroid
        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue

        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]

        # Distance from click to centroid
        dist = np.sqrt((cx - roi_click_x)**2 + (cy - roi_click_y)**2)

        if dist < best_distance:
            best_distance = dist
            best_contour = contour
            best_area = area

    # No valid contour found
    if best_contour is None:
        return None

    # Calculate refined centroid in full-frame coordinates
    M = cv2.moments(best_contour)
    cx_roi = M["m10"] / M["m00"]
    cy_roi = M["m01"] / M["m00"]

    cx_full = int(cx_roi + x_min)
    cy_full = int(cy_roi + y_min)

    # Calculate equivalent radius (assuming circular dot)
    radius = np.sqrt(best_area / np.pi)

    return {
        "x": cx_full,
        "y": cy_full,
        "radius": float(radius),
        "area": float(best_area),
    }


def create_synthetic_dot_frame(
    width: int = 640,
    height: int = 480,
    dots: list[tuple[int, int, int]] = None,
    background_intensity: int = 200,
    dot_intensity: int = 50,
) -> np.ndarray:
    """
    Create a synthetic frame with black dots on white background for testing.

    Args:
        width: Frame width in pixels
        height: Frame height in pixels
        dots: List of (x, y, radius) tuples for dot positions
        background_intensity: Grayscale value for background (0-255)
        dot_intensity: Grayscale value for dots (0-255)

    Returns:
        Grayscale numpy array (height, width) with dots drawn

    Example:
        >>> frame = create_synthetic_dot_frame(
        ...     dots=[(100, 100, 10), (200, 150, 15)]
        ... )
        >>> refined = refine_dot_at_click(frame, 105, 98)
        >>> assert abs(refined['x'] - 100) < 2  # Within 2 pixels
    """
    if dots is None:
        dots = []

    # Create white background
    frame = np.full((height, width), background_intensity, dtype=np.uint8)

    # Draw black dots
    for x, y, radius in dots:
        cv2.circle(frame, (x, y), radius, dot_intensity, -1)

    return frame
