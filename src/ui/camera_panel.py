"""
Camera Panel - Interactive camera feed display with manual dot selection.

Three-mode state machine:
1. VIEW_ONLY: Live camera feed, no interaction
2. SELECT_DOTS: User clicks to add/edit dots
3. TRACKING: Dots locked, frame-to-frame tracking active

Uses QGraphicsView for native coordinate transformation and easy overlay graphics.
"""

import logging
from enum import Enum
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGraphicsView,
    QGraphicsScene,
    QListWidget,
    QListWidgetItem,
    QComboBox,
)

from src.ui.graphics_items import DotGraphicsItem, FrameGraphicsItem

logger = logging.getLogger(__name__)


class ViewMode(Enum):
    """Camera panel interaction modes."""
    VIEW_ONLY = "view"
    SELECT_DOTS = "select"
    TRACKING = "tracking"


class CameraPanel(QWidget):
    """
    Camera feed display panel with interactive dot selection.

    Modes:
    - VIEW_ONLY: Display camera feed only
    - SELECT_DOTS: User can click to add dots, drag to adjust
    - TRACKING: Dots locked, tracking active, displacement vectors shown

    Signals:
        dot_added(x: int, y: int): User clicked to add dot at (x, y)
        dot_removed(dot_id: int): User removed dot
        dot_moved(dot_id: int, x: int, y: int): User dragged dot to new position
        mode_changed(mode: str): Mode changed
        tracking_started(): User started tracking
        reference_set(): User set reference position
    """

    # Signals
    dot_added = pyqtSignal(int, int)  # x, y in image coords
    dot_removed = pyqtSignal(int)  # dot ID
    dot_moved = pyqtSignal(int, int, int)  # dot ID, new x, new y
    mode_changed = pyqtSignal(str)  # mode name
    tracking_started = pyqtSignal()
    reference_set = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize camera panel."""
        super().__init__(parent)

        self.mode = ViewMode.VIEW_ONLY
        self.current_frame = None  # Cache current frame for refinement

        # Graphics scene and view
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(self.view.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)

        # Frame item (holds camera image)
        self.frame_item = FrameGraphicsItem()
        self.scene.addItem(self.frame_item)

        # Dot items (keyed by dot ID)
        self.dot_items: dict[int, DotGraphicsItem] = {}

        # UI
        self._setup_ui()
        self._connect_signals()

        logger.info("CameraPanel initialized")

    def _setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Top controls
        controls_layout = QHBoxLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["View Only", "Select Dots", "Tracking"])
        self.mode_combo.setCurrentIndex(0)
        controls_layout.addWidget(QLabel("Mode:"))
        controls_layout.addWidget(self.mode_combo)

        controls_layout.addStretch()

        self.set_reference_btn = QPushButton("Set Reference (t=0)")
        self.set_reference_btn.setEnabled(False)
        controls_layout.addWidget(self.set_reference_btn)

        layout.addLayout(controls_layout)

        # Graphics view
        layout.addWidget(self.view, stretch=1)

        # Bottom panel: dot list
        bottom_layout = QHBoxLayout()

        # Dot list
        dot_list_layout = QVBoxLayout()
        dot_list_layout.addWidget(QLabel("Selected Dots:"))

        self.dot_list = QListWidget()
        self.dot_list.setMaximumHeight(100)
        dot_list_layout.addWidget(self.dot_list)

        # Dot management buttons
        dot_buttons_layout = QHBoxLayout()
        self.remove_dot_btn = QPushButton("Remove Selected")
        self.remove_dot_btn.setEnabled(False)
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setEnabled(False)
        dot_buttons_layout.addWidget(self.remove_dot_btn)
        dot_buttons_layout.addWidget(self.clear_all_btn)
        dot_list_layout.addLayout(dot_buttons_layout)

        bottom_layout.addLayout(dot_list_layout)

        # FPS display
        self.fps_label = QLabel("FPS: --")
        bottom_layout.addWidget(self.fps_label)

        layout.addLayout(bottom_layout)

        self.setLayout(layout)

    def _connect_signals(self):
        """Connect internal signals."""
        self.mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        self.set_reference_btn.clicked.connect(self._on_set_reference)
        self.remove_dot_btn.clicked.connect(self._on_remove_dot)
        self.clear_all_btn.clicked.connect(self._on_clear_all)
        self.dot_list.itemSelectionChanged.connect(self._on_dot_selection_changed)

        # Scene click events
        self.view.mousePressEvent = self._on_view_mouse_press

    def _on_mode_combo_changed(self, index: int):
        """Handle mode combo box change."""
        mode_map = {
            0: ViewMode.VIEW_ONLY,
            1: ViewMode.SELECT_DOTS,
            2: ViewMode.TRACKING,
        }

        new_mode = mode_map[index]
        self.set_mode(new_mode)

    def set_mode(self, mode: ViewMode):
        """
        Set interaction mode.

        Args:
            mode: ViewMode enum value
        """
        if mode == self.mode:
            return

        logger.info(f"CameraPanel mode: {self.mode.value} → {mode.value}")
        self.mode = mode

        # Update UI based on mode
        if mode == ViewMode.VIEW_ONLY:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.set_reference_btn.setEnabled(False)
            self.clear_all_btn.setEnabled(False)
            self._set_all_dots_draggable(False)

        elif mode == ViewMode.SELECT_DOTS:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.set_reference_btn.setEnabled(False)
            self.clear_all_btn.setEnabled(True)
            self._set_all_dots_draggable(True)

        elif mode == ViewMode.TRACKING:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.set_reference_btn.setEnabled(True)
            self.clear_all_btn.setEnabled(False)
            self._set_all_dots_draggable(False)

            # Emit tracking started signal
            self.tracking_started.emit()

        # Emit mode changed signal
        self.mode_changed.emit(mode.value)

    def _set_all_dots_draggable(self, draggable: bool):
        """Enable/disable dragging for all dots."""
        for dot_item in self.dot_items.values():
            dot_item.set_draggable(draggable)

    def _on_view_mouse_press(self, event):
        """Handle mouse press in view (for adding dots in SELECT mode)."""
        # Call original mousePressEvent
        QGraphicsView.mousePressEvent(self.view, event)

        # Only handle clicks in SELECT_DOTS mode
        if self.mode != ViewMode.SELECT_DOTS:
            return

        # Get click position in scene coordinates
        scene_pos = self.view.mapToScene(event.pos())

        # Check if click is on an existing dot (for dragging)
        item = self.scene.itemAt(scene_pos, self.view.transform())
        if isinstance(item, DotGraphicsItem):
            # Clicking on existing dot - allow dragging
            return

        # Click on empty space - add new dot
        # Convert scene coords to image coords (they should be the same since we don't scale)
        x = int(scene_pos.x())
        y = int(scene_pos.y())

        # Validate click is within frame bounds
        if self.current_frame is not None:
            height, width = self.current_frame.shape[:2]
            if 0 <= x < width and 0 <= y < height:
                logger.debug(f"User clicked at ({x}, {y}) to add dot")
                self.dot_added.emit(x, y)

    def update_frame(self, frame_data: dict):
        """
        Update displayed frame.

        Args:
            frame_data: Dict with "frame" (numpy array) and "timestamp"
        """
        frame = frame_data.get("frame")
        if frame is None:
            return

        # Cache frame for refinement
        self.current_frame = frame

        # Update frame display
        self.frame_item.set_frame(frame)

        # Update FPS if available
        if "fps" in frame_data:
            self.fps_label.setText(f"FPS: {frame_data['fps']:.1f}")

        # Fit view to frame on first frame
        if self.scene.sceneRect().isEmpty():
            self.view.fitInView(self.frame_item, Qt.AspectRatioMode.KeepAspectRatio)

    def update_tracking(self, tracking_data: dict):
        """
        Update dot positions from tracking results.

        Args:
            tracking_data: Dict from DotTracker.detect() with "dots" list
        """
        if self.mode != ViewMode.TRACKING:
            return

        dots = tracking_data.get("dots", [])

        for dot in dots:
            dot_id = dot["id"]
            x = dot["x"]
            y = dot["y"]
            dx = dot.get("dx", 0)
            dy = dot.get("dy", 0)
            is_lost = dot.get("lost", False)

            if dot_id in self.dot_items:
                # Update existing dot
                dot_item = self.dot_items[dot_id]
                dot_item.update_position(x, y)
                dot_item.set_lost(is_lost)
                dot_item.set_displacement(dx, dy)

    def add_dot_visual(self, refined: dict, dot_id: int):
        """
        Add visual representation of a dot.

        Args:
            refined: Dict from refine_dot_at_click() with x, y, radius, area
            dot_id: Dot ID from tracker
        """
        x = refined["x"]
        y = refined["y"]
        radius = refined.get("radius", 15.0)

        # Create dot item
        dot_item = DotGraphicsItem(dot_id, x, y, radius)
        self.scene.addItem(dot_item)
        self.dot_items[dot_id] = dot_item

        # Set draggable if in SELECT mode
        if self.mode == ViewMode.SELECT_DOTS:
            dot_item.set_draggable(True)

        # Add to list widget
        list_item = QListWidgetItem(f"Dot #{dot_id} @ ({x}, {y})")
        list_item.setData(Qt.ItemDataRole.UserRole, dot_id)  # Store dot ID
        self.dot_list.addItem(list_item)

        # Enable buttons
        self.clear_all_btn.setEnabled(True)

        logger.debug(f"Added dot #{dot_id} at ({x}, {y})")

    def show_refinement_failed(self, x: int, y: int):
        """
        Show visual feedback when refinement fails.

        Args:
            x: Click X
            y: Click Y
        """
        # TODO: Show red X or flash animation at click position
        logger.warning(f"Refinement failed at ({x}, {y})")

    def _on_set_reference(self):
        """Handle Set Reference button click."""
        logger.info("User set reference position")
        self.reference_set.emit()

    def _on_remove_dot(self):
        """Handle Remove Dot button click."""
        selected_items = self.dot_list.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        dot_id = item.data(Qt.ItemDataRole.UserRole)

        # Remove from scene
        if dot_id in self.dot_items:
            dot_item = self.dot_items[dot_id]
            self.scene.removeItem(dot_item)
            if dot_item.arrow:
                self.scene.removeItem(dot_item.arrow)
            del self.dot_items[dot_id]

        # Remove from list
        row = self.dot_list.row(item)
        self.dot_list.takeItem(row)

        # Emit signal
        self.dot_removed.emit(dot_id)

        # Disable buttons if no dots left
        if self.dot_list.count() == 0:
            self.clear_all_btn.setEnabled(False)
            self.remove_dot_btn.setEnabled(False)

        logger.debug(f"Removed dot #{dot_id}")

    def _on_clear_all(self):
        """Handle Clear All button click."""
        # Remove all dots from scene
        for dot_item in self.dot_items.values():
            self.scene.removeItem(dot_item)
            if dot_item.arrow:
                self.scene.removeItem(dot_item.arrow)

        # Emit removal signals
        for dot_id in list(self.dot_items.keys()):
            self.dot_removed.emit(dot_id)

        self.dot_items.clear()

        # Clear list
        self.dot_list.clear()

        # Disable buttons
        self.clear_all_btn.setEnabled(False)
        self.remove_dot_btn.setEnabled(False)

        logger.info("Cleared all dots")

    def _on_dot_selection_changed(self):
        """Handle dot list selection change."""
        selected = len(self.dot_list.selectedItems()) > 0
        self.remove_dot_btn.setEnabled(selected)

    def get_dot_count(self) -> int:
        """Get number of dots currently displayed."""
        return len(self.dot_items)

    def get_dot_ids(self) -> list[int]:
        """Get list of dot IDs."""
        return list(self.dot_items.keys())
