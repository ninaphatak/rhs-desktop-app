"""2x2 live graph panel using pyqtgraph for RHS sensor data."""

from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QGridLayout

from src.utils.config import GRAPH_BUFFER_SIZE, COLORS


class GraphPanel(QWidget):
    """Four live-updating graphs: pressure, flow, HR, temperature."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_buffers()
        self._init_ui()

    def _init_buffers(self) -> None:
        """Create rolling deque buffers for each data field."""
        n = GRAPH_BUFFER_SIZE
        self._time = deque(maxlen=n)
        self._p1 = deque(maxlen=n)
        self._p2 = deque(maxlen=n)
        self._flow = deque(maxlen=n)
        self._hr = deque(maxlen=n)
        self._vt1 = deque(maxlen=n)
        self._vt2 = deque(maxlen=n)
        self._at1 = deque(maxlen=n)
        self._start_time: float | None = None

    def _init_ui(self) -> None:
        """Build the 2x2 plot grid."""
        pg.setConfigOptions(antialias=True)

        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # -- Pressure plot (top-left) --
        self._pressure_plot = pg.PlotWidget(title="Pressure")
        self._pressure_plot.setLabel("left", "mmHg")
        self._pressure_plot.setLabel("bottom", "Time (s)")
        self._pressure_plot.addLegend(labelTextSize="10pt")
        self._p1_curve = self._pressure_plot.plot(
            pen=pg.mkPen(COLORS["p1"], width=2), name="P1 (Atrium)"
        )
        self._p2_curve = self._pressure_plot.plot(
            pen=pg.mkPen(COLORS["p2"], width=2), name="P2 (Ventricle)"
        )
        layout.addWidget(self._pressure_plot, 0, 0)

        # -- Flow rate plot (top-right) --
        self._flow_plot = pg.PlotWidget(title="Flow Rate")
        self._flow_plot.setLabel("left", "mL/s")
        self._flow_plot.setLabel("bottom", "Time (s)")
        self._flow_plot.addLegend(labelTextSize="10pt")
        self._flow_curve = self._flow_plot.plot(
            pen=pg.mkPen(COLORS["flow"], width=2), name="Flow"
        )
        layout.addWidget(self._flow_plot, 0, 1)

        # -- Heart rate plot (bottom-left) --
        self._hr_plot = pg.PlotWidget(title="Heart Rate")
        self._hr_plot.setLabel("left", "BPM")
        self._hr_plot.setLabel("bottom", "Time (s)")
        self._hr_plot.addLegend(labelTextSize="10pt")
        self._hr_curve = self._hr_plot.plot(
            pen=pg.mkPen(COLORS["hr"], width=2), name="HR"
        )
        layout.addWidget(self._hr_plot, 1, 0)

        # -- Temperature plot (bottom-right) --
        self._temp_plot = pg.PlotWidget(title="Temperature")
        self._temp_plot.setLabel("left", "C")
        self._temp_plot.setLabel("bottom", "Time (s)")
        self._temp_plot.addLegend(labelTextSize="10pt")
        self._vt1_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["vt1"], width=2), name="VT1"
        )
        self._vt2_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["vt2"], width=2), name="VT2"
        )
        self._at1_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["at1"], width=2), name="AT1"
        )
        layout.addWidget(self._temp_plot, 1, 1)

        # Dark background for all plots
        for plot in [self._pressure_plot, self._flow_plot, self._hr_plot, self._temp_plot]:
            plot.setBackground("#1e1e1e")

    def update_plots(self, data: dict) -> None:
        """Append new data point and refresh all curves.

        Called by SerialReader.data_received signal.
        """
        if self._start_time is None:
            self._start_time = data["timestamp"]

        t = data["timestamp"] - self._start_time
        self._time.append(t)
        self._p1.append(data.get("p1", 0.0))
        self._p2.append(data.get("p2", 0.0))
        self._flow.append(data.get("flow", 0.0))
        self._hr.append(data.get("hr", 0.0))
        self._vt1.append(data.get("vt1", 0.0))
        self._vt2.append(data.get("vt2", 0.0))
        self._at1.append(data.get("at1", 0.0))

        time_arr = np.array(self._time)

        self._p1_curve.setData(time_arr, np.array(self._p1))
        self._p2_curve.setData(time_arr, np.array(self._p2))
        self._flow_curve.setData(time_arr, np.array(self._flow))
        self._hr_curve.setData(time_arr, np.array(self._hr))
        self._vt1_curve.setData(time_arr, np.array(self._vt1))
        self._vt2_curve.setData(time_arr, np.array(self._vt2))
        self._at1_curve.setData(time_arr, np.array(self._at1))

    def show_no_connection(self) -> None:
        """Display a 'No Arduino Connected' message on the pressure plot."""
        self._pressure_plot.setTitle("Pressure  —  No Arduino Connected")

    def show_connected(self) -> None:
        """Restore normal title when Arduino connects."""
        self._pressure_plot.setTitle("Pressure")
