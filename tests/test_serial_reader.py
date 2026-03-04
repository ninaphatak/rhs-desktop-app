"""Tests for SerialReader and port detection."""

import pytest
from unittest.mock import patch, MagicMock
from src.utils.port_detection import find_serial_port
from src.utils.config import SERIAL_FIELDS, SERIAL_FIELD_COUNT


class TestPortDetection:
    """Tests for auto-detect Arduino serial port."""

    @patch("src.utils.port_detection.platform.system", return_value="Darwin")
    @patch("src.utils.port_detection.glob.glob")
    def test_macos_finds_usbmodem(self, mock_glob, _mock_sys):
        mock_glob.side_effect = lambda p: (
            ["/dev/cu.usbmodem14101"] if "usbmodem" in p else []
        )
        assert find_serial_port() == "/dev/cu.usbmodem14101"

    @patch("src.utils.port_detection.platform.system", return_value="Darwin")
    @patch("src.utils.port_detection.glob.glob", return_value=[])
    def test_macos_no_port(self, _mock_glob, _mock_sys):
        assert find_serial_port() is None

    @patch("src.utils.port_detection.platform.system", return_value="Windows")
    @patch("src.utils.port_detection.serial.tools.list_ports.comports")
    def test_windows_finds_com(self, mock_comports, _mock_sys):
        port = MagicMock()
        port.device = "COM3"
        mock_comports.return_value = [port]
        assert find_serial_port() == "COM3"

    @patch("src.utils.port_detection.platform.system", return_value="Linux")
    @patch("src.utils.port_detection.glob.glob")
    def test_linux_finds_ttyusb(self, mock_glob, _mock_sys):
        mock_glob.side_effect = lambda p: (
            ["/dev/ttyUSB0"] if "ttyUSB" in p else []
        )
        assert find_serial_port() == "/dev/ttyUSB0"


class TestSerialConfig:
    """Verify serial protocol configuration."""

    def test_field_count(self):
        assert SERIAL_FIELD_COUNT == 7

    def test_field_names(self):
        assert SERIAL_FIELDS == ["p1", "p2", "flow", "hr", "vt1", "vt2", "at1"]


class TestMockArduino:
    """Tests for mock Arduino data generation."""

    def test_generate_all_fields(self):
        from tests.mock_arduino import MockArduino
        mock = MockArduino()
        data = mock.get_sample(0)
        assert "timestamp" in data
        for field in SERIAL_FIELDS:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], (int, float))

    def test_values_in_range(self):
        from tests.mock_arduino import MockArduino
        mock = MockArduino()
        for i in range(50):
            data = mock.get_sample(i)
            assert 0 <= data["p1"] <= 40
            assert 0 <= data["p2"] <= 258
            assert 0 <= data["flow"] <= 10
            assert data["hr"] > 0
