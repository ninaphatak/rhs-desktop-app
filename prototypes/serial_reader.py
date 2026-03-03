import csv  # saving data into a csv file instead of a exe file which only runs on windows
import glob
import platform
import sys
import time  # used to measure elapsed time
from datetime import datetime
from pathlib import Path

import numpy as np  # numeric arrays
import pyqtgraph as pg  # fast plotting library
import serial  # serial communication with arduino
import serial.tools.list_ports
from PyQt6 import QtCore, QtGui, QtWidgets  # GUI framework for the window plotting


# automatically find the Arduino's serial port (macOS + Windows compatible)
def find_serial_port():
    system = platform.system()

    if system == "Darwin":  # macOS
        # Use glob to avoid pyserial enumeration hang on macOS
        patterns = ["/dev/cu.usbmodem*", "/dev/cu.usbserial*"]
        for pattern in patterns:
            ports = glob.glob(pattern)
            if ports:
                print(f"Found Arduino at: {ports[0]}")
                return ports[0]
    elif system == "Windows":
        # Windows enumeration is usually reliable
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "COM" in port.device:
                print(f"Found Arduino at: {port.device}")
                return port.device
    else:  # Linux
        patterns = ["/dev/ttyUSB*", "/dev/ttyACM*"]
        for pattern in patterns:
            ports = glob.glob(pattern)
            if ports:
                print(f"Found Arduino at: {ports[0]}")
                return ports[0]

    print("❌ No compatible serial port found.")
    sys.exit(1)


