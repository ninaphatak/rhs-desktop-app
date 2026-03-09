"""2x2 live graph panel using pyqtgraph for RHS sensor data."""

from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QWidget

from src.utils.config import COLORS, GRAPH_BUFFER_SIZE


class GraphPanel(QWidget):
    """Four live-updating graphs: pressure, flow, HR, temperature."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dirty = False
        self._init_buffers()
        self._init_ui()

        # 20 Hz refresh timer — only repaints when new data has arrived
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(50)  # 50ms = 20 Hz
        self._refresh_timer.timeout.connect(self._refresh_curves)
        self._refresh_timer.start()

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
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Shared font for axis tick labels
        tick_font = pg.QtGui.QFont()
        tick_font.setPixelSize(20)

        # Shared style for axis labels
        label_style = {"font-size": "20px", "color": "white"}

        # -- Pressure plot (top-left) --
        self._pressure_plot = pg.PlotWidget(title="Pressure")
        self._pressure_plot.setLabel("left", "mmHg", **label_style)
        self._pressure_plot.setLabel("bottom", "Time (s)", **label_style)
        self._pressure_plot.addLegend(labelTextSize="14pt")
        self._p1_curve = self._pressure_plot.plot(
            pen=pg.mkPen(COLORS["p1"], width=2),
            name="P1 (Atrium)",
            symbol="o",
            symbolSize=5,
            symbolBrush=COLORS["p1"],
        )
        self._p2_curve = self._pressure_plot.plot(
            pen=pg.mkPen(COLORS["p2"], width=2),
            name="P2 (Ventricle)",
            symbol="o",
            symbolSize=5,
            symbolBrush=COLORS["p2"],
        )
        layout.addWidget(self._pressure_plot, 0, 0)

        # -- Heart rate plot (top-right) --
        self._hr_plot = pg.PlotWidget(title="Heart Rate")
        self._hr_plot.setLabel("left", "BPM", **label_style)
        self._hr_plot.setLabel("bottom", "Time (s)", **label_style)
        self._hr_plot.addLegend(labelTextSize="14pt")
        self._hr_curve = self._hr_plot.plot(
            pen=pg.mkPen(COLORS["hr"], width=2),
            name="HR",
            symbol="o",
            symbolSize=5,
            symbolBrush=COLORS["hr"],
        )
        layout.addWidget(self._hr_plot, 0, 1)

        # -- Temperature plot (bottom-right) --
        self._temp_plot = pg.PlotWidget(title="Temperature")
        self._temp_plot.setLabel("left", "ºC", **label_style)
        self._temp_plot.setLabel("bottom", "Time (s)", **label_style)
        self._temp_plot.addLegend(labelTextSize="14pt")
        self._vt1_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["vt1"], width=2),
            name="VT1",
            symbol="o",
            symbolSize=5,
            symbolBrush=COLORS["vt1"],
        )
        self._vt2_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["vt2"], width=2),
            name="VT2",
            symbol="o",
            symbolSize=5,
            symbolBrush=COLORS["vt2"],
        )
        self._at1_curve = self._temp_plot.plot(
            pen=pg.mkPen(COLORS["at1"], width=2),
            name="AT1",
            symbol="o",
            symbolSize=5,
            symbolBrush=COLORS["at1"],
        )
        layout.addWidget(self._temp_plot, 1, 0, 1, 2)

        # Dark background + tick font for all plots
        for plot in [self._pressure_plot, self._hr_plot, self._temp_plot]:
            plot.setBackground("#1e1e1e")
            for axis_name in ("bottom", "left"):
                plot.getAxis(axis_name).setTickFont(tick_font)
                plot.getAxis(axis_name).setTextPen("white")

    def update_data(self, data: dict) -> None:
        """Append new data point and mark dirty for next refresh.

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
        self._dirty = True

    def _refresh_curves(self) -> None:
        """Repaint curves if new data has arrived (called by 20 Hz timer)."""
        if not self._dirty or not self._time:
            return
        self._dirty = False

        time_arr = np.array(self._time)
        t_now = time_arr[-1]

        self._p1_curve.setData(time_arr, np.array(self._p1))
        self._p2_curve.setData(time_arr, np.array(self._p2))
        self._hr_curve.setData(time_arr, np.array(self._hr))
        self._vt1_curve.setData(time_arr, np.array(self._vt1))
        self._vt2_curve.setData(time_arr, np.array(self._vt2))
        self._at1_curve.setData(time_arr, np.array(self._at1))

        # Trailing 5-second X-range
        for plot in [self._pressure_plot, self._hr_plot, self._temp_plot]:
            plot.setXRange(t_now - 5, t_now, padding=0)

    def show_no_connection(self) -> None:
        """Display a 'No Arduino Connected' message on the pressure plot."""
        self._pressure_plot.setTitle("Pressure  —  No Arduino Connected")

    def show_connected(self) -> None:
        """Restore normal title when Arduino connects."""
        self._pressure_plot.setTitle("Pressure")
