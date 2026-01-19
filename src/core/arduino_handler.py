"""
Docstring for rhs-desktop-app.src.core.arduino_handler
ArduinoHandler - Bidirectional Serial Communication

**Purpose:** Manage serial I/O with Arduino for both sensor data and control commands

**Class Structure:**
ArduinoHandler(QThread)
│
├── Signals:
│   ├── data_received(dict)              # Sensor data
│   ├── connection_changed(bool)         # Connection status
│   ├── command_sent(str)                # 🆕 Command was sent
│   ├── command_acknowledged(str, bool)  # 🆕 Arduino responded
│   ├── hardware_state_updated(dict)     # 🆕 Hardware state changed
│   └── error_occurred(str)              # Error message
│
├── Attributes:
│   ├── _serial: Serial                  # Serial port object
│   ├── _running: bool                   # Thread control
│   ├── _command_queue: Queue            # 🆕 Thread-safe command queue
│   ├── _pending_command: str            # 🆕 Awaiting ACK
│   └── _command_timeout: float          # 🆕 1.0 seconds
│
├── Methods (existing):
│   ├── list_ports() → list[str]         # Static: enumerate ports
│   ├── connect(port: str)               # Open connection
│   ├── disconnect()                     # Close connection
│   ├── run()                            # Thread loop
│   └── stop()                           # Stop thread
│
├── Methods (NEW):
│   ├── send_command(cmd: str) → None   # Queue command for sending
│   ├── set_fan(state: bool) → None     # Helper: fan control
│   ├── set_bpm(value: int) → None      # Helper: BPM setpoint
│   ├── set_mode(mode: str) → None      # Helper: POT/AUTO/MANUAL
│   ├── set_solenoid(state: bool) → None # Helper: solenoid (MANUAL mode)
│   ├── emergency_stop() → None         # Helper: kill all outputs
│   └── get_status() → None             # Request hardware state
│
└── Internal (NEW):
├── _process_command_queue()         # Write queued commands
├── _parse_response(line: str) → dict  # Parse OK/ERROR/STATUS
└── _handle_command_ack(success: bool)
"""

"""

**Key Implementation Details:**
```python
from queue import Queue
from PyQt6.QtCore import QThread, Signal
import serial
import time

class ArduinoHandler(QThread):
    # Signals
    data_received = Signal(dict)
    connection_changed = Signal(bool)
    command_sent = Signal(str)
    command_acknowledged = Signal(str, bool)  # command, success
    hardware_state_updated = Signal(dict)
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._serial = None
        self._running = False
        self._command_queue = Queue()
        self._pending_command = None
        self._command_timeout = 1.0
        self._last_command_time = 0
        
    def send_command(self, cmd: str):
        # Thread-safe command queueing
        self._command_queue.put(cmd)
        
    def set_fan(self, state: bool):
        # High-level fan control
        self.send_command(f"SET_FAN {1 if state else 0}")
        
    def set_bpm(self, value: int):
        # High-level BPM control (AUTO mode)
        if 60 <= value <= 180:
            self.send_command(f"SET_BPM {value}")
        else:
            self.error_occurred.emit("BPM out of range (60-180)")
            
    def set_mode(self, mode: str):
        # High-level mode control
        if mode in ["POT", "AUTO", "MANUAL"]:
            self.send_command(f"SET_MODE {mode}")
        else:
            self.error_occurred.emit(f"Invalid mode: {mode}")
            
    def emergency_stop(self):
        Emergency: kill all outputs immediately
        # Clear queue and send immediately
        while not self._command_queue.empty():
            self._command_queue.get()
        self.send_command("EMERGENCY_STOP")
        
    def run(self):
        # Main thread loop - read data AND process command queue
        self._running = True
        
        while self._running:
            try:
                # 1. Process outgoing commands
                self._process_command_queue()
                
                # 2. Read incoming data
                if self._serial and self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8').strip()
                    
                    # Check if it's a response or sensor data
                    if line.startswith(("OK", "ERROR", "STATUS")):
                        self._handle_response(line)
                    else:
                        # Parse sensor data
                        data = self._parse_data(line)
                        if data:
                            self.data_received.emit(data)
                            
            except Exception as e:
                self.error_occurred.emit(str(e))
                
        self.disconnect()
        
    def _process_command_queue(self):
        Send queued commands to Arduino
        if self._pending_command:
            # Check timeout
            if time.time() - self._last_command_time > self._command_timeout:
                self.command_acknowledged.emit(self._pending_command, False)
                self._pending_command = None
                
        # Send next command if no pending ACK
        if not self._pending_command and not self._command_queue.empty():
            cmd = self._command_queue.get()
            self._serial.write(f"{cmd}\n".encode('utf-8'))
            self._pending_command = cmd
            self._last_command_time = time.time()
            self.command_sent.emit(cmd)
            
    def _handle_response(self, line: str):
        # Parse Arduino response
        if line.startswith("OK"):
            self.command_acknowledged.emit(self._pending_command, True)
            self._pending_command = None
            
        elif line.startswith("ERROR"):
            error_msg = line.split(" ", 1)[1] if " " in line else "Unknown error"
            self.command_acknowledged.emit(self._pending_command, False)
            self.error_occurred.emit(f"Arduino error: {error_msg}")
            self._pending_command = None
            
        elif line.startswith("STATUS"):
            # Parse: STATUS FAN:1 SOL:0 BPM:72 MODE:AUTO
            state = self._parse_status(line)
            self.hardware_state_updated.emit(state)
            
    def _parse_status(self, line: str) -> dict:
        # Parse STATUS response into dict
        parts = line.split()[1:]  # Skip "STATUS"
        state = {}
        for part in parts:
            key, value = part.split(":")
            state[key.lower()] = value
        return state
```

"""