# Remove Flow Rate (Demo Branch) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all flow rate display and recording from the UI on the `fix/temp-remove-FR` branch while keeping the 7-field Arduino serial protocol intact.

**Architecture:** Flow still arrives in the parsed data dict (hardware sends 7 fields and serial_reader.py must stay unchanged), but is silently ignored everywhere downstream — not written to CSV, not graphed live, not plotted from CSV. Four files change; no new logic, only removal and rearrangement.

**Tech Stack:** PySide6 + pyqtgraph (live graphs), matplotlib GridSpec (plot dialog), pandas (CSV read in plot dialog), pytest (regression check)

---

### Task 1: Remove flow from CSV headers (`config.py`)

**Files:**
- Modify: `src/utils/config.py:16-25`

**Step 1: Make the change**

In `CSV_HEADERS`, remove the `"Flow Rate (mL/s)"` entry. Result should be 6 strings:

```python
CSV_HEADERS = [
    "Time (s)",
    "Pressure 1 (mmHg)",
    "Pressure 2 (mmHg)",
    "Heart Rate (BPM)",
    "Ventricle Temperature 1 (C)",
    "Ventricle Temperature 2 (C)",
    "Atrium Temperature (C)",
]
```

Do NOT touch `SERIAL_FIELDS` or `SERIAL_FIELD_COUNT` — the Arduino still sends 7 fields.

**Step 2: Run existing tests to verify nothing breaks**

```bash
pytest tests/ -v
```

Expected: all tests pass (no test depends on CSV_HEADERS length).

**Step 3: Commit**

```bash
git add src/utils/config.py
git commit -m "Remove flow rate from CSV headers (demo branch)"
```

---

### Task 2: Filter flow from CSV recording (`data_recorder.py`)

**Files:**
- Modify: `src/core/data_recorder.py:82`

**Step 1: Make the change**

In `record_row`, change the row construction to skip the `"flow"` field:

```python
row = [t] + [data.get(field, 0.0) for field in SERIAL_FIELDS if field != "flow"]
```

This keeps the 6-column CSV aligned with the updated `CSV_HEADERS`.

**Step 2: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 3: Commit**

```bash
git add src/core/data_recorder.py
git commit -m "Filter flow rate from CSV recording (demo branch)"
```

---

### Task 3: Rearrange live graph layout (`graph_panel.py`)

**Files:**
- Modify: `src/ui/graph_panel.py`

New layout:
- `(0, 0)` — Pressure (unchanged)
- `(0, 1)` — Heart Rate (moved from row 1)
- `(1, 0, 1, 2)` — Temperature (spans both columns)

**Step 1: Remove the flow plot block from `_init_ui`**

Delete the entire `# -- Flow rate plot (top-right) --` block (lines 69–78):

```python
        # -- Flow rate plot (top-right) --
        self._flow_plot = pg.PlotWidget(title="Flow Rate")
        self._flow_plot.setLabel("left", "mL/s", **label_style)
        self._flow_plot.setLabel("bottom", "Time (s)", **label_style)
        self._flow_plot.addLegend(labelTextSize="14pt")
        self._flow_curve = self._flow_plot.plot(
            pen=pg.mkPen(COLORS["flow"], width=2), name="Flow",
            symbol="o", symbolSize=5, symbolBrush=COLORS["flow"],
        )
        layout.addWidget(self._flow_plot, 0, 1)
```

**Step 2: Move HR to top-right**

Change:
```python
        layout.addWidget(self._hr_plot, 1, 0)
```
To:
```python
        layout.addWidget(self._hr_plot, 0, 1)
```

**Step 3: Expand Temperature to full bottom row**

Change:
```python
        layout.addWidget(self._temp_plot, 1, 1)
```
To:
```python
        layout.addWidget(self._temp_plot, 1, 0, 1, 2)
```

**Step 4: Remove `_flow_plot` from the dark background + tick font loop**

Change:
```python
        for plot in [self._pressure_plot, self._flow_plot, self._hr_plot, self._temp_plot]:
```
To:
```python
        for plot in [self._pressure_plot, self._hr_plot, self._temp_plot]:
```

