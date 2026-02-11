"""MockArduino - Simulated Arduino for Testing

Simulates read-only Arduino sensor data output for testing without hardware.
Generates realistic sensor readings: P1, P2, FLOW, HR

This is a READ-ONLY mock - it does NOT accept or process commands.
Matches production scope: monitoring-only, no bidirectional control.

Serial configuration:
- Baud rate: 31250
- Data format: "P1 P2 FLOW HR\n" (space-separated)
- Update rate: ~30Hz

Signals:
    data_received(dict): New sensor data
    error_occurred(str): Serial error message
    connection_changed(bool): Connection state

Usage:
    mock_arduino = MockArduino()
    mock_arduino.data_received.connect(on_data)
    mock_arduino.start()
    # Receives sensor data at ~30Hz
    mock_arduino.stop()
"""

import time
import math
from PyQt6.QtCore import QThread, pyqtSignal
import random


class MockArduino(QThread):
    """Simulates Arduino sensor data stream (read-only, no commands)"""

    # Signals
    data_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = False

        # Waveform generation parameters
        self._bpm = 72  # Heart rate for waveform generation
        self._time_offset = 0.0
        self._frame_count = 0

        # Timing
        self._update_rate = 30  # Hz
        self._update_interval = 1.0 / self._update_rate

    def run(self):
        """Main thread loop - generate sensor data only"""
        self._running = True
        self.connection_changed.emit(True)

        last_update = time.time()

        while self._running:
            current_time = time.time()

            # Generate sensor data at target rate
            if current_time - last_update >= self._update_interval:
                data = self._generate_sensor_data()
                self.data_received.emit(data)
                last_update = current_time
                self._time_offset += self._update_interval

            # Small sleep to prevent CPU spinning
            time.sleep(0.001)

        self.connection_changed.emit(False)

    def stop(self):
        """Stop thread gracefully"""
        self._running = False
        self.wait()

    def _generate_sensor_data(self) -> dict:
        """Generate realistic sensor data with cardiovascular waveforms"""
        t = self._time_offset

        # Heart rate determines cycle frequency
        freq = self._bpm / 60.0  # Convert BPM to Hz
        phase = 2 * math.pi * freq * t

        # P1: Right atrial pressure (0-40 mmHg, mean ~8 mmHg)
        # Realistic waveform: a-wave (atrial contraction), c-wave (tricuspid closure), v-wave (atrial filling)
        p1_baseline = 8.0
        p1_a_wave = 6.0 * math.sin(phase) if math.sin(phase) > 0 else 0
        p1_c_wave = 3.0 * math.sin(phase + 0.3) if math.sin(phase + 0.3) > 0 else 0
        p1_v_wave = 4.0 * math.sin(phase + math.pi) if math.sin(phase + math.pi) > 0 else 0
        p1 = p1_baseline + p1_a_wave + p1_c_wave + p1_v_wave

        # Add small noise
        p1 += random.uniform(-0.5, 0.5)
        p1 = max(0, min(40, p1))  # Clamp to realistic range

        # P2: Pulmonary artery pressure (0-258 mmHg, systolic ~25, diastolic ~10)
        # Pulsatile waveform matching cardiac cycle
        p2_systolic = 25.0
        p2_diastolic = 10.0
        p2_amplitude = (p2_systolic - p2_diastolic) / 2
        p2_mean = (p2_systolic + p2_diastolic) / 2

        # Systolic upstroke, diastolic decay
        pulse_shape = math.sin(phase) if phase % (2 * math.pi) < math.pi else -0.3 * math.sin(phase)
        p2 = p2_mean + p2_amplitude * pulse_shape

        # Add noise
        p2 += random.uniform(-1.0, 1.0)
        p2 = max(0, min(258, p2))  # Clamp to sensor range

        # FLOW: Blood flow (0-5 L/min, pulsatile)
        # Flow follows pressure gradient
        flow_mean = 3.5  # Average cardiac output
        flow_amplitude = 1.5
        flow = flow_mean + flow_amplitude * math.sin(phase + math.pi/4)
        flow += random.uniform(-0.2, 0.2)
        flow = max(0, min(5, flow))

        # HR: Computed from actual BPM with small variation
        hr = self._bpm + random.randint(-2, 2)

        self._frame_count += 1

        return {
            "timestamp": time.time(),
            "p1": round(p1, 2),
            "p2": round(p2, 2),
            "flow": round(flow, 2),
            "hr": hr,
            "frame_number": self._frame_count
        }


# Simple test function for monitoring-only mock
def test_mock_arduino():
    """Test the mock Arduino generator (monitoring only)"""
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    mock = MockArduino()

    def on_data(data):
        print(f"Data: P1={data['p1']:.2f} P2={data['p2']:.2f} FLOW={data['flow']:.2f} HR={data['hr']}")

    def on_connection(connected):
        print(f"Connection: {'Connected' if connected else 'Disconnected'}")

    mock.data_received.connect(on_data)
    mock.connection_changed.connect(on_connection)

    print("Starting mock Arduino (read-only monitoring)...")
    mock.start()

    # Run for 3 seconds, then stop
    time.sleep(3)

    print("Stopping mock Arduino...")
    mock.stop()

    sys.exit(0)


if __name__ == "__main__":
    test_mock_arduino()
