import sys
import serial  # serial communication with arduino
import serial.tools.list_ports
import numpy as np #numeric arrays
import time #used to measure elapsed time
import csv #saving data into a csv file instead of a exe file which only runs on windows
import tkinter as tk #GUI dialog for file saving
from tkinter import filedialog #file dialog popup
from PyQt6 import QtWidgets, QtCore, QtGui #GUI framework for the window plotting
import pyqtgraph as pg #fast plotting library
import glob
import platform

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

    def __init__(self, *args, **kwargs):
        super(RHSData, self).__init__(*args, **kwargs)

        # open and initialize CSV file and also truncate it
        self.f = open(filePath, 'w', newline='')
        self.f.truncate()
        self.writer = csv.writer(self.f, delimiter=",")
        self.writer.writerow(["Time (s)", "Pressure 1 (mmHg)", "Pressure 2 (mmHg)", "Flow Rate (mL/s)", "Heart Rate (BPM)"])

        # setup PyQtGraph layout which includes the plotting and how big it is
        self.view = pg.GraphicsView()
        self.win = pg.GraphicsLayout()
        self.view.setCentralItem(self.win)
        self.view.setWindowTitle('Right Heart Simulator')
        self.font = QtGui.QFont()
        self.font.setPixelSize(20)

        self.win.nextRow()
        self.graph1 = self.win.addPlot()
        self.win.nextRow()
        self.graph2 = self.win.addPlot()
        self.win.nextRow()
        self.graph3 = self.win.addPlot()
        self.startTime = time.time()

        for graph, ylabel in zip([self.graph1, self.graph2, self.graph3],
                                 ['Pressure (mmHg)', 'Flow Rate (L/min)', 'Heart Rate (bpm)']):
            graph.setLabel('left', ylabel)
            graph.setLabel('bottom', 'Time (s)')
            graph.getAxis('bottom').setTickFont(self.font)
            graph.getAxis('left').setTickFont(self.font)
            graph.getAxis('bottom').label.setFont(self.font)
            graph.getAxis('left').label.setFont(self.font)
            graph.addLegend(labelTextSize="14pt")

        # reset Arduino state
        dataSet.setDTR(False)
        time.sleep(1)
        dataSet.flushInput()
        dataSet.setDTR(True)

        # plot initial data lines
        self.dataLine1 = self.graph1.plot(RHSData.timeData, RHSData.P1, pen=(255, 0, 0), name="Atrium Pressure", symbol='o', symbolBrush=(255, 0, 0), symbolSize=5)
        self.dataLine2 = self.graph1.plot(RHSData.timeData, RHSData.P2, pen=(0, 0, 255), name="Ventricle Pressure", symbol='o', symbolBrush=(0, 0, 255), symbolSize=5)
        self.dataLine3 = self.graph2.plot(RHSData.timeData, RHSData.FR, pen=(255, 255, 0), name="Flow Rate", symbol='o', symbolBrush=(255, 255, 0), symbolSize=5)
        self.dataLine4 = self.graph3.plot(RHSData.timeData, RHSData.HR, pen=(255, 255, 255), name="Heart Rate", symbol='o', symbolBrush=(255, 255, 255), symbolSize=5)

        # setup update timer
        self.timer = QtCore.QTimer()
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.view.showMaximized()

    def update(self):
        while(dataSet.in_waiting == 0):
            pass
        s_bytes = dataSet.readline()
        decoded_bytes = s_bytes.decode("utf-8").strip('\r\n')
        duration = round(time.time() - self.startTime, 4)
        values = [float(x) for x in decoded_bytes.split()]
        if duration:
            RHSData.timeData = np.append(self.timeData, duration)
            RHSData.P1 = np.append(self.P1, round(values[0], 2))
            RHSData.P2 = np.append(self.P2, round(values[1], 2))
            RHSData.FR = np.append(self.FR, round(values[2], 2))
            RHSData.HR = np.append(self.HR, round(values[3], 2))

        self.dataArray = np.dstack([RHSData.timeData[-1:], RHSData.P1[-1:], RHSData.P2[-1:], RHSData.FR[-1:], RHSData.HR[-1:]])
        self.writer.writerows(self.dataArray[0])

        self.graph1.setXRange(duration - 5, duration)
        self.graph1.setYRange(0, np.amax(RHSData.P1) + 10)
        self.graph2.setXRange(duration - 5, duration)
        self.graph2.setYRange(0, np.amax(RHSData.FR) + 10)
        self.graph3.setXRange(duration - 5, duration)
        self.graph3.setYRange(0, np.amax(RHSData.HR) + 10)

        self.dataLine1.setData(RHSData.timeData, RHSData.P1)
        self.dataLine2.setData(RHSData.timeData, RHSData.P2)
        self.dataLine3.setData(RHSData.timeData, RHSData.FR)
        self.dataLine4.setData(RHSData.timeData, RHSData.HR)

        RHSData.timeData = RHSData.timeData[-300:]
        RHSData.P1 = RHSData.P1[-300:]
        RHSData.P2 = RHSData.P2[-300:]
        RHSData.FR = RHSData.FR[-300:]
        RHSData.HR = RHSData.HR[-300:]

    def fileDestination():
        root = tk.Tk()
        filePath = filedialog.asksaveasfilename(title='Save as...', defaultextension='.csv')
        root.destroy()
        return filePath

    def closeCSV(self):
        self.f.close()

# === Main execution block ===
if __name__ == '__main__':
    filePath = RHSData.fileDestination()
    port_name = find_serial_port()
    dataSet = serial.Serial(port_name, 31250)

    app = QtWidgets.QApplication(sys.argv)
    plot = RHSData()
    app.exec()
    plot.closeCSV()
