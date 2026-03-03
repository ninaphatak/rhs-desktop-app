"""In-app CSV plotting dialog with embedded matplotlib figure."""

from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFileDialog,
    QMessageBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from src.utils.config import OUTPUTS_DIR


class PlotDialog(QDialog):
    """File picker + 4-subplot matplotlib view of a recorded CSV."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plot CSV")
        self.resize(1000, 700)

        self._layout = QVBoxLayout(self)

        # Pick file
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV to plot",
            str(OUTPUTS_DIR),
            "CSV Files (*.csv)",
        )
        if not filepath:
            self.reject()
            return

        try:
            df = pd.read_csv(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read CSV:\n{e}")
            self.reject()
            return

        if "Time (s)" not in df.columns:
            QMessageBox.critical(self, "Error", "CSV missing 'Time (s)' column.")
            self.reject()
            return

        self._plot(df, Path(filepath).name)

    def _plot(self, df: pd.DataFrame, title: str) -> None:
        """Render 4 subplots from the dataframe."""
        fig = Figure(figsize=(10, 7), facecolor="#1e1e1e")
        canvas = FigureCanvas(fig)
        self._layout.addWidget(canvas)

        t = df["Time (s)"]

        # -- Pressure --
        ax1 = fig.add_subplot(2, 2, 1)
        if "Pressure 1 (mmHg)" in df.columns:
            ax1.plot(t, df["Pressure 1 (mmHg)"], "r-", label="P1 (Atrium)")
        if "Pressure 2 (mmHg)" in df.columns:
            ax1.plot(t, df["Pressure 2 (mmHg)"], "b-", label="P2 (Ventricle)")
        ax1.set_ylabel("Pressure (mmHg)")
        ax1.set_title("Pressure")
        ax1.legend(fontsize=8)
        ax1.grid(True, alpha=0.3)

        # -- Flow Rate --
        ax2 = fig.add_subplot(2, 2, 2)
        if "Flow Rate (mL/s)" in df.columns:
            ax2.plot(t, df["Flow Rate (mL/s)"], color="gold", label="Flow")
        ax2.set_ylabel("mL/s")
        ax2.set_title("Flow Rate")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

        # -- Heart Rate --
        ax3 = fig.add_subplot(2, 2, 3)
        if "Heart Rate (BPM)" in df.columns:
            ax3.plot(t, df["Heart Rate (BPM)"], "w-", label="HR")
        ax3.set_ylabel("BPM")
        ax3.set_xlabel("Time (s)")
        ax3.set_title("Heart Rate")
        ax3.legend(fontsize=8)
        ax3.grid(True, alpha=0.3)

        # -- Temperature --
        ax4 = fig.add_subplot(2, 2, 4)
        temp_cols = {
            "Ventricle Temperature 1 (C)": ("magenta", "VT1"),
            "Ventricle Temperature 2 (C)": ("cyan", "VT2"),
            "Atrium Temperature (C)": ("lime", "AT1"),
        }
        for col, (color, label) in temp_cols.items():
            if col in df.columns:
                ax4.plot(t, df[col], color=color, label=label)
        ax4.set_ylabel("C")
        ax4.set_xlabel("Time (s)")
        ax4.set_title("Temperature")
        ax4.legend(fontsize=8)
        ax4.grid(True, alpha=0.3)

        # Style all axes for dark background
        for ax in [ax1, ax2, ax3, ax4]:
            ax.set_facecolor("#2a2a2a")
            ax.tick_params(colors="white")
            ax.xaxis.label.set_color("white")
            ax.yaxis.label.set_color("white")
            ax.title.set_color("white")
            for spine in ax.spines.values():
                spine.set_color("#555")

        fig.suptitle(title, color="white", fontsize=12)
        fig.tight_layout()
        canvas.draw()
