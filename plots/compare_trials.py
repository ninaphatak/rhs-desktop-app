import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys

# Load two CSV files
if len(sys.argv) == 3:
    file1, file2 = sys.argv[1], sys.argv[2]
else:
    file1 = input("Enter first CSV path: ").strip().strip('"')
    file2 = input("Enter second CSV path: ").strip().strip('"')

df1 = pd.read_csv(file1)
df2 = pd.read_csv(file2)

name1 = "TPU Trial"
name2 = "Silicone Trial"

fig, axes = plt.subplots(3, 2, figsize=(14, 10))

# === TOP LEFT: P1 Trial 1 ===
axes[0, 0].plot(df1['Time (s)'], df1['Pressure 1 (mmHg)'], 'r-')
axes[0, 0].set_ylabel('P1 (mmHg)')
axes[0, 0].set_title(f'P1 (Atrium) - {name1}')
axes[0, 0].grid(True, alpha=0.3)

# === TOP RIGHT: P1 Trial 2 ===
axes[0, 1].plot(df2['Time (s)'], df2['Pressure 1 (mmHg)'], 'b-')
axes[0, 1].set_ylabel('P1 (mmHg)')
axes[0, 1].set_title(f'P1 (Atrium) - {name2}')
axes[0, 1].grid(True, alpha=0.3)

# === MIDDLE LEFT: P2 Trial 1 ===
axes[1, 0].plot(df1['Time (s)'], df1['Pressure 2 (mmHg)'], 'r-')
axes[1, 0].set_ylabel('P2 (mmHg)')
axes[1, 0].set_title(f'P2 (Ventricle) - {name1}')
axes[1, 0].grid(True, alpha=0.3)

# === MIDDLE RIGHT: P2 Trial 2 ===
axes[1, 1].plot(df2['Time (s)'], df2['Pressure 2 (mmHg)'], 'b-')
axes[1, 1].set_ylabel('P2 (mmHg)')
axes[1, 1].set_title(f'P2 (Ventricle) - {name2}')
axes[1, 1].grid(True, alpha=0.3)

# Make y-axes match for fair comparison
p1_max = max(df1['Pressure 1 (mmHg)'].max(), df2['Pressure 1 (mmHg)'].max()) + 2
p2_max = max(df1['Pressure 2 (mmHg)'].max(), df2['Pressure 2 (mmHg)'].max()) + 2
axes[0, 0].set_ylim(0, p1_max)
axes[0, 1].set_ylim(0, p1_max)
axes[1, 0].set_ylim(0, p2_max)
axes[1, 1].set_ylim(0, p2_max)

# === BOTTOM LEFT: Bar Chart ===
stats = {
    'P1 Mean': [df1['Pressure 1 (mmHg)'].mean(), df2['Pressure 1 (mmHg)'].mean()],
    'P1 Std': [df1['Pressure 1 (mmHg)'].std(), df2['Pressure 1 (mmHg)'].std()],
    'P2 Mean': [df1['Pressure 2 (mmHg)'].mean(), df2['Pressure 2 (mmHg)'].mean()],
    'P2 Std': [df1['Pressure 2 (mmHg)'].std(), df2['Pressure 2 (mmHg)'].std()],
}

x = np.arange(len(stats))
width = 0.35

axes[2, 0].bar(x - width/2, [v[0] for v in stats.values()], width, label=name1, color='red', alpha=0.7)
axes[2, 0].bar(x + width/2, [v[1] for v in stats.values()], width, label=name2, color='blue', alpha=0.7)
axes[2, 0].set_ylabel('Pressure (mmHg)')
axes[2, 0].set_xticks(x)
axes[2, 0].set_xticklabels(stats.keys(), rotation=15)
axes[2, 0].legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=2, frameon=True)
axes[2, 0].grid(True, alpha=0.3, axis='y')

# === BOTTOM RIGHT: Text Summary ===
axes[2, 1].axis('off')

def percent_diff(v1, v2):
    avg = (v1 + v2) / 2
    return abs(v1 - v2) / avg * 100 if avg != 0 else 0

p1_mean1 = df1['Pressure 1 (mmHg)'].mean()
p1_mean2 = df2['Pressure 1 (mmHg)'].mean()
p2_mean1 = df1['Pressure 2 (mmHg)'].mean()
p2_mean2 = df2['Pressure 2 (mmHg)'].mean()

p1_std1 = df1['Pressure 1 (mmHg)'].std()
p1_std2 = df2['Pressure 1 (mmHg)'].std()
p2_std1 = df1['Pressure 2 (mmHg)'].std()
p2_std2 = df2['Pressure 2 (mmHg)'].std()

p1_mean_diff = percent_diff(p1_mean1, p1_mean2)
p2_mean_diff = percent_diff(p2_mean1, p2_mean2)
p1_std_diff = percent_diff(p1_std1, p1_std2)
p2_std_diff = percent_diff(p2_std1, p2_std2)

summary_text = f"""
COMPARISON SUMMARY
{'='*40}

Trial 1: {name1}
Trial 2: {name2}

P1 (Atrium):
  Trial 1: {p1_mean1:.2f} ± {p1_std1:.2f} mmHg
  Trial 2: {p1_mean2:.2f} ± {p1_std2:.2f} mmHg
  Mean Difference: {p1_mean_diff:.1f}%
  Std Dev Difference: {p1_std_diff:.1f}%

P2 (Ventricle):
  Trial 1: {p2_mean1:.2f} ± {p2_std1:.2f} mmHg
  Trial 2: {p2_mean2:.2f} ± {p2_std2:.2f} mmHg
  Mean Difference: {p2_mean_diff:.1f}%
  Std Dev Difference: {p2_std_diff:.1f}%

{'='*40}
"""

axes[2, 1].text(0.05, 0.95, summary_text, transform=axes[2, 1].transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace')

plt.tight_layout()
plt.show()
