"""ArduinoHandler - Read-Only Serial Communication

Manages serial I/O with Arduino for sensor data monitoring only.
This is a READ-ONLY handler - it does NOT send commands to Arduino.

Reads space-separated sensor data: "P1 P2 FLOW HR\n"
- P1: Pressure sensor 1 (mmHg)
- P2: Pressure sensor 2 (mmHg)
- FLOW: Flow rate sensor
- HR: Heart rate (BPM)

Serial configuration:
- Baud rate: 31250
- Data format: ASCII text, newline-delimited
- Read interval: ~30ms (30Hz sampling)

Signals:
    data_received(dict): New sensor data {"P1": float, "P2": float, "FLOW": float, "HR": float}
    error_occurred(str): Serial communication error message
    connection_changed(bool): Connection state changed

Methods:
    list_ports() -> list[str]: Enumerate available serial ports
    connect(port: str): Open serial connection
    disconnect(): Close serial connection
    run(): Thread loop for reading sensor data
    stop(): Stop the reading thread

Example usage:
```python
from PyQt6.QtCore import QThread, pyqtSignal as Signal
import serial
import time

class ArduinoHandler(QThread):
    # Signals
    data_received = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._serial = None
        self._running = False

    @staticmethod
    def list_ports():
        # Return list of available serial ports
        import serial.tools.list_ports
        return [port.device for port in serial.tools.list_ports.comports()]

    def connect(self, port: str, baud_rate: int = 31250):
        try:
            self._serial = serial.Serial(port, baud_rate, timeout=0.1)
            self.connection_changed.emit(True)
        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {e}")

    def disconnect(self):
        if self._serial:
            self._serial.close()
            self._serial = None
            self.connection_changed.emit(False)

    def run(self):
        # Main thread loop - read sensor data only
        self._running = True

        while self._running:
            try:
                if self._serial and self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8').strip()
                    data = self._parse_data(line)
                    if data:
                        self.data_received.emit(data)
                time.sleep(0.01)  # ~30Hz sampling

            except Exception as e:
                self.error_occurred.emit(str(e))

        self.disconnect()

    def stop(self):
        self._running = False

    def _parse_data(self, line: str) -> dict:
        # Parse "P1 P2 FLOW HR" format
        try:
            parts = line.split()
            if len(parts) == 4:
                return {
                    "P1": float(parts[0]),
                    "P2": float(parts[1]),
                    "FLOW": float(parts[2]),
                    "HR": float(parts[3])
                }
        except ValueError:
            pass
        return None
```
"""
