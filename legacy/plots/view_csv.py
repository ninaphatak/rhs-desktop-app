import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys

# Load CSV (drag file onto terminal or pass as argument)
if len(sys.argv) > 1:
    filepath = sys.argv[1]
else:
    filepath = input("Enter CSV path: ").strip().strip('"')

df = pd.read_csv(filepath)

# Detect laps early so we can offer lap-based filtering
has_laps = 'Lap' in df.columns and df['Lap'].nunique() > 1
lap_info: dict[int, tuple[float, float]] = {}  # lap_num -> (t_start, t_end)
if has_laps:
    for lap_num in sorted(df['Lap'].unique()):
        lap_data = df[df['Lap'] == lap_num]
        lap_info[lap_num] = (lap_data['Time (s)'].iloc[0], lap_data['Time (s)'].iloc[-1])

# Optional time range / lap filter
t_min = df['Time (s)'].min()
t_max = df['Time (s)'].max()
print(f"\nTime range in file: {t_min:.1f}s – {t_max:.1f}s")
if has_laps:
    print("\nAvailable laps:")
    for lap_num, (ls, le) in lap_info.items():
        print(f"  Lap {lap_num}: {ls:.1f}s – {le:.1f}s")
    print("\nFilter options:")
    print("  - Enter a time range as 'start end' (e.g. '3000 4000')")
    print("  - Enter a lap number (e.g. '3') or range (e.g. '2-5')")
    print("  - Press Enter to plot all")
    range_input = input("Choice: ").strip()
else:
    range_input = input("Enter time range as 'start end' (e.g. '3000 4000'), or press Enter to plot all: ").strip()

if range_input:
    # Check if input is a lap number or lap range
    if has_laps and '-' in range_input and not any(c == '.' for c in range_input):
        # Lap range like "2-5"
        lap_start, lap_end = map(int, range_input.split('-'))
        selected_laps = [n for n in lap_info if lap_start <= n <= lap_end]
        df = df[df['Lap'].isin(selected_laps)]
    elif has_laps and range_input.isdigit():
        # Single lap number
        lap_num = int(range_input)
        df = df[df['Lap'] == lap_num]
    else:
        # Time range
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

# Ask whether to run peak/trough analysis on the flow plot
show_peak_analysis = False
show_value_labels = False
if group in ("all", "flow"):
    analysis_input = input("Run peak/trough analysis on flow plot? (y/N): ").strip().lower()
    show_peak_analysis = analysis_input == 'y'
    if show_peak_analysis:
        label_input = input("  Label peak & trough values on plot? (y/N): ").strip().lower()
        show_value_labels = label_input == 'y'

# Optional custom plot title
custom_title = input("Enter plot title (or press Enter for filename): ").strip()

# Build list of panels to show: (axes_label, plot_fn)
def plot_pressure(ax: plt.Axes, t: pd.Series) -> None:
    ax.plot(t, df['Pressure 1 (mmHg)'], 'r-', label='P1 (Atrium)')
    ax.plot(t, df['Pressure 2 (mmHg)'], 'b-', label='P2 (Ventricle)')
    ax.set_ylabel('Pressure (mmHg)')
    ax.legend()
    ax.grid(True, alpha=0.3)

def find_flow_peaks_and_troughs(t: pd.Series, flow: pd.Series):
    """Detect local max/min turning points in a step-function flow signal.

    Collapses consecutive duplicate values to find the underlying steps,
    then identifies where direction reverses (peak = higher than both
    neighbors, trough = lower than both neighbors among the step levels).
    """
    t_arr = t.values
    flow_arr = flow.values

    # Collapse consecutive duplicates to get step change points
    change_mask = np.concatenate(([True], flow_arr[1:] != flow_arr[:-1]))
    step_idx = np.where(change_mask)[0]
    step_t = t_arr[step_idx]
    step_v = flow_arr[step_idx]

    # Find all turning points among the step levels
    raw_peaks = []   # (time, value, index)
    raw_troughs = []
    for i in range(1, len(step_v) - 1):
        if step_v[i] > step_v[i - 1] and step_v[i] > step_v[i + 1]:
            raw_peaks.append((step_t[i], step_v[i], i))
        elif step_v[i] < step_v[i - 1] and step_v[i] < step_v[i + 1]:
            raw_troughs.append((step_t[i], step_v[i], i))

    # Filter: a peak must be >10 mL/s above its nearest trough(s)
    peak_times, peak_vals = [], []
    trough_times, trough_vals = [], []
    trough_arr = np.array([v for _, v, _ in raw_troughs]) if raw_troughs else np.array([])
    trough_t_arr = np.array([t for t, _, _ in raw_troughs]) if raw_troughs else np.array([])

    for pt, pv, pi in raw_peaks:
        if len(trough_t_arr) == 0:
            peak_times.append(pt)
            peak_vals.append(pv)
            continue
        # Find the previous trough (latest trough before this peak)
        before = np.where(trough_t_arr < pt)[0]
        # Find the next trough (earliest trough after this peak)
        after = np.where(trough_t_arr > pt)[0]
        prev_tv = trough_arr[before[-1]] if len(before) else None
        next_tv = trough_arr[after[0]] if len(after) else None
        # Peak must be >10 mL/s above both adjacent troughs
        ok = True
        if prev_tv is not None and pv - prev_tv <= 10.0:
            ok = False
        if next_tv is not None and pv - next_tv <= 10.0:
            ok = False
        if ok:
            peak_times.append(pt)
            peak_vals.append(pv)

    # Keep only troughs that sit between accepted peaks
    if len(peak_times) >= 2:
        for tt, tv, ti in raw_troughs:
            if peak_times[0] <= tt <= peak_times[-1]:
                trough_times.append(tt)
                trough_vals.append(tv)
    else:
        trough_times = [t for t, _, _ in raw_troughs]
        trough_vals = [v for _, v, _ in raw_troughs]

    return (np.array(peak_times), np.array(peak_vals),
            np.array(trough_times), np.array(trough_vals))


