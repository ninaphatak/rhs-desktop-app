"""
Mock Arduino Generator - Simulates RHS Arduino sensor data and command responses

Purpose: Provides realistic sensor waveforms and echoes commands for testing without hardware

Features:
- Generates realistic pressure waveforms (P1: 0-258 mmHg, P2: 0-40 mmHg)
- Simulates flow data (0-5 L/min)
- Computes heart rate from pressure peaks
- Responds to control commands (SET_FAN, SET_BPM, SET_MODE, etc.)
- Emits data at 30+ Hz like real Arduino
- Thread-safe command handling

Usage:
    mock_arduino = MockArduino()
    mock_arduino.data_received.connect(on_data)
    mock_arduino.command_acknowledged.connect(on_ack)
    mock_arduino.start()
    mock_arduino.send_command("SET_FAN 1")
"""

import math
import random
import time
from queue import Queue

from PyQt6.QtCore import QThread, pyqtSignal


class MockArduino(QThread):
    """Simulates Arduino sensor data stream and command responses"""

    # Signals (matching ArduinoHandler interface)
    data_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    command_sent = pyqtSignal(str)
    command_acknowledged = pyqtSignal(str, bool)  # command, success
    hardware_state_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._command_queue = Queue()

        # Hardware state
        self._fan_on = False
        self._solenoid_open = False
        self._bpm = 72  # Default heart rate
        self._mode = "POT"  # POT, AUTO, MANUAL

        # Waveform generation
        self._time_offset = 0.0
        self._frame_count = 0

        # Timing
        self._update_rate = 30  # Hz
        self._update_interval = 1.0 / self._update_rate

    def send_command(self, cmd: str):
        """Queue command for processing (thread-safe)"""
        self._command_queue.put(cmd)

    def set_fan(self, state: bool):
        """Helper: control fan"""
        self.send_command(f"SET_FAN {1 if state else 0}")

    def set_bpm(self, value: int):
        """Helper: set BPM setpoint (AUTO mode)"""
        if 60 <= value <= 180:
            self.send_command(f"SET_BPM {value}")
        else:
            self.error_occurred.emit("BPM out of range (60-180)")

    def set_mode(self, mode: str):
        """Helper: set control mode"""
        if mode in ["POT", "AUTO", "MANUAL"]:
            self.send_command(f"SET_MODE {mode}")
        else:
            self.error_occurred.emit(f"Invalid mode: {mode}")

    def set_solenoid(self, state: bool):
        """Helper: manual solenoid control (MANUAL mode only)"""
        self.send_command(f"SET_SOLENOID {1 if state else 0}")

    def emergency_stop(self):
        """Emergency: kill all outputs immediately"""
        while not self._command_queue.empty():
            self._command_queue.get()
        self.send_command("EMERGENCY_STOP")

    def get_status(self):
        """Request hardware status"""
        self.send_command("GET_STATUS")

    def run(self):
        """Main thread loop - generate data and process commands"""
        self._running = True
        self.connection_changed.emit(True)

        last_update = time.time()

        while self._running:
            current_time = time.time()

            # Process commands
            self._process_command_queue()

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

    def _process_command_queue(self):
        """Process queued commands and emit responses"""
        while not self._command_queue.empty():
            cmd = self._command_queue.get()
            self.command_sent.emit(cmd)

            # Parse and execute command
            success = self._execute_command(cmd)

            # Simulate small processing delay
            time.sleep(0.01)

            # Send acknowledgment
            self.command_acknowledged.emit(cmd, success)

            if not success:
                self.error_occurred.emit(f"Command failed: {cmd}")

    def _execute_command(self, cmd: str) -> bool:
        """Execute command and update hardware state"""
        parts = cmd.strip().split()
        if not parts:
            return False

        command = parts[0]

        try:
            if command == "SET_FAN":
                if len(parts) != 2:
                    return False
                self._fan_on = (parts[1] == "1")
                self._emit_status()
                return True

            elif command == "SET_SOLENOID":
                if len(parts) != 2:
                    return False
                # Only works in MANUAL mode
                if self._mode != "MANUAL":
                    self.error_occurred.emit("Solenoid control only in MANUAL mode")
                    return False
                self._solenoid_open = (parts[1] == "1")
                self._emit_status()
                return True

            elif command == "SET_BPM":
                if len(parts) != 2:
                    return False
                bpm = int(parts[1])
                if 60 <= bpm <= 180:
                    self._bpm = bpm
                    self._emit_status()
                    return True
                return False

            elif command == "SET_MODE":
                if len(parts) != 2:
                    return False
                mode = parts[1]
                if mode in ["POT", "AUTO", "MANUAL"]:
                    self._mode = mode
                    # Mode changes may affect solenoid state
                    if mode != "MANUAL":
                        self._solenoid_open = False
                    self._emit_status()
                    return True
                return False

            elif command == "EMERGENCY_STOP":
                self._fan_on = False
                self._solenoid_open = False
                self._mode = "POT"
                self._emit_status()
                return True

            elif command == "GET_STATUS":
                self._emit_status()
                return True

            else:
                return False

        except (ValueError, IndexError):
            return False

    def _emit_status(self):
        """Emit current hardware state"""
        state = {
            "fan": self._fan_on,
            "sol": self._solenoid_open,
            "bpm": self._bpm,
            "mode": self._mode
        }
        self.hardware_state_updated.emit(state)

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


# Convenience function for testing
def test_mock_arduino():
    """Test the mock Arduino generator"""
    import sys

    from PyQt6.QtWidgets import QApplication

    QApplication(sys.argv)

    mock = MockArduino()

    def on_data(data):
        print(f"Data: P1={data['p1']:.2f} P2={data['p2']:.2f} FLOW={data['flow']:.2f} HR={data['hr']}")

    def on_command_ack(cmd, success):
        print(f"Command '{cmd}': {'OK' if success else 'FAILED'}")

    def on_state_update(state):
        print(f"Hardware state: {state}")

    mock.data_received.connect(on_data)
    mock.command_acknowledged.connect(on_command_ack)
    mock.hardware_state_updated.connect(on_state_update)

    mock.start()

    # Test commands
    print("Testing commands...")
    time.sleep(0.5)
    mock.set_fan(True)
    time.sleep(0.5)
    mock.set_mode("AUTO")
    time.sleep(0.5)
    mock.set_bpm(120)
    time.sleep(2)

    mock.stop()
    sys.exit(0)


if __name__ == "__main__":
    test_mock_arduino()
