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

# Create 4 subplots like the real-time viewer + temperature
fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(12, 10), sharex=True)

# Pressure plot (P1 and P2)
ax1.plot(df['Time (s)'], df['Pressure 1 (mmHg)'], 'r-', label='P1 (Atrium)')
ax1.plot(df['Time (s)'], df['Pressure 2 (mmHg)'], 'b-', label='P2 (Ventricle)')
ax1.set_ylabel('Pressure (mmHg)')
ax1.legend()
ax1.grid(True, alpha=0.3)

# Flow rate plot
ax2.plot(df['Time (s)'], df['Flow Rate (mL/s)'], 'g-', label='Flow Rate')
ax2.set_ylabel('Flow Rate (mL/s)')
ax2.legend()
ax2.grid(True, alpha=0.3)

# Heart rate plot
ax3.plot(df['Time (s)'], df['Heart Rate (BPM)'], 'purple', label='Heart Rate')
ax3.set_ylabel('Heart Rate (BPM)')
ax3.legend()
ax3.grid(True, alpha=0.3)

# Temperature plot
temp_cols = [c for c in df.columns if 'Temperature' in c]
colors = ['orange', 'red', 'cyan', 'magenta']
for col, color in zip(temp_cols, colors):
    ax4.plot(df['Time (s)'], df[col], color=color, label=col.replace(' (°C)', ''))
ax4.set_ylabel('Temperature (°C)')
ax4.set_xlabel('Time (s)')
ax4.set_ylim(25, 39)
ax4.legend()
ax4.grid(True, alpha=0.3)

plt.suptitle(filepath.split('/')[-1])
plt.tight_layout()
plt.show()