"""
Mock Basler Camera - Simulates camera frames with dots in circular pattern

Purpose: Provides synthetic camera frames for testing dot tracking without hardware

Features:
- Generates 1920x1200 grayscale frames at 60 FPS
- Simulates 3-8 colored dots arranged in a circular pattern
- Dots randomly displace from rest positions (realistic organ motion)
- Displacement is measurable for motion tracking validation
- Matches BaslerCamera interface exactly
- Thread-safe frame emission

Usage:
    mock_camera = MockCamera()
    mock_camera.frame_ready.connect(on_frame)
    mock_camera.start()
    mock_camera.set_exposure(1000)
"""

import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import random
import math


class Dot:
    """Represents a dot with circular arrangement and random displacement"""

    def __init__(self, rest_x, rest_y):
        # Rest position (where dot returns to)
        self.rest_x = rest_x
        self.rest_y = rest_y

        # Current position (starts at rest)
        self.x = rest_x
        self.y = rest_y

        # Displacement parameters
        self.max_displacement = random.uniform(10, 40)  # Maximum displacement in pixels
        self.displacement_freq = random.uniform(0.5, 2.0)  # Hz (breathing/pulsation rate)
        self.phase_offset = random.uniform(0, 2 * math.pi)  # Random phase for each dot

        # Random walk parameters (simulates small random motion)
        self.random_walk_x = 0
        self.random_walk_y = 0
        self.random_walk_speed = 5  # pixels/sec

        # Size (radius in pixels)
        self.radius = random.randint(4, 8)

        # Intensity (0-255 grayscale)
        self.intensity = random.randint(20, 50)

        # Color identifier (for tracking)
        self.color_id = random.randint(0, 2)  # 0=red, 1=green, 2=blue

    def update(self, dt, time_elapsed):
        """Update position with displacement from rest position"""
        # Periodic displacement (simulates rhythmic motion like breathing/pulsation)
        phase = 2 * math.pi * self.displacement_freq * time_elapsed + self.phase_offset
        displacement_magnitude = self.max_displacement * math.sin(phase)

        # Direction of displacement (varies per dot, can be radial or tangential)
        displacement_angle = self.phase_offset  # Use phase offset as displacement direction
        displacement_x = displacement_magnitude * math.cos(displacement_angle)
        displacement_y = displacement_magnitude * math.sin(displacement_angle)

        # Update random walk (small random jitter)
        self.random_walk_x += random.uniform(-self.random_walk_speed, self.random_walk_speed) * dt
        self.random_walk_y += random.uniform(-self.random_walk_speed, self.random_walk_speed) * dt

        # Limit random walk to prevent drift
        max_walk = 15  # pixels
        self.random_walk_x = max(-max_walk, min(max_walk, self.random_walk_x))
        self.random_walk_y = max(-max_walk, min(max_walk, self.random_walk_y))

        # Apply damping to random walk (returns to zero)
        damping = 0.95
        self.random_walk_x *= damping
        self.random_walk_y *= damping

        # Calculate final position
        self.x = self.rest_x + displacement_x + self.random_walk_x
        self.y = self.rest_y + displacement_y + self.random_walk_y

    def get_displacement(self):
        """Calculate current displacement magnitude from rest position"""
        dx = self.x - self.rest_x
        dy = self.y - self.rest_y
        return math.sqrt(dx**2 + dy**2)

    def draw(self, frame):
        """Draw dot on frame with anti-aliasing"""
        # Create coordinate grids
        y_coords, x_coords = np.ogrid[:frame.shape[0], :frame.shape[1]]

        # Calculate distance from dot center
        distance = np.sqrt((x_coords - self.x)**2 + (y_coords - self.y)**2)

        # Anti-aliased circle (smooth edges)
        mask = np.maximum(0, 1 - (distance - self.radius) / 2)

        # Draw dot (additive blending)
        frame[:, :] = np.clip(frame.astype(np.int16) - (mask * (255 - self.intensity)).astype(np.int16), 0, 255).astype(np.uint8)


