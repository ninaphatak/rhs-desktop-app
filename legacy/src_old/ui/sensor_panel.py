"""
Docstring for sensor_panel

**Purpose:** Real-time sensor data visualization

**Class Structure:**
```
SensorPanel(QWidget)
│
├── Attributes:
│   ├── pressure_plot: PlotWidget    # P1 and P2 lines
│   ├── flow_plot: PlotWidget        # Flow rate line
│   ├── hr_label: QLabel             # Large HR display
│   ├── p1_buffer: deque             # Rolling data (5 seconds)
│   ├── p2_buffer: deque
│   ├── flow_buffer: deque
│   └── time_buffer: deque
│
├── Methods:
│   ├── update_data(sensor_data: dict)  # Slot: receive new data
│   ├── _update_plots()                  # Redraw graphs
│   ├── _update_hr_display(hr: int)      # Update heart rate
│   ├── clear()                          # Clear all data
│   └── set_time_window(seconds: int)    # Adjust display window
```

---
"""