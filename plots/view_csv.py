import pandas as pd
import matplotlib.pyplot as plt
import sys

# Load CSV (drag file onto terminal or pass as argument)
if len(sys.argv) > 1:
    filepath = sys.argv[1]
else:
    filepath = input("Enter CSV path: ").strip().strip('"')

df = pd.read_csv(filepath)

# Create 3 subplots like the real-time viewer
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8), sharex=True)

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
ax3.set_xlabel('Time (s)')
ax3.legend()
ax3.grid(True, alpha=0.3)

plt.suptitle(filepath.split('/')[-1])
plt.tight_layout()
plt.show()