def compute_cv(values: np.ndarray) -> float:
    """Coefficient of variation (std / mean) as a percentage."""
    if len(values) == 0 or np.mean(values) == 0:
        return 0.0
    return (np.std(values) / np.mean(values)) * 100


def plot_flow(ax: plt.Axes, t: pd.Series) -> None:
    flow = df['Flow Rate (mL/s)']
    ax.plot(t, flow, 'g-', label='Flow Rate')

    # --- Peak / trough analysis (only if user opted in) ---
    if show_peak_analysis:
        peak_t, peak_v, trough_t, trough_v = find_flow_peaks_and_troughs(t, flow)

        # Mark peaks and troughs on the plot
        ax.plot(peak_t, peak_v, 'ro', markersize=7)
        if len(trough_t):
            ax.plot(trough_t, trough_v, 'bo', markersize=7)

        # Label each peak/trough with its value (if user opted in)
        if show_value_labels:
            for pt, pv in zip(peak_t, peak_v):
                ax.annotate(f'{pv:.1f}', xy=(pt, pv), xytext=(0, 8),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='red', fontweight='bold')
            for tt, tv in zip(trough_t, trough_v):
                ax.annotate(f'{tv:.1f}', xy=(tt, tv), xytext=(0, -12),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='blue', fontweight='bold')

        # Compute statistics
        peak_cv = compute_cv(peak_v)
        trough_cv = compute_cv(trough_v)
        if len(peak_t) >= 2:
            inter_peak = np.diff(peak_t)
            mean_period = np.mean(inter_peak)
            cv_period = compute_cv(inter_peak)
        else:
            mean_period = 0.0
            cv_period = 0.0

        # Peak-to-nearby-peak time: for each peak, time to the next peak
        if len(peak_t) >= 3:
            peak_to_peak_times = np.diff(peak_t)
            cv_p2p_time = compute_cv(peak_to_peak_times)
            mean_p2p_time = np.mean(peak_to_peak_times)
        else:
            cv_p2p_time = 0.0
            mean_p2p_time = mean_period

        # Store stats for display below the figure
        ax._flow_stats = {
            'peak_cv': peak_cv, 'trough_cv': trough_cv,
            'mean_period': mean_period, 'cv_period': cv_period,
            'mean_p2p_time': mean_p2p_time, 'cv_p2p_time': cv_p2p_time,
            'n_peaks': len(peak_v), 'n_troughs': len(trough_v),
            'peak_mean': np.mean(peak_v) if len(peak_v) else 0,
            'trough_mean': np.mean(trough_v) if len(trough_v) else 0,
        }

    ax.set_ylabel('Flow Rate (mL/s)')
    ax.legend(loc='upper right')
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

# Highlight lap regions if Lap column exists and has multiple laps in the filtered data
if 'Lap' in df.columns and df['Lap'].nunique() > 1:
    lap_nums = sorted(df['Lap'].unique())

    # Ask user if they want to rename any lap labels
    print(f"\nLaps in plot: {', '.join(f'Lap {n}' for n in lap_nums)}")
    rename_input = input("Rename lap labels? (y/N): ").strip().lower()
    lap_labels: dict[int, str] = {}
    if rename_input == 'y':
        for lap_num in lap_nums:
            custom = input(f"  Replace 'Lap {lap_num}' as (press Enter to keep): ").strip()
            lap_labels[lap_num] = custom if custom else f'Lap {lap_num}'
    else:
        lap_labels = {ln: f'Lap {ln}' for ln in lap_nums}

    lap_colors = plt.cm.tab10.colors
    for lap_num in lap_nums:
        lap_data = df[df['Lap'] == lap_num]
        ls = lap_data['Time (s)'].iloc[0]
        le = lap_data['Time (s)'].iloc[-1]
        color = lap_colors[int((lap_num - 1) % len(lap_colors))]
        for ax in axes:
            ax.axvspan(ls, le, alpha=0.1, color=color)
        # Label with lap name + start time
        axes[0].text(
            (ls + le) / 2, axes[0].get_ylim()[1],
            f'{lap_labels[lap_num]} ({ls:.1f}s)',
            ha='center', va='bottom',
            fontsize=9, color=color, fontweight='bold',
        )

axes[-1].set_xlabel('Time (s)')
plt.suptitle(custom_title if custom_title else filepath.split('/')[-1])

# Add flow stats as text below the figure if flow was plotted
flow_stats = None
for ax in axes:
    if hasattr(ax, '_flow_stats'):
        flow_stats = ax._flow_stats
        break

if flow_stats:
    s = flow_stats
    stats_text = (
        f"Peaks (n={s['n_peaks']}): mean={s['peak_mean']:.2f} mL/s, CV={s['peak_cv']:.1f}%    "
        f"Troughs (n={s['n_troughs']}): mean={s['trough_mean']:.2f} mL/s, CV={s['trough_cv']:.1f}%    "
        f"Peak-to-peak time: mean={s['mean_p2p_time']:.3f}s ({60/s['mean_p2p_time']:.0f} BPM), CV={s['cv_p2p_time']:.1f}%"
    )
    fig.subplots_adjust(bottom=0.12)
    fig.text(0.5, 0.01, stats_text, ha='center', va='bottom',
             fontsize=9, fontfamily='monospace',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='wheat', alpha=0.8))

plt.tight_layout(rect=[0, 0.05 if flow_stats else 0, 1, 0.96])
plt.show()