"""Mock Arduino — generates synthetic 7-field sensor data for testing."""

import math
import random
import time

from PySide6.QtCore import QThread, Signal


class MockArduino(QThread):
    """Simulates Arduino sensor data stream (7 fields, ~30Hz)."""

    data_received = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        self._bpm = 72
        self._time_offset = 0.0
        self._update_interval = 1.0 / 30  # 30 Hz

    def run(self) -> None:
        self._running = True
        self.connection_changed.emit(True)
        last_update = time.time()

        while self._running:
            now = time.time()
            if now - last_update >= self._update_interval:
                self.data_received.emit(self._generate())
                last_update = now
                self._time_offset += self._update_interval
            time.sleep(0.001)

        self.connection_changed.emit(False)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    def _generate(self) -> dict:
        t = self._time_offset
        freq = self._bpm / 60.0
        phase = 2 * math.pi * freq * t

        # P1: Right atrial pressure (~8 mmHg baseline)
        p1 = 8.0
        p1 += 6.0 * max(0, math.sin(phase))
        p1 += 4.0 * max(0, math.sin(phase + math.pi))
        p1 += random.uniform(-0.5, 0.5)
        p1 = max(0, min(40, p1))

        # P2: Pulmonary artery pressure (~10-25 mmHg)
        p2_mean = 17.5
        p2_amp = 7.5
        pulse = math.sin(phase) if (phase % (2 * math.pi)) < math.pi else -0.3 * math.sin(phase)
        p2 = p2_mean + p2_amp * pulse + random.uniform(-1.0, 1.0)
        p2 = max(0, min(258, p2))

        # Flow rate
        flow = 3.5 + 1.5 * math.sin(phase + math.pi / 4) + random.uniform(-0.2, 0.2)
        flow = max(0, min(5, flow))

        # Heart rate
        hr = self._bpm + random.randint(-2, 2)

        # Temperatures (slowly varying, realistic ranges 20-37 C)
        vt1 = 30.0 + 2.0 * math.sin(0.1 * t) + random.uniform(-0.3, 0.3)
        vt2 = 29.5 + 1.8 * math.sin(0.1 * t + 0.5) + random.uniform(-0.3, 0.3)
        at1 = 28.0 + 1.5 * math.sin(0.08 * t + 1.0) + random.uniform(-0.3, 0.3)

        return {
            "timestamp": time.time(),
            "p1": round(p1, 2),
            "p2": round(p2, 2),
            "flow": round(flow, 2),
            "hr": round(hr, 2),
            "vt1": round(vt1, 2),
            "vt2": round(vt2, 2),
            "at1": round(at1, 2),
        }