**Step 5: Remove flow from `_refresh_curves`**

Delete this line:
```python
        self._flow_curve.setData(time_arr, np.array(self._flow))
```

**Step 6: Remove `_flow_plot` from the `setXRange` loop**

Change:
```python
        for plot in [self._pressure_plot, self._flow_plot, self._hr_plot, self._temp_plot]:
```
To:
```python
        for plot in [self._pressure_plot, self._hr_plot, self._temp_plot]:
```

**Step 7: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 8: Commit**

```bash
git add src/ui/graph_panel.py
git commit -m "Remove flow graph, rearrange live graph layout (demo branch)"
```

---

### Task 4: Remove flow subplot from plot dialog (`plot_dialog.py`)

**Files:**
- Modify: `src/ui/plot_dialog.py`

New layout: 3 subplots using `GridSpec` — Pressure (top-left), Heart Rate (top-right), Temperature (full bottom row).

**Step 1: Add GridSpec import**

At the top of the file, `matplotlib.figure` is already imported. Add `GridSpec` to the matplotlib imports:

```python
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
```

**Step 2: Replace `_plot` method**

Replace the entire `_plot` method with:

```python
    def _plot(self, df: pd.DataFrame, title: str) -> None:
        """Render 3 subplots from the dataframe (flow rate excluded)."""
        fig = Figure(figsize=(10, 7), facecolor="#1e1e1e")
        canvas = FigureCanvas(fig)
        self._layout.addWidget(canvas)

        t = df["Time (s)"]
        gs = GridSpec(2, 2, figure=fig)

        # -- Pressure (top-left) --
        ax1 = fig.add_subplot(gs[0, 0])
        if "Pressure 1 (mmHg)" in df.columns:
            ax1.plot(t, df["Pressure 1 (mmHg)"], "r-", label="P1 (Atrium)")
        if "Pressure 2 (mmHg)" in df.columns:
            ax1.plot(t, df["Pressure 2 (mmHg)"], "b-", label="P2 (Ventricle)")
        ax1.set_ylabel("Pressure (mmHg)")
        ax1.set_title("Pressure")
        ax1.legend(fontsize=8)
        ax1.grid(True, alpha=0.3)

        # -- Heart Rate (top-right) --
        ax2 = fig.add_subplot(gs[0, 1])
        if "Heart Rate (BPM)" in df.columns:
            ax2.plot(t, df["Heart Rate (BPM)"], "w-", label="HR")
        ax2.set_ylabel("BPM")
        ax2.set_title("Heart Rate")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

        # -- Temperature (full bottom row) --
        ax3 = fig.add_subplot(gs[1, :])
        temp_cols = {
            "Ventricle Temperature 1 (C)": ("magenta", "VT1"),
            "Ventricle Temperature 2 (C)": ("cyan", "VT2"),
            "Atrium Temperature (C)": ("lime", "AT1"),
        }
        for col, (color, label) in temp_cols.items():
            if col in df.columns:
                ax3.plot(t, df[col], color=color, label=label)
        ax3.set_ylabel("C")
        ax3.set_xlabel("Time (s)")
        ax3.set_title("Temperature")
        ax3.legend(fontsize=8)
        ax3.grid(True, alpha=0.3)

        # Style all axes for dark background
        for ax in [ax1, ax2, ax3]:
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
```

**Step 3: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

**Step 4: Commit**

```bash
git add src/ui/plot_dialog.py
git commit -m "Remove flow subplot, use GridSpec 3-panel layout (demo branch)"
```

---

### Task 5: Smoke test the full app

**Step 1: Launch in mock mode**

```bash
bash run.sh --mock
```

Verify:
- Live graph shows 3 panels: Pressure (top-left), Heart Rate (top-right), Temperature (full bottom)
- No flow graph anywhere
- Record button creates a CSV — open it and confirm no "Flow Rate" column
- Plot button opens a CSV — confirm 3 subplots with no flow panel

**Step 2: Final test run**

```bash
pytest tests/ -v
```

Expected: all tests pass.
