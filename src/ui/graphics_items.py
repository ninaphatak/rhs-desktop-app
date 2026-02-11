"""
Custom QGraphicsItem subclasses for manual dot selection UI.

This module provides custom graphics items for:
- DotGraphicsItem: Represents a tracked dot with ID label and optional displacement vector
- FrameGraphicsItem: Displays camera frame as a QPixmap with auto-scaling

These items are used in CameraPanel's QGraphicsView for interactive dot selection
and tracking visualization.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QFont, QPainter, QPixmap, QImage
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsTextItem,
    QGraphicsLineItem,
)
import numpy as np


class DotGraphicsItem(QGraphicsEllipseItem):
    """
    Custom graphics item for displaying a tracked dot.

    Features:
    - Circle at dot position
    - ID label
    - Draggable in SELECT mode
    - Displays displacement vector in TRACKING mode
    - Color-coded by state (normal, lost, reference)

    Signals are emitted via parent CameraPanel, not directly from this item.
    """

    def __init__(
        self,
        dot_id: int,
        x: int,
        y: int,
        radius: float = 15.0,
        parent=None,
    ):
        """
        Initialize dot graphics item.

        Args:
            dot_id: Dot ID (persistent across frames)
            x: Dot center X in image coordinates
            y: Dot center Y in image coordinates
            radius: Display radius in pixels (not the actual dot radius)
            parent: Parent QGraphicsItem
        """
        # Create ellipse centered at (x, y) with given radius
        super().__init__(
            x - radius,
            y - radius,
            radius * 2,
            radius * 2,
            parent
        )

        self.dot_id = dot_id
        self.center_x = x
        self.center_y = y
        self.display_radius = radius

        # State
        self.is_lost = False
        self.is_draggable = False
        self.displacement_vector = None  # (dx, dy) or None

        # Visual properties
        self._setup_appearance()

        # ID label
        self.label = QGraphicsTextItem(f"#{dot_id}", self)
        self.label.setDefaultTextColor(QColor(255, 255, 0))  # Yellow
        self.label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.label.setPos(x + radius + 5, y - radius - 5)

        # Displacement arrow (created when needed)
        self.arrow = None

    def _setup_appearance(self):
        """Setup visual appearance (colors, pen, brush)."""
        # Green circle for normal dots
        pen = QPen(QColor(0, 255, 0), 2)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # Transparent fill

        # Enable hover events if draggable
        self.setAcceptHoverEvents(True)

    def set_draggable(self, draggable: bool):
        """Enable/disable dragging."""
        self.is_draggable = draggable
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, draggable)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, draggable)

        # Update cursor
        if draggable:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_lost(self, lost: bool):
        """Mark dot as lost (changes color to orange)."""
        self.is_lost = lost

        if lost:
            pen = QPen(QColor(255, 165, 0), 2)  # Orange
            self.setPen(pen)
            self.label.setDefaultTextColor(QColor(255, 165, 0))
        else:
            pen = QPen(QColor(0, 255, 0), 2)  # Green
            self.setPen(pen)
            self.label.setDefaultTextColor(QColor(255, 255, 0))

    def update_position(self, x: int, y: int):
        """
        Update dot position (e.g., from tracking update).

        Args:
            x: New center X
            y: New center Y
        """
        self.center_x = x
        self.center_y = y

        # Update ellipse position
        r = self.display_radius
        self.setRect(x - r, y - r, r * 2, r * 2)

        # Update label position
        self.label.setPos(x + r + 5, y - r - 5)

        # Update arrow if exists
        if self.arrow and self.displacement_vector:
            self._update_arrow()

    def set_displacement(self, dx: int, dy: int):
        """
        Set displacement vector for visualization.

        Args:
            dx: Displacement in X
            dy: Displacement in Y
        """
        self.displacement_vector = (dx, dy)

        if dx == 0 and dy == 0:
            # No displacement, remove arrow
            if self.arrow:
                self.scene().removeItem(self.arrow)
                self.arrow = None
        else:
            # Create or update arrow
            self._update_arrow()

    def _update_arrow(self):
        """Create or update displacement arrow."""
        if not self.displacement_vector:
            return

        dx, dy = self.displacement_vector

        # Reference position (where dot was at t=0)
        ref_x = self.center_x - dx
        ref_y = self.center_y - dy

        # Remove old arrow
        if self.arrow:
            self.scene().removeItem(self.arrow)

        # Create arrow line
        self.arrow = QGraphicsLineItem(ref_x, ref_y, self.center_x, self.center_y)
        pen = QPen(QColor(0, 165, 255), 2)  # Orange
        self.arrow.setPen(pen)
        self.scene().addItem(self.arrow)

        # TODO: Add arrowhead (requires polygon item)

    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if self.is_draggable:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release after dragging."""
        if self.is_draggable:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

            # Notify parent of position change
            # Get new position from scene
            rect = self.rect()
            new_x = int(rect.center().x())
            new_y = int(rect.center().y())

            # Update internal state
            self.center_x = new_x
            self.center_y = new_y

            # Parent CameraPanel should connect to this event
            # via itemChange() or by polling after drag

        super().mouseReleaseEvent(event)


class FrameGraphicsItem(QGraphicsPixmapItem):
    """
    Custom graphics item for displaying camera frame.

    Holds the camera frame as a QPixmap and handles auto-scaling.
    """

    def __init__(self, parent=None):
        """Initialize frame graphics item."""
        super().__init__(parent)

        # Enable smooth transformation for better quality when scaled
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    def set_frame(self, frame: np.ndarray):
        """
        Update displayed frame.

        Args:
            frame: Numpy array (H, W) grayscale or (H, W, 3) BGR
        """
        # Convert numpy array to QPixmap
        pixmap = self._numpy_to_pixmap(frame)
        self.setPixmap(pixmap)

    def _numpy_to_pixmap(self, frame: np.ndarray) -> QPixmap:
        """
        Convert numpy array to QPixmap.

        Args:
            frame: Numpy array (H, W) or (H, W, 3)

        Returns:
            QPixmap
        """
        height, width = frame.shape[:2]

        if len(frame.shape) == 2:
            # Grayscale
            # Convert to RGB by stacking
            frame_rgb = np.stack([frame, frame, frame], axis=-1)
        elif frame.shape[2] == 3:
            # BGR to RGB
            frame_rgb = frame[:, :, ::-1].copy()
        else:
            raise ValueError(f"Unsupported frame shape: {frame.shape}")

        # Create QImage
        bytes_per_line = 3 * width
        qimage = QImage(
            frame_rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )

        # Convert to QPixmap
        return QPixmap.fromImage(qimage)
