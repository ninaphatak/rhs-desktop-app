"""
Mock Basler Camera - Simulates camera frames with moving colored dots

Purpose: Provides synthetic camera frames for testing dot tracking without hardware

Features:
- Generates 1920x1200 grayscale frames at 60 FPS
- Simulates 3-5 colored dots moving in realistic patterns
- Dots move with physics (velocity, acceleration, bounce off walls)
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
    """Represents a moving colored dot with physics"""

    def __init__(self, width, height):
        self.width = width
        self.height = height

        # Position (center of frame initially)
        self.x = random.uniform(width * 0.3, width * 0.7)
        self.y = random.uniform(height * 0.3, height * 0.7)

        # Velocity (pixels per second)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(50, 200)  # pixels/sec
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)

        # Size (radius in pixels)
        self.radius = random.randint(8, 20)

        # Intensity (0-255 grayscale)
        self.intensity = random.randint(200, 255)

        # Color identifier (for tracking)
        self.color_id = random.randint(0, 2)  # 0=red, 1=green, 2=blue

    def update(self, dt):
        """Update position with simple physics"""
        # Update position
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Bounce off walls with damping
        damping = 0.9
        if self.x < self.radius or self.x > self.width - self.radius:
            self.vx *= -damping
            self.x = max(self.radius, min(self.width - self.radius, self.x))

        if self.y < self.radius or self.y > self.height - self.radius:
            self.vy *= -damping
            self.y = max(self.radius, min(self.height - self.radius, self.y))

        # Add small random acceleration (simulates realistic motion)
        self.vx += random.uniform(-20, 20) * dt
        self.vy += random.uniform(-20, 20) * dt

        # Limit max speed
        max_speed = 300
        speed = math.sqrt(self.vx**2 + self.vy**2)
        if speed > max_speed:
            self.vx = (self.vx / speed) * max_speed
            self.vy = (self.vy / speed) * max_speed

    def draw(self, frame):
        """Draw dot on frame with anti-aliasing"""
        # Create coordinate grids
        y_coords, x_coords = np.ogrid[:frame.shape[0], :frame.shape[1]]

        # Calculate distance from dot center
        distance = np.sqrt((x_coords - self.x)**2 + (y_coords - self.y)**2)

        # Anti-aliased circle (smooth edges)
        mask = np.maximum(0, 1 - (distance - self.radius) / 2)

        # Draw dot (additive blending)
        frame[:, :] = np.clip(frame + (mask * self.intensity).astype(np.uint8), 0, 255)


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

        # FPS measurement
        self._fps_samples = []
        self._last_fps_update = time.time()

        # Dots
        self._num_dots = random.randint(3, 5)
        self._dots = [Dot(self.WIDTH, self.HEIGHT) for _ in range(self._num_dots)]

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

        last_frame_time = time.time()
        last_update_time = time.time()

        while self._running:
            current_time = time.time()
            dt = current_time - last_update_time
            last_update_time = current_time

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

    def _generate_frame(self, dt) -> dict:
        """Generate synthetic frame with moving dots"""
        # Create blank grayscale frame (dark background)
        frame = np.full((self.HEIGHT, self.WIDTH), 20, dtype=np.uint8)

        # Add some noise (realistic camera noise)
        noise = np.random.randint(-5, 5, (self.HEIGHT, self.WIDTH), dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Update and draw dots
        for dot in self._dots:
            dot.update(dt)
            dot.draw(frame)

        # Simulate exposure effect (brighter = more exposure)
        exposure_factor = self._exposure_us / 1000.0  # Normalize
        frame = np.clip(frame.astype(np.float32) * (exposure_factor / 1000.0 + 0.5), 0, 255).astype(np.uint8)

        self._frame_count += 1

        return {
            "timestamp": time.time(),
            "frame": frame,
            "frame_number": self._frame_count
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