# main plotting and data acquisition GUI class
class RHSData(QtWidgets.QMainWindow):
    timeData = np.array([])
    P1 = np.array([])
    P2 = np.array([])
    FR = np.array([])
    HR = np.array([])
    VT1 = np.array([])
    VT2 = np.array([])
    AT1 = np.array([])

    def __init__(self, *args, **kwargs):
        super(RHSData, self).__init__(*args, **kwargs)

        # open and initialize CSV file and also truncate it
        self.f = open(filePath, "w", newline="")
        self.f.truncate()
        self.writer = csv.writer(self.f, delimiter=",")
        self.writer.writerow(
            [
                "Time (s)",
                "Pressure 1 (mmHg)",
                "Pressure 2 (mmHg)",
                "Flow Rate (mL/s)",
                "Heart Rate (BPM)",
                "Ventricle Temperature 1 (°C)",
                "Ventricle Temperature 2 (°C)",
                "Atrium Temperature (°C)",
            ]
        )

        # setup PyQtGraph layout which includes the plotting and how big it is
        self.view = pg.GraphicsView()
        self.win = pg.GraphicsLayout()
        self.view.setCentralItem(self.win)
        self.view.setWindowTitle("Right Heart Simulator")
        self.font = QtGui.QFont()
        self.font.setPixelSize(20)

        self.win.nextRow()
        self.graph1 = self.win.addPlot()
        self.win.nextRow()
        self.graph2 = self.win.addPlot()
        self.win.nextRow()
        self.graph3 = self.win.addPlot()
        self.win.nextRow()
        self.graph4 = self.win.addPlot()
        self.startTime = time.time()

        for graph, ylabel in zip(
            [self.graph1, self.graph2, self.graph3, self.graph4],
            [
                "Pressure (mmHg)",
                "Flow Rate (L/min)",
                "Heart Rate (bpm)",
                "Temperature (°C)",
            ],
        ):
            graph.setLabel("left", ylabel)
            graph.setLabel("bottom", "Time (s)")
            graph.getAxis("bottom").setTickFont(self.font)
            graph.getAxis("left").setTickFont(self.font)
            graph.getAxis("bottom").label.setFont(self.font)
            graph.getAxis("left").label.setFont(self.font)
            graph.addLegend(labelTextSize="14pt")

        # reset Arduino state
        dataSet.setDTR(False)
        time.sleep(1)
        dataSet.flushInput()
        dataSet.setDTR(True)

        # plot initial data lines
        self.dataLine1 = self.graph1.plot(
            RHSData.timeData,
            RHSData.P1,
            pen=(255, 0, 0),
            name="Atrium Pressure",
            symbol="o",
            symbolBrush=(255, 0, 0),
            symbolSize=5,
        )
        self.dataLine2 = self.graph1.plot(
            RHSData.timeData,
            RHSData.P2,
            pen=(0, 0, 255),
            name="Ventricle Pressure",
            symbol="o",
            symbolBrush=(0, 0, 255),
            symbolSize=5,
        )
        self.dataLine3 = self.graph2.plot(
            RHSData.timeData,
            RHSData.FR,
            pen=(255, 255, 0),
            name="Flow Rate",
            symbol="o",
            symbolBrush=(255, 255, 0),
            symbolSize=5,
        )
        self.dataLine4 = self.graph3.plot(
            RHSData.timeData,
            RHSData.HR,
            pen=(255, 255, 255),
            name="Heart Rate",
            symbol="o",
            symbolBrush=(255, 255, 255),
            symbolSize=5,
        )
        self.dataLine5 = self.graph4.plot(
            RHSData.timeData,
            RHSData.VT1,
            pen=(255, 0, 255),
            name="Ventricle Temperature 1",
            symbol="o",
            symbolBrush=(255, 0, 255),
            symbolSize=5,
        )
        self.dataLine6 = self.graph4.plot(
            RHSData.timeData,
            RHSData.VT2,
            pen=(0, 255, 255),
            name="VentricleTemperature 2",
            symbol="o",
            symbolBrush=(0, 255, 255),
            symbolSize=5,
        )
        self.dataLine7 = self.graph4.plot(
            RHSData.timeData,
            RHSData.AT1,
            pen=(255, 255, 0),
            name="Atrial Temperature 1",
            symbol="o",
            symbolBrush=(255, 255, 0),
            symbolSize=5,
        )

        # setup update timer
        self.timer = QtCore.QTimer()
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.view.showMaximized()

    def update(self):
        while dataSet.in_waiting == 0:
            pass
        s_bytes = dataSet.readline()
        decoded_bytes = s_bytes.decode("utf-8").strip("\r\n")
        duration = round(time.time() - self.startTime, 4)
        values = [float(x) for x in decoded_bytes.split()]
        if duration:
            RHSData.timeData = np.append(self.timeData, duration)
            RHSData.P1 = np.append(self.P1, round(values[0], 2))
            RHSData.P2 = np.append(self.P2, round(values[1], 2))
            RHSData.FR = np.append(self.FR, round(values[2], 2))
            RHSData.HR = np.append(self.HR, round(values[3], 2))
            RHSData.VT1 = np.append(self.VT1, round(values[4], 2))
            RHSData.VT2 = np.append(self.VT2, round(values[5], 2))
            RHSData.AT1 = np.append(self.AT1, round(values[6], 2))

        self.dataArray = np.dstack(
            [
                RHSData.timeData[-1:],
                RHSData.P1[-1:],
                RHSData.P2[-1:],
                RHSData.FR[-1:],
                RHSData.HR[-1:],
                RHSData.VT1[-1:],
                RHSData.VT2[-1:],
                RHSData.AT1[-1:],
            ]
        )
        self.writer.writerows(self.dataArray[0])

        self.graph1.setXRange(duration - 5, duration)
        self.graph1.setYRange(0, max(np.amax(RHSData.P1), np.amax(RHSData.P2)) + 10)
        self.graph2.setXRange(duration - 5, duration)
        self.graph2.setYRange(0, np.amax(RHSData.FR) + 10)
        self.graph3.setXRange(duration - 5, duration)
        self.graph3.setYRange(0, np.amax(RHSData.HR) + 10)
        self.graph4.setXRange(duration - 5, duration)
        self.graph4.setYRange(
            0,
            max(np.amax(RHSData.VT1), np.amax(RHSData.VT2), np.amax(RHSData.AT1)) + 10,
        )

        self.dataLine1.setData(RHSData.timeData, RHSData.P1)
        self.dataLine2.setData(RHSData.timeData, RHSData.P2)
        self.dataLine3.setData(RHSData.timeData, RHSData.FR)
        self.dataLine4.setData(RHSData.timeData, RHSData.HR)
        self.dataLine5.setData(RHSData.timeData, RHSData.VT1)
        self.dataLine6.setData(RHSData.timeData, RHSData.VT2)
        self.dataLine7.setData(RHSData.timeData, RHSData.AT1)

        RHSData.timeData = RHSData.timeData[-300:]
        RHSData.P1 = RHSData.P1[-300:]
        RHSData.P2 = RHSData.P2[-300:]
        RHSData.FR = RHSData.FR[-300:]
        RHSData.HR = RHSData.HR[-300:]
        RHSData.VT1 = RHSData.VT1[-300:]
        RHSData.VT2 = RHSData.VT2[-300:]
        RHSData.AT1 = RHSData.AT1[-300:]

    def closeCSV(self):
        self.f.close()


def get_output_path() -> Path:
    """Prompt for valve type and return an auto-numbered CSV path in outputs/."""
    valid = {"silicone", "tpu"}
    while True:
        valve = input("Valve type? Enter 'silicone' or 'tpu': ").strip().lower()
        if valve in valid:
            break
        print(f"  Invalid input '{valve}'. Please enter 'silicone' or 'tpu'.")

    outputs_dir = Path(__file__).parent.parent / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%d%m%Y")
    n = 1
    while True:
        candidate = outputs_dir / f"{valve}_{date_str}_{n}.csv"
        if not candidate.exists():
            return candidate
        n += 1


# === Main execution block ===
if __name__ == "__main__":
    filePath = get_output_path()
    port_name = find_serial_port()
    dataSet = serial.Serial(port_name, 31250)

    app = QtWidgets.QApplication(sys.argv)
    plot = RHSData()
    app.exec()
    plot.closeCSV()
