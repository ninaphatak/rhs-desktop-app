"""Mock Basler Camera — generates synthetic frames with moving dots (PySide6)."""

import math
import random
import time

import numpy as np
from PySide6.QtCore import QThread, Signal


class MockCamera(QThread):
    """Simulates Basler camera with moving dots on a light background."""

    frame_ready = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    WIDTH = 640
    HEIGHT = 480

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        self._target_fps = 30
        self._frame_interval = 1.0 / self._target_fps
        self._frame_count = 0
        self._start_time: float | None = None

        # Create dots
        self._num_dots = random.randint(4, 7)
        self._dots = self._create_dots()

    @staticmethod
    def list_cameras() -> list[str]:
        return ["Mock Camera 0", "Mock Camera 1"]

    def connect(self, index: int = 0) -> bool:
        self.connection_changed.emit(True)
        return True

    def disconnect(self) -> None:
        self._running = False
        self.connection_changed.emit(False)

    def run(self) -> None:
        self._running = True
        self.connection_changed.emit(True)
        self._start_time = time.time()
        last_frame = time.time()

        while self._running:
            now = time.time()
            if now - last_frame >= self._frame_interval:
                elapsed = now - self._start_time
                frame = self._generate_frame(elapsed)
                self._frame_count += 1
                self.frame_ready.emit({
                    "timestamp": now,
                    "frame": frame,
                    "frame_number": self._frame_count,
                })
                last_frame = now
            time.sleep(0.001)

        self.connection_changed.emit(False)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    def _create_dots(self) -> list[tuple[float, float, int, float, float]]:
        """Create dot specs: (cx, cy, radius, freq, phase)."""
        dots = []
        cx, cy = self.WIDTH / 2, self.HEIGHT / 2
        r = min(self.WIDTH, self.HEIGHT) * 0.25
        for i in range(self._num_dots):
            angle = 2 * math.pi * i / self._num_dots
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            radius = random.randint(6, 14)
            freq = random.uniform(0.5, 2.0)
            phase = random.uniform(0, 2 * math.pi)
            dots.append((x, y, radius, freq, phase))
        return dots

    def _generate_frame(self, elapsed: float) -> np.ndarray:
        """Generate a light-background frame with dark moving dots."""
        frame = np.full((self.HEIGHT, self.WIDTH), 200, dtype=np.uint8)
        noise = np.random.randint(-3, 3, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        for (cx, cy, radius, freq, phase) in self._dots:
            disp = 15 * math.sin(2 * math.pi * freq * elapsed + phase)
            dx = cx + disp * math.cos(phase)
            dy = cy + disp * math.sin(phase)
            y_coords, x_coords = np.ogrid[:self.HEIGHT, :self.WIDTH]
            dist = np.sqrt((x_coords - dx) ** 2 + (y_coords - dy) ** 2)
            mask = dist <= radius
            frame[mask] = 30  # Dark dot on light background

        return frame
