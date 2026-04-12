import pandas as pd
import matplotlib.pyplot as plt
import sys

# Load CSV (drag file onto terminal or pass as argument)
if len(sys.argv) > 1:
    filepath = sys.argv[1]
else:
    filepath = input("Enter CSV path: ").strip().strip('"')

df = pd.read_csv(filepath)

# Optional time range filter
t_min = df['Time (s)'].min()
t_max = df['Time (s)'].max()
print(f"Time range in file: {t_min:.1f}s – {t_max:.1f}s")
range_input = input("Enter time range as 'start end' (e.g. '3000 4000'), or press Enter to plot all: ").strip()
if range_input:
    t_start, t_end = map(float, range_input.split())
    df = df[(df['Time (s)'] >= t_start) & (df['Time (s)'] <= t_end)]

# Channel group selection
GROUPS = {
    "1": "all",
    "2": "pressure",
    "3": "flow",
    "4": "heart_rate",
    "5": "temperature",
}
print("\nWhich channels would you like to plot?")
print("  1) All (default)")
print("  2) Pressure only  (P1, P2)")
print("  3) Flow rate only")
print("  4) Heart rate only")
print("  5) Temperature only")
group_input = input("Enter number [1]: ").strip() or "1"
group = GROUPS.get(group_input, "all")

# Build list of panels to show: (axes_label, plot_fn)
def plot_pressure(ax: plt.Axes, t: pd.Series) -> None:
    ax.plot(t, df['Pressure 1 (mmHg)'], 'r-', label='P1 (Atrium)')
    ax.plot(t, df['Pressure 2 (mmHg)'], 'b-', label='P2 (Ventricle)')
    ax.set_ylabel('Pressure (mmHg)')
    ax.legend()
    ax.grid(True, alpha=0.3)

def plot_flow(ax: plt.Axes, t: pd.Series) -> None:
    ax.plot(t, df['Flow Rate (mL/s)'], 'g-', label='Flow Rate')
    ax.set_ylabel('Flow Rate (mL/s)')
    ax.legend()
    ax.grid(True, alpha=0.3)

def plot_heart_rate(ax: plt.Axes, t: pd.Series) -> None:
    ax.plot(t, df['Heart Rate (BPM)'], color='purple', label='Heart Rate')
    ax.set_ylabel('Heart Rate (BPM)')
    ax.legend()
    ax.grid(True, alpha=0.3)

def plot_temperature(ax: plt.Axes, t: pd.Series) -> None:
    temp_cols = [c for c in df.columns if 'Temperature' in c]
    colors = ['orange', 'red', 'cyan', 'magenta']
    for col, color in zip(temp_cols, colors):
        ax.plot(t, df[col], color=color, label=col.replace(' (°C)', ''))
    ax.set_ylabel('Temperature (°C)')
    ax.set_ylim(25, 39)
    ax.legend()
    ax.grid(True, alpha=0.3)

panel_map = {
    "pressure":   plot_pressure,
    "flow":       plot_flow,
    "heart_rate": plot_heart_rate,
    "temperature": plot_temperature,
}

if group == "all":
    panels = list(panel_map.keys())
else:
    panels = [group]

t = df['Time (s)']
n = len(panels)
fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True)
if n == 1:
    axes = [axes]

for ax, key in zip(axes, panels):
    panel_map[key](ax, t)

axes[-1].set_xlabel('Time (s)')
plt.suptitle(filepath.split('/')[-1])
plt.tight_layout()
plt.show()