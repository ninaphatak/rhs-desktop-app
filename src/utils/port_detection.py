"""Auto-detect Arduino serial port (macOS, Windows, Linux)."""

import glob
import platform
from typing import Optional

import serial.tools.list_ports


def find_serial_port() -> Optional[str]:
    """Detect the Arduino's serial port.

    Returns:
        Port path string, or None if no port found.
    """
    system = platform.system()

    if system == "Darwin":
        # macOS: use glob to avoid pyserial enumeration hang
        for pattern in ["/dev/cu.usbmodem*", "/dev/cu.usbserial*"]:
            ports = glob.glob(pattern)
            if ports:
                return ports[0]

    elif system == "Windows":
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "COM" in port.device:
                return port.device

    else:
        # Linux
        for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
            ports = glob.glob(pattern)
            if ports:
                return ports[0]

    return None