class MockCamera(QThread):
    """Simulates Basler camera with moving dots"""

    # Signals (matching BaslerCamera interface)
    frame_ready = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    fps_updated = pyqtSignal(float)
    error_occurred = pyqtSignal(str)

    # Camera specifications (matching Basler acA1920-155um)
    WIDTH = 1920
    HEIGHT = 1200
    DEFAULT_FPS = 60
    DEFAULT_EXPOSURE = 1000  # microseconds

    def __init__(self):
        super().__init__()
        self._running = False

        # Camera settings
        self._target_fps = self.DEFAULT_FPS
        self._exposure_us = self.DEFAULT_EXPOSURE
        self._frame_interval = 1.0 / self._target_fps

        # Frame tracking
        self._frame_count = 0
        self._start_time = None
        self._time_elapsed = 0

        # FPS measurement
        self._fps_samples = []
        self._last_fps_update = time.time()

        # Dots arranged in circular pattern
        self._num_dots = random.randint(5, 8)
        self._dots = self._create_circular_dots()

    @staticmethod
    def list_cameras():
        """Enumerate available cameras (mock always returns one)"""
        return ["Mock Camera 0 (Simulated Basler acA1920-155um)"]

    def connect(self, index: int = 0):
        """Connect to camera (always succeeds for mock)"""
        self.connection_changed.emit(True)
        return True

    def disconnect(self):
        """Disconnect camera"""
        self._running = False
        self.connection_changed.emit(False)

    def set_exposure(self, microseconds: int):
        """Set exposure time"""
        if 100 <= microseconds <= 100000:  # 0.1ms to 100ms
            self._exposure_us = microseconds
        else:
            self.error_occurred.emit(f"Exposure out of range: {microseconds} us")

    def set_fps(self, fps: int):
        """Set target frame rate"""
        if 1 <= fps <= 155:  # Basler max is 155 fps
            self._target_fps = fps
            self._frame_interval = 1.0 / fps
        else:
            self.error_occurred.emit(f"FPS out of range: {fps}")

    def run(self):
        """Main thread loop - generate and emit frames"""
        self._running = True
        self.connection_changed.emit(True)
        self._start_time = time.time()

        last_frame_time = time.time()
        last_update_time = time.time()

        while self._running:
            current_time = time.time()
            dt = current_time - last_update_time
            last_update_time = current_time
            self._time_elapsed = current_time - self._start_time

            # Generate frame at target rate
            if current_time - last_frame_time >= self._frame_interval:
                frame_data = self._generate_frame(dt)
                self.frame_ready.emit(frame_data)

                # Measure actual FPS
                self._update_fps_measurement(current_time - last_frame_time)
                last_frame_time = current_time

            # Small sleep to prevent CPU spinning
            time.sleep(0.001)

        self.connection_changed.emit(False)

    def stop(self):
        """Stop thread gracefully"""
        self._running = False
        self.wait()

    def _create_circular_dots(self):
        """Create dots arranged in a circular pattern"""
        dots = []
        center_x = self.WIDTH / 2
        center_y = self.HEIGHT / 2
        radius = min(self.WIDTH, self.HEIGHT) * 0.3  # Circle radius (30% of smaller dimension)

        # Arrange dots evenly around circle
        for i in range(self._num_dots):
            angle = (2 * math.pi * i) / self._num_dots
            rest_x = center_x + radius * math.cos(angle)
            rest_y = center_y + radius * math.sin(angle)
            dots.append(Dot(rest_x, rest_y))

        return dots

    def _generate_frame(self, dt) -> dict:
        """Generate synthetic frame with displacing dots"""
        # Create blank grayscale frame (dark background)
        frame = np.full((self.HEIGHT, self.WIDTH), 220, dtype=np.uint8)

        # Add some noise (realistic camera noise)
        noise = np.random.randint(-5, 5, (self.HEIGHT, self.WIDTH), dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Update and draw dots
        displacements = []
        for dot in self._dots:
            dot.update(dt, self._time_elapsed)
            dot.draw(frame)
            displacements.append(dot.get_displacement())

        self._frame_count += 1

        return {
            "timestamp": time.time(),
            "frame": frame,
            "frame_number": self._frame_count,
            "displacements": displacements  # Include displacement data for validation
        }

    def _update_fps_measurement(self, frame_time):
        """Calculate and emit actual FPS"""
        # Rolling average of last 30 frames
        self._fps_samples.append(1.0 / frame_time if frame_time > 0 else 0)
        if len(self._fps_samples) > 30:
            self._fps_samples.pop(0)

        # Emit FPS update every second
        current_time = time.time()
        if current_time - self._last_fps_update >= 1.0:
            avg_fps = sum(self._fps_samples) / len(self._fps_samples)
            self.fps_updated.emit(avg_fps)
            self._last_fps_update = current_time


# Convenience function for testing
def test_mock_camera():
    """Test the mock camera generator"""
    from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow
    from PyQt6.QtGui import QImage, QPixmap
    import sys

    app = QApplication(sys.argv)

    # Create window to display frames
    window = QMainWindow()
    window.setWindowTitle("Mock Camera Test")
    label = QLabel()
    window.setCentralWidget(label)
    window.resize(960, 600)  # Half resolution for display
    window.show()

    mock = MockCamera()

    def on_frame(data):
        frame = data['frame']
        # Convert to QImage for display
        height, width = frame.shape
        bytes_per_line = width
        q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image)
        # Scale down for display
        label.setPixmap(pixmap.scaled(960, 600))

    def on_fps_update(fps):
        window.setWindowTitle(f"Mock Camera Test - {fps:.1f} FPS")

    mock.frame_ready.connect(on_frame)
    mock.fps_updated.connect(on_fps_update)

    mock.start()

    # Let it run for 5 seconds
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(5000, lambda: (mock.stop(), app.quit()))

    sys.exit(app.exec())


if __name__ == "__main__":
    test_mock_camera()